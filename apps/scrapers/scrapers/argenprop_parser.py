"""Parse Argenprop listing cards.

Argenprop's frontend renders cards server-side and embeds rich metadata in
the `<a class="card" data-*>` attributes (portal id, price, currency id,
dormitorios, ambientes). We mostly rely on those — selectors are stable.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import cast

from parsel import Selector

from .models import Currency, MlListingCard, Operation, PropertyType

# Argenprop's idmoneda values
_CURRENCY_MAP: dict[str, Currency] = {"1": "ARS", "2": "USD"}


def _norm(s: str | None) -> str:
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


# "temporal", "temporario/a", "temporada" — un alquiler temporario es un mercado de
# magnitud distinta al permanente (enorme en MdP de verano). El scraper pasa RENT fijo;
# acá lo refinamos a TEMP_RENT si el texto/URL lo delata. \b evita "contemporáneo".
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


def _parse_attributes(sel: Selector) -> dict:
    """Parse .card__main-features li for ambientes, baños, m²."""
    result: dict = {
        "bedrooms": None,
        "bathrooms": None,
        "total_sqm": None,
        "covered_sqm": None,
    }
    for li in sel.css(".card__main-features li"):
        icon = li.css("i::attr(class)").get() or ""
        text = " ".join(li.css("span ::text").getall()).strip()
        m = re.search(r"(\d+[\.,]?\d*)", text)
        if not m:
            continue
        n = _parse_decimal_es(m.group(1))
        if n is None:
            continue
        if "superficie_cubierta" in icon:
            result["covered_sqm"] = n
        elif "superficie_total" in icon:
            result["total_sqm"] = n
        elif "cantidad_ambientes" in icon:
            result["bedrooms"] = int(n)
        elif "cantidad_dormitorios" in icon and result["bedrooms"] is None:
            # Fallback: use dormitorios if ambientes not present
            result["bedrooms"] = int(n)
        elif "cantidad_banos" in icon:
            result["bathrooms"] = int(n)
    return result


_NEIGHBORHOOD_URL_RE = re.compile(
    r"/(?:departamento|casa|ph|local|terreno|oficina)-en-(?:venta|alquiler)-en-"
    r"([\w-]+?)(?:-\d+-(?:ambientes?|dormitorios?|amb))?--\d+"
)


def _neighborhood_from_url(url: str) -> str | None:
    m = _NEIGHBORHOOD_URL_RE.search(url)
    if not m:
        return None
    slug = m.group(1)
    # Title-case from kebab-case: "plaza-colon" → "Plaza Colon"
    return slug.replace("-", " ").title()


def parse_listing_card(
    card_html: str,
    operation_type: Operation,
    property_type: PropertyType,
) -> MlListingCard | None:
    """Parse one Argenprop card. Returns None if parsing fails."""
    sel = Selector(card_html)
    a = sel.css("a.card")
    if not a:
        return None

    href = a.attrib.get("href", "")
    if not href:
        return None
    url = "https://www.argenprop.com" + href if href.startswith("/") else href

    portal_id = (
        a.attrib.get("data-item-card")
        or a.attrib.get("idaviso")
        or ""
    )
    if not portal_id:
        m = re.search(r"--(\d+)(?:[#?].*)?$", url)
        if m:
            portal_id = m.group(1)
    if not portal_id:
        return None

    monto = a.attrib.get("montonormalizado", "")
    moneda_id = a.attrib.get("idmoneda", "")
    price_amount = _parse_decimal_es(monto)
    if price_amount is None or price_amount <= 0:
        return None
    currency: Currency = _CURRENCY_MAP.get(moneda_id, "ARS")

    title = (sel.css(".card__title::text").get() or "").strip()
    if not title:
        title = (sel.css("img::attr(alt)").get() or "").strip()
    title = title or f"Argenprop {portal_id}"

    address = (sel.css(".card__address::text").get() or "").strip() or None
    neighborhood = _neighborhood_from_url(url)

    attrs = _parse_attributes(sel)
    if attrs["bedrooms"] is None:
        try:
            d = int(a.attrib.get("dormitorios") or 0)
            attrs["bedrooms"] = d or None
        except (ValueError, TypeError):
            pass
    if attrs["bedrooms"] is None:
        # Fallback: parse "N-ambiente(s)" out of the slug (e.g. "...-2-ambientes--ID")
        m = re.search(r"-(\d+)-ambiente", url)
        if m:
            attrs["bedrooms"] = int(m.group(1))
        elif "mono-ambiente" in url.lower() or "monoambiente" in url.lower():
            attrs["bedrooms"] = 1

    # Photo: prefer the eager-loaded src; fall back to data-src
    photo = sel.css(".card__photos img::attr(src)").get()
    if not photo or photo.startswith("/content/"):
        photo = sel.css(".card__photos img::attr(data-src)").get() or photo
    photos = [photo] if photo and photo.startswith("http") else []

    # Agency: the publisher logo's alt text carries the inmobiliaria name
    # ("Ruger Negocios Inmobiliarios", "Vidigh Propiedades", ...). Identifying who
    # holds each listing is the core of the reverse search — before this it was
    # always None for Argenprop.
    agency = (sel.css(".card__agent img::attr(alt)").get() or "").strip() or None

    return MlListingCard(
        portal_id=str(portal_id),
        url=url,
        title=title,
        operation_type=_maybe_temp_rent(operation_type, title, url),
        property_type=property_type,
        price_amount=price_amount,
        price_currency=cast(Currency, currency),
        address_full=address,
        neighborhood=neighborhood,
        city=None,
        province=None,
        photos=photos,
        agency_name=agency,
        **attrs,
    )


def parse_listing_page(
    html: str,
    operation_type: Operation,
    property_type: PropertyType,
) -> list[MlListingCard]:
    sel = Selector(html)
    cards = sel.css("div.listing__item")
    out: list[MlListingCard] = []
    for c in cards:
        parsed = parse_listing_card(c.get(), operation_type, property_type)
        if parsed is not None:
            out.append(parsed)
    return out
