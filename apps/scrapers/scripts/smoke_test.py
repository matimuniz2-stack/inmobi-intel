"""Smoke test for the daily cron: ensure the scrape touched ≥1 property recently.

Exits 0 if at least MIN_TOUCHED (default: 1) properties have a `last_seen_at`
in the last hour. Otherwise exits 1 to mark the cron job as failed.
"""

from __future__ import annotations

import os
import sys

import psycopg

MIN_TOUCHED = int(os.environ.get("MIN_TOUCHED", "1"))
WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "1"))


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    with psycopg.connect(url) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM properties "
            "WHERE last_seen_at > NOW() - (%s || ' hours')::interval",
            (WINDOW_HOURS,),
        )
        row = cur.fetchone()
        touched = int(row[0]) if row else 0

        # Bonus stats: how many created in this window
        cur = conn.execute(
            "SELECT COUNT(*) FROM properties "
            "WHERE first_seen_at > NOW() - (%s || ' hours')::interval",
            (WINDOW_HOURS,),
        )
        row = cur.fetchone()
        created = int(row[0]) if row else 0

    print(f"Properties touched in last {WINDOW_HOURS}h: {touched} (of which {created} new)")

    if touched < MIN_TOUCHED:
        print(f"FAIL: expected ≥{MIN_TOUCHED}, got {touched}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
