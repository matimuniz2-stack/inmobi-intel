"""Tests for the ZonaProp parser."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scrapers.zonaprop_parser import (
    _parse_decimal_es,
    _parse_features,
    _parse_price,
    _split_location,
    detect_total_results,
    parse_listing_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "zonaprop_mdp_dpto_venta.html"


def test_parse_price():
    assert _parse_price("USD 85.000") == (Decimal("85000"), "USD")
    assert _parse_price("$ 1.500.000") == (Decimal("1500000"), "ARS")
    assert _parse_price("USD 250.000") == (Decimal("250000"), "USD")
    assert _parse_price("Consultar") is None
    assert _parse_price("") is None


def test_split_location():
    assert _split_location("Macrocentro, Mar del Plata") == ("Macrocentro", "Mar del Plata")
    assert _split_location("Centro, Mar del Plata, Buenos Aires") == ("Centro", "Mar del Plata")
    assert _split_location("Mar del Plata") == (None, "Mar del Plata")
    assert _split_location("") == (None, None)


def test_parse_features():
    feats = _parse_features("51 m² tot. 2 amb. 1 dorm. 1 baño")
    assert feats["total_sqm"] == Decimal("51")
    assert feats["bedrooms"] == 2
    assert feats["bathrooms"] == 1

    feats = _parse_features("100 m² cub. 3 amb. 2 baños")
    assert feats["covered_sqm"] == Decimal("100")
    assert feats["bedrooms"] == 3
    assert feats["bathrooms"] == 2


def test_parse_decimal_es():
    assert _parse_decimal_es("85000") == Decimal("85000")
    assert _parse_decimal_es("1.500.000") == Decimal("1500000")
    assert _parse_decimal_es("1.500,50") == Decimal("1500.50")


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_parse_real_page_yields_cards():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    assert len(cards) >= 20, f"only parsed {len(cards)} cards"
    first = cards[0]
    assert first.portal_id
    assert first.url.startswith("https://www.zonaprop.com.ar")
    assert first.title
    assert first.price_amount > 0
    assert first.price_currency in ("USD", "ARS")


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_attributes_parse():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    with_bedrooms = [c for c in cards if c.bedrooms is not None]
    with_sqm = [c for c in cards if c.covered_sqm is not None or c.total_sqm is not None]
    assert len(with_bedrooms) >= len(cards) * 0.7
    assert len(with_sqm) >= len(cards) * 0.7


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_has_locations():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    with_loc = [c for c in cards if c.city or c.neighborhood]
    assert len(with_loc) >= len(cards) * 0.9


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_detect_total_results():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    total = detect_total_results(html)
    assert total is not None and total > 1000
