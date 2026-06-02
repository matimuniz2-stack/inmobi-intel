# Mega-plan nocturno — Cobertura completa MdP + calidad de datos

> Generado 2026-06-01 por workflow de auditoria (14 agentes) + mesa de planes (3 jueces unanimes). Rama: `overnight/cobertura-calidad-2026-06-01`.

---

# EXECUTIVE SUMMARY

Veredicto del jurado (unánime, 3/3): el ganador es PARTICIÓN EXHAUSTIVA del espacio de búsqueda (barrio × operación × tipo) corrida lento de noche desde la IP residencial — ataca la causa raíz (la mega-query "todo Mar del Plata" se trunca en ~10 páginas por portal) en vez de pelear el anti-bot, a USD 0 y respetando la decisión 004. Los 3 jueces coinciden en injertarle 4 piezas: (1) ML a API oficial OAuth (mata el RENT=0 de raíz, trae geo+published_at+agency_id reales), (2) Argenprop parseado desde el JSON embebido (sosiva451) en vez de cards CSS, (3) instrumentar total_publicado vs total_scrapeado para medir cobertura real, y (4) dedup cross-portal como PRE-REQUISITO BLOQUEANTE antes de escalar volumen (sin él, más barrios = triplicar duplicados y envenenar las cohortes del scorer).

Verifiqué los hallazgos críticos contra el código real: scrape-all.ps1:83 corre 1 sola zona "mar-del-plata" con --op "SALE,RENT" SIN --type (default APT → casas/PH/terrenos = 0%); argenprop.py:61 y zonaprop.py:64 buscan argenpropSlug/zonapropSlug que NO existen en zones.json (siempre cae al slug genérico); argenprop_parser.py:174 fija agency_name=None hard; db.py:57-66 el UPSERT solo escribe un subconjunto de columnas (description, expenses, amenities, lat/lng, agency_phone existen en schema pero quedan NULL); is_active nunca se pone en false; scorer.py:198-210 cohort_key NO segmenta por bedrooms; scorer.py:357 stale usa first_seen_at; falta migrate resolve de 20260531120000; web properties.ts no muestra contacto ni deduplica, route.ts:10 createContext vacío (sin auth), no hay middleware.ts.

Hay MUCHÍSIMO trabajo SAFE para una noche larga: arreglos de cobertura (slugs, tipos, ML por barrio), persistir las columnas muertas, dedup cross-portal, pricing engine (zone_price_stats), realinear el scorer a la spec, contacto+dedup en la UI, auth básica, dedup, índices, migrate resolve, registrar la tarea de Windows e instrumentar heartbeat. Lo único que requiere decisión humana es: revisitar (o no) la decisión 004 / gastar en proxies/4G, registrar OAuth de ML (alta de app + credenciales), deploy a prod y disparar el scrape masivo nocturno real. Prioricé "data pesimista correcta > optimista" (sweep de is_active, dedup conservador, no scorear sin razones) y "sin overengineering" (PostGIS y saved_searches se difieren, zone_price_stats solo cuando la búsqueda lo necesite).

# WORKSTREAMS

## Cobertura / Scrapers — Pasar de ~1 zona/solo-deptos/~8-15% del mercado a partición barrio×op×tipo que capture casas/PH/terrenos, RENT y la cola larga, a USD 0 desde IP residencial (estrategia ganadora).

[T1] (safe/M) Poblar argenpropSlug/zonapropSlug por barrio en zones.json
  detalle: argenprop.py:61 (zone.get('argenpropSlug') or zone['slug']) y zonaprop.py:64 (zonapropSlug) buscan claves que NO existen en zones.json (verificado), así que TODA zona cae al slug genérico — bug latente de cobertura. Agregar argenpropSlug/zonapropSlug a cada una de las ~44 zonas MdP (+ las CABA que se vayan a scrapear) usando el patrón de URL real de cada portal (ej. /departamentos-venta-playa-grande-mar-del-plata). Empezar por las de priority>=95 (Centro, Playa Grande, Güemes, Los Troncos). Como no hay red para validar contra los portales en esta corrida, derivar los slugs de forma determinística a partir de displayName + 'mar-del-plata' y dejar un TODO de validación-en-vivo marcada por zona.
  files: packages/shared-types/src/data/zones.json
  aceptacion: Cada zona MdP tiene argenpropSlug y zonapropSlug no vacíos; un test (nuevo) afirma que ninguna zona MdP cae al fallback genérico (zone.get('argenpropSlug') no es None para todas).

