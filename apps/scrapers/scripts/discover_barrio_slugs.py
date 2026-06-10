"""Discover canonical barrio slugs for Argenprop and ZonaProp (T1).

Instead of guessing URL slugs per barrio, we read them off the portals
themselves: each listing page exposes a "Barrios" facet whose links carry the
canonical location slug. Facets only show the top-N barrios per page, so we
sweep several seed pages (type x operation) per portal and merge the results.

Usage (from apps/scrapers/):
    poetry run python scripts/discover_barrio_slugs.py            # both portals
    poetry run python scripts/discover_barrio_slugs.py --portal argenprop

Writes scripts/out/slug-candidates.json with every facet link found, so the
mapping against zones.json can be reviewed by hand before editing it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

OUT_DIR = Path(__file__).parent / "out"

TYPES = ["departamentos", "casas", "ph", "locales", "terrenos"]
OPS = ["venta", "alquiler"]

# Facet links that are locations look like the listing URL itself with another
# location slug. Anything carrying refinements (page, rooms, baths, garages,
# free-text q-...) is noise.
NOISE_RE = re.compile(
    r"(-pagina-\d+$|-q-|-\d+-ambientes?$|-mas-de-\d+-(ambientes|banos)$"
    r"|-1-ambiente$|-sin-garages$|-con-|-desde-|-hasta-)"
)
SKIP_SLUGS = {"mar-del-plata", "buenos-aires", "buenos-aires-costa-atlantica",
              "partido-de-general-pueyrredon", "otro"}


async def _collect_links(page) -> list[dict]:
    return await page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => ({
            href: a.getAttribute('href'),
            text: (a.textContent || '').trim().replace(/\\s+/g, ' '),
        }))""",
    )


def _filter(links: list[dict], href_re: re.Pattern) -> dict[str, str]:
    out: dict[str, str] = {}
    for link in links:
        m = href_re.match(link["href"] or "")
        if not m:
            continue
        slug = m.group(1)
        if slug in SKIP_SLUGS or NOISE_RE.search(slug):
            continue
        out.setdefault(slug, link["text"])
    return out


async def discover_argenprop(browser) -> dict[str, str]:
    ctx = await browser.new_context(user_agent=USER_AGENT, locale="es-AR")
    page = await ctx.new_page()
    found: dict[str, str] = {}
    for ptype in TYPES:
        for op in OPS:
            url = f"https://www.argenprop.com/{ptype}/{op}/mar-del-plata"
            href_re = re.compile(rf"^/{ptype}/{op}/([a-z0-9-]+)$")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector("div.listing__item", timeout=10000)
                except Exception:
                    await page.wait_for_timeout(2000)
                links = await _collect_links(page)
                new = _filter(links, href_re)
                fresh = {k: v for k, v in new.items() if k not in found}
                found.update(fresh)
                print(f"  argenprop {ptype}/{op}: +{len(fresh)} (total {len(found)})")
            except Exception as e:
                print(f"  argenprop {ptype}/{op}: ERROR {e!r}", file=sys.stderr)
            await asyncio.sleep(random.uniform(2, 4))
    await ctx.close()
    return found


async def discover_zonaprop(browser) -> dict[str, str]:
    from playwright_stealth import stealth_async

    found: dict[str, str] = {}
    for ptype in TYPES:
        for op in OPS:
            url = f"https://www.zonaprop.com.ar/{ptype}-{op}-mar-del-plata.html"
            href_re = re.compile(rf"^/{ptype}-{op}-([a-z0-9-]+)\.html$")
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
            )
            page = await ctx.new_page()
            await stealth_async(page)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(6000)
                html = await page.content()
                if len(html) < 100_000 or "Un momento" in html[:5000]:
                    print(f"  zonaprop {ptype}/{op}: DataDome challenge, skipping", file=sys.stderr)
                else:
                    links = await _collect_links(page)
                    new = _filter(links, href_re)
                    fresh = {k: v for k, v in new.items() if k not in found}
                    found.update(fresh)
                    print(f"  zonaprop {ptype}/{op}: +{len(fresh)} (total {len(found)})")
            except Exception as e:
                print(f"  zonaprop {ptype}/{op}: ERROR {e!r}", file=sys.stderr)
            finally:
                await ctx.close()
            await asyncio.sleep(random.uniform(8, 14))
    return found


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal", choices=["argenprop", "zonaprop", "all"], default="all")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    result: dict[str, dict[str, str]] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        if args.portal in ("argenprop", "all"):
            result["argenprop"] = await discover_argenprop(browser)
            print(f"argenprop: {len(result['argenprop'])} barrio slugs")
        if args.portal in ("zonaprop", "all"):
            result["zonaprop"] = await discover_zonaprop(browser)
            print(f"zonaprop: {len(result['zonaprop'])} barrio slugs")
        await browser.close()

    out_file = OUT_DIR / "slug-candidates.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_file}")
    for portal, items in result.items():
        for slug, text in sorted(items.items()):
            print(f"  [{portal}] {slug:50s} {text[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
