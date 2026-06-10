# 010 — Partición barrio×operación×tipo con slugs canónicos descubiertos del portal

**Fecha**: 2026-06-10
**Estado**: aceptada (implementa T1/T4/T5/T8 del mega-plan 2026-06-01)

## Contexto

Cada portal capea cuántos resultados devuelve una búsqueda: Argenprop ~200 por
(zona, op, tipo) (robots.txt permite páginas 1–10), ZonaProp ~600 (30 páginas),
ML ~2.500 (50 páginas). Una sola query city-wide "mar-del-plata" truncaba en
silencio: Argenprop reporta 6.444 deptos en venta solo en MdP ciudad — con el
cap viejo capturábamos ~3%.

## Decisión

1. **Partición por barrio**: `scrape-all.ps1` ya no corre una query por portal
   sino una matriz (portal × zona), donde las zonas son las 4 city-level + cada
   barrio de MdP. Las ops y tipos los itera cada scraper internamente
   (`--op SALE,RENT --type APT,HOUSE,PH,LOCAL,TERRENO`).

2. **Slugs canónicos, nunca adivinados**: los portales usan slugs propios que
   no coinciden con los nuestros (Argenprop: `centro-mdp`, `zona-guemes`;
   ZonaProp: `centro-mar-del-plata`, `playa-varese`). Adivinar un slug
   inexistente arriesga redirect silencioso a resultados city-wide con
   `zone_slug` equivocado. Se descubren desde los links de facetas "Barrios"
   de los propios portales (`scripts/discover_barrio_slugs.py`) y se aplican a
   `zones.json` (`scripts/apply_barrio_slugs.py`) como `argenpropSlug` /
   `zonapropSlug`. Un barrio sin slug de un portal NO se scrapea en ese portal.

3. **ML solo con barrios validados**: el orquestador solo manda a ML zonas con
   `mlNeighborhoodId` resuelto (`pnpm zones:resolve`). 19 barrios nuevos
   descubiertos en los portales (Villa Primera, Alfar, Sierra de los Padres,
   etc.) no existen en el catálogo de locations de ML → quedan AP/ZP-only; su
   cobertura ML viene de la query city-level.

4. **Checkpoint/resume diario**: cada (portal, zona) completado se anota en
   `logs/checkpoint-<fecha>.json`. Re-correr el mismo día retoma donde quedó
   (un bloqueo DataDome a mitad de la noche ya no pierde lo anterior). Exit 3
   (corrió limpio, 0 items) también checkpointea: para un barrio chico ×tipo es
   un resultado legítimo.

5. **KPI de cobertura (T8)**: los 3 scrapers detectan el total publicado que
   reporta el portal (h1/título de la página 1) y lo persisten en
   `scrape_jobs.params.portal_totals` + `params.coverage` (items_found/total),
   sin migración de schema. Es el dato que faltaba para decidir si la partición
   alcanza o si hay que revisitar proxies (decisión 004, pregunta Q1).

## Consecuencias

- La corrida nocturna pasa de ~12 (portal, zona-ciudad) a ~140 (portal, zona)
  con pausas anti-bot → estimado 4–6 hs desde IP residencial, USD 0
  (consistente con decisión 004). `register-scrape-task.ps1` sube el límite de
  ejecución de 3 h a 8 h.
- Solapamiento barrio ⊂ ciudad es inofensivo: el upsert dedupea por
  (portal, portal_id). Sí infla el tiempo; si molesta, sacar las city-level de
  la matriz cuando la cobertura por barrio esté medida.
- **Límite conocido**: los barrios más grandes siguen excediendo el cap de
  Argenprop (Centro: 1.277 deptos venta vs ~200 capturables). El próximo nivel
  de partición es por dormitorios/ambientes (ZonaProp expone facetas
  `-N-ambientes`) o rango de precio. Medir primero con el KPI de cobertura.
- ZonaProp: ante challenge DataDome ahora hace un backoff de 60–120 s y
  reintenta una vez antes de cortar el (zona, op, tipo); Argenprop ganó delay
  de 1,5–3,5 s entre páginas.
