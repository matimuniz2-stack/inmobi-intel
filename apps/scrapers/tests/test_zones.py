"""Sanity tests for zones.json loading from shared-types."""

from __future__ import annotations

from scrapers.config import get_zone, load_zones


def test_load_zones_count_and_unique_slugs():
    # 108 = 89 (MdP region + CABA) + 19 barrios MdP descubiertos en los portales
    # (apply_barrio_slugs.py, T1 — solo existen en Argenprop/ZonaProp).
    zones = load_zones()
    assert len(zones) == 108, f"expected 108 zones, got {len(zones)}"
    slugs = [z["slug"] for z in zones]
    assert len(slugs) == len(set(slugs)), "duplicate zone slugs in zones.json"


def test_mdp_barrios_have_portal_slugs():
    """T1: la partición barrio×op×tipo necesita slugs canónicos por portal."""
    zones = load_zones()
    mdp_barrios = [
        z for z in zones
        if z["province"] == "Buenos Aires" and z.get("mlNeighborhood")
    ]
    with_ap = [z for z in mdp_barrios if z.get("argenpropSlug")]
    with_zp = [z for z in mdp_barrios if z.get("zonapropSlug")]
    # Snapshot del descubrimiento 2026-06-10: si esto baja, se perdió cobertura.
    assert len(with_ap) >= 38, f"argenpropSlug en {len(with_ap)} barrios (esperaba >=38)"
    assert len(with_zp) >= 40, f"zonapropSlug en {len(with_zp)} barrios (esperaba >=40)"


def test_new_portal_only_zones_lack_ml_id():
    """Los barrios que ML no reconoce no deben tener mlNeighborhoodId: el
    orquestador usa ese campo para no mandarle a ML un barrio inválido (riesgo
    de fallback silencioso a resultados city-wide con zone_slug equivocado)."""
    zones = load_zones()
    for slug in ("villa-primera", "alfar", "sierra-de-los-padres", "la-perla-norte"):
        z = next(z for z in zones if z["slug"] == slug)
        assert not z.get("mlNeighborhoodId"), f"{slug} no fue validado contra ML"
        assert z.get("argenpropSlug") or z.get("zonapropSlug")


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


def test_portal_build_url_uses_canonical_slugs():
    """build_url debe preferir el slug del portal sobre zone['slug']."""
    from scrapers.argenprop import build_url as ap_url
    from scrapers.zonaprop import build_url as zp_url

    centro = get_zone("centro")
    assert ap_url(centro, "SALE", "APT").endswith("/departamentos/venta/centro-mdp")
    assert zp_url(centro, "SALE", "APT").endswith(
        "/departamentos-venta-centro-mar-del-plata.html"
    )
    # Sin override cae al slug de la zona (city-level)
    mdp = get_zone("mar-del-plata")
    assert ap_url(mdp, "RENT", "HOUSE").endswith("/casas/alquiler/mar-del-plata")
