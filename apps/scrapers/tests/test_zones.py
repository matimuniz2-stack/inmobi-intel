"""Sanity tests for zones.json loading from shared-types."""

from __future__ import annotations

from scrapers.config import get_zone, load_zones


def test_load_zones_returns_all_52():
    zones = load_zones()
    assert len(zones) == 52, f"expected 52 zones, got {len(zones)}"


def test_zone_fields_required():
    zones = load_zones()
    for z in zones:
        assert z.get("slug"), f"zone missing slug: {z}"
        assert z.get("displayName")
        assert z.get("province") in ("Buenos Aires", "CABA")
        assert z.get("mlState")
        assert z.get("mlCity")
        # Resolved IDs (M2)
        assert z.get("mlStateId"), f"unresolved mlStateId for {z['slug']}"
        assert z.get("mlCityId"), f"unresolved mlCityId for {z['slug']}"
        if z["province"] == "CABA":
            assert z.get("mlNeighborhood"), f"CABA zone missing neighborhood: {z['slug']}"
            assert z.get("mlNeighborhoodId"), f"CABA zone unresolved neighborhood id: {z['slug']}"


def test_get_zone_by_slug():
    mdp = get_zone("mar-del-plata")
    assert mdp["displayName"] == "Mar del Plata"
    assert mdp["mlCity"] == "Mar del Plata"

    palermo = get_zone("palermo")
    assert palermo["province"] == "CABA"
    assert palermo["mlNeighborhood"] == "Palermo"
