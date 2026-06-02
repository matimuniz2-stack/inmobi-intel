"""Abstract scraper base class. Future portals (Argenprop, ZonaProp) inherit this."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypeVar

# Process exit code meaning "the scrape ran without crashing but pulled 0 items
# from every (zone, op)". For these portals that almost always means we were
# blocked (DataDome 403, bot-wall, empty-page interstitial) rather than a
# legitimately empty result set, so we surface it as a failure instead of a
# misleading green check. Distinct from 2 (config/usage error).
EXIT_SCRAPED_NOTHING = 3

_T = TypeVar("_T")


async def fetch_with_retry(
    fetch: Callable[[], Awaitable[_T]],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    logger: Any | None = None,
) -> _T:
    """Retry a network fetch on transient errors with exponential backoff.

    Wraps a Playwright navigation that may fail with a timeout or a transient
    network error (common with headless Chromium on a residential IP). Retries
    `attempts` times with delays base_delay, 2·base_delay, 4·base_delay, ...
    and re-raises the last exception if all attempts fail.

    Only retries on EXCEPTIONS. Anti-bot block detection (DataDome challenge,
    bot-wall, empty page) happens AFTER the fetch in each scraper — a block must
    not be retried in a tight loop, it should break/back off at the zone level.
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return await fetch()
        except Exception as e:  # noqa: BLE001 — re-raised below if all attempts fail
            last_exc = e
            if logger is not None:
                logger.warning("fetch_retry", attempt=i + 1, attempts=attempts, error=repr(e))
            if i < attempts - 1:
                await asyncio.sleep(base_delay * (2**i))
    assert last_exc is not None
    raise last_exc


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
