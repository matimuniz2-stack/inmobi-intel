"""CLI de desactivación de avisos caídos (megaplan T14, decisión 011).

Marca `is_active = false` en propiedades que dejaron de aparecer en los portales,
para que /buscar, /mapa y /oportunidades no muestren avisos vendidos/retirados.
Corre después del scrape diario (cableado en scrape-all.ps1) y antes del scorer,
así las oportunidades no se calculan sobre avisos muertos.

Criterio (conservador a propósito):
  una propiedad se desactiva sólo si su par (portal, zone_slug) tiene al menos
  un scrape exitoso (job SUCCEEDED con items_found > 0) Y la propiedad no fue
  vista en los --days días PREVIOS a ese último scrape exitoso. Es decir:
  "la última vez que miramos esa zona, el aviso ya llevaba días sin aparecer".
  Se compara contra la fecha del último job de la zona (no contra now()), así
  el criterio no depende de la cadencia: sirve igual con corridas nocturnas
  que con corridas espaciadas semanas, y se puede correr suelto en cualquier
  momento. Zonas bloqueadas, nunca corridas (p. ej. CABA hoy no entra en
  scrape-all) o que devolvieron 0 quedan intactas.

Límite conocido: en zonas donde el portal capea los resultados (Argenprop ~200
por zona/op/tipo), un aviso vigente pero más allá del cap también deja de verse
y termina desactivado. Es el trade-off elegido: mejor ocultar un aviso vivo que
no podemos verificar que mostrar cientos de avisos muertos. Si el aviso
reaparece en un scrape, el UPSERT lo revive (is_active = true) solo.

    python -m deactivate                # desactiva y persiste
    python -m deactivate --dry-run      # sólo informa cuántas desactivaría
    python -m deactivate --days 7       # ventana en días (default 7)
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from scrapers.config import DATABASE_URL
from scrapers.db import db_conn
from scrapers.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

# Último scrape exitoso por (portal, zone_slug). items_found > 0 distingue
# "miramos y había avisos" de "el portal nos bloqueó / devolvió vacío": ante una
# corrida vacía preferimos no desactivar nada de esa zona. Se guarda la fecha
# (max(completed_at)) para comparar contra ella y no contra now(): así una
# corrida vieja sigue sirviendo de evidencia aunque este CLI corra semanas
# después (las corridas reales son espaciadas y a veces se interrumpen antes
# de llegar a este paso).
SCRAPED_PAIRS_CTE = """
    SELECT portal, params->>'zone' AS zone_slug, max(completed_at) AS scraped_at
    FROM scrape_jobs
    WHERE status = 'SUCCEEDED'
      AND items_found > 0
    GROUP BY portal, params->>'zone'
"""

DEACTIVATE_SQL = f"""
WITH scraped AS ({SCRAPED_PAIRS_CTE})
UPDATE properties p
SET is_active = false
FROM scraped s
WHERE p.is_active
  AND p.portal = s.portal
  AND p.zone_slug = s.zone_slug
  AND p.last_seen_at < s.scraped_at - make_interval(days => %(days)s)
RETURNING p.portal;
"""

COUNT_SQL = f"""
WITH scraped AS ({SCRAPED_PAIRS_CTE})
SELECT p.portal, count(*)
FROM properties p
JOIN scraped s ON p.portal = s.portal AND p.zone_slug = s.zone_slug
WHERE p.is_active
  AND p.last_seen_at < s.scraped_at - make_interval(days => %(days)s)
GROUP BY p.portal;
"""


def run(*, dry_run: bool, days: int) -> int:
    with db_conn() as conn:
        if dry_run:
            cur = conn.execute(COUNT_SQL, {"days": days})
            by_portal = Counter(dict(cur.fetchall()))
        else:
            cur = conn.execute(DEACTIVATE_SQL, {"days": days})
            by_portal = Counter(portal for (portal,) in cur.fetchall())
            conn.commit()

        cur = conn.execute("SELECT count(*) FROM properties WHERE is_active")
        row = cur.fetchone()
        still_active = row[0] if row else 0

    total = sum(by_portal.values())
    logger.info(
        "deactivate_done",
        deactivated=total,
        by_portal=dict(by_portal),
        still_active=still_active,
        days=days,
        dry_run=dry_run,
    )
    return total


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Desactiva propiedades que ya no aparecen en los portales."
    )
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la DB.")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help=(
            "Margen en días: se desactiva si la propiedad no fue vista en los N días "
            "previos al último scrape exitoso de su zona."
        ),
    )
    args = parser.parse_args()

    if not DATABASE_URL:
        logger.error("no_database_url", hint="definí DATABASE_URL en apps/scrapers/.env")
        sys.exit(1)

    run(dry_run=args.dry_run, days=args.days)


if __name__ == "__main__":
    main()
