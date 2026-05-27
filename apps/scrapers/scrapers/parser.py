"""Parse MercadoLibre listing cards from search results HTML.

Pure functions, no I/O. Easy to test with HTML fixtures.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import cast

from parsel import Selector

from .models import Currency, MlListingCard, Operation, PropertyType

_PROPERTY_TYPE_MAP: dict[str, PropertyType] = {
    "departamento": "APT",
    "casa": "HOUSE",
    "ph": "PH",
    "local": "LOCAL",
    "oficina": "LOCAL",
    "deposito": "LOCAL",
    "galpon": "LOCAL",
    "terreno": "TERRENO",
    "lote": "TERRENO",
    "quinta": "TERRENO",
    "campo": "TERRENO",
    "cochera": "OTRO",
}


def _norm(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def _parse_property_type(headline: str) -> PropertyType:
    n = _norm(headline)
    for kw, ptype in _PROPERTY_TYPE_MAP.items():
        if kw in n:
            return ptype
    return "OTRO"


def _parse_operation(headline: str) -> Operation:
    n = _norm(headline)
    if "alquiler temporario" in n or "temporal" in n:
        return "TEMP_RENT"
    if "alquiler" in n:
        return "RENT"
    if "venta" in n:
        return "SALE"
    return "SALE"


def _parse_decimal_es(num_str: str) -> Decimal | None:
    """Parse Spanish-locale numbers: '1.234' = 1234, '1.234,5' = 1234.5, '120' = 120."""
    s = (num_str or "").strip()
    if not s:
        return None
    has_dot = "." in s
    has_comma = "," in s
    try:
        if has_comma and has_dot:
            # Decimal comma, thousands dot: "1.234,56"
            return Decimal(s.replace(".", "").replace(",", "."))
        if has_comma:
            return Decimal(s.replace(",", "."))
        if has_dot:
            parts = s.split(".")
            # Heuristic: if exactly one dot AND the right side is 3 digits → thousands separator
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]):
                return Decimal(s.replace(".", ""))
            return Decimal(s)
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_price(card_sel: Selector) -> tuple[Decimal, Currency] | None:
    # Use the FIRST price block (the current price); skip discount struck-through prices.
    price_block = card_sel.css(".poly-price__current").css(".andes-money-amount").get()
    if not price_block:
        return None
    pb = Selector(price_block)
    symbol = (pb.css(".andes-money-amount__currency-symbol::text").get() or "").strip()
    fraction_raw = pb.css(".andes-money-amount__fraction::text").get() or ""
    cents_raw = pb.css(".andes-money-amount__cents::text").get() or ""
    amount = _parse_decimal_es(fraction_raw)
    if amount is None:
        return None
    if cents_raw and cents_raw != "0":
        cents_dec = _parse_decimal_es(cents_raw)
        if cents_dec is not None and cents_dec < 100:
            amount += cents_dec / Decimal(100)
    currency: Currency = "USD" if symbol in ("US$", "USD", "U$S") else "ARS"
    return amount, currency


def _parse_portal_id(url: str) -> str | None:
    m = re.search(r"(MLA-?\d+)", url)
    if not m:
        return None
    return m.group(1).replace("-", "")


def _looks_like_address(s: str) -> bool:
    """Returns True if a location fragment looks like a street address."""
    low = s.lower()
    if any(kw in low for kw in ("calle ", "av. ", "avenida ", "ruta ", "diagonal ", " al ")):
        return True
    if re.search(r"\b\d{2,5}\b", s):
        return True
    return False


def _parse_attributes(card_sel: Selector) -> dict:
    """Parse the attributes list (ambientes, baños, m²)."""
    result: dict = {
        "bedrooms": None,
        "bathrooms": None,
        "total_sqm": None,
        "covered_sqm": None,
    }
    items = card_sel.css(".poly-attributes_list__item::text").getall()
    for raw in items:
        text = _norm(raw)
        if "amb" in text:
            m = re.search(r"(\d+)", text)
            if m:
                result["bedrooms"] = int(m.group(1))
        elif "bano" in text:  # "baño" normalized → "bano"
            m = re.search(r"(\d+)", text)
            if m:
                result["bathrooms"] = int(m.group(1))
        elif "m" in text and ("²" in raw or "2" in text):
            m = re.search(r"([\d.,]+)", text)
            if not m:
                continue
            v = _parse_decimal_es(m.group(1))
            if v is None:
                continue
            if "cub" in text:
                result["covered_sqm"] = v
            elif "tot" in text:
                result["total_sqm"] = v
            else:
                # Default unspecified to total
                if result["total_sqm"] is None:
                    result["total_sqm"] = v
    return result


def parse_listing_card(card_html: str) -> MlListingCard | None:
    """Parse a single listing card. Returns None if the card can't be parsed safely."""
    sel = Selector(card_html)

    title_a = sel.css("a.poly-component__title")
    if not title_a:
        return None
    url = title_a.attrib.get("href", "")
    title = (title_a.css("::text").get() or "").strip()
    if not url or not title:
        return None

    clean_url = url.split("#")[0]
    portal_id = _parse_portal_id(clean_url)
    if not portal_id:
        return None

    headline = (sel.css(".poly-component__headline::text").get() or "").strip()
    if not headline:
        # Fall back to title for type inference
        headline = title

    price_pair = _parse_price(sel)
    if price_pair is None:
        return None  # listings without price aren't useful for our search
    price_amount, price_currency = price_pair

    location = (sel.css(".poly-component__location::text").get() or "").strip()
    location_parts = [p.strip() for p in location.split(",")] if location else []

    address_full: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    province: str | None = None
    if len(location_parts) == 4:
        address_full, neighborhood, city, province = location_parts
    elif len(location_parts) == 3:
        # Ambiguous: "address, city, province" OR "neighborhood, city, province"
        if _looks_like_address(location_parts[0]):
            address_full, city, province = location_parts
        else:
            neighborhood, city, province = location_parts
    elif len(location_parts) == 2:
        city, province = location_parts
    elif len(location_parts) == 1:
        city = location_parts[0]

    attrs = _parse_attributes(sel)
    photo = sel.css("img.poly-component__picture::attr(src)").get()
    photos = [photo] if photo else []

    agency_raw = sel.css(".poly-component__seller").xpath("string()").get()
    agency = agency_raw.strip() if agency_raw else None
    if agency == "":
        agency = None

    return MlListingCard(
        portal_id=portal_id,
        url=clean_url,
        title=title,
        operation_type=_parse_operation(headline),
        property_type=cast(PropertyType, _parse_property_type(headline)),
        price_amount=price_amount,
        price_currency=price_currency,
        address_full=address_full,
        neighborhood=neighborhood,
        city=city,
        province=province,
        photos=photos,
        agency_name=agency,
        **attrs,
    )


def parse_listing_page(html: str) -> list[MlListingCard]:
    """Parse all listing cards from a search results page HTML."""
    sel = Selector(html)
    cards = sel.css("li.ui-search-layout__item")
    out: list[MlListingCard] = []
    for c in cards:
        parsed = parse_listing_card(c.get())
        if parsed is not None:
            out.append(parsed)
    return out


def detect_total_results(html: str) -> int | None:
    """Try to extract the total result count shown on the page (best effort)."""
    sel = Selector(html)
    for sel_str in (
        ".ui-search-search-result__quantity-results::text",
        ".ui-search-search-result__quantity-results",
    ):
        txt = sel.css(sel_str).xpath("string()").get()
        if txt:
            m = re.search(r"([\d.]+)", txt)
            if m:
                dec = _parse_decimal_es(m.group(1))
                if dec is not None:
                    return int(dec)
    return None
