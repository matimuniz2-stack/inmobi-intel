"""Postgres connection + upsert helpers (synchronous psycopg).

Playwright on Windows needs the ProactorEventLoop, but psycopg-async requires
SelectorEventLoop. They're incompatible, so we use sync psycopg in this project.
Inserts are <1ms against local Postgres, so blocking the event loop briefly is fine.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from typing import Iterator
from uuid import UUID

import psycopg

from .config import DATABASE_URL
from .models import MlListingCard, UsdRateRecord


@contextmanager
def db_conn() -> Iterator[psycopg.Connection]:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set (check apps/scrapers/.env)")
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


def insert_usd_rate(conn: psycopg.Connection, record: UsdRateRecord) -> None:
    conn.execute(
        "INSERT INTO usd_rates (id, source, rate, recorded_at) "
        "VALUES (gen_random_uuid(), %s, %s, %s)",
        (record.source, record.rate, record.fetched_at),
    )
    conn.commit()


def get_latest_usd_rate(conn: psycopg.Connection) -> Decimal | None:
    cur = conn.execute("SELECT rate FROM usd_rates ORDER BY recorded_at DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


def _normalize_usd(amount: Decimal, currency: str, usd_rate: Decimal | None) -> Decimal | None:
    if currency == "USD":
        return amount
    if currency == "ARS" and usd_rate and usd_rate > 0:
        return (amount / usd_rate).quantize(Decimal("0.01"))
    return None


# Upsert: insert new properties or update existing ones (by portal + portal_id).
# last_updated_at advances only when fields that matter for the user have changed
# (price, currency). last_seen_at is always bumped to now().
UPSERT_PROPERTY_SQL = """
INSERT INTO properties (
    id, portal, portal_id, url, title,
    operation_type, property_type,
    price_amount, price_currency, price_usd_normalized,
    bedrooms, bathrooms, total_sqm, covered_sqm,
    address_full, neighborhood, city, province,
    photos, agency_name,
    zone_slug,
    first_seen_at, last_seen_at, last_updated_at,
    is_active
) VALUES (
    gen_random_uuid(), %(portal)s::"Portal", %(portal_id)s, %(url)s, %(title)s,
    %(operation_type)s::"OperationType", %(property_type)s::"PropertyType",
    %(price_amount)s, %(price_currency)s::"Currency", %(price_usd_normalized)s,
    %(bedrooms)s, %(bathrooms)s, %(total_sqm)s, %(covered_sqm)s,
    %(address_full)s, %(neighborhood)s, %(city)s, %(province)s,
    %(photos)s::jsonb, %(agency_name)s,
    %(zone_slug)s,
    now(), now(), now(),
    true
)
ON CONFLICT (portal, portal_id) DO UPDATE SET
    url = EXCLUDED.url,
    title = EXCLUDED.title,
    operation_type = EXCLUDED.operation_type,
    property_type = EXCLUDED.property_type,
    price_amount = EXCLUDED.price_amount,
    price_currency = EXCLUDED.price_currency,
    price_usd_normalized = EXCLUDED.price_usd_normalized,
    bedrooms = EXCLUDED.bedrooms,
    bathrooms = EXCLUDED.bathrooms,
    total_sqm = EXCLUDED.total_sqm,
    covered_sqm = EXCLUDED.covered_sqm,
    address_full = EXCLUDED.address_full,
    neighborhood = EXCLUDED.neighborhood,
    city = EXCLUDED.city,
    province = EXCLUDED.province,
    photos = EXCLUDED.photos,
    agency_name = EXCLUDED.agency_name,
    zone_slug = EXCLUDED.zone_slug,
    last_seen_at = now(),
    is_active = true,
    last_updated_at = CASE
        WHEN properties.price_amount IS DISTINCT FROM EXCLUDED.price_amount
          OR properties.price_currency IS DISTINCT FROM EXCLUDED.price_currency
          OR properties.is_active = false
        THEN now()
        ELSE properties.last_updated_at
    END
RETURNING (xmax = 0) AS inserted;
"""


# Append a price point only when the property's newest price differs from the
# last one we recorded (or it has no history yet). Keeps re-scrapes at the same
# price from spamming rows, while capturing every real change — that's the raw
# material the "recent price drop" opportunity signal reads.
INSERT_PRICE_POINT_SQL = """
INSERT INTO price_history (
    id, property_id, price_amount, price_currency, price_usd_normalized, observed_at
)
SELECT gen_random_uuid(), p.id, %(price_amount)s, %(price_currency)s::"Currency",
       %(price_usd_normalized)s, now()
