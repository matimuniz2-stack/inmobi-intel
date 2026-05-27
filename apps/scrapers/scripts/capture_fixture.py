"""One-shot exploration: bypass ML challenge, capture real listings HTML."""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT_DIR = Path(__file__).parent / "tests" / "fixtures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://listado.mercadolibre.com.ar/inmuebles/venta/bs-as-costa-atlantica/mar-del-plata/_DisplayType_LF"


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
        )

        # Pre-seed the bypass cookie (5min validity)
        await context.add_cookies([
            {
                "name": "_bm_skipml",
                "value": "true",
                "domain": ".mercadolibre.com.ar",
                "path": "/",
            }
        ])

        page = await context.new_page()
        resp = await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        print(f"INITIAL status={resp.status if resp else None} url={page.url}")

        # If we hit the challenge, wait for navigation to complete
        for _ in range(30):
            await page.wait_for_timeout(1000)
            title = await page.title()
            html_len = len(await page.content())
            print(f"  title={title!r}  html_size={html_len}")
            if "ui-search" in await page.content() or html_len > 50000:
                print("  → looks like the real listings page!")
                break

        # Try common selectors
        sel_counts: dict[str, int] = {}
        for sel in [
            "li.ui-search-layout__item",
            ".ui-search-result",
            ".ui-search-result__wrapper",
            ".andes-card",
            "[data-testid]",
            "a.poly-component__title",
            "h2",
            "h3",
            ".poly-card",
            ".poly-component",
        ]:
            sel_counts[sel] = await page.locator(sel).count()
        print(f"SELECTOR COUNTS: {json.dumps(sel_counts, indent=2)}")

        # Save final HTML
        html = await page.content()
        html_path = OUT_DIR / "ml_mdp_venta_real.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"SAVED {len(html)} bytes to {html_path}")
        print(f"FINAL URL: {page.url}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
