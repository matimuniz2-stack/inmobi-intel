"""Tests del mapeo de la API oficial de ML (lo único verificable offline sin creds)."""

from __future__ import annotations

from decimal import Decimal

from scrapers.mercadolibre_api import (
    _map_operation,
    _map_property_type,
    _parse_area,
    map_search_item,
)


def _item(**over):
    base = {
        "id": "MLA123456789",
        "title": "Departamento 3 ambientes en Playa Grande",
        "price": 125000,
        "currency_id": "USD",
        "permalink": "https://departamento.mercadolibre.com.ar/MLA-123456789-depto#track",
        "thumbnail": "http://http2.mlstatic.com/D_NQ_123-O.jpg",
        "seller": {"id": 99, "nickname": "INMOBILIARIA RUGER"},
        "seller_address": {
            "address_line": "Alem 1234",
            "neighborhood": {"name": "Playa Grande"},
            "city": {"name": "Mar del Plata"},
            "state": {"name": "Buenos Aires"},
            "latitude": -38.01,
            "longitude": -57.53,
        },
        "attributes": [
            {"id": "PROPERTY_TYPE", "value_name": "Departamento"},
            {"id": "OPERATION", "value_name": "Venta"},
            {"id": "ROOMS", "value_name": "3"},
            {"id": "BEDROOMS", "value_name": "2"},
            {"id": "FULL_BATHROOMS", "value_name": "1"},
            {"id": "COVERED_AREA", "value_name": "50 m²"},
            {"id": "TOTAL_AREA", "value_name": "55 m²"},
        ],
    }
    base.update(over)
    return base


def test_map_search_item_full():
    card = map_search_item(_item())
    assert card is not None
    assert card.portal_id == "MLA123456789"
    assert card.url.endswith("depto")  # se cortó el #track
    assert card.price_amount == Decimal("125000")
    assert card.price_currency == "USD"
    assert card.property_type == "APT"
    assert card.operation_type == "SALE"
    assert card.bedrooms == 3  # ROOMS (ambientes), convención actual
    assert card.bathrooms == 1
    assert card.covered_sqm == Decimal("50")
    assert card.total_sqm == Decimal("55")
    assert card.neighborhood == "Playa Grande"
    assert card.city == "Mar del Plata"
    assert card.province == "Buenos Aires"
    assert card.agency_name == "INMOBILIARIA RUGER"
    assert card.photos == ["https://http2.mlstatic.com/D_NQ_123-O.jpg"]  # http→https


def test_map_search_item_temp_rent():
    item = _item(attributes=[
        {"id": "PROPERTY_TYPE", "value_name": "Departamento"},
        {"id": "OPERATION", "value_name": "Alquiler temporal"},
    ])
    card = map_search_item(item)
    assert card is not None and card.operation_type == "TEMP_RENT"


def test_map_search_item_rejects_missing_essentials():
    assert map_search_item(_item(price=None)) is None
    assert map_search_item(_item(permalink=None)) is None
    assert map_search_item({"id": "MLA1"}) is None


def test_map_search_item_ars_and_no_area():
    item = _item(currency_id="ARS", price=85000000, attributes=[
        {"id": "PROPERTY_TYPE", "value_name": "Casa"},
        {"id": "OPERATION", "value_name": "Alquiler"},
    ])
    card = map_search_item(item)
    assert card is not None
    assert card.price_currency == "ARS"
    assert card.property_type == "HOUSE"
    assert card.operation_type == "RENT"
    assert card.covered_sqm is None and card.bedrooms is None


def test_helpers():
    assert _map_property_type("PH") == "PH"
    assert _map_property_type("Local comercial") == "LOCAL"
    assert _map_operation("Alquiler") == "RENT"
    assert _map_operation("Venta") == "SALE"
    assert _parse_area("50,5 m²") == Decimal("50.5")
    assert _parse_area(None) is None