[T2] (safe/M) Smoke test por (zona,op,tipo) que falle si una combinación poblada da 0
  detalle: Hoy EXIT_SCRAPED_NOTHING (base.py:47) solo dispara si TODA la sesión da 0; un slug roto o un barrio capeado pasa en verde. Agregar un test/validación que, dado un set de zonas-conocidas-pobladas, falle ruidoso si una (zona,op,tipo) devuelve 0 cuando históricamente daba >0. Sirve de red para T1 (slugs nuevos rotos = página vacía/redirect a ciudad).
  files: apps/scrapers/scrapers/base.py, apps/scrapers/tests/
  aceptacion: Existe test que, con un fixture de slug roto (redirect a ciudad / 0 cards), falla; con slug bueno, pasa.

[T3] (safe/S) Pasar --type a Argenprop/ZonaProp y particionar por tipo en scrape-all.ps1
  detalle: argenprop.py:91 y zonaprop.py:116 hacen 'types = prop_types or [APT]'; scrape-all.ps1:83 no pasa --type, así casas/PH/local/terreno = 0% en 2 de 3 portales (los slugs YA están mapeados en PROP_TYPE_SLUG). Cambiar scrape-all.ps1 para iterar tipos APT,HOUSE,PH,LOCAL,TERRENO. Nota: el scorer solo puntúa APT (scorer.py:268) — los demás tipos entran a búsqueda reversa pero no a oportunidades hasta T17.
  files: apps/scrapers/scripts/scrape-all.ps1
  aceptacion: scrape-all.ps1 (en --DryRun) imprime invocaciones para los 5 tipos en Argenprop y ZonaProp; un run de prueba sobre 1 barrio trae >0 de al menos HOUSE.
  depende: T1

[T4] (safe/M) ML por barrio × op × tipo (explotar build_url barrio-level que ya funciona)
  detalle: mercadolibre.py:50 ya soporta mlNeighborhood y _resolve_zones('all') devuelve los barrios; ML capea a ~1000 por query (no por sesión), así barrio cae bajo el cap y se destapa la cola y RENT por barrio. Agregar --type a ML (hoy OPERATION_SLUGS solo venta/alquiler; el parser infiere tipo) y orquestar 34 barrios × 2 ops × tipos. Escalonar con pausas largas (60-120s) entre bloques de barrio + orden aleatorio cada noche.
  files: apps/scrapers/scrapers/mercadolibre.py, apps/scrapers/scripts/scrape-all.ps1
  aceptacion: DryRun lista sub-queries por barrio; run de 1 barrio con --op RENT trae >0 ítems (hoy RENT=0 en la mega-query).
  depende: T3

[T5] (safe/L) Reescribir scrape-all.ps1 como orquestador de matriz con checkpoint y backoff por-barrio
  detalle: Iterar la matriz barrio×op×tipo, persistir progreso (qué combinaciones ya se hicieron esta noche, ej. JSON en logs/) para reanudar si la corrida se corta; backoff exponencial al primer DataDome (pausar 10-20min y seguir con OTRO barrio, nunca abortar el portal entero como hace hoy el break). Priorizar barrios priority>=95 primero. Pausas largas + jitter entre bloques.
  files: apps/scrapers/scripts/scrape-all.ps1
  aceptacion: Matar el script a mitad y re-lanzarlo reanuda solo las combinaciones pendientes (no re-scrapea las hechas); un DataDome simulado en un barrio no aborta el resto.
  depende: T3,T4

[T6] (safe/M) Retry/backoff en _fetch_page_html distinguiendo transitorio vs bloqueo
  detalle: Los 3 scrapers hacen 'break' ante cualquier excepción (mercadolibre.py:106, argenprop.py:104, zonaprop.py:127). Agregar retry con backoff exponencial (2-3 intentos) para timeouts/errores de red transitorios, distinguiéndolos de señales de bloqueo (DataDome/bot-wall: el detector len<100KB o 'Un momento' ya existe en ZonaProp) que SÍ deben abortar/backoff-largo.
  files: apps/scrapers/scrapers/base.py, mercadolibre.py, argenprop.py, zonaprop.py
  aceptacion: Test: un fetch que falla 2 veces con timeout y luego responde, termina OK; un fetch que devuelve página DataDome no reintenta en loop sino que escala a backoff de bloqueo.

[T7] (safe/L) storage_state persistente por bloque de barrio + pool de 5-8 UAs por sesión
  detalle: ZonaProp abre contexto nuevo por página (caro y sospechoso). Cambiar a UN storage_state Playwright persistente por bloque de barrio reusando la cookie datadome/_bm_skipml entre páginas, rotando solo entre barrios. Pool chico (5-8) de UAs Chrome reales recientes con viewport/timezone/Sec-Ch-Ua-Platform COHERENTES, uno por bloque (no por request — mal hecho es más detectable que el UA único).
  files: apps/scrapers/scrapers/base.py, zonaprop.py, mercadolibre.py, argenprop.py, config.py
  aceptacion: Una corrida de N páginas del mismo barrio reusa 1 solo context/cookie; test verifica coherencia UA↔platform↔viewport en cada UA del pool.
  depende: T6

