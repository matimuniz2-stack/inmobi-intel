"""MercadoLibre scraper. Uses Playwright (Chromium) to bypass anti-bot WAF."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import unicodedata
from decimal import Decimal
from typing import Literal

from playwright.async_api import BrowserContext, Page, async_playwright

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
from .parser import detect_total_results, parse_listing_page

logger = get_logger(__name__)

PORTAL = "MERCADOLIBRE"
OPERATION_SLUGS: dict[str, str] = {"SALE": "venta", "RENT": "alquiler"}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def slugify(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    no_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", no_accents.lower()).strip("-")


def build_url(zone: dict, operation: str, page: int = 1) -> str:
    """Build the listings URL. ML uses two formats; we use the canonical pagination one
    (`inmuebles.mercadolibre.com.ar/inmuebles-<op>-<state>-<city>[-<barrio>]_Desde_N_...`).
    Verified via Playwright click on the 'next' button.
    """
    op_slug = OPERATION_SLUGS[operation]
    parts = ["inmuebles", op_slug, slugify(zone["mlState"]), slugify(zone["mlCity"])]
    if zone.get("mlNeighborhood"):
        parts.append(slugify(zone["mlNeighborhood"]))
    path = "-".join(parts)
    if page > 1:
        # ML returns 50 items per page; offset is the 1-based index of the first item.
        offset = (page - 1) * 50 + 1
        return (
            f"https://inmuebles.mercadolibre.com.ar/"
            f"{path}_Desde_{offset}_DisplayType_LF_NoIndex_True"
        )
    return f"https://inmuebles.mercadolibre.com.ar/{path}_DisplayType_LF"


class MercadoLibreScraper(BaseScraper):
    PORTAL = "MERCADOLIBRE"

    def __init__(self, context: BrowserContext) -> None:
        self._ctx = context

    async def _fetch_page_html(self, page: Page, url: str) -> str:
        """Navigate and wait for the listings to render. Returns HTML."""
        log = logger.bind(url=url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Wait up to 30s for either listings OR a clear "no results" indicator
        for _ in range(30):
            await page.wait_for_timeout(1000)
            html = await page.content()
            if "ui-search-layout__item" in html or "search-no-results" in html:
                return html
            if len(html) > 100_000 and "poly-card" in html:
                return html
        log.warning("page_did_not_render_listings", html_size=len(await page.content()))
        return await page.content()

    async def scrape_zone(
        self,
        zone: dict,
        operation: str,
        *,
        usd_rate: Decimal | None,
        max_pages: int | None = None,
        dry_run: bool = False,
    ) -> ScrapeResult:
        result = ScrapeResult()
        page = await self._ctx.new_page()
        prev_first_id: str | None = None
        try:
            for page_num in range(1, (max_pages or 50) + 1):
                url = build_url(zone, operation, page=page_num)
                log = logger.bind(zone=zone["slug"], op=operation, page=page_num)
                log.info("scrape_page_start", url=url)

                try:
                    html = await fetch_with_retry(
                        lambda: self._fetch_page_html(page, url), logger=log
                    )
                except Exception as e:
                    log.error("scrape_page_fetch_failed", error=repr(e))
                    result.errors += 1
                    break

                if "search-no-results" in html:
                    log.info("scrape_page_no_results")
                    break

                cards = parse_listing_page(html)
                if not cards:
                    log.info("scrape_page_zero_parsed", html_size=len(html))
                    break

                if prev_first_id is not None and cards[0].portal_id == prev_first_id:
                    log.warning("scrape_pagination_stuck", first_id=cards[0].portal_id)
                    break
                prev_first_id = cards[0].portal_id

                if page_num == 1:
                    total = detect_total_results(html)
                    if total is not None:
                        log.info("scrape_zone_total", total=total)
                        result.portal_totals["ALL"] = total

                log.info("scrape_page_parsed", count=len(cards))
                result.items_found += len(cards)

                if dry_run:
                    continue

                with db_conn() as conn:
                    for card in cards:
                        try:
                            inserted = upsert_property(
                                conn, card, zone_slug=zone["slug"], usd_rate=usd_rate,
                                portal="MERCADOLIBRE",
                            )
                            if inserted:
                                result.items_created += 1
                            else:
                                result.items_updated += 1
                        except Exception as e:
                            log.error("upsert_failed", portal_id=card.portal_id, error=repr(e))
                            result.errors += 1
                    conn.commit()

                # ML pages return 48 items normally; if fewer, we're at the last page
                if len(cards) < 40:
                    log.info("scrape_page_short_last_page", count=len(cards))
                    break
        finally:
            await page.close()
        return result


async def _build_context(playwright) -> BrowserContext:
    browser = await playwright.chromium.launch(headless=True)
    ctx = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="es-AR",
    )
    # Pre-seed the bypass cookie to skip ML's bot-challenge landing page
    await ctx.add_cookies([
        {
            "name": "_bm_skipml",
            "value": "true",
            "domain": ".mercadolibre.com.ar",
            "path": "/",
        },
    ])
    return ctx


async def _resolve_zones(zone_arg: str) -> list[dict]:
    if zone_arg in ("all", "*"):
        return load_zones()
    slugs = [s.strip() for s in zone_arg.split(",") if s.strip()]
    return [get_zone(s) for s in slugs]


async def run(
    zones: list[dict],
    operations: list[str],
    *,
    max_pages: int | None,
    dry_run: bool,
    skip_usd: bool,
) -> ScrapeResult:
    total = ScrapeResult()
    # 1. Refresh USD rate (always — cheap, idempotent within the day).
    usd_rate: Decimal | None = None
    if not skip_usd:
        try:
            rate_rec = await fetch_blue_rate()
            usd_rate = rate_rec.rate
            logger.info("usd_rate_fetched", rate=str(usd_rate), source=rate_rec.source)
            if not dry_run:
                with db_conn() as conn:
                    insert_usd_rate(conn, rate_rec)
        except Exception as e:
            logger.warning("usd_rate_fetch_failed", error=repr(e))
            # Fall back to latest from DB
            if not dry_run:
                with db_conn() as conn:
                    usd_rate = get_latest_usd_rate(conn)
            if usd_rate:
                logger.info("usd_rate_using_fallback", rate=str(usd_rate))
    elif not dry_run:
        with db_conn() as conn:
            usd_rate = get_latest_usd_rate(conn)

    # 2. Scrape each (zone, operation) pair.
    async with async_playwright() as pw:
        ctx = await _build_context(pw)
        scraper = MercadoLibreScraper(ctx)

        for zone in zones:
            for op in operations:
                job_id = None
                if not dry_run:
                    with db_conn() as conn:
                        job_id = create_scrape_job(
                            conn,
                            portal=PORTAL,
                            params={"zone": zone["slug"], "operation": op},
                        )
                logger.info("scrape_zone_start", zone=zone["slug"], op=op, job_id=str(job_id))

                try:
                    res = await scraper.scrape_zone(
                        zone, op, usd_rate=usd_rate, max_pages=max_pages, dry_run=dry_run
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

        if ctx.browser is not None:
            await ctx.browser.close()

    return total


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-friendly
    parser = argparse.ArgumentParser(
        prog="scrapers.mercadolibre",
        description="MercadoLibre property scraper for Inmobi Intel.",
    )
    parser.add_argument(
        "--zone",
        required=True,
        help="Comma-separated zone slugs, or 'all' to scrape every zone.",
    )
    parser.add_argument(
        "--op",
        default="SALE,RENT",
        help="Comma-separated operations (SALE, RENT). Default: SALE,RENT.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max pages per (zone, operation). Default: scrape until exhausted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse pages and log results but skip all DB writes.",
    )
    parser.add_argument(
        "--skip-usd",
        action="store_true",
        help="Don't refresh the blue rate; use the latest already in DB.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)
    if not args.dry_run and not DATABASE_URL:
        print("ERROR: DATABASE_URL not set. Copy apps/scrapers/.env.example to .env.", file=sys.stderr)
        sys.exit(2)

    operations = [o.strip().upper() for o in args.op.split(",") if o.strip()]
    invalid = [o for o in operations if o not in OPERATION_SLUGS]
    if invalid:
        print(f"ERROR: unsupported operations: {invalid}. Allowed: {list(OPERATION_SLUGS)}", file=sys.stderr)
        sys.exit(2)

    zones = asyncio.run(_resolve_zones(args.zone))
    logger.info(
        "scrape_session_start",
        zones=[z["slug"] for z in zones],
        ops=operations,
        max_pages=args.limit,
        dry_run=args.dry_run,
    )
    summary = asyncio.run(
        run(zones, operations, max_pages=args.limit, dry_run=args.dry_run, skip_usd=args.skip_usd)
    )
    logger.info("scrape_session_end")
    sys.exit(session_exit_code(summary, logger=logger))


if __name__ == "__main__":
    main()
