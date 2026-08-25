"""Parse Properati (properati.com.ar) search result pages.

Properati renders cards server-side (`article.snippet`) and additionally embeds
a schema.org `SearchResultsPage` JSON-LD whose `about` array mirrors the cards
1:1 in order. The card carries id/url/price/agency; the JSON-LD contributes
street address and — unique among our portals — lat/lng coordinates, which fill
the map without geocoding.
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from parsel import Selector

from .models import Currency, MlListingCard, Operation, PropertyType


def _norm(s: str | None) -> str:
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


# Same TEMP_RENT refinement as Argenprop/ZonaProp: the scraper passes RENT and the
# title decides ("alquiler temporal/temporario/temporada"). \b avoids "contemporáneo".
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
    try:
        if "," in s and "." in s:
            return Decimal(s.replace(".", "").replace(",", "."))
        if "," in s:
            return Decimal(s.replace(",", "."))
        if "." in s:
            parts = s.split(".")
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]):
                return Decimal(s.replace(".", ""))
            return Decimal(s)
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


# "USD 124.800" | "U$S 92.000" | "$ 750.000" (pesos). "Consultar precio" → None.
_PRICE_RE = re.compile(r"(USD|U\$S|\$)\s*([\d.,]+)")


def _parse_price(text: str | None) -> tuple[Decimal, Currency] | None:
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    amount = _parse_decimal_es(m.group(2))
    if amount is None or amount <= 0:
        return None
    currency: Currency = "ARS" if m.group(1) == "$" else "USD"
    return amount, currency


def _first_int(text: str | None) -> int | None:
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else None


def _ld_listings(sel: Selector) -> list[dict[str, Any]]:
    """The SearchResultsPage JSON-LD `about` array, [] if absent/malformed."""
    raw = sel.css('script[type="application/ld+json"]::text').get()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if isinstance(data, list):
        data = next(
            (d for d in data if isinstance(d, dict) and d.get("@type") == "SearchResultsPage"),
            None,
        )
    if not isinstance(data, dict):
        return []
    about = data.get("about")
    return about if isinstance(about, list) else []


def _geo_from_ld(ld: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    geo = ld.get("geo") or {}
    try:
        lat = Decimal(str(geo["latitude"]))
        lng = Decimal(str(geo["longitude"]))
    except (KeyError, InvalidOperation, TypeError):
        return None, None
    # Guard against portal placeholder coords (0,0 is in the Gulf of Guinea)
    if lat == 0 and lng == 0:
        return None, None
    return lat, lng


def parse_listing_card(
    card: Selector,
    operation_type: Operation,
    property_type: PropertyType,
    ld: dict[str, Any] | None = None,
) -> MlListingCard | None:
    """Parse one `article.snippet`. `ld` is this card's JSON-LD twin (may be None)."""
    portal_id = (card.attrib.get("data-idanuncio") or "").strip()
    url = (card.attrib.get("data-url") or "").strip()
    if not portal_id or not url:
        return None

    price = _parse_price(card.css(".price::text").get())
    if price is None:
        return None
    price_amount, currency = price

    title = (card.css("a.title::text").get() or "").strip()
    # The photo alt carries the publisher's own title ("DUEÑO VENDE! 2 amb vista al
    # mar"), which beats Properati's generic "Apartamento en Venta en Barrio X" for
    # urgency-signal detection. "Foto N de <title>" → strip the prefix.
    alt = (card.css(".snippet__image img::attr(alt)").get() or "").strip()
    alt_title = re.sub(r"^Foto \d+ de ", "", alt)
    if alt_title and not alt_title.startswith("Foto"):
        title = alt_title or title
    title = title or f"Properati {portal_id}"

    # "Barrio La Armonía, Mar del Plata, Buenos Aires Costa Atlántica"
    location = (card.css(".location::text").get() or "").strip()
    parts = [p.strip() for p in location.split(",") if p.strip()]
    neighborhood = re.sub(r"^Barrio\s+", "", parts[0]) if parts else None
    city = parts[1] if len(parts) > 1 else None

    bedrooms = _first_int(card.css(".properties__bedrooms::text").get())
    bathrooms = _first_int(card.css(".properties__bathrooms::text").get())
    sqm = _parse_decimal_es(
        (card.css(".properties__area::text").get() or "").replace("m²", "").strip()
    )

    photo = card.css(".snippet__image img::attr(src)").get()
    photos = [photo] if photo and photo.startswith("http") else []

    agency = (card.css(".agency__name::text").get() or "").strip() or None

    address_full = None
    lat = lng = None
    if ld:
        addr = ld.get("address") or {}
        address_full = (addr.get("streetAddress") or "").strip() or None
        lat, lng = _geo_from_ld(ld)

    return MlListingCard(
        portal_id=portal_id,
        url=url,
        title=title,
        operation_type=_maybe_temp_rent(operation_type, title, url),
        property_type=property_type,
        price_amount=price_amount,
        price_currency=currency,
        address_full=address_full,
        neighborhood=neighborhood,
        city=city,
        province=None,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        total_sqm=sqm,
        covered_sqm=None,
        photos=photos,
        agency_name=agency,
        lat=lat,
        lng=lng,
    )


def parse_listing_page(
    html: str,
    operation_type: Operation,
    property_type: PropertyType,
) -> list[MlListingCard]:
    sel = Selector(html)
    cards = sel.css("article.snippet")
    lds = _ld_listings(sel)
    # The JSON-LD `about` array mirrors the cards in order; pair by index only
    # when the counts agree, otherwise skip the LD extras rather than risk
    # attaching another listing's coordinates.
    aligned: list[dict[str, Any] | None]
    if len(lds) == len(cards):
        aligned = cast("list[dict[str, Any] | None]", lds)
    else:
        aligned = [None] * len(cards)

    out: list[MlListingCard] = []
    for card, ld in zip(cards, aligned, strict=True):
        parsed = parse_listing_card(card, operation_type, property_type, ld)
        if parsed is not None:
            out.append(parsed)
    return out


def detect_total_results(html: str) -> int | None:
    """Parse the portal's own total ('9.158 resultados') for the coverage KPI."""
    m = re.search(r"([\d.,]+)\s*resultados", html)
    if not m:
        return None
    n = _parse_decimal_es(m.group(1))
    return int(n) if n is not None else None
