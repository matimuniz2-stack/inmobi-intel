"""Tests for the Argenprop parser. Run when Argenprop changes their HTML."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scrapers.argenprop_parser import (
    _neighborhood_from_url,
    _parse_decimal_es,
    parse_listing_card,
    parse_listing_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "argenprop_mdp_dpto_venta.html"


def test_neighborhood_from_url():
    cases = [
        ("https://www.argenprop.com/departamento-en-venta-en-plaza-colon-2-ambientes--19559383", "Plaza Colon"),
        ("https://www.argenprop.com/departamento-en-venta-en-mar-del-plata-1-ambiente--19531379", "Mar Del Plata"),
        ("https://www.argenprop.com/departamento-en-venta-en-zona-guemes-4-ambientes--19681137", "Zona Guemes"),
        ("https://www.argenprop.com/departamento-en-venta-en-mar-del-plata--19209572", "Mar Del Plata"),
    ]
    for url, expected in cases:
        assert _neighborhood_from_url(url) == expected, url


def test_parse_decimal_es():
    assert _parse_decimal_es("85000") == Decimal("85000")
    assert _parse_decimal_es("1.500.000") == Decimal("1500000")
    assert _parse_decimal_es("1.500,50") == Decimal("1500.50")
    assert _parse_decimal_es(None) is None
    assert _parse_decimal_es("") is None


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_parse_real_page_yields_cards():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    assert len(cards) >= 15, f"only parsed {len(cards)} cards"
    first = cards[0]
    assert first.portal_id
    assert first.url.startswith("https://www.argenprop.com")
    assert first.title
    assert first.price_amount > 0
    assert first.price_currency in ("USD", "ARS")
    assert first.operation_type == "SALE"
    assert first.property_type == "APT"


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_attributes_parse():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    with_bedrooms = [c for c in cards if c.bedrooms is not None]
    with_sqm = [c for c in cards if c.covered_sqm is not None or c.total_sqm is not None]
    assert len(with_bedrooms) >= len(cards) * 0.7
    assert len(with_sqm) >= len(cards) * 0.6


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_has_neighborhoods():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html, operation_type="SALE", property_type="APT")
    with_nh = [c for c in cards if c.neighborhood]
    # All Argenprop URLs include a location slug we extract as neighborhood
    assert len(with_nh) >= len(cards) * 0.9
