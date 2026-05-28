"""Find ML's pagination URL format from the fixture HTML."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from parsel import Selector

html = open("tests/fixtures/ml_mdp_venta_real.html", encoding="utf-8").read()
sel = Selector(html)

print("=== Pagination links (andes-pagination) ===")
for a in sel.css(".andes-pagination a::attr(href)").getall()[:10]:
    print("  ", a)

print()
print("=== Any URL with Desde / From ===")
seen = set()
for a in sel.css("a::attr(href)").getall():
    if ("Desde" in a or "_From_" in a) and a not in seen:
        seen.add(a)
        print("  ", a)
        if len(seen) >= 8:
            break

print()
print(f"Total anchor tags: {len(sel.css('a::attr(href)').getall())}")