[T8] (safe/M) Instrumentar total_publicado vs total_scrapeado por (zona,op,tipo)
  detalle: detect_total_results ya existe (loguea el total). Persistir total_publicado y total_capturado por zona/op/tipo en scrape_jobs (o tabla coverage) para tener el KPI honesto de cobertura ('capturás 491 de 1100 = 45%'). Convierte la decisión de revisitar 004 de emocional a financiera. Es el dato que el dueño necesita para decidir D1.
  files: apps/scrapers/scrapers/base.py, mercadolibre.py, zonaprop.py, packages/db/prisma/schema.prisma
  aceptacion: Tras un run, una query a scrape_jobs/coverage muestra total_publicado y total_capturado por zona; el ratio aparece en el resumen del log.

[T9] (safe/M) Derivar TEMP_RENT del título/slug en Argenprop/ZonaProp (alquiler temporario MdP)
  detalle: ML infiere TEMP_RENT del headline (parser.py:48) pero Argenprop/ZonaProp pasan operation_type fijo y NUNCA marcan TEMP_RENT, así un temporario se guarda como RENT permanente (mercados de magnitud distinta, contamina cohortes). CLAUDE.md marca el temporario de verano como 'enorme'. Derivar TEMP_RENT del título/slug en ambos parsers, y opcionalmente agregar slug de operación alquiler-temporal por portal.
  files: apps/scrapers/scrapers/argenprop_parser.py, zonaprop_parser.py
  aceptacion: Test con fixture de aviso temporario en Argenprop/ZonaProp produce operation_type=TEMP_RENT.

## Calidad de datos / Persistencia / Dedup — Que las columnas del schema dejen de estar muertas, separar ambientes de dormitorios, desactivar avisos caídos, y deduplicar entre portales (PRE-REQUISITO BLOQUEANTE antes de escalar volumen).

[T10] (safe/L) Persistir columnas muertas: description, expenses, amenities, lat/lng, agency contacto
  detalle: UPSERT_PROPERTY_SQL (db.py:57-66) solo escribe un subconjunto; description/expenses/amenities/lat/lng/agency_phone/email/url existen en schema (verificado líneas 79-89) pero quedan SIEMPRE NULL. description es combustible de 2 señales del scorer (urgencia + antigüedad, hoy leen solo el título) y agency_phone es core de la búsqueda reversa. Ampliar MlListingCard (models.py) con esos campos y el UPSERT para escribirlos. Requiere extracción en parsers (description al menos desde la card; ideal: fetch de detalle para top-N en T11).
  files: apps/scrapers/scrapers/db.py, models.py, parser.py, argenprop_parser.py, zonaprop_parser.py
  aceptacion: Tras un run, properties tiene filas con description y agency_phone NO NULL en >X% de las cards que los exponen; tests de parser cubren los nuevos campos.

[T11] (safe/L) Fetch de página de detalle para candidatos del scorer (description/expenses/published_at/geo)
  detalle: El listado da lo justo; el detalle tiene m², antigüedad, expensas, texto completo y fecha real de publicación (combustible del scorer y de dedup). No scrapear todos los detalles (caro): solo los candidatos del scorer (~400 oportunidades) con delay. Persistir description, expenses, published_at, lat/lng, amenities. published_at alimenta directamente la señal stale (T16). Validar que published_at sea fecha de alta y no de actualización antes de confiar.
  files: apps/scrapers/scrapers/base.py, mercadolibre.py, argenprop.py, zonaprop.py, db.py
  aceptacion: Un job de enriquecimiento sobre N candidatos persiste description/published_at no nulos; añade ~20-30min al run, no más.
  depende: T10

[T12] (safe/M) Arreglar extracción de agency en Argenprop + anclar ZonaProp a data-qa estables
  detalle: argenprop_parser.py:174 fija agency_name=None hard (~399 ítems/run sin agencia) — rompe el núcleo de la búsqueda reversa. Extraer la inmobiliaria de la card/detalle (logo alt, publisher). ZonaProp depende de clases module-hashed que rotan: anclar a data-qa estables. ML usa string() sobre .poly-component__seller que a veces trae 'Publicado por'. Agregar test que afirme un % mínimo de cards con agency_name no nulo por portal (regresión rompe CI, no degrada en silencio).
  files: apps/scrapers/scrapers/argenprop_parser.py, zonaprop_parser.py, parser.py
  aceptacion: Test con fixtures reales: >=70% de cards Argenprop y ZonaProp tienen agency_name no nulo.