FROM properties p
WHERE p.portal = %(portal)s::"Portal" AND p.portal_id = %(portal_id)s
  AND NOT EXISTS (
      SELECT 1 FROM price_history ph
      WHERE ph.property_id = p.id
        AND ph.price_amount = %(price_amount)s
        AND ph.price_currency = %(price_currency)s::"Currency"
        AND ph.observed_at = (
            SELECT max(ph2.observed_at) FROM price_history ph2 WHERE ph2.property_id = p.id
        )
  );
"""


def record_price_point(
    conn: psycopg.Connection,
    *,
    portal: str,
    portal_id: str,
    price_amount: Decimal,
    price_currency: str,
    price_usd_normalized: Decimal | None,
) -> None:
    """Record a price point for an already-upserted property if the price moved.

    Must run in the same transaction as the upsert so the property row is visible.
    """
    conn.execute(
        INSERT_PRICE_POINT_SQL,
        {
            "portal": portal,
            "portal_id": portal_id,
            "price_amount": price_amount,
            "price_currency": price_currency,
            "price_usd_normalized": price_usd_normalized,
        },
    )


def upsert_property(
    conn: psycopg.Connection,
    card: MlListingCard,
    zone_slug: str,
    usd_rate: Decimal | None,
    portal: str = "MERCADOLIBRE",
) -> bool:
    """Upsert a property. Returns True if inserted (new), False if updated.
    `portal` must match a value of the Portal Postgres enum.

    Also records a price-history point when the price moved (same transaction).
    """
    price_usd_normalized = _normalize_usd(
        card.price_amount, card.price_currency, usd_rate
    )
    params = {
        "portal": portal,
        "portal_id": card.portal_id,
        "url": card.url,
        "title": card.title,
        "operation_type": card.operation_type,
        "property_type": card.property_type,
        "price_amount": card.price_amount,
        "price_currency": card.price_currency,
        "price_usd_normalized": price_usd_normalized,
        "bedrooms": card.bedrooms,
        "bathrooms": card.bathrooms,
        "total_sqm": card.total_sqm,
        "covered_sqm": card.covered_sqm,
        "address_full": card.address_full,
        "neighborhood": card.neighborhood,
        "city": card.city,
        "province": card.province,
        "photos": json.dumps(card.photos),
        "agency_name": card.agency_name,
        "zone_slug": zone_slug,
    }
    cur = conn.execute(UPSERT_PROPERTY_SQL, params)
    row = cur.fetchone()
    record_price_point(
        conn,
        portal=portal,
        portal_id=card.portal_id,
        price_amount=card.price_amount,
        price_currency=card.price_currency,
        price_usd_normalized=price_usd_normalized,
    )
    return bool(row[0]) if row else False


def create_scrape_job(
    conn: psycopg.Connection,
    portal: str,
    params: dict,
) -> UUID:
    cur = conn.execute(
        "INSERT INTO scrape_jobs (id, portal, params, status, started_at) "
        "VALUES (gen_random_uuid(), %s::\"Portal\", %s::jsonb, %s::\"ScrapeJobStatus\", now()) "
        "RETURNING id",
        (portal, json.dumps(params), "RUNNING"),
    )
    row = cur.fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("scrape_jobs INSERT did not return an id")
    return row[0]


def finish_scrape_job(
    conn: psycopg.Connection,
    job_id: UUID,
    *,
    status: str,
    items_found: int,
    items_created: int,
    items_updated: int,
    error: str | None = None,
    portal_totals: dict[str, int] | None = None,
) -> None:
    """Close a scrape job. `portal_totals` (the portal's own result count per
    property type) is merged into the params JSONB so coverage can be computed
    per job without a schema migration: items_found / sum(portal_totals)."""
    extra_params: dict = {}
    if portal_totals:
        extra_params["portal_totals"] = portal_totals
        total = sum(portal_totals.values())
        if total > 0:
            extra_params["coverage"] = round(items_found / total, 4)
    conn.execute(
        "UPDATE scrape_jobs SET status = %s::\"ScrapeJobStatus\", completed_at = now(), "
        "items_found = %s, items_created = %s, items_updated = %s, "
        "error_log = %s::jsonb, "
        "params = params || %s::jsonb "
        "WHERE id = %s",
        (
            status,
            items_found,
            items_created,
            items_updated,
            json.dumps({"error": error}) if error else None,
            json.dumps(extra_params),
            job_id,
        ),
    )
    conn.commit()
