"""ZonaProp scraper. Uses Playwright + playwright-stealth to bypass Datadome.

Strategy:
- Fresh browser context per page (defeats session tracking).
- playwright-stealth to mask the automation fingerprint.
- 10–20 s random delays between requests (avoids triggering rate-limiter).
- If Datadome blocks, we get the "Un momento…" challenge page (size < 100 KB)
  and we abort the run rather than spin endlessly.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from decimal import Decimal
from typing import cast

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async

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
from .models import Operation, PropertyType
from .zonaprop_parser import detect_total_results, parse_listing_page

logger = get_logger(__name__)

PORTAL = "ZONAPROP"
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
    """ZonaProp URL: /{tipo}-{op}-{location}-pagina-N.html"""
    type_slug = PROP_TYPE_SLUG[prop_type]
    op_slug = OPERATION_SLUG[operation]
    loc_slug = zone.get("zonapropSlug") or zone["slug"]
    base = f"https://www.zonaprop.com.ar/{type_slug}-{op_slug}-{loc_slug}"
    return f"{base}-pagina-{page}.html" if page > 1 else f"{base}.html"


async def _new_context(browser) -> BrowserContext:
    return await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
        extra_http_headers={
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
    )


class ZonapropScraper(BaseScraper):
    PORTAL = "ZONAPROP"

    def __init__(self, browser) -> None:
        self._browser = browser

    async def _fetch_page_html(self, url: str) -> tuple[str, int]:
        """Open a fresh context with stealth, fetch the URL, return (html, http_status).
        On Datadome challenge, returns the challenge HTML — caller decides what to do.
        """
        ctx = await _new_context(self._browser)
        page = await ctx.new_page()
        await stealth_async(page)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            return await page.content(), (resp.status if resp else 0)
        finally:
            await ctx.close()

    async def scrape_zone(
        self,
        zone: dict,
        operation: str,
        *,
        usd_rate: Decimal | None,
        max_pages: int | None = None,
        dry_run: bool = False,
        prop_types: list[str] | None = None,
        min_delay: float = 8.0,
        max_delay: float = 15.0,
    ) -> ScrapeResult:
        result = ScrapeResult()
        types = prop_types or ["APT"]
        cap = max_pages or 30
        for prop_type in types:
            prev_first_id: str | None = None
            for page_num in range(1, cap + 1):
                url = build_url(zone, operation, prop_type, page=page_num)
                log = logger.bind(zone=zone["slug"], op=operation, type=prop_type, page=page_num)
                log.info("scrape_page_start", url=url)

                try:
                    html, status = await fetch_with_retry(
                        lambda: self._fetch_page_html(url), logger=log
                    )
                except Exception as e:
                    log.error("fetch_failed", error=repr(e))
                    result.errors += 1
                    break

                # Datadome challenge detector
                if len(html) < 100_000 or "Un momento" in html[:5000]:
                    log.warning("datadome_challenge", html_size=len(html), status=status)
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

                if page_num == 1:
                    total = detect_total_results(html)
                    if total:
                        log.info("scrape_zone_total", total=total)

                log.info("page_parsed", count=len(cards))
                result.items_found += len(cards)

                if not dry_run:
                    with db_conn() as conn:
                        for card in cards:
                            if card.city is None:
                                card = card.model_copy(update={"city": zone.get("mlCity")})
                            try:
                                inserted = upsert_property(
                                    conn,
                                    card,
                                    zone_slug=zone["slug"],
                                    usd_rate=usd_rate,
                                    portal="ZONAPROP",
                                )
                                if inserted:
                                    result.items_created += 1
                                else:
                                    result.items_updated += 1
                            except Exception as e:
                                log.error("upsert_failed", portal_id=card.portal_id, error=repr(e))
                                result.errors += 1
                        conn.commit()

                # Last page heuristic
                if len(cards) < 20:
                    log.info("last_page_short", count=len(cards))
                    break

                # Random delay between pages
                delay = random.uniform(min_delay, max_delay)
                log.info("sleep", seconds=round(delay, 1))
                await asyncio.sleep(delay)
        return result


async def _resolve_zones(zone_arg: str) -> list[dict]:
    if zone_arg in ("all", "*"):
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
    min_delay: float,
    max_delay: float,
) -> ScrapeResult:
    total = ScrapeResult()
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
        browser = await pw.chromium.launch(headless=True)
        scraper = ZonapropScraper(browser)

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
                logger.info("scrape_zone_start", zone=zone["slug"], op=op, job_id=str(job_id))

                try:
                    res = await scraper.scrape_zone(
                        zone,
                        op,
                        usd_rate=usd_rate,
                        max_pages=max_pages,
                        dry_run=dry_run,
                        prop_types=prop_types,
                        min_delay=min_delay,
                        max_delay=max_delay,
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

        await browser.close()

    return total


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="scrapers.zonaprop")
    parser.add_argument("--zone", required=True)
    parser.add_argument("--op", default="SALE,RENT")
    parser.add_argument("--type", default="APT")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-usd", action="store_true")
    parser.add_argument("--min-delay", type=float, default=8.0)
    parser.add_argument("--max-delay", type=float, default=15.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)
    if not args.dry_run and not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)

    operations = [o.strip().upper() for o in args.op.split(",") if o.strip()]
    if any(o not in OPERATION_SLUG for o in operations):
        print("ERROR: unsupported op", file=sys.stderr)
        sys.exit(2)
    prop_types = [t.strip().upper() for t in args.type.split(",") if t.strip()]
    if any(t not in PROP_TYPE_SLUG for t in prop_types):
        print("ERROR: unsupported type", file=sys.stderr)
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
    summary = asyncio.run(
        run(
            zones,
            operations,
            prop_types,
            max_pages=args.limit,
            dry_run=args.dry_run,
            skip_usd=args.skip_usd,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
        )
    )
    logger.info("scrape_session_end")
    sys.exit(session_exit_code(summary, logger=logger))


if __name__ == "__main__":
    main()