[T13] (safe/M) Separar ambientes (rooms) de dormitorios (bedrooms) en modelo, schema y parsers
  detalle: El campo bedrooms se carga preferentemente con AMBIENTES (parser.py:129, argenprop_parser.py:72, zonaprop_parser.py:91) cayendo a dormitorios solo como fallback — en AR un 2 ambientes = 1 dormitorio, así un mismo depto aparece como 2 en un portal y 1 en otro, rompiendo la comparabilidad y el filtro de la búsqueda reversa. Agregar campo 'rooms' (ambientes) separado de 'bedrooms' (dormitorios) en MlListingCard + schema + migración local, y mapear cada portal a la semántica correcta. La UI debe filtrar por ambientes.
  files: apps/scrapers/scrapers/models.py, parser.py, argenprop_parser.py, zonaprop_parser.py, packages/db/prisma/schema.prisma
  aceptacion: Migración local crea columna rooms; tests de parser afirman que un fixture '2 ambientes 1 dormitorio' setea rooms=2, bedrooms=1.

[T14] (safe/M) Sweep de is_active=false para avisos caídos (data pesimista correcta)
  detalle: is_active NUNCA se pone en false (db.py solo reactiva a true); la búsqueda reversa (properties.ts) y las 404 oportunidades muestran avisos vendidos/caídos como vigentes — viola el principio core. Agregar sweep post-scrape: por cada portal scrapeado con ÉXITO en la corrida, UPDATE properties SET is_active=false WHERE portal=X AND last_seen_at < inicio_de_corrida. CRÍTICO: condicionar a que el scrape de ese portal haya sido exitoso (scrape_jobs.status=SUCCEEDED con items_found razonable) — si no, NO tocar is_active (un ML en bot-wall desactivaría medio catálogo).
  files: apps/scrapers/scrapers/db.py, apps/scrapers/scripts/scrape-all.ps1
  aceptacion: Test: con un portal marcado exitoso, las filas no vistas en la corrida quedan is_active=false; con portal fallido (0 items), no se desactiva nada de ese portal.
  depende: T8

[T15] (safe/L) Dedup cross-portal: listing_group_id + dedup_key (PRE-REQUISITO BLOQUEANTE)
  detalle: No existe normalize/deduplicator (CLAUDE.md lo lista pero falta). El @@unique es solo (portal, portal_id), así la misma prop en ML+Argenprop+ZonaProp = 3 filas: triplica en la búsqueda reversa y envenena las cohortes del scorer (MIN_COHORT=8) con precios duplicados → falsos 'bajo precio' (viola 'data pesimista correcta'). Implementar dedup conservador: clave (operation, property_type, neighborhood, bedrooms, round(price_usd,-3)) + similitud title/m². Marcar grupos con listing_group_id (soft, respeta is_active), elegir representante. Es pre-requisito de TODO escalado de volumen (lo exigen los 3 jueces).
  files: apps/scrapers/normalize/deduplicator.py (nuevo), packages/db/prisma/schema.prisma, apps/scrapers/scrapers/db.py
  aceptacion: Migración local agrega listing_group_id indexado; test con 3 filas de la misma prop en 3 portales las agrupa bajo 1 listing_group_id; el scorer cuenta el grupo 1 vez en la cohorte.
  depende: T13

## Pricing engine / Scorer — Realinear el detector de oportunidades a la spec (sección 6): cohorte por ambientes, stale por fecha real, urgencia completa, baja real (no oscilación de dólar), pesos trazables.

[T16] (safe/M) Cohorte por bedrooms_bucket + stale por published_at + zone_price_stats
  detalle: DOS desviaciones de la spec: (1) cohort_key (scorer.py:198-210) NO segmenta por ambientes — la spec pide zona+tipo+ambientes; mezclar mono con 3-4 amb infla/deprime la mediana de US$/m² → falsos positivos/negativos en la señal de mayor peso (40%). Agregar bedrooms_bucket (0/1,2,3,4+) a cohort_key con fallback a barrio-sin-ambientes si no llega a MIN_COHORT=8 (anotándolo en la razón). (2) signal_stale (scorer.py:357) usa first_seen_at (cuándo lo detectamos) — con la app recién poblada NUNCA dispara aunque el aviso lleve 6 meses; usar published_at de T11 con preferencia, first_seen_at solo como piso. Materializar zone_price_stats solo cuando la búsqueda reversa lo necesite (no antes — sin overengineering).
  files: apps/scrapers/opportunity/scorer.py
  aceptacion: Tests: una cohorte con mono+3amb se separa por bucket; con published_at de hace 200d la señal stale dispara aunque first_seen_at sea de ayer. Validar con datos reales que el split no vacíe demasiadas cohortes.
  depende: T11,T13

