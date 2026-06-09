"""Cliente Nominatim + caché en disco + estrategia de geocodificación por niveles.

Nominatim (OpenStreetMap) es gratis y sin API key, pero tiene una política de uso
estricta: máximo 1 request/segundo y un User-Agent identificable. La respetamos con
un rate-limit explícito y una caché en disco para no re-consultar la misma dirección
(las consultas a nivel barrio se comparten entre cientos de avisos → la caché baja
las llamadas reales de miles a decenas).

Estrategia por niveles (de más preciso a menos):
  1. address  → "{address_full}, {neighborhood}, {city}, {province}, Argentina"
  2. street   → "{address_full}, {city}, {province}, Argentina"   (sin barrio)
  3. barrio   → "{neighborhood}, {city}, {province}, Argentina"
  4. ciudad   → "{city}, {province}, Argentina"

Cuando el match es a nivel barrio/ciudad (no hay calle+altura), aplicamos un jitter
determinístico (derivado del id) para que los avisos no se apilen en un único punto
y el mapa siga siendo legible al hacer hover. El jitter es chico (~150 m) y estable
entre corridas (mismo id → mismo desplazamiento).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from scrapers.config import SCRAPERS_ROOT
from scrapers.logging_config import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Política de uso de Nominatim: User-Agent identificable con forma de contacto.
USER_AGENT = "inmobi-intel/1.0 (internal real-estate tool; matimuniz2@gmail.com)"
MIN_INTERVAL_S = 1.1  # un pelín > 1 req/s para no rozar el límite

CACHE_FILE: Path = SCRAPERS_ROOT / "geocode_cache.json"

# Niveles cuyo match es impreciso (no hay calle+altura) → conviene jitter.
_COARSE_LEVELS = {"barrio", "ciudad"}
_JITTER_RADIUS_DEG = 0.0015  # ~165 m en latitud


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lng: float
    level: str  # address | street | barrio | ciudad
    query: str


class GeocodeCache:
    """Caché JSON en disco: query normalizada → [lat, lng] o null (miss recordado)."""

    def __init__(self, path: Path = CACHE_FILE) -> None:
        self.path = path
        self._data: dict[str, list[float] | None] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("geocode_cache_unreadable", path=str(path))
                self._data = {}
        self._dirty = False

    def __contains__(self, query: str) -> bool:
        return query in self._data

    def get(self, query: str) -> list[float] | None:
        return self._data.get(query)

    def put(self, query: str, value: list[float] | None) -> None:
        self._data[query] = value
        self._dirty = True

    def flush(self) -> None:
        if self._dirty:
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
            )
            self._dirty = False


class Nominatim:
    """Cliente HTTP con rate-limit propio (1 req/s) sobre Nominatim."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=20.0, headers={"User-Agent": USER_AGENT}
        )
        self._last_call = 0.0

    def search(self, query: str) -> tuple[float, float] | None:
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()
        try:
            resp = self._client.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "countrycodes": "ar",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("nominatim_error", query=query, error=str(exc))
            return None
        if not data:
            return None
        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except (KeyError, ValueError, TypeError):
            return None

    def close(self) -> None:
        self._client.close()


def _clean(value: str | None) -> str | None:
    v = (value or "").strip()
    return v or None


def build_query_tiers(
    *,
    address_full: str | None,
    neighborhood: str | None,
    city: str | None,
    province: str | None,
) -> Iterator[tuple[str, str]]:
    """Devuelve (nivel, query) de más preciso a menos. Omite niveles sin datos."""
    address = _clean(address_full)
    barrio = _clean(neighborhood)
    ciudad = _clean(city)
    prov = _clean(province) or "Buenos Aires"

    def join(*parts: str | None) -> str:
        return ", ".join([p for p in parts if p] + ["Argentina"])

    if address and barrio and ciudad:
        yield "address", join(address, barrio, ciudad, prov)
    if address and ciudad:
        yield "street", join(address, ciudad, prov)
    if barrio and ciudad and barrio.lower() != ciudad.lower():
        yield "barrio", join(barrio, ciudad, prov)
    if ciudad:
        yield "ciudad", join(ciudad, prov)


def _jitter(lat: float, lng: float, seed: str) -> tuple[float, float]:
    """Desplazamiento determinístico y chico, estable por `seed` (id de la prop)."""
    h = hashlib.md5(seed.encode("utf-8")).digest()
    angle = (h[0] / 255.0) * 2 * math.pi
    radius = (h[1] / 255.0) * _JITTER_RADIUS_DEG
    d_lat = radius * math.cos(angle)
    # corrige por latitud para que el desplazamiento en lng sea ~igual en metros
    d_lng = radius * math.sin(angle) / max(math.cos(math.radians(lat)), 0.1)
    return round(lat + d_lat, 6), round(lng + d_lng, 6)


def geocode_property(
    *,
    prop_id: str,
    address_full: str | None,
    neighborhood: str | None,
    city: str | None,
    province: str | None,
    nominatim: Nominatim,
    cache: GeocodeCache,
) -> GeoResult | None:
    """Geocodifica una propiedad probando niveles. Usa caché por query."""
    for level, query in build_query_tiers(
        address_full=address_full,
        neighborhood=neighborhood,
        city=city,
        province=province,
    ):
        if query in cache:
            cached = cache.get(query)
            coords = (cached[0], cached[1]) if cached else None
        else:
            coords = nominatim.search(query)
            cache.put(query, list(coords) if coords else None)

        if coords is None:
            continue

        lat, lng = coords
        if level in _COARSE_LEVELS:
            lat, lng = _jitter(lat, lng, prop_id)
        return GeoResult(lat=lat, lng=lng, level=level, query=query)

    return None
