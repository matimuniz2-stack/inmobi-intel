# Kickoff Prompt — Fase 1

> Pegá este prompt completo en Claude Code (CLI) **después de hacer `cd` al directorio `app-inmobi/`** y arrancar la sesión. Ya tenés `CLAUDE.md` con el contexto del proyecto.

---

## CÓMO USARLO

1. Abrí terminal.
2. `cd "C:\Users\matim\OneDrive\Documentos\Claude\Projects\quasor\app-inmobi"`
3. Iniciá Claude Code: `claude`
4. Pegá todo lo que está debajo de la línea `--- INICIO DEL PROMPT ---` hasta `--- FIN DEL PROMPT ---`.

---

## --- INICIO DEL PROMPT ---

Hola Claude. Vas a construir conmigo la **Fase 1** de **Inmobi Intel**, una app de inteligencia inmobiliaria para Mar del Plata + CABA. El contexto completo del proyecto está en `CLAUDE.md` (leelo ahora antes de seguir) y el plan maestro en `../plan-app-scraper-inmobiliario.md`.

### Objetivo de Fase 1

Construir un **MVP funcional end-to-end** con:

1. Setup completo del monorepo según la estructura de `CLAUDE.md`
2. Base de datos PostgreSQL con schema básico (tabla `properties` + auxiliares)
3. Scraper de MercadoLibre (la fuente más limpia, tiene API oficial) funcionando para zonas de Mar del Plata y CABA
4. Frontend Next.js con una pantalla de **búsqueda reversa** funcional:
   - Filtros: zona (autocomplete), ambientes (rango), precio min/max en USD, tipo de operación (venta/alquiler), tipo de propiedad
   - Resultados ordenados por relevancia
   - Cada resultado muestra: foto principal, precio, ubicación, ambientes/m², **nombre de la inmobiliaria** + datos de contacto si están disponibles, link directo al aviso original
   - Vista mobile bien resuelta
5. Cron job que corre el scraper diariamente

### Cómo trabajar

**Antes de escribir código**:
1. Leé `CLAUDE.md` y `../plan-app-scraper-inmobiliario.md`.
2. Hacé una propuesta de plan de implementación de Fase 1 dividido en milestones cortos (idealmente 4-6 milestones, cada uno entregable independientemente).
3. Mostrame el plan y esperá mi OK antes de arrancar.

**Durante la implementación**:
- Trabajá en milestones de a uno. Al terminar cada milestone, hacé pausa, mostrame qué funciona, commiteá, y esperá feedback antes de pasar al siguiente.
- Si te trabás con algo o tenés que tomar una decisión no trivial (qué librería, cómo modelar X, qué hacer ante data ambigua de MercadoLibre, etc.), preguntame en vez de asumir.
- Tests donde tenga sentido (sobre todo en scrapers — necesito poder validar que siguen funcionando cuando MercadoLibre cambie la API).

### Stack confirmado

- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui + tRPC
- **Backend (API)**: Next.js API Routes (mismo repo)
- **DB**: PostgreSQL via Supabase + Prisma ORM
- **Scraper**: Python 3.11 + Playwright + Scrapy + Pydantic, en `apps/scrapers/`
- **Package manager web**: pnpm
- **Package manager scrapers**: Poetry
- **Monorepo**: pnpm workspaces

### Sobre MercadoLibre como fuente

MercadoLibre tiene **API oficial gratuita** para inmuebles (`https://api.mercadolibre.com/sites/MLA/search?category=MLA1459`). Usar la API antes que scrapear HTML. Endpoints clave:

- Búsqueda por categoría con filtros: `/sites/MLA/search`
- Detalle de item: `/items/{item_id}`
- Listings activos en Argentina: `category=MLA1459` (Inmuebles)
- Para filtrar por zona usar `state` y `city` (MLA city IDs)

Documentación: https://developers.mercadolibre.com.ar/

Para Fase 1, alcanza con OAuth público (no hace falta token). Si más adelante hace falta, pedime credenciales.

### Zonas a configurar inicialmente

