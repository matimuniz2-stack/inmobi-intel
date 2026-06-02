"""Parse ZonaProp listing cards.

ZonaProp uses `data-qa` attributes for stable selectors. The card root is
`[data-qa='posting PROPERTY']` with `data-id` and `data-to-posting`.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import cast

from parsel import Selector

from .models import Currency, MlListingCard, Operation, PropertyType


def _norm(s: str | None) -> str:
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


# Un alquiler temporario es otro mercado (enorme en MdP de verano). El scraper pasa
# RENT fijo; lo refinamos a TEMP_RENT si el texto/URL lo delata. \b evita "contemporáneo".
_TEMP_RENT_RE = re.compile(r"\btempora")


def _maybe_temp_rent(operation_type: Operation, *texts: str | None) -> Operation:
    if operation_type != "RENT":
        return operation_type
    blob = _norm(" ".join(t for t in texts if t))
    return "TEMP_RENT" if _TEMP_RENT_RE.search(blob) else operation_type


def _parse_decimal_es(num_str: str | None) -> Decimal | None:
    s = (num_str or "").strip()
    if not s:
        return None
    has_dot = "." in s
    has_comma = "," in s
    try:
        if has_comma and has_dot:
            return Decimal(s.replace(".", "").replace(",", "."))
        if has_comma:
            return Decimal(s.replace(",", "."))
        if has_dot:
            parts = s.split(".")
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]):
                return Decimal(s.replace(".", ""))
            return Decimal(s)
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_price(text: str) -> tuple[Decimal, Currency] | None:
    """Parse 'USD 85.000' or '$ 1.500.000' into (amount, currency)."""
    t = text.strip()
    if not t or "Consultar" in t.lower():
        return None
    currency: Currency = "ARS"
    if "USD" in t or "U$S" in t.upper() or "U$D" in t.upper():
        currency = "USD"
    m = re.search(r"([\d.,]+)", t)
    if not m:
        return None
    amount = _parse_decimal_es(m.group(1))
    if amount is None or amount <= 0:
        return None
    return amount, currency


def _parse_features(text: str) -> dict:
    """Parse 'X m² tot.', 'X m² cub.', 'N amb.', 'N dorm.', 'N baño(s)'."""
    result: dict = {
        "bedrooms": None,
        "bathrooms": None,
        "total_sqm": None,
        "covered_sqm": None,
    }
    # Each feature is in its own span; text concatenates them. Split by m²/amb/dorm/bañ.
    # We just regex over the whole string.
    for m in re.finditer(
        r"(\d+(?:[.,]\d+)?)\s*(m²\s*tot\.?|m²\s*cub\.?|m²|amb\.?|amb|dorm\.?|dormitorios?|baño?s?)",
        text,
        re.IGNORECASE,
    ):
        n_str, label = m.group(1), m.group(2).lower()
        n = _parse_decimal_es(n_str)
        if n is None:
            continue
        if "tot" in label:
            result["total_sqm"] = n
        elif "cub" in label:
            result["covered_sqm"] = n
        elif label.startswith("m"):
            # Bare m² — assume total if no qualifier yet
            if result["total_sqm"] is None:
                result["total_sqm"] = n
        elif "amb" in label:
            result["bedrooms"] = int(n)
        elif "dorm" in label and result["bedrooms"] is None:
            result["bedrooms"] = int(n)
        elif "ba" in label:
            result["bathrooms"] = int(n)
    return result


def _split_location(text: str) -> tuple[str | None, str | None]:
    """Split 'Macrocentro, Mar del Plata' into (neighborhood, city)."""
    if not text:
        return None, None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return None, parts[0]
    return None, None


def parse_listing_card(
    card_html: str,
    operation_type: Operation,
    property_type: PropertyType,
) -> MlListingCard | None:
    sel = Selector(card_html)
    root = sel.css("[data-qa='posting PROPERTY']")
    if not root:
        return None

    portal_id = root.attrib.get("data-id", "")
    href = root.attrib.get("data-to-posting", "") or ""
    if not portal_id or not href:
        return None
    url = "https://www.zonaprop.com.ar" + href if href.startswith("/") else href
    # Strip query string for cleaner storage / dedupe
    url = url.split("?", 1)[0]

    price_text = sel.css("[data-qa='POSTING_CARD_PRICE']::text").get() or ""
    price_pair = _parse_price(price_text)
    if price_pair is None:
        return None
    price_amount, price_currency = price_pair

    loc_text = sel.css("[data-qa='POSTING_CARD_LOCATION']::text").get() or ""
    neighborhood, city = _split_location(loc_text)

    # Optional address line (under location)
    address = sel.css(".postingLocations-module__location-address::text").get()
    address = address.strip() if address else None

    features_text = " ".join(sel.css("[data-qa='POSTING_CARD_FEATURES'] span::text").getall())
    feats = _parse_features(features_text)

    title = (
        sel.css("[data-qa='POSTING_CARD_DESCRIPTION'] a::text").get()
        or sel.css("img::attr(alt)").get()
        or f"ZonaProp {portal_id}"
    ).strip()

    photo = sel.css("img::attr(src)").get()
    photos = [photo] if photo and photo.startswith("http") else []

    agency = (
        sel.css("[data-qa='POSTING_CARD_PUBLISHER'] img::attr(alt)").get()
        or sel.css(".postingPublisher-module__publisher-name::text").get()
    )
    agency = agency.strip() if agency else None

    return MlListingCard(
        portal_id=str(portal_id),
        url=url,
        title=title,
        operation_type=_maybe_temp_rent(operation_type, title, url),
        property_type=property_type,
        price_amount=price_amount,
        price_currency=cast(Currency, price_currency),
        address_full=address,
        neighborhood=neighborhood,
        city=city,
        province=None,
        photos=photos,
        agency_name=agency,
        **feats,
    )


def parse_listing_page(
    html: str,
    operation_type: Operation,
    property_type: PropertyType,
) -> list[MlListingCard]:
    sel = Selector(html)
    cards = sel.css("[data-qa='posting PROPERTY']")
    out: list[MlListingCard] = []
    for c in cards:
        parsed = parse_listing_card(c.get(), operation_type, property_type)
        if parsed is not None:
            out.append(parsed)
    return out


def detect_total_results(html: str) -> int | None:
    """Parse 'N.NNN Departamentos en venta' from the page title or h1."""
    sel = Selector(html)
    for q in ("h1::text", "title::text"):
        t = sel.css(q).get()
        if not t:
            continue
        m = re.search(r"([\d.,]+)\s+(?:Departamentos?|Casas?|PHs?|Terrenos?|Locales?)", t)
        if m:
            n = _parse_decimal_es(m.group(1))
            if n is not None:
                return int(n)
    return None
