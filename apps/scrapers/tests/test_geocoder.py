"""Tests del geocoder: niveles de query, jitter determinístico y uso de caché.

No tocan la red: inyectamos un Nominatim falso y una caché en memoria.
"""

from __future__ import annotations

from geocode.geocoder import (
    GeocodeCache,
    build_query_tiers,
    geocode_property,
)


class FakeNominatim:
    """Devuelve coords fijas y cuenta cuántas veces se la llamó (para testear caché)."""

    def __init__(self, result: tuple[float, float] | None) -> None:
        self.result = result
        self.calls: list[str] = []

    def search(self, query: str) -> tuple[float, float] | None:
        self.calls.append(query)
        return self.result


def make_cache(tmp_path) -> GeocodeCache:
    return GeocodeCache(path=tmp_path / "cache.json")


def test_query_tiers_order_and_skips_missing():
    tiers = list(
        build_query_tiers(
            address_full="Alem 1234",
            neighborhood="Playa Grande",
            city="Mar del Plata",
            province="Buenos Aires",
        )
    )
    levels = [level for level, _ in tiers]
    assert levels == ["address", "street", "barrio", "ciudad"]
    assert tiers[0][1] == "Alem 1234, Playa Grande, Mar del Plata, Buenos Aires, Argentina"
    assert tiers[-1][1] == "Mar del Plata, Buenos Aires, Argentina"


def test_query_tiers_without_address():
    tiers = list(
        build_query_tiers(
            address_full=None,
            neighborhood="Centro",
            city="Mar del Plata",
            province=None,
        )
    )
    levels = [level for level, _ in tiers]
    # Sin address_full no hay niveles address/street; province cae a default.
    assert levels == ["barrio", "ciudad"]
    assert "Buenos Aires" in tiers[0][1]


def test_query_tiers_barrio_equal_city_is_skipped():
    # Cuando el "barrio" es en realidad la ciudad (zonas catch-all de MdP), no se
    # genera un nivel barrio redundante.
    tiers = list(
        build_query_tiers(
            address_full=None,
            neighborhood="Mar del Plata",
            city="Mar del Plata",
            province="Buenos Aires",
        )
    )
    assert [level for level, _ in tiers] == ["ciudad"]


def test_address_level_has_no_jitter(tmp_path):
    nom = FakeNominatim((-38.0, -57.55))
    cache = make_cache(tmp_path)
    res = geocode_property(
        prop_id="abc",
        address_full="Alem 1234",
        neighborhood="Playa Grande",
        city="Mar del Plata",
        province="Buenos Aires",
        nominatim=nom,
        cache=cache,
    )
    assert res is not None
    assert res.level == "address"
    # Match a nivel calle+altura: coords exactas, sin jitter.
    assert (res.lat, res.lng) == (-38.0, -57.55)


def test_barrio_level_jitter_is_deterministic(tmp_path):
    nom = FakeNominatim((-38.0, -57.55))
    args = {
        "address_full": None,
        "neighborhood": "Centro",
        "city": "Mar del Plata",
        "province": "Buenos Aires",
        "nominatim": nom,
        "cache": make_cache(tmp_path),
    }
    a = geocode_property(prop_id="same-id", **args)
    b = geocode_property(prop_id="same-id", **{**args, "cache": make_cache(tmp_path)})
    c = geocode_property(prop_id="other-id", **{**args, "cache": make_cache(tmp_path)})

    assert a is not None and b is not None and c is not None
    assert a.level == "barrio"
    # Mismo id → mismo desplazamiento; id distinto → desplazamiento distinto.
    assert (a.lat, a.lng) == (b.lat, b.lng)
    assert (a.lat, a.lng) != (c.lat, c.lng)
    # El jitter es chico (≤ ~0.02°, unos cientos de metros).
    assert abs(a.lat - (-38.0)) < 0.02


def test_cache_avoids_second_network_call(tmp_path):
    nom = FakeNominatim((-38.0, -57.55))
    cache = make_cache(tmp_path)
    common = {
        "address_full": None,
        "neighborhood": "Centro",
        "city": "Mar del Plata",
        "province": "Buenos Aires",
        "nominatim": nom,
        "cache": cache,
    }
    geocode_property(prop_id="p1", **common)
    calls_after_first = len(nom.calls)
    geocode_property(prop_id="p2", **common)
    # La segunda propiedad del mismo barrio sale 100% de caché.
    assert len(nom.calls) == calls_after_first


def test_falls_back_to_coarser_level_on_miss(tmp_path):
    # Nominatim "no encuentra" el address exacto → cae a barrio/ciudad.
    class MissThenHit:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query: str):
            self.calls.append(query)
            # Sólo resuelve la query de ciudad.
            return (-38.0, -57.55) if query.startswith("Mar del Plata") else None

    nom = MissThenHit()
    res = geocode_property(
        prop_id="x",
        address_full="Calle Inexistente 9999",
        neighborhood="Barrio Fantasma",
        city="Mar del Plata",
        province="Buenos Aires",
        nominatim=nom,
        cache=make_cache(tmp_path),
    )
    assert res is not None
    assert res.level == "ciudad"
