"""MercadoLibre OFICIAL API source (OAuth) — terreno preparado, inactivo hasta tener creds.

Por qué: el scraper HTML de ML (mercadolibre.py, Playwright + cookie _bm_skipml) sufre
el bot-wall (RENT devuelve 0) y es frágil. La API oficial lo resuelve de raíz: legal,
estable, y trae datos que el listado HTML no da (lat/lng, fecha de publicación, agencia,
ambientes Y dormitorios por separado).

Estado: NO se usa todavía. Se activa cuando el dueño dé de alta la app en
developers.mercadolibre.com y se completen ML_APP_ID / ML_SECRET / ML_REFRESH_TOKEN en
.env.production.local. Ver docs/decisions/008-mercadolibre-api-oficial.md para el alta.

Lo único que NO se puede validar offline (sin creds) es la llamada de red y los IDs de
filtro exactos (categoría/operación) — marcados con TODO VALIDAR EN VIVO. El mapeo
`map_search_item` (el grueso) sí está testeado contra la forma documentada de la respuesta.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx

from .config import ML_APP_ID, ML_REFRESH_TOKEN, ML_SECRET
from .models import Currency, MlListingCard, Operation, PropertyType

API_BASE = "https://api.mercadolibre.com"
SITE = "MLA"  # Argentina
# Categoría "Inmuebles" en MLA. TODO VALIDAR EN VIVO: confirmar contra
# GET /sites/MLA/categories que sigue siendo MLA1459.
REALES_CATEGORY = "MLA1459"

# PROPERTY_TYPE.value_name (ML) → nuestro enum. Sin acentos/lower al comparar.
_PROPERTY_TYPE_MAP: dict[str, PropertyType] = {
    "departamento": "APT",
    "casa": "HOUSE",
    "ph": "PH",
    "local": "LOCAL",
    "oficina": "LOCAL",
    "deposito": "LOCAL",
    "galpon": "LOCAL",
    "terreno": "TERRENO",
    "lote": "TERRENO",
    "quinta": "TERRENO",
    "campo": "TERRENO",
    "cochera": "OTRO",
}


def _norm(s: str | None) -> str:
    import unicodedata

    nfd = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def _map_property_type(value_name: str | None) -> PropertyType:
    n = _norm(value_name)
    for kw, ptype in _PROPERTY_TYPE_MAP.items():
        if kw in n:
            return ptype
    return "OTRO"


def _map_operation(value_name: str | None) -> Operation:
    n = _norm(value_name)
    if "temporal" in n or "temporario" in n:
        return "TEMP_RENT"
    if "alquiler" in n:
        return "RENT"
    return "SALE"


def _parse_area(value_name: str | None) -> Decimal | None:
    """'50 m²' / '50.5 m2' → Decimal. None si no hay número."""
    if not value_name:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", value_name)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def _attrs_by_id(item: dict[str, Any]) -> dict[str, str]:
    """Aplana attributes [{id, value_name}] → {id: value_name}."""
    out: dict[str, str] = {}
    for a in item.get("attributes") or []:
        aid = a.get("id")
        val = a.get("value_name")
        if aid and val is not None:
            out[aid] = val
    return out


def map_search_item(item: dict[str, Any]) -> MlListingCard | None:
    """Mapea un item de /sites/MLA/search a MlListingCard. None si falta lo esencial.

    Defensivo (la API a veces omite campos). El grueso de valor de este módulo: es
    100% testeable offline contra la forma documentada de la respuesta.
    """
    portal_id = item.get("id")
    permalink = item.get("permalink")
    title = item.get("title")
    price = item.get("price")
    if not portal_id or not permalink or not title or price is None:
        return None

    try:
        price_amount = Decimal(str(price))
    except InvalidOperation:
        return None
    if price_amount <= 0:
        return None

    currency: Currency = "USD" if item.get("currency_id") == "USD" else "ARS"
    attrs = _attrs_by_id(item)

    property_type = _map_property_type(attrs.get("PROPERTY_TYPE"))
    # OPERATION / OPERATION_SUBTYPE traen "Venta" / "Alquiler" / "Alquiler temporal"
    operation = _map_operation(attrs.get("OPERATION") or attrs.get("OPERATION_SUBTYPE"))

    # ROOMS = ambientes; BEDROOMS = dormitorios. Hoy bedrooms guarda AMBIENTES (igual
    # que el scraper HTML) para mantener la convención; cuando aterrice T13 (separar
    # rooms/bedrooms) la API ya entrega ambos limpios.
    rooms_raw = attrs.get("ROOMS") or attrs.get("BEDROOMS")
    bedrooms = None
    if rooms_raw:
        m = re.search(r"\d+", rooms_raw)
        bedrooms = int(m.group()) if m else None
    baths_raw = attrs.get("FULL_BATHROOMS") or attrs.get("BATHROOMS")
    bathrooms = None
    if baths_raw:
        m = re.search(r"\d+", baths_raw)
        bathrooms = int(m.group()) if m else None

    covered_sqm = _parse_area(attrs.get("COVERED_AREA"))
    total_sqm = _parse_area(attrs.get("TOTAL_AREA"))

    addr = item.get("seller_address") or item.get("address") or {}

    def _named(key: str, flat_key: str | None = None) -> str | None:
        v = addr.get(key)
        if isinstance(v, dict):
            return v.get("name")
        return addr.get(flat_key) if flat_key else None

    neighborhood = _named("neighborhood")
    city = _named("city", "city_name")
    province = _named("state", "state_name")

    thumb = item.get("thumbnail") or ""
    # ML thumbnails vienen en http y chicas; subir a https para next/image.
    if thumb.startswith("http://"):
        thumb = "https://" + thumb[len("http://"):]
    photos = [thumb] if thumb.startswith("https://") else []

    # En search, el seller suele venir como nickname; el nombre de la inmobiliaria
    # real puede requerir GET /users/{id}. Best-effort por ahora.
    seller = item.get("seller") or {}
    agency = seller.get("nickname") or None

    return MlListingCard(
        portal_id=str(portal_id),
        url=str(permalink).split("#")[0],
        title=str(title),
        operation_type=operation,
        property_type=cast(PropertyType, property_type),
        price_amount=price_amount,
        price_currency=currency,
        address_full=addr.get("address_line") or None,
        neighborhood=neighborhood,
        city=city,
        province=province,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        total_sqm=total_sqm,
        covered_sqm=covered_sqm,
        photos=photos,
        agency_name=agency,
    )


# --- Red (no testeable offline sin creds; marcado TODO VALIDAR EN VIVO) ---


async def refresh_access_token(client: httpx.AsyncClient) -> str:
    """Cambia el refresh_token por un access_token fresco (grant_type=refresh_token).

    ML rota el refresh_token en cada uso; en producción habría que persistir el nuevo.
    Por ahora devolvemos solo el access_token (la persistencia se hace al activar).
    """
    if not (ML_APP_ID and ML_SECRET and ML_REFRESH_TOKEN):
        raise RuntimeError("ML API no configurada (faltan ML_APP_ID/ML_SECRET/ML_REFRESH_TOKEN)")
    resp = await client.post(
        f"{API_BASE}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ML_APP_ID,
            "client_secret": ML_SECRET,
            "refresh_token": ML_REFRESH_TOKEN,
        },
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    return cast(str, resp.json()["access_token"])


async def search_listings(
    access_token: str,
    *,
    state_id: str,
    operation_filter: str | None = None,
    limit: int = 50,
    max_items: int = 1000,
) -> list[MlListingCard]:
    """Pagina /sites/MLA/search en la categoría Inmuebles y devuelve cards mapeadas.

    TODO VALIDAR EN VIVO: los nombres exactos de los params de filtro de ML
    (`state`, `OPERATION`, `PROPERTY_TYPE`) y el límite real de offset (ML capea
    el paginado por query, por eso conviene filtrar por barrio como en el scraper HTML).
    """
    out: list[MlListingCard] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for offset in range(0, max_items, limit):
            params: dict[str, Any] = {
                "category": REALES_CATEGORY,
                "state": state_id,
                "offset": offset,
                "limit": limit,
            }
            if operation_filter:
                params["OPERATION"] = operation_filter
            resp = await client.get(
                f"{API_BASE}/sites/{SITE}/search",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if not results:
                break
            for item in results:
                card = map_search_item(item)
                if card is not None:
                    out.append(card)
    return out
