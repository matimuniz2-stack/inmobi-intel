"""Abstract scraper base class. Future portals (Argenprop, ZonaProp) inherit this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Process exit code meaning "the scrape ran without crashing but pulled 0 items
# from every (zone, op)". For these portals that almost always means we were
# blocked (DataDome 403, bot-wall, empty-page interstitial) rather than a
# legitimately empty result set, so we surface it as a failure instead of a
# misleading green check. Distinct from 2 (config/usage error).
EXIT_SCRAPED_NOTHING = 3


@dataclass
class ScrapeResult:
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    errors: int = 0

    def merge(self, other: ScrapeResult) -> None:
        """Accumulate another (zone, op) result into this session-wide total."""
        self.items_found += other.items_found
        self.items_created += other.items_created
        self.items_updated += other.items_updated
        self.errors += other.errors


def session_exit_code(total: ScrapeResult, *, logger: Any) -> int:
    """Decide a scraper process's exit code from its session-wide totals.

    Logs a one-line summary and returns EXIT_SCRAPED_NOTHING when the whole run
    found 0 items (likely blocked), else 0. Keeps a blocked portal from passing
    as a green step — only the global smoke test caught that before.
    """
    logger.info(
        "scrape_session_summary",
        found=total.items_found,
        created=total.items_created,
        updated=total.items_updated,
        errors=total.errors,
    )
    if total.items_found == 0:
        logger.error(
            "scrape_session_empty",
            hint="0 items scraped across all zones — likely blocked (DataDome/bot-wall/empty page)",
            errors=total.errors,
        )
        return EXIT_SCRAPED_NOTHING
    return 0


class BaseScraper(ABC):
    PORTAL: str = ""

    @abstractmethod
    async def scrape_zone(
        self,
        zone: dict,
        operation: str,
        *,
        usd_rate: Decimal | None,
        max_pages: int | None = None,
        dry_run: bool = False,
    ) -> ScrapeResult:
        """Scrape one (zone, operation) pair. Returns aggregate metrics."""