[T17] (safe/M) Completar urgencia, baja real (nominal vs USD), tramos temporales y realinear pesos
  detalle: Cuatro arreglos del scorer alineados a la spec: (a) _URGENCY_TERMS (scorer.py:130) omite 7 de 13 señales fuertes — agregar 'sucesion'(~12), 'desocupada'(~6), 'mudanza'/'por viaje'(~8), 'negociable'(~6), 'ya escriturada'(~4); el ejemplo canónico del plan ('sucesión urgente') hoy NO se detecta. (b) price_drop (scorer.py:317) compara solo en USD normalizado: en avisos ARS una suba del dólar se reporta como falsa 'baja' no accionable — comparar también el NOMINAL en la misma moneda y exigir que el nominal haya bajado, o distinguir explícitamente en la razón. (c) baja reciente: implementar tramos 7d/30d/60d + bonus por >=2 bajadas en 60d (señal de desesperación). (d) realinear MAX_POINTS a 40/20/20/20 de la spec (hoy LOW_PRICE=45, DROP=30) O documentar los nuevos pesos como deliberados en decisión 005 — pesos y razones deben contar la misma historia.
  files: apps/scrapers/opportunity/scorer.py, docs/decisions/005-*.md
  aceptacion: Tests: aviso con 'sucesión' suma urgencia; aviso ARS con nominal igual y dólar subió NO reporta baja; aviso con 2 bajadas en 60d recibe el bonus; suma de MAX_POINTS coherente con spec o decisión documentada.

[T18] (safe/S) usd_per_sqm homogéneo (covered) + condition regex acotado
  detalle: (1) usd_per_sqm (scorer.py:189) mezcla covered y total entre peers de la misma cohorte (covered<total con balcón/patio) → US$/m² no homogéneo, falsos 'bajo precio'. Para APT preferir SIEMPRE covered_sqm y descartar del cálculo de bajo-precio las filas sin covered (en vez de caer a total); documentar. (2) extract_condition (scorer.py:242) el regex r'(\d{1,3})\s*anos' captura '3 años de garantía' / '10 años de financiación' → antigüedad incorrecta en la razón. Acotar a contextos de antigüedad ('antiguedad X anos', 'construido hace X anos') o restar confianza si hay 'garantia'/'financiacion' cerca.
  files: apps/scrapers/opportunity/scorer.py
  aceptacion: Tests: fila sin covered_sqm no entra al cálculo de bajo-precio; '3 años de garantía' no setea antiguedad_years.

[T19] (safe/M) Decisión documentada sobre needs_work y precio-on-request (visibilidad)
  detalle: (1) needs_work (scorer.py:284): 'a refaccionar' mata TODA la señal de precio — pero un depto 25% bajo mediana a refaccionar SIGUE siendo oportunidad para un inversor/flip. Cambiar a puntuar con haircut + razón anotada ('barato, pero a refaccionar') en vez de suprimir, O mantener supresión pero documentarla. (2) Listings sin precio ('Consultar precio') se descartan del todo (parser.py:179, argenprop_parser.py:128) — para la búsqueda reversa (mostrar TODO lo disponible) el agente igual quiere verlos. Persistir con flag price_on_request (price_amount nullable), excluyéndolos solo del scoring. Confirmar la preferencia exacta con el dueño (ver D5).
  files: apps/scrapers/opportunity/scorer.py, parser.py, argenprop_parser.py, models.py
  aceptacion: Avisos sin precio aparecen en búsqueda reversa con badge 'consultar precio' y NO en oportunidades; needs_work documentado o con haircut + test.

## Web / UX — Cerrar la brecha de la búsqueda reversa vs spec sección 5: mostrar contacto de la inmo, deduplicar visualmente, auth básica, y medir el <200ms.

[T20] (safe/S) Mostrar contacto de la inmobiliaria (tel/email/web) en PropertyCard
  detalle: El plan §5.4 exige mostrar la inmo 'con teléfono/email/web' — el dato más accionable. El schema lo soporta (agencyName/Phone/Email/Url, líneas 86-89) pero property-card.tsx:147 solo renderiza agencyName ?? 'Sin inmobiliaria'. Mostrar agencyPhone (link tel:), agencyEmail (mailto:) y agencyUrl. Depende de que el scraper los persista (T10/T12).
  files: apps/web/components/search/property-card.tsx
  aceptacion: Una card con agencyPhone renderiza un link tel: clickeable; sin teléfono muestra fallback claro.
  depende: T12

[T21] (safe/L) Dedup multi-portal en la búsqueda reversa: 1 card con badges de N portales
  detalle: El plan §5 edge case central: 'misma propiedad en 3 portales → un solo card con badges'. properties.ts hace findMany plano (cada fila = 1 card). Una vez exista listing_group_id (T15), agrupar resultados en el router y renderizar múltiples PortalBadges + múltiples inmos por card, mostrando el precio más reciente y un warning si difiere entre portales (otro edge case del plan).
  files: apps/web/lib/trpc/routers/properties.ts, apps/web/components/search/property-card.tsx
  aceptacion: Una prop en 3 portales aparece como 1 card con 3 badges; si los precios difieren se muestra warning.
  depende: T15

