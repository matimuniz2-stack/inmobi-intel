"""Geocodificación de propiedades: llena lat/lng a partir de la dirección.

Las columnas `lat`/`lng` existen en el schema pero el scraper NO las escribe
(el UPSERT no las toca). Este módulo corre como paso aparte después del scrape:
toma las propiedades activas sin coordenadas, las geocodifica contra Nominatim
(OpenStreetMap, gratis y sin API key) y persiste el resultado. Eso alimenta el
mapa del frontend (`/mapa`).

    python -m geocode              # geocodifica y persiste
    python -m geocode --dry-run    # muestra qué haría, sin escribir
    python -m geocode --limit 200  # tope de propiedades por corrida
"""
