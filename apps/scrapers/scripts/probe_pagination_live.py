"""Open ML listings page, scroll to pagination, dump 'next' link href."""

import asyncio
import sys
from playwright.async_api import async_playwright

URL = "https://listado.mercadolibre.com.ar/inmuebles/venta/bs-as-costa-atlantica/mar-del-plata/_DisplayType_LF"


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
        )
        await ctx.add_cookies([
            {"name": "_bm_skipml", "value": "true", "domain": ".mercadolibre.com.ar", "path": "/"}
        ])
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("li.ui-search-layout__item", timeout=30000)
        # Scroll to bottom (pagination is at the end)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

        # Find pagination
        candidates = [
            "li.andes-pagination__button--next a",
            "a.andes-pagination__link",
            ".ui-search-pagination a",
            "a[title*='Siguiente']",
            "a[rel='next']",
            "nav[aria-label*='paginación'] a",
        ]
        for sel in candidates:
            count = await page.locator(sel).count()
            if count > 0:
                hrefs = await page.locator(sel).evaluate_all("els => els.map(e => e.href)")
                print(f"sel={sel}  count={count}")
                for h in hrefs[:5]:
                    print(f"  → {h}")

        # First item on page 1
        first_link_p1 = await page.locator("a.poly-component__title").first.get_attribute("href")
        print(f"\nFIRST ITEM PAGE 1: {first_link_p1[:120] if first_link_p1 else 'NONE'}...")

        # CLICK the "next" button and see where we end up
        print("\n=== Clicking 'next' ===")
        try:
            next_btn = page.locator("li.andes-pagination__button--next a")
            await next_btn.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            print(f"After click, URL is: {page.url}")
            first_link_p2 = await page.locator("a.poly-component__title").first.get_attribute("href")
            print(f"FIRST ITEM PAGE 2: {first_link_p2[:120] if first_link_p2 else 'NONE'}...")
            print(f"Same as page 1? {first_link_p1 == first_link_p2}")
        except Exception as e:
            print(f"Click failed: {e!r}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