[T22] (safe/M) Auth básica de Supabase + middleware que proteja la app interna
  detalle: createContext es () => ({}) (route.ts:10), no hay middleware.ts (verificado), publicProcedure no valida nada — la app pública en vercel expone toda la data scrapeada + el detector, contradiciendo 'uso 100% interno' del dueño. Agregar auth básica de Supabase (alcance aceptado en CLAUDE.md para Fase 1) + middleware.ts que proteja /buscar, /oportunidades y /api/trpc.
  files: apps/web/middleware.ts (nuevo), apps/web/app/api/trpc/[trpc]/route.ts, apps/web/lib/
  aceptacion: Acceso sin sesión a /buscar o al endpoint tRPC redirige a login; con sesión válida funciona.

[T23] (safe/M) Medir <200ms real + índices para el orderBy default + count cacheable
  detalle: El claim <200ms no está medido y es frágil: tRPC serverless Vercel→Supabase sa-east-1 con Promise.all(findMany + count()) por request (properties.ts:70-78), sin caché. NO hay índice compuesto para el orderBy default lastUpdatedAt; mode:'insensitive' genera ILIKE que un btree normal no usa. Medir p50/p95 con EXPLAIN ANALYZE sobre el dataset real (medir antes de optimizar). Agregar índice [isActive, lastUpdatedAt], normalizar neighborhood/city a lower() en ingest o índice funcional, índice parcial WHERE is_active=true, y no recalcular count al paginar.
  files: packages/db/prisma/schema.prisma, apps/web/lib/trpc/routers/properties.ts
  aceptacion: EXPLAIN ANALYZE muestra uso de índice para el orden default; p95 medido y documentado; si >200ms, plan de caché documentado.

[T24] (safe/M) Tests web (toQueryInput, mapeo zod, serialización Decimal) + next/image hosts
  detalle: 0 tests en apps/web (la lógica de bedrooms '5plus' y mapeo de enums es frágil sin red). Agregar tests unitarios de toQueryInput/format.ts + un test del router properties.search. Además next.config.ts solo permite mlstatic; Argenprop/ZonaProp (la mayoría de las fotos) cargan sin optimización — agregar sus hostnames a remotePatterns o documentar el <img> lazy como decisión consciente (mobile-first/datos móviles MdP).
  files: apps/web/lib/trpc/routers/properties.ts, apps/web/lib/format.ts, apps/web/next.config.ts, apps/web/**/*.test.ts (nuevos)
  aceptacion: Tests verdes para toQueryInput y serialización Decimal→string; remotePatterns incluye Argenprop/ZonaProp o decisión documentada.

## Infra / Automatización — Que el scrape corra solo y que cualquier fallo nocturno sea visible (hoy es invisible).

[T25] (safe/S) Heartbeat de alerta (healthchecks.io / Better Stack) al final de scrape-all.ps1
  detalle: CERO monitoring/alertas en el repo (grep confirma). Un fallo nocturno (PC apagada, Supabase pausada, 3 portales bloqueados) es invisible hasta que un usuario ve data vieja con el cliente al lado — peor modo de fallo para un producto de 'data fresca'. Agregar ping a un heartbeat (Invoke-RestMethod a URL de éxito si todo OK, a URL de fail si no) al final de scrape-all.ps1. Cubre el 90% del riesgo gratis. Un escalón más: resumen found/created por portal a un webhook de Telegram. Código listo, parametrizado por env var; la URL real del heartbeat la setea el dueño (ver D4).
  files: apps/scrapers/scripts/scrape-all.ps1
  aceptacion: El script hace ping de éxito/fallo según el resultado (probado con una URL de prueba o mock); falla del script → ping al fail-URL.

[T26] (safe/M) Correr smoke_test.py atado al run dentro de scrape-all.ps1 (no DB global)
  detalle: smoke_test solo corre en GHA, no en la ruta local que es la fuente de verdad. Además mide 'DB tocada por cualquiera en la última hora' (global, compartida con GHA) — un bloqueo total puede pasar en verde. Atar el smoke al run actual: cada scraper escribe un sentinel run_id+items y el smoke lo lee (o decidir el fail por los exit codes de los 3 portales). Invocarlo al final de scrape-all.ps1 y usar SU exit code para el heartbeat. Detecta el caso found>0 pero upserts fallaron por DB/credencial.
  files: apps/scrapers/scripts/scrape-all.ps1, apps/scrapers/scripts/smoke_test.py, apps/scrapers/scrapers/base.py
  aceptacion: Un run que scrapea found>0 pero no persiste nada (DB mock caída) → smoke falla → heartbeat dispara fail.
  depende: T25

