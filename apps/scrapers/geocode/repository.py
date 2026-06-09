"""Lectura de propiedades a geocodificar y escritura de coordenadas."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

# Propiedades activas sin coordenadas que tienen al menos algún dato de ubicación.
# Las más recientes primero: si una corrida se corta por el tope, geocodificamos
# lo que el usuario más probablemente esté mirando.
LOAD_PENDING_SQL = """
SELECT id::text, address_full, neighborhood, city, province
FROM properties
WHERE is_active = true
  AND (lat IS NULL OR lng IS NULL)
  AND (neighborhood IS NOT NULL OR city IS NOT NULL OR address_full IS NOT NULL)
ORDER BY last_updated_at DESC
LIMIT %(limit)s;
"""

UPDATE_COORDS_SQL = """
UPDATE properties SET lat = %(lat)s, lng = %(lng)s WHERE id = %(id)s::uuid;
"""


@dataclass(frozen=True)
class PendingRow:
    id: str
    address_full: str | None
    neighborhood: str | None
    city: str | None
    province: str | None


def load_pending(conn: psycopg.Connection, *, limit: int) -> list[PendingRow]:
    cur = conn.execute(LOAD_PENDING_SQL, {"limit": limit})
    return [
        PendingRow(
            id=r[0],
            address_full=r[1],
            neighborhood=r[2],
            city=r[3],
            province=r[4],
        )
        for r in cur.fetchall()
    ]


def save_coords(conn: psycopg.Connection, *, prop_id: str, lat: float, lng: float) -> None:
    conn.execute(UPDATE_COORDS_SQL, {"id": prop_id, "lat": lat, "lng": lng})
