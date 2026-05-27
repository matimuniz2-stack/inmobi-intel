"""Tests for the ML listings parser. Run when ML changes their HTML."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scrapers.parser import (
    _parse_decimal_es,
    _parse_operation,
    _parse_portal_id,
    _parse_property_type,
    parse_listing_card,
    parse_listing_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "ml_mdp_venta_real.html"


# ---------- unit tests on private helpers ----------

def test_parse_property_type():
    assert _parse_property_type("Departamento en venta") == "APT"
    assert _parse_property_type("Casa en venta") == "HOUSE"
    assert _parse_property_type("PH en alquiler") == "PH"
    assert _parse_property_type("Local en alquiler") == "LOCAL"
    assert _parse_property_type("Terreno en venta") == "TERRENO"
    assert _parse_property_type("Lote en venta") == "TERRENO"
    assert _parse_property_type("Cochera en alquiler") == "OTRO"
    assert _parse_property_type("Algo raro") == "OTRO"


def test_parse_operation():
    assert _parse_operation("Departamento en venta") == "SALE"
    assert _parse_operation("Casa en alquiler") == "RENT"
    assert _parse_operation("Departamento en alquiler temporario") == "TEMP_RENT"
    assert _parse_operation("PH en venta") == "SALE"


def test_parse_decimal_es():
    assert _parse_decimal_es("120") == Decimal("120")
    assert _parse_decimal_es("1.234") == Decimal("1234")  # thousands
    assert _parse_decimal_es("1.234,56") == Decimal("1234.56")  # thousands + decimal
    assert _parse_decimal_es("12,5") == Decimal("12.5")
    assert _parse_decimal_es("1.234.567") == Decimal("1234567")
    assert _parse_decimal_es("not a number") is None
    assert _parse_decimal_es("") is None


def test_parse_portal_id():
    assert _parse_portal_id("https://x.com/MLA-1234567890-foo-bar") == "MLA1234567890"
    assert _parse_portal_id("https://x.com/MLA1234567890-foo") == "MLA1234567890"
    assert _parse_portal_id("https://x.com/no-id") is None


# ---------- integration with captured HTML fixture ----------

@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_parse_real_page_yields_cards():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html)
    # Real ML page should have ~48 results per page
    assert len(cards) >= 30, f"only parsed {len(cards)} cards, ML may have changed HTML"

    # First card sanity checks
    first = cards[0]
    assert first.portal_id.startswith("MLA")
    assert first.url.startswith("https://")
    assert first.title
    assert first.price_amount > 0
    assert first.price_currency in ("USD", "ARS")
    assert first.operation_type in ("SALE", "RENT", "TEMP_RENT")
    assert first.property_type in ("APT", "HOUSE", "PH", "LOCAL", "TERRENO", "OTRO")


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_has_addresses_and_agencies():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html)
    with_location = [c for c in cards if c.city or c.neighborhood]
    with_agency = [c for c in cards if c.agency_name]
    # Most listings should have location info, and many should have an agency
    assert len(with_location) >= len(cards) * 0.7, "most listings lack location"
    assert len(with_agency) >= len(cards) * 0.3, "few listings have agency info — selector may be off"


@pytest.mark.skipif(not SAMPLE_HTML.exists(), reason="fixture not captured")
def test_real_page_attributes_parse():
    html = SAMPLE_HTML.read_text(encoding="utf-8")
    cards = parse_listing_page(html)
    with_bedrooms = [c for c in cards if c.bedrooms is not None]
    with_sqm = [c for c in cards if c.total_sqm is not None or c.covered_sqm is not None]
    # Most listings have at least bedrooms; sqm is sometimes missing for "lote"/"campo"
    assert len(with_bedrooms) >= len(cards) * 0.6
    assert len(with_sqm) >= len(cards) * 0.5
