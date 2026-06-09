"""CLI del geocoder.

Corre después del scrape diario (y del scoreo de oportunidades): toma las
propiedades activas sin coordenadas y las geocodifica contra Nominatim, persistiendo
lat/lng. Idempotente: las que ya tienen coordenadas se saltean, y la caché en disco
evita re-consultar direcciones ya resueltas.

    python -m geocode               # geocodifica y persiste
    python -m geocode --dry-run     # no escribe en la DB (pero sí cachea respuestas)
    python -m geocode --limit 200   # tope de propiedades por corrida (default 500)
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from scrapers.config import DATABASE_URL
from scrapers.db import db_conn
from scrapers.logging_config import configure_logging, get_logger

from .geocoder import GeocodeCache, Nominatim, geocode_property
from .repository import load_pending, save_coords

logger = get_logger(__name__)


def run(*, dry_run: bool, limit: int) -> int:
    cache = GeocodeCache()
    nominatim = Nominatim()
    by_level: Counter[str] = Counter()
    geocoded = 0
    failed = 0
    try:
        with db_conn() as conn:
            pending = load_pending(conn, limit=limit)
            logger.info("geocode_start", pending=len(pending), dry_run=dry_run)

            for row in pending:
                result = geocode_property(
                    prop_id=row.id,
                    address_full=row.address_full,
                    neighborhood=row.neighborhood,
                    city=row.city,
                    province=row.province,
                    nominatim=nominatim,
                    cache=cache,
                )
                if result is None:
                    failed += 1
                    logger.debug(
                        "geocode_miss",
                        id=row.id,
                        neighborhood=row.neighborhood,
                        city=row.city,
                    )
                    continue

                by_level[result.level] += 1
                geocoded += 1
                if not dry_run:
                    save_coords(conn, prop_id=row.id, lat=result.lat, lng=result.lng)

                # Commit + flush de caché de a tandas para no perder progreso si se corta.
                if geocoded % 25 == 0:
                    if not dry_run:
                        conn.commit()
                    cache.flush()
                    logger.info("geocode_progress", geocoded=geocoded, failed=failed)

            if not dry_run:
                conn.commit()
    finally:
        cache.flush()
        nominatim.close()

    logger.info(
        "geocode_done",
        geocoded=geocoded,
        failed=failed,
        address=by_level["address"],
        street=by_level["street"],
        barrio=by_level["barrio"],
        ciudad=by_level["ciudad"],
        dry_run=dry_run,
    )
    return geocoded


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Geocodifica propiedades (Nominatim).")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la DB.")
    parser.add_argument(
        "--limit", type=int, default=500, help="Máx. de propiedades por corrida."
    )
    args = parser.parse_args()

    if not DATABASE_URL:
        logger.error("no_database_url", hint="definí DATABASE_URL en apps/scrapers/.env")
        sys.exit(1)

    run(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
