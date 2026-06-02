# 008 — Migrar el scraper de ML a la API oficial (OAuth)

> Estado: **terreno preparado, inactivo** (esperando alta de la app) · Fecha: 2026-06-01

## Contexto

El scraper HTML de ML (`scrapers/mercadolibre.py`, Playwright + cookie `_bm_skipml`)
sufre el bot-wall: en el scrape del 2026-06-01 **RENT devolvió 0** (una página no
renderizó). Es frágil y depende de un bypass que ML puede cerrar.

ML tiene una **API oficial gratuita**. Resuelve el problema de raíz: legal, estable, y
trae datos que el listado HTML no da — lat/lng, fecha real de publicación, ambientes Y
dormitorios por separado, y datos de la inmobiliaria. Es la mejor pieza individual del
mega-plan (D3).

## Decisión

Preparar el cliente de API ahora (hecho) y **activarlo cuando el dueño dé de alta la app**.
No reemplaza al scraper HTML de un día para el otro: primero corre en paralelo para validar,
después se vuelve la fuente primaria de ML con el HTML como fallback.

### Lo que ya está hecho (rama overnight)
- `scrapers/mercadolibre_api.py`: OAuth (`refresh_access_token`), búsqueda paginada
  (`search_listings`) y el mapeo `map_search_item` (item JSON → `MlListingCard`).
- `config.py`: lee `ML_APP_ID` / `ML_SECRET` / `ML_REFRESH_TOKEN` + helper `ml_api_configured()`.
- Tests del mapeo (5) contra la forma documentada de la respuesta.
- NO está cableado a `scrape-all.ps1` — inactivo hasta tener creds.

## Alta de la app (pasos para Mati — ~15 min, una vez)

1. Entrar a **https://developers.mercadolibre.com.ar/** con la cuenta de ML, ir a "Mis aplicaciones" → **Crear aplicación**.
2. Completar: nombre, descripción, y **Redirect URI** (poné `https://inmobi-intel.vercel.app/callback` o `http://localhost:3000/callback`; sólo se usa para el primer OAuth).
3. Scopes: `read` (y `offline_access` para obtener refresh_token).
4. Anotar el **App ID (client_id)** y el **Secret Key (client_secret)**.
5. **Primer OAuth (una vez)** para obtener el `refresh_token`: abrir en el navegador
   `https://auth.mercadolibre.com.ar/authorization?response_type=code&client_id=APP_ID&redirect_uri=REDIRECT_URI`,
   autorizar, copiar el `code=...` de la URL de retorno, y canjearlo:
   ```
   curl -X POST https://api.mercadolibre.com/oauth/token \
     -d grant_type=authorization_code -d client_id=APP_ID -d client_secret=SECRET \
     -d code=EL_CODE -d redirect_uri=REDIRECT_URI
   ```
   La respuesta trae `access_token` y **`refresh_token`** (este último es el que persiste).
6. Pegar en `apps/scrapers/.env.production.local`:
   ```
   ML_APP_ID=...
   ML_SECRET=...
   ML_REFRESH_TOKEN=...
   ```
7. Avisar a Claude para cablear la fuente API a `scrape-all` (con validación en paralelo primero).

## A validar en vivo (marcado TODO en el código)
- Categoría Inmuebles (`MLA1459`) sigue vigente (`GET /sites/MLA/categories`).
- Nombres exactos de los params de filtro (`state`, `OPERATION`, `PROPERTY_TYPE`).
- **`start_time` = fecha de alta o de actualización** (alimenta la señal `stale` — T16; no confiar hasta validar).
- ML rota el `refresh_token` en cada uso → persistir el nuevo al activar.

## Consecuencias
- ✅ Mata el RENT=0 de raíz; datos más ricos y estables; menos frágil que el HTML.
- ⚠️ Requiere mantener el `refresh_token` vivo (rota en cada refresh).
- ⚠️ La API puede tener su propio rate-limit (generoso para uso interno).