[T27] (safe/S) Rotación/purga de logs locales
  detalle: scrape-all.ps1 crea logs/scrape-<timestamp>.log por corrida y nunca los borra (la ruta local corre todos los días). Agregar al final: borrar logs >30 días. Trivial, evita el growth sin límite.
  files: apps/scrapers/scripts/scrape-all.ps1
  aceptacion: Tras correr, los .log con LastWriteTime > 30 días se eliminan.

[T28] (safe/S) Runbook de re-setup de la infra de ingest (SPOF físico)
  detalle: Toda la pipeline confiable depende de UNA PC Windows personal (decisión 004 lo reconoce). Documentar el runbook de re-setup en 5 min (crear .env.production.local + correr register-scrape-task.ps1 + verificar Get-ScheduledTaskInfo) para que cualquiera lo rehaga, y dejar el cron de GHA como red de seguridad los días que la IP datacenter no esté bloqueada. El heartbeat (T25) convierte 'PC apagada' de invisible a notificado.
  files: docs/decisions/004-scrape-local-ip-residencial.md
  aceptacion: docs/decisions/004 tiene una sección runbook paso-a-paso reproducible.

[T29] (needs-approval/S) Registrar la Scheduled Task de Windows (el scrape no corre solo hoy)
  detalle: register-scrape-task.ps1 existe y está bien hecho pero NO fue ejecutado — la fuente confiable depende 100% de que Mati corra el script a mano; el detector 'cada mañana' no se cumple. Requiere crear .env.production.local con el DATABASE_URL real de Supabase y ejecutar el registro. Es needs-approval porque toca la máquina/credenciales de prod y la cadencia (el -At default 09:00 vs 3am ART es decisión, ver D2).
  files: apps/scrapers/scripts/register-scrape-task.ps1
  aceptacion: Get-ScheduledTaskInfo -TaskName 'InmobiIntel-ScrapeDaily' reporta LastRunTime/LastTaskResult OK.

## Deuda técnica / DB — Sincronizar el ledger de Prisma y diferir conscientemente lo que no se usa (sin overengineering).

[T30] (needs-approval/S) prisma migrate resolve de 20260531120000 + verificar status
  detalle: La migración del detector se aplicó por SQL Editor: las tablas existen pero la fila NO está en _prisma_migrations — el próximo 'migrate deploy' fallará (relation already exists) o un 'migrate dev' propondrá un reset que borra datos. Correr 'prisma migrate resolve --applied 20260531120000_opportunity_detector' contra la DB (DIRECT_URL) y verificar con 'migrate status' que reporta up to date. Es needs-approval porque toca la DB de prod.
  files: packages/db/prisma/migrations/20260531120000_opportunity_detector/
  aceptacion: prisma migrate status reporta 'Database schema is up to date'.

[T31] (safe/S) Documentar diferimientos conscientes: PostGIS, saved_searches, export, CRM
  detalle: Para evitar que parezcan olvidos: documentar en docs/decisions/ que (a) lat/lng se mantienen como Decimal y PostGIS se difiere hasta que exista la vista mapa; (b) saved_searches/alertas y export Excel/PDF son Fase 3 (requieren modelo de usuario primero); (c) el tag 'ya está en nuestra base' depende de integrar el CRM de Zamboni (dependencia externa); (d) la vista mapa (Leaflet+OSM) se difiere tras dedup/contacto. Sin overengineering: confirmar el faltante sin construirlo.
  files: docs/decisions/, CLAUDE.md
  aceptacion: Existe una decisión que lista cada diferimiento con su razón y la fase objetivo.

[T32] (safe/S) Actualizar CLAUDE.md con limitaciones conocidas y estado real
  detalle: Documentar como limitaciones conocidas (para que nadie asuma feature completa): columnas que se empezaron a poblar en esta noche y cuáles siguen pendientes, cobertura real medida (T8), dedup activo (T15), y el estado del scorer vs spec (T16/T17). Actualizar la sección 'Fase actual'.
  files: CLAUDE.md
  aceptacion: CLAUDE.md refleja el estado tras la corrida nocturna (qué quedó safe-hecho, qué espera aprobación).

# OVERNIGHT SEQUENCE
T1 -> T2 -> T3 -> T4 -> T6 -> T7 -> T9 -> T8 -> T10 -> T12 -> T13 -> T11 -> T15 -> T14 -> T16 -> T17 -> T18 -> T19 -> T5 -> T20 -> T21 -> T23 -> T24 -> T22 -> T25 -> T26 -> T27 -> T28 -> T31 -> T32

