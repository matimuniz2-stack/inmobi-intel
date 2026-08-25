"""Properati scraper. Plain httpx — the portal serves full server-side HTML
with no bot-wall (verified 2026-08-25 from the residential IP), so no Playwright.

Coverage note: unlike ML (~2k cap) and Argenprop (10-page robots cap), Properati
paginates the whole result set (page 150+ of the 9k-listing MdP query verified
live), so the city-level zone alone covers the full market — no barrio partition
needed. Pagination is path-suffix: /s/<zone>/<type>/<operation>/<page>.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from decimal import Decimal
from typing import cast

import httpx

from .base import BaseScraper, ScrapeResult, fetch_with_retry, session_exit_code
from .config import DATABASE_URL, get_zone, load_zones
from .db import (
    create_scrape_job,
    db_conn,
    finish_scrape_job,
    get_latest_usd_rate,
    insert_usd_rate,
    upsert_property,
)
from .exchange import fetch_blue_rate
from .logging_config import configure_logging, get_logger
from .models import Operation, PropertyType
from .properati_parser import detect_total_results, parse_listing_page

logger = get_logger(__name__)

PORTAL = "PROPERATI"
BASE_URL = "https://www.properati.com.ar"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Properati's URL taxonomy has no PH / local / temp-rent segment (verified live:
# /ph/, /local-comercial/ and /alquiler-temporal/ all 404). PH listings surface
# under casa/departamento; TEMP_RENT is refined from the title by the parser.
PROP_TYPE_SLUG: dict[str, str] = {
    "APT": "departamento",
    "HOUSE": "casa",
    "TERRENO": "terreno",
}

OPERATION_SLUG: dict[str, str] = {
    "SALE": "venta",
    "RENT": "alquiler",
}

# 30 cards/page → 400 pages = 12.000 listings per (zone, op, type), comfortably
# above MdP's largest query (9.2k deptos venta). Backstop against an infinite
# loop if the portal ever starts serving repeats instead of an empty last page.
MAX_PAGES_HARD_CAP = 400


def build_url(zone: dict, operation: str, prop_type: str, page: int = 1) -> str:
    type_slug = PROP_TYPE_SLUG[prop_type]
    op_slug = OPERATION_SLUG[operation]
    loc_slug = zone["properatiSlug"]
    base = f"{BASE_URL}/s/{loc_slug}/{type_slug}/{op_slug}"
    return f"{base}/{page}" if page > 1 else base


class ProperatiScraper(BaseScraper):
    PORTAL = "PROPERATI"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _fetch_page_html(self, url: str) -> tuple[int, str]:
        r = await self._client.get(url)
        return r.status_code, r.text

    async def scrape_zone(
        self,
        zone: dict,
        operation: str,
        *,
        usd_rate: Decimal | None,
        max_pages: int | None = None,
        dry_run: bool = False,
        prop_types: list[str] | None = None,
    ) -> ScrapeResult:
        result = ScrapeResult()
        types = prop_types or ["APT"]
        for prop_type in types:
            prev_first_id: str | None = None
            for page_num in range(1, (max_pages or MAX_PAGES_HARD_CAP) + 1):
                url = build_url(zone, operation, prop_type, page=page_num)
                log = logger.bind(zone=zone["slug"], op=operation, type=prop_type, page=page_num)
                log.info("scrape_page_start", url=url)

                try:
                    status, html = await fetch_with_retry(
                        lambda url=url: self._fetch_page_html(url), logger=log
                    )
                except Exception as e:
                    log.error("fetch_failed", error=repr(e))
                    result.errors += 1
                    break

                # 404 = the (zone, type, op) combo doesn't exist in Properati's
                # taxonomy — a legit empty result, not a block.
                if status == 404:
                    log.info("combo_not_found_404")
                    break
                if status != 200:
                    log.error("unexpected_status", status=status, html_size=len(html))
                    result.errors += 1
                    break

                cards = parse_listing_page(
                    html,
                    operation_type=cast(Operation, operation),
                    property_type=cast(PropertyType, prop_type),
                )
                if not cards:
                    log.info("no_cards_break", html_size=len(html))
                    break

                if page_num == 1:
                    total = detect_total_results(html)
                    if total is not None:
                        log.info("scrape_zone_total", total=total)
                        result.portal_totals[prop_type] = total

                if prev_first_id is not None and cards[0].portal_id == prev_first_id:
                    log.warning("pagination_stuck")
                    break
                prev_first_id = cards[0].portal_id

                log.info("page_parsed", count=len(cards))
                result.items_found += len(cards)

                if not dry_run:
                    with db_conn() as conn:
                        for card in cards:
                            if card.city is None:
                                card = card.model_copy(update={"city": zone.get("mlCity")})
                            try:
                                inserted = upsert_property(
                                    conn,
                                    card,
                                    zone_slug=zone["slug"],
                                    usd_rate=usd_rate,
                                    portal=PORTAL,
                                )
                                if inserted:
                                    result.items_created += 1
                                else:
                                    result.items_updated += 1
                            except Exception as e:
                                log.error("upsert_failed", portal_id=card.portal_id, error=repr(e))
                                result.errors += 1
                        conn.commit()

                # Pages carry 30 cards; a short page is the last one.
                if len(cards) < 25:
                    log.info("last_page_short", count=len(cards))
                    break

                await asyncio.sleep(random.uniform(1.0, 2.5))
        return result


def _resolve_zones(zone_arg: str) -> list[dict]:
    """Only zones with an explicit properatiSlug are scrapeable — the city-level
    query paginates fully, so (unlike Argenprop/ZonaProp) barrio partition isn't
    needed and most zones intentionally have no slug."""
    if zone_arg in ("all", "*"):
        return [z for z in load_zones() if z.get("properatiSlug")]
    zones = [get_zone(s.strip()) for s in zone_arg.split(",") if s.strip()]
    missing = [z["slug"] for z in zones if not z.get("properatiSlug")]
    if missing:
        raise SystemExit(f"ERROR: zones without properatiSlug: {missing}")
    return zones


async def run(
    zones: list[dict],
    operations: list[str],
    prop_types: list[str],
    *,
    max_pages: int | None,
    dry_run: bool,
    skip_usd: bool,
) -> ScrapeResult:
    total = ScrapeResult()
    usd_rate: Decimal | None = None
    if not skip_usd:
        try:
            rec = await fetch_blue_rate()
            usd_rate = rec.rate
            logger.info("usd_rate_fetched", rate=str(usd_rate))
            if not dry_run:
                with db_conn() as conn:
                    insert_usd_rate(conn, rec)
        except Exception as e:
            logger.warning("usd_rate_fetch_failed", error=repr(e))
            if not dry_run:
                with db_conn() as conn:
                    usd_rate = get_latest_usd_rate(conn)
    elif not dry_run:
        with db_conn() as conn:
            usd_rate = get_latest_usd_rate(conn)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        scraper = ProperatiScraper(client)

        for zone in zones:
            for op in operations:
                job_id = None
                if not dry_run:
                    with db_conn() as conn:
                        job_id = create_scrape_job(
                            conn,
                            portal=PORTAL,
                            params={
                                "zone": zone["slug"],
                                "operation": op,
                                "prop_types": prop_types,
                            },
                        )
                logger.info(
                    "scrape_zone_start", zone=zone["slug"], op=op, job_id=str(job_id)
                )

                try:
                    res = await scraper.scrape_zone(
                        zone,
                        op,
                        usd_rate=usd_rate,
                        max_pages=max_pages,
                        dry_run=dry_run,
                        prop_types=prop_types,
                    )
                    total.merge(res)
                    logger.info(
                        "scrape_zone_end",
                        zone=zone["slug"],
                        op=op,
                        found=res.items_found,
                        created=res.items_created,
                        updated=res.items_updated,
                        errors=res.errors,
                    )
                    if not dry_run and job_id:
                        with db_conn() as conn:
                            finish_scrape_job(
                                conn,
                                job_id,
                                status="SUCCEEDED" if res.errors == 0 else "FAILED",
                                items_found=res.items_found,
                                items_created=res.items_created,
                                items_updated=res.items_updated,
                                portal_totals=res.portal_totals,
                            )
                except Exception as e:
                    total.errors += 1
                    logger.error("scrape_zone_failed", zone=zone["slug"], op=op, error=repr(e))
                    if not dry_run and job_id:
                        with db_conn() as conn:
                            finish_scrape_job(
                                conn,
                                job_id,
                                status="FAILED",
                                items_found=0,
                                items_created=0,
                                items_updated=0,
                                error=repr(e),
                            )

    return total


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="scrapers.properati",
        description="Properati property scraper for Inmobi Intel.",
    )
    parser.add_argument(
        "--zone",
        required=True,
        help="Comma-separated zone slugs (need properatiSlug), or 'all'.",
    )
    parser.add_argument("--op", default="SALE,RENT", help="SALE, RENT")
    parser.add_argument(
        "--type",
        default="APT,HOUSE,TERRENO",
        help="Comma-separated property types (APT, HOUSE, TERRENO).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max pages per zone/op/type.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-usd", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)
    if not args.dry_run and not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)

    operations = [o.strip().upper() for o in args.op.split(",") if o.strip()]
    invalid_ops = [o for o in operations if o not in OPERATION_SLUG]
    if invalid_ops:
        print(f"ERROR: unsupported ops: {invalid_ops}", file=sys.stderr)
        sys.exit(2)

    prop_types = [t.strip().upper() for t in args.type.split(",") if t.strip()]
    invalid_types = [t for t in prop_types if t not in PROP_TYPE_SLUG]
    if invalid_types:
        print(f"ERROR: unsupported types: {invalid_types}", file=sys.stderr)
        sys.exit(2)

    zones = _resolve_zones(args.zone)
    logger.info(
        "scrape_session_start",
        zones=[z["slug"] for z in zones],
        ops=operations,
        types=prop_types,
        max_pages=args.limit,
        dry_run=args.dry_run,
    )
    summary = asyncio.run(
        run(
            zones,
            operations,
            prop_types,
            max_pages=args.limit,
            dry_run=args.dry_run,
            skip_usd=args.skip_usd,
        )
    )
    logger.info("scrape_session_end")
    sys.exit(session_exit_code(summary, logger=logger))


if __name__ == "__main__":
    main()
