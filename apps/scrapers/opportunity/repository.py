"""Cáscara de DB del scorer: leer propiedades + historial, persistir oportunidades.

Reutiliza la conexión sync de los scrapers (scrapers.db.db_conn). La dependencia
va opportunity → scrapers (consumidor → infraestructura), nunca al revés.
"""

from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row

from .scorer import PricePoint, PropertyRow, ScoredOpportunity

LOAD_ROWS_SQL = """
SELECT id, operation_type, property_type, price_amount, price_currency,
       price_usd_normalized, covered_sqm, total_sqm, bedrooms, zone_slug, neighborhood,
       city, title, description, first_seen_at
FROM properties
WHERE is_active = true
"""

LOAD_HISTORY_SQL = """
SELECT ph.property_id, ph.price_amount, ph.price_currency, ph.price_usd_normalized,
       ph.observed_at
FROM price_history ph
JOIN properties p ON p.id = ph.property_id
WHERE p.is_active = true
ORDER BY ph.property_id, ph.observed_at
"""

UPSERT_OPPORTUNITY_SQL = """
INSERT INTO opportunities (
    id, property_id, score, reasons, signals, price_usd_at_score, computed_at
) VALUES (
    gen_random_uuid(), %(property_id)s::uuid, %(score)s, %(reasons)s,
    %(signals)s::jsonb, %(price_usd_at_score)s, now()
)
ON CONFLICT (property_id) DO UPDATE SET
    score = EXCLUDED.score,
    reasons = EXCLUDED.reasons,
    signals = EXCLUDED.signals,
    price_usd_at_score = EXCLUDED.price_usd_at_score,
    computed_at = now();
"""

# Borra las oportunidades de propiedades que ya no califican (keep = las vigentes).
# Con keep vacío borra todo: x <> ALL(ARRAY[]) es vacuosamente verdadero.
PRUNE_OPPORTUNITIES_SQL = """
DELETE FROM opportunities WHERE property_id <> ALL(%(keep)s::uuid[]);
"""


def load_scoring_rows(conn: psycopg.Connection) -> list[PropertyRow]:
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(LOAD_ROWS_SQL)
    return [
        PropertyRow(
            id=str(r["id"]),
            operation_type=r["operation_type"],
            property_type=r["property_type"],
            price_amount=r["price_amount"],
            price_currency=r["price_currency"],
            price_usd=r["price_usd_normalized"],
            covered_sqm=r["covered_sqm"],
            total_sqm=r["total_sqm"],
            bedrooms=r["bedrooms"],
            zone_slug=r["zone_slug"],
            neighborhood=r["neighborhood"],
            city=r["city"],
            title=r["title"],
            description=r["description"],
            first_seen_at=r["first_seen_at"],
        )
        for r in cur.fetchall()
    ]


def load_price_histories(conn: psycopg.Connection) -> dict[str, list[PricePoint]]:
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(LOAD_HISTORY_SQL)
    out: dict[str, list[PricePoint]] = {}
    for r in cur.fetchall():
        out.setdefault(str(r["property_id"]), []).append(
            PricePoint(
                price_amount=r["price_amount"],
                price_currency=r["price_currency"],
                price_usd=r["price_usd_normalized"],
                observed_at=r["observed_at"],
            )
        )
    return out


def persist_opportunities(
    conn: psycopg.Connection, opportunities: list[ScoredOpportunity]
) -> None:
    """Upsert de las oportunidades vigentes + borrado de las que dejaron de serlo.

    El caller hace commit. Idempotente: una segunda corrida con el mismo input deja
    la tabla igual (salvo computed_at).
    """
    for op in opportunities:
        conn.execute(
            UPSERT_OPPORTUNITY_SQL,
            {
                "property_id": op.property_id,
                "score": op.score,
                "reasons": op.reasons,  # list[str] → text[]
                "signals": json.dumps(op.signals),
                "price_usd_at_score": op.price_usd_at_score,
            },
        )
    conn.execute(
        PRUNE_OPPORTUNITIES_SQL, {"keep": [op.property_id for op in opportunities]}
    )