# NEEDS HUMAN DECISION

- Q: ¿Revisitar la decisión 004 (sin proxies pagos) o mantenerla? Los 3 jueces dicen que NO hace falta todavía: partición + ML API oficial estiman 80-90% de cobertura a USD 0. Pero queda una cola larga cuantificable.
  opciones: A) Mantener 004 y esperar el KPI de T8 antes de cualquier gasto (recomendado por los 3 jueces). B) 4G móvil DIY (~USD 8-15/mes de datos, IP móvil AR, infra propia, no 'proxy pago') solo si T8 muestra que la cola larga perdida vale clientes. C) Proxy residencial pay-per-GB (~USD 10-35/mes real, no 80) — postergado indefinidamente.
  por que: Es la decisión estratégica de cobertura. La partición ataca la causa raíz sin gastar, pero ZonaProp/ML siguen capeados en profundidad desde una IP única. El número exacto de cuánto falta sale recién de instrumentar T8 (total_publicado vs total_scrapeado). Pagar a ciegas viola 'sin overengineering' y la decisión del dueño.

- Q: ¿Migrar ML a la API oficial OAuth? Es la mejor pieza individual del set (mata RENT=0 de raíz, legal, estable, trae geo+published_at+agency_id).
  opciones: A) Sí, dar de alta la app ML ahora (alto impacto, desbloquea RENT y enriquece datos). B) Posponer y seguir con el scraper Playwright+_bm_skipml como hoy (RENT sigue en 0). C) Hacer la app pero usar la API solo como complemento, manteniendo el scraper HTML como fallback.
  por que: Requiere dar de alta una app en developers.mercadolibre.com (APP_ID+SECRET), correr el flujo OAuth una vez y guardar el refresh_token — pasos que necesitan credenciales/cuenta del dueño. No lo puedo hacer solo de noche. Validar que published_at sea fecha de alta y no de actualización antes de alimentar la señal stale.

- Q: ¿Qué cadencia para el scrape nocturno y a qué hora registrar la Scheduled Task? (T29)
  opciones: A) 1x/día ~2-3am ART (defendible por 'sin overengineering' + menor exposición anti-bot; recomendado). B) Full diario 3am + scan cada 6h (más frescura, más riesgo de bloqueo). Decidir + confirmar credencial Supabase activa.
  por que: El -At default de register-scrape-task.ps1 es 09:00 local; el plan sugería 3am ART. Una sola foto diaria reduce la resolución de las señales 'baja reciente'/'urgencia'; más frecuencia desde la misma IP residencial sube el riesgo de DataDome. Registrar la tarea toca la máquina y requiere crear .env.production.local con la credencial de prod (que estuvo pausada).

- Q: ¿Qué servicio de heartbeat/alerta usar y a qué canal? (T25/T26)
  opciones: A) healthchecks.io (gratis, email/Telegram, simple). B) Better Stack heartbeat (gratis, más features). C) Webhook de Telegram con resumen found/created por portal (Mati lo ve en el celular cada mañana).
  por que: El código del ping queda listo de noche, pero la URL del heartbeat y el canal de notificación (email/Telegram) requieren crear la cuenta/integración del dueño. Sin esto, un fallo nocturno sigue invisible.

- Q: Sobre 'a refaccionar' (needs_work) y 'consultar precio': ¿suprimir o mostrar con flag? (T19)
  opciones: A) needs_work: puntuar con haircut + razón anotada en vez de suprimir; precio-on-request: persistir con flag y mostrarlo en búsqueda (excluido de scoring). B) Mantener supresión de needs_work pero documentarla en la UI; persistir precio-on-request igual. C) Status quo (suprimir ambos) — descartado por contradecir el caso de uso #1.
  por que: Hoy 'a refaccionar' elimina la oportunidad del ranking y 'consultar precio' descarta el aviso del todo. Para una inmo, un depto barato a refaccionar SIGUE siendo negocio (flip/inversor) y un aviso sin precio igual quiere verlo el agente. Es una decisión de producto sobre qué ve el agente.

- Q: ¿Deploy a prod de los cambios SAFE de esta noche y disparar el primer scrape masivo nocturno real?
  opciones: A) Revisar el diff a la mañana y aprobar deploy + rampa gradual (recomendado). B) Deploy de la web/scorer pero scrape masivo solo tras validar slugs en vivo (T1/T2). C) Mantener todo en una branch hasta revisión completa.
  por que: Todo el trabajo nocturno se hace y testea en local. El deploy a Vercel/Supabase y la primera corrida masiva real (cientos de sub-queries barrio×op×tipo contra los portales) son acciones de producción con riesgo anti-bot y deben ser aprobadas — más aún con la rampa gradual recomendada (empezar por barrios priority>=95).