**Mar del Plata + alrededores** (priorizar):
- Mar del Plata (todos los barrios)
- Mar Chiquita partido
- Santa Clara del Mar
- Camet
- Sierra de los Padres

**CABA**:
- Todas las comunas / barrios

Querría poder agregar zonas nuevas fácilmente sin tener que tocar código (config-driven).

### Modelo de datos mínimo para Fase 1

```
properties
├── id (uuid)
├── portal (enum: mercadolibre, ...)
├── portal_id (string, unique con portal)
├── url
├── operation_type (sale | rent | temp_rent)
├── property_type (apt | house | ph | local | terreno | otro)
├── price_amount (decimal)
├── price_currency (ARS | USD)
├── price_usd_normalized (decimal, calculado con cotización del día)
├── expenses_amount, expenses_currency
├── bedrooms (int)
├── bathrooms (int)
├── total_sqm (decimal)
├── covered_sqm (decimal)
├── address_full (string, nullable)
├── neighborhood (string)
├── city (string)
├── province (string)
├── lat, lng (decimal)
├── photos (jsonb)
├── description (text)
├── amenities (jsonb)
├── agency_name (string)
├── agency_phone, agency_email, agency_url
├── first_seen_at, last_seen_at, last_updated_at
└── is_active (boolean)

scrape_jobs
├── id, portal, params (jsonb), status, started_at, completed_at, items_found, error_log

usd_rates
├── id, source, rate, recorded_at  -- tipo de cambio histórico (dolar blue)
```

Para Fase 1 NO hace falta:
- Tabla de price history (la sumamos en Fase 2 para detectar bajadas)
- Tabla de zone_price_stats (Fase 2)
- Sistema de scoring de oportunidades (Fase 2)
- Sistema de auth (Fase 1 puede ser sin auth o con auth básica de Supabase)

### Entregables al final de Fase 1

1. Repo monorepo configurado, lintea, tipo-checea, corre sin errores.
2. Migration de DB lista y aplicada en una instancia de Supabase.
3. Scraper de MercadoLibre que:
   - Ingiere todas las propiedades de MdP y CABA al menos una vez
   - Corre con `poetry run python -m scrapers.mercadolibre --zone "mar-del-plata"` o equivalente
   - Tiene logging útil (qué encontró, qué descartó, errores)
   - Maneja errores de red sin morir
4. Frontend Next.js con:
   - Pantalla de búsqueda reversa funcional
   - Resultados live desde la DB
   - Buen UX mobile y desktop
5. Cron job configurado (puede ser GitHub Actions, Vercel Cron, o Railway scheduler) que corre el scraper 1x/día.
6. README.md actualizado con instrucciones de cómo correr todo localmente.
7. CLAUDE.md actualizado con cualquier decisión técnica que hayas tomado durante el camino.

### Primera tarea concreta

Empezá leyendo `CLAUDE.md` y `../plan-app-scraper-inmobiliario.md`. Después proponé el plan de milestones para Fase 1 y esperá mi OK. NO escribas código todavía.

## --- FIN DEL PROMPT ---

---

## DESPUÉS DEL KICKOFF

Una vez que Claude Code arranca y proponga el plan de milestones, revisalo y dale OK (o pedile ajustes). Después dejá que vaya milestone por milestone.

### Tips para la sesión

- **Si Claude empieza a hacer mucho de golpe**, frenalo: "pará, hagamos un milestone a la vez".
- **Si una librería que sugiere no te convence**, decile que proponga 2 alternativas con pros/contras.
- **Cuando un milestone termine**, pedile que commitee con mensaje claro antes de seguir.
- **Si se rompe algo**, pedile que escriba un test que reproduzca el problema antes de arreglarlo.

### Comandos útiles dentro de Claude Code

- `/clear` — limpiar contexto si la sesión se vuelve muy larga
- `/init` — regenerar CLAUDE.md (no lo uses, ya está armado a mano)
- `/help` — ayuda

### Cuando termines Fase 1

Volvé a este documento y armamos el prompt de Fase 2 (multi-portal + oportunidades).
