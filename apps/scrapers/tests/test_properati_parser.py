"""Tests for the Properati parser. Run when Properati changes their HTML."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scrapers.properati_parser import (
    _parse_price,
    detect_total_results,
    parse_listing_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
SALE_HTML = FIXTURES / "properati_mdp_dpto_venta.html"
RENT_HTML = FIXTURES / "properati_mdp_dpto_alquiler.html"


def test_parse_price():
    assert _parse_price("USD 124.800") == (Decimal("124800"), "USD")
    assert _parse_price("U$S 92.000") == (Decimal("92000"), "USD")
    assert _parse_price("$ 750.000") == (Decimal("750000"), "ARS")
    assert _parse_price("Consultar precio") is None
    assert _parse_price(None) is None


@pytest.mark.skipif(not SALE_HTML.exists(), reason="fixture not captured")
def test_parse_sale_page_yields_cards():
    html = SALE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    assert len(cards) >= 25, f"only parsed {len(cards)} cards"
    first = cards[0]
    assert first.portal_id
    assert first.url.startswith("https://www.properati.com.ar/detalle/")
    assert first.title
    assert first.price_amount > 0
    assert first.price_currency in ("USD", "ARS")
    # Location "Barrio X, Mar del Plata, ..." → neighborhood without the prefix
    assert first.neighborhood and not first.neighborhood.startswith("Barrio ")
    assert first.city == "Mar del Plata"


@pytest.mark.skipif(not SALE_HTML.exists(), reason="fixture not captured")
def test_jsonld_geo_alignment():
    """The JSON-LD twin array must contribute lat/lng + street address to cards."""
    html = SALE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    with_geo = [c for c in cards if c.lat is not None and c.lng is not None]
    # Not every listing is geolocated, but an aligned page yields a majority
    assert len(with_geo) >= len(cards) // 2, f"only {len(with_geo)}/{len(cards)} with geo"
    for c in with_geo:
        # MdP bounding box, sanity check that coordinates are plausible
        assert Decimal("-39") < c.lat < Decimal("-37"), c.lat
        assert Decimal("-59") < c.lng < Decimal("-56"), c.lng


@pytest.mark.skipif(not RENT_HTML.exists(), reason="fixture not captured")
def test_parse_rent_page_ars_prices():
    html = RENT_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="RENT", property_type="APT")
    assert len(cards) >= 15
    assert any(c.price_currency == "ARS" for c in cards)
    # Rent pages mix permanent and temporary listings; RENT must survive as
    # the default (TEMP_RENT only on textual evidence)
    assert any(c.operation_type == "RENT" for c in cards)


@pytest.mark.skipif(not SALE_HTML.exists(), reason="fixture not captured")
def test_detect_total_results():
    html = SALE_HTML.read_text(encoding="utf-8")
    total = detect_total_results(html)
    assert total is not None and total > 1000, total
