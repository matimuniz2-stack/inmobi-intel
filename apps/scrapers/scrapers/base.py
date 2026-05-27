"""Abstract scraper base class. Future portals (Argenprop, ZonaProp) inherit this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ScrapeResult:
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    errors: int = 0


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
