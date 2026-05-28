"""Argenprop scraper. Uses Playwright (Chromium); no anti-bot bypass needed."""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import cast

from playwright.async_api import BrowserContext, Page, async_playwright

from .argenprop_parser import parse_listing_page
from .base import BaseScraper, ScrapeResult
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

logger = get_logger(__name__)

PORTAL = "ARGENPROP"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

PROP_TYPE_SLUG: dict[str, str] = {
    "APT": "departamentos",
    "HOUSE": "casas",
    "PH": "ph",
    "LOCAL": "locales",
    "TERRENO": "terrenos",
}

OPERATION_SLUG: dict[str, str] = {
    "SALE": "venta",
    "RENT": "alquiler",
}


def build_url(zone: dict, operation: str, prop_type: str, page: int = 1) -> str:
    type_slug = PROP_TYPE_SLUG[prop_type]
    op_slug = OPERATION_SLUG[operation]
    loc_slug = zone.get("argenpropSlug") or zone["slug"]
    base = f"https://www.argenprop.com/{type_slug}/{op_slug}/{loc_slug}"
    return f"{base}?pagina={page}" if page > 1 else base


class ArgenpropScraper(BaseScraper):
    PORTAL = "ARGENPROP"

    def __init__(self, context: BrowserContext) -> None:
        self._ctx = context

    async def _fetch_page_html(self, page: Page, url: str) -> str:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector("div.listing__item, .listing--empty", timeout=15000)
        except Exception:
            await page.wait_for_timeout(2000)
        return await page.content()

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
        page = await self._ctx.new_page()
        try:
            for prop_type in types:
                prev_first_id: str | None = None
                for page_num in range(1, (max_pages or 50) + 1):
                    url = build_url(zone, operation, prop_type, page=page_num)
                    log = logger.bind(zone=zone["slug"], op=operation, type=prop_type, page=page_num)
                    log.info("scrape_page_start", url=url)

                    try:
                        html = await self._fetch_page_html(page, url)
                    except Exception as e:
                        log.error("fetch_failed", error=repr(e))
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

                    if prev_first_id is not None and cards[0].portal_id == prev_first_id:
                        log.warning("pagination_stuck")
                        break
                    prev_first_id = cards[0].portal_id

                    log.info("page_parsed", count=len(cards))
                    result.items_found += len(cards)

                    if dry_run:
                        continue

                    with db_conn() as conn:
                        for card in cards:
                            # Argenprop cards don't include the city in their address. We
                            # attach the zone's mlCity for consistency with ML rows.
                            if card.city is None:
                                card = card.model_copy(update={"city": zone.get("mlCity")})
                            try:
                                inserted = upsert_property(
                                    conn,
                                    card,
                                    zone_slug=zone["slug"],
                                    usd_rate=usd_rate,
                                    portal="ARGENPROP",
                                )
                                if inserted:
                                    result.items_created += 1
                                else:
                                    result.items_updated += 1
                            except Exception as e:
                                log.error("upsert_failed", portal_id=card.portal_id, error=repr(e))
                                result.errors += 1
                        conn.commit()

                    # Argenprop pages have ~20 items; <15 = last page
                    if len(cards) < 15:
                        log.info("last_page_short", count=len(cards))
                        break
        finally:
            await page.close()
        return result


async def _build_context(playwright) -> BrowserContext:
    browser = await playwright.chromium.launch(headless=True)
    return await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="es-AR",
    )


async def _resolve_zones(zone_arg: str) -> list[dict]:
    if zone_arg in ("all", "*"):
        # Argenprop URLs work at city-level. Skip neighborhood-only zones for now.
        return [z for z in load_zones() if not z.get("mlNeighborhood")]
    slugs = [s.strip() for s in zone_arg.split(",") if s.strip()]
    return [get_zone(s) for s in slugs]


async def run(
    zones: list[dict],
    operations: list[str],
    prop_types: list[str],
    *,
    max_pages: int | None,
    dry_run: bool,
    skip_usd: bool,
) -> None:
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

    async with async_playwright() as pw:
        ctx = await _build_context(pw)
        scraper = ArgenpropScraper(ctx)

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
                            )
                except Exception as e:
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

        if ctx.browser is not None:
            await ctx.browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="scrapers.argenprop",
        description="Argenprop property scraper for Inmobi Intel.",
    )
    parser.add_argument(
        "--zone",
        required=True,
        help="Comma-separated zone slugs, or 'all' for every city-level zone.",
    )
    parser.add_argument("--op", default="SALE,RENT", help="SALE, RENT")
    parser.add_argument(
        "--type",
        default="APT",
        help="Comma-separated property types (APT, HOUSE, PH, LOCAL, TERRENO).",
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

    zones = asyncio.run(_resolve_zones(args.zone))
    logger.info(
        "scrape_session_start",
        zones=[z["slug"] for z in zones],
        ops=operations,
        types=prop_types,
        max_pages=args.limit,
        dry_run=args.dry_run,
    )
    asyncio.run(
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


if __name__ == "__main__":
    main()
