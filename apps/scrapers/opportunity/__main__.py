"""CLI del detector de oportunidades.

Corre después del scrape diario: lee las propiedades activas + su historial de
precios, las scorea y persiste las oportunidades vigentes.

    python -m opportunity              # scorea y persiste
    python -m opportunity --dry-run    # scorea y muestra el top, sin escribir
    python -m opportunity --min-score 25
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime

from scrapers.config import DATABASE_URL
from scrapers.db import db_conn
from scrapers.logging_config import configure_logging, get_logger

from .repository import (
    load_price_histories,
    load_scoring_rows,
    persist_opportunities,
)
from .scorer import DEFAULT_MIN_SCORE, score_all

logger = get_logger(__name__)


def run(*, dry_run: bool, min_score: int) -> int:
    now = datetime.now(UTC)
    with db_conn() as conn:
        rows = load_scoring_rows(conn)
        histories = load_price_histories(conn)
        logger.info("scoring_start", properties=len(rows), min_score=min_score)

        opportunities = score_all(rows, histories, now, min_score=min_score)

        # Resumen: cuántas oportunidades dispara cada señal (para auditar la corrida).
        by_signal: Counter[str] = Counter()
        for op in opportunities:
            by_signal.update(op.signals.keys())
        logger.info(
            "scoring_done",
            opportunities=len(opportunities),
            top_score=opportunities[0].score if opportunities else 0,
            low_price=by_signal["low_price"],
            price_drop=by_signal["price_drop"],
            stale=by_signal["stale"],
            urgency=by_signal["urgency"],
        )

        if dry_run:
            for op in opportunities[:20]:
                logger.info(
                    "opportunity",
                    property_id=op.property_id,
                    score=op.score,
                    reasons=op.reasons,
                )
            logger.info("dry_run_no_writes")
            return len(opportunities)

        persist_opportunities(conn, opportunities)
        conn.commit()
        logger.info("opportunities_persisted", count=len(opportunities))

    return len(opportunities)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-friendly
    parser = argparse.ArgumentParser(
        prog="opportunity",
        description="Detector de oportunidades para Inmobi Intel.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scorea y muestra el top sin escribir en la DB.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"Score mínimo para listar como oportunidad (default {DEFAULT_MIN_SCORE}).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)
    if not DATABASE_URL:
        print(
            "ERROR: DATABASE_URL not set. Copy apps/scrapers/.env.example to .env.",
            file=sys.stderr,
        )
        sys.exit(2)

    logger.info("scoring_session_start", min_score=args.min_score, dry_run=args.dry_run)
    count = run(dry_run=args.dry_run, min_score=args.min_score)
    logger.info("scoring_session_end", opportunities=count)


if __name__ == "__main__":
    main()
