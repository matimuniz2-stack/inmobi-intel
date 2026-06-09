# 009 — Geocoding (Nominatim) + mapa de propiedades (Leaflet)

> Estado: **shipped (código)**, esperando primera corrida contra la DB · Fecha: 2026-06-09

## Contexto

El dueño pidió un **mapa "a lo Google Maps"**: grande, movible, con las propiedades
ubicadas por zona y, al pasar el mouse sobre un pin, su info + fotos.

El schema ya tenía columnas `lat`/`lng` (`Decimal(9,6)`), pero **nadie las poblaba**:
el `UPSERT_PROPERTY_SQL` ni siquiera las escribe (eran T10/T11, diferidas). Y
`zones.json` no tiene centroides ni bounds. O sea: sin un paso de geocoding, no hay
un solo pin que dibujar.

Decisión del dueño (sobre las opciones planteadas): **geocoding real de direcciones**
(no centroides de zona) + **Leaflet + OpenStreetMap** como proveedor (gratis, sin API
key, sin tarjeta — encaja con el principio de costo ~0 de la decisión 004).

## Decisión

Geocoding como **paso aparte** del scrape (igual que el scorer de oportunidades), y un
mapa client-side con Leaflet.

### Backend de geocoding — `apps/scrapers/geocode/`

- Módulo CLI espejo de `opportunity/`: `python -m geocode [--dry-run] [--limit N]`.
- **Nominatim** (OpenStreetMap) como geocoder: gratis, sin API key. Respetamos su
  política de uso — **1 req/s** (rate-limit explícito) + User-Agent identificable.
- **Caché en disco** (`geocode_cache.json`, gitignored): las queries a nivel barrio se
  comparten entre cientos de avisos → la caché baja las llamadas reales de miles a
  decenas, y hace la corrida idempotente entre noches.
- **Estrategia por niveles** (de más preciso a menos), porque la dirección que traen
  los portales es despareja (ML a veces trae calle+altura; Argenprop/ZonaProp suelen
  tener sólo barrio): `address → street → barrio → ciudad`. Se usa el primero que
  resuelve.
- **Jitter determinístico** (~150 m, derivado del id) cuando el match es a nivel
  barrio/ciudad, para que los avisos no se apilen en un único punto y el hover siga
  siendo usable. Mismo id → mismo desplazamiento (estable entre corridas).
- Sólo procesa filas `is_active = true` sin `lat/lng`, las más recientes primero.
  Commit + flush de caché de a tandas de 25 para no perder progreso si se corta.
- Cableado en `scrape-all.ps1` después del scorer (no afecta el exit code del scrape).
- 7 tests (`tests/test_geocoder.py`): niveles de query, jitter determinístico, uso de
  caché, fallback a nivel más grueso. Sin red (Nominatim falso inyectado).

### Backend tRPC — `properties.forMap`

- Nuevo procedure: mismos filtros que `search` (zona/op/tipo/ambientes/precio,
  refactorizados a un `buildWhere` compartido), pero **devuelve todas las matcheadas
  con `lat/lng` no nulo** (no pagina), con payload mínimo (sólo lo que el pin + popup
  necesitan) y **tope de 2000** (las más recientes; flag `capped`).
- Devuelve también `totalAll` (matchean, con o sin coords) → el frontend avisa
  "N sin ubicar todavía".

### Frontend — `/mapa`

- Leaflet **vanilla + `leaflet.markercluster`** manejado imperativamente. Se descartó
  `react-leaflet` por el churn de peer-deps con **React 19** (el proyecto usa React 19
  + Next 15); el approach imperativo es el más robusto acá.
- Carga **dinámica sin SSR** (`next/dynamic`, `ssr:false`): Leaflet toca `window`.
  Queda en un chunk lazy → la página suma sólo ~3.7 kB a la carga inicial.
- Pin coloreado por operación (Venta/Alquiler/Temporal), clustering, y **popup con
  foto + precio + datos + link al aviso que aparece al hacer hover** sobre el pin.
- Filtros reutilizados: se extrajo `FiltersPanel` + tipos a
  `components/search/filters.ts` y `filters-panel.tsx`, compartidos por `/buscar` y
  `/mapa`.
- Link cruzado en el header de la búsqueda (botón "Mapa") y vuelta a la lista.

## Limitaciones / pendientes

- **El mapa está vacío hasta correr `python -m geocode` contra la DB** (necesita
  `DATABASE_URL` de Supabase, hoy administrada por el dueño). Una vez geocodificadas,
  los pins aparecen solos.
- La **precisión depende de la dirección del portal**: muchos avisos de
  Argenprop/ZonaProp sólo dan barrio → caen a nivel barrio + jitter (aproximado, no la
  ubicación exacta del inmueble). Cuando ML migre a la API oficial (decisión 008), va a
  traer lat/lng exactas y el geocoder se saltea esas (ya tienen coords).
- Nominatim a 1 req/s es lento para un backfill inicial grande; por eso el `--limit`
  por corrida y el llenado progresivo entre noches. Si se necesita acelerar, evaluar un
  geocoder con más throughput (Photon/Pelias self-host, o Google con API key) — no hoy.

## Cómo correrlo

```powershell
# Backfill de coordenadas (desde apps/scrapers/, con DATABASE_URL seteada)
python -m geocode --dry-run        # ver qué haría
python -m geocode --limit 500      # geocodifica y persiste (tope por corrida)
```

El mapa queda en **`/mapa`** (link "Mapa" en el header de la búsqueda).
