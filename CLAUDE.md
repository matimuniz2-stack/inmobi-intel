# Inmobi Intel — Project Context

> Este archivo le da contexto persistente a Claude Code sobre el proyecto. Léelo siempre al inicio de cada sesión.

---

## Qué es esto

**Inmobi Intel** es una app interna para una operación inmobiliaria que opera en **Mar del Plata + alrededores y CABA**. Tiene dos funciones críticas:

1. **Búsqueda reversa multi-portal**: cuando un cliente busca algo que la inmo no tiene en stock, el usuario tira filtros (zona, ambientes, precio, venta/alquiler) y la app devuelve propiedades de todos los portales (ZonaProp, Argenprop, MercadoLibre, Properati, etc.) identificando claramente qué inmobiliaria tiene cada una. Salva el cliente que se cae.

2. **Detector de oportunidades**: cada mañana, una lista curada de propiedades nuevas o actualizadas que matchean al menos una señal de oportunidad (bajo precio, baja reciente, mucho tiempo publicada, urgencia en el texto). Cada oportunidad viene con **score 0-100 y razones explicadas en lenguaje natural**.

El plan completo del proyecto está en `../plan-app-scraper-inmobiliario.md`. Léelo si necesitás contexto profundo.

---

## Zonas de cobertura

### Mar del Plata + alrededores
- **Barrios MdP** (no exhaustivo): Centro, La Perla, Playa Grande, Playa Chica, Constitución, Los Troncos, Stella Maris, Caisamar, San Carlos, Pinares, Chauvin, Punta Mogotes, Punta Iglesia, La Florida, Sierra de los Padres
- **Periferia**: Mar Chiquita, Santa Clara del Mar, Camet, Estación Camet, Mar de Cobo, Santa Elena
- **Particularidades del mercado MdP**:
  - Fuerte estacionalidad (alquiler temporario de verano es enorme)
  - Premium por cercanía al mar
  - Dinámica de precios distinta a CABA (más USD-centric en venta, más ARS en alquiler permanente)
  - Inmobiliarias locales fuertes (no todas usan los grandes portales)

### CABA
- Todas las comunas y barrios de la Ciudad Autónoma de Buenos Aires
- Coverage estándar en los portales grandes

---

## Stack técnico

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 14+ (App Router) + TypeScript + Tailwind + shadcn/ui |
| API | Next.js API Routes + tRPC para type-safety end-to-end |
| Base de datos | PostgreSQL + extensión PostGIS (para geo) |
| ORM | Prisma (o Drizzle si preferís más control sobre SQL) |
| Hosting DB | Supabase |
| Scrapers | Python 3.11+ + Playwright + Scrapy + BeautifulSoup |
| Queue | BullMQ (Node) o Celery + Redis para Python |
| Cache | Upstash Redis |
| Hosting frontend | Vercel |
| Hosting scrapers | Railway o VPS Hetzner (necesitan correr fuera de Vercel por timeouts) |
| Tipo de cambio | API pública de dolarapi.com (gratis) |

---

## Principios de diseño

1. **Velocidad es feature**: búsquedas en <200ms. Usuario está sentado con cliente al lado.
2. **Confiabilidad sobre vanidad**: prefiero data correcta pesimista que data optimista incorrecta.
3. **Resiliencia ante cambios de portales**: cada scraper debe tener tests automáticos que validen extracción de campos clave.
4. **Explicabilidad**: ningún score sin razones. El usuario tiene que poder explicarle a su cliente por qué algo es oportunidad.
5. **Mobile-first real**: el flujo crítico (búsqueda reversa) tiene que funcionar genial en celular, no solo "no romperse".
6. **Sin overengineering**: no construir features que no se van a usar. Empezar simple, iterar con uso real.

---

## Estructura del proyecto (objetivo)

```
app-inmobi/
├── CLAUDE.md                      # este archivo
├── README.md                      # cómo correr el proyecto
├── apps/
│   ├── web/                       # Next.js app (frontend + API routes)
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── package.json
│   └── scrapers/                  # workers Python
│       ├── scrapers/
│       │   ├── mercadolibre.py
│       │   ├── argenprop.py
│       │   ├── zonaprop.py
│       │   └── base.py
│       ├── pricing/
│       │   └── engine.py
│       ├── opportunity/
│       │   └── scorer.py
│       ├── normalize/
│       │   └── deduplicator.py
│       └── pyproject.toml
├── packages/
│   ├── db/                        # schema + migrations + Prisma client
│   │   ├── prisma/
│   │   │   └── schema.prisma
│   │   └── package.json
│   └── shared-types/              # tipos compartidos entre web y scrapers
├── docs/
│   ├── KICKOFF-PROMPT-FASE-1.md   # prompt inicial para Claude Code
│   └── scrapers/                  # documentación de cada scraper
└── infrastructure/
    ├── docker-compose.yml          # para dev local con Postgres + Redis
    └── README.md
```

---

## Convenciones de código

### TypeScript / Next.js
- TypeScript estricto (`strict: true`)
- Server Components por default, Client Components solo cuando hace falta
- Nombres en inglés (variables, funciones, componentes); UI en español
- Imports absolutos con alias `@/`
- Componentes en PascalCase, funciones en camelCase, archivos en kebab-case

### Python (scrapers)
- Python 3.11+
- `ruff` para linting + formatting
- Type hints obligatorios
- `pydantic` para validación de datos extraídos
- Cada scraper hereda de una clase base `BaseScraper` con interfaz común

### Base de datos
- Todos los precios se guardan en su moneda original + un campo derivado `price_usd_normalized`
- Timestamps siempre en UTC, conversión en el frontend
- Soft delete (campo `is_active`), nunca hard delete de propiedades

### Commits
- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
- Mensajes en español o inglés, consistencia por sesión

---

## Comandos comunes

```bash
# Web app (desde apps/web/)
pnpm dev                    # arrancar dev server
pnpm build                  # build de producción
pnpm test                   # tests

# Scrapers (desde apps/scrapers/)
poetry install              # instalar deps
poetry run python -m scrapers.mercadolibre --zone "mar-del-plata"
poetry run pytest           # tests

# DB (desde packages/db/)
pnpm prisma migrate dev     # crear migration nueva
pnpm prisma studio          # GUI para inspeccionar la DB

# Infrastructure
docker-compose up -d        # arrancar postgres + redis localmente
```

---

## Fase actual

**Fase 1 — MVP**: scraper de MercadoLibre + búsqueda reversa funcional end-to-end.

Progreso:
- [x] **M1** — monorepo + docker-compose
- [x] **M2** — schema Prisma + 52 zonas (MdP region + 48 barrios CABA) resueltas contra ML
- [x] **M3** — scraper MercadoLibre con Playwright + dolar blue + tests con fixtures
- [x] **M4** — frontend Next.js 15 + tRPC + búsqueda reversa con 5 filtros + mobile-first
- [x] **M5** — workflows GitHub Actions (CI + cron diario 3am ART con smoke test)
- [ ] **M6** — deploy Supabase + Vercel

Decisiones técnicas tomadas durante Fase 1: ver `docs/decisions/`.

Plan completo en `../plan-app-scraper-inmobiliario.md`. Fases siguientes documentadas ahí.

---

## Cosas a NO hacer (para evitar fricción)

- No agregues frameworks nuevos sin justificación clara.
- No optimices prematuramente — primero hacelo funcionar, después medilo, después optimizalo.
- No metas autenticación compleja en Fase 1, alcanza con auth básica de Supabase.
- No intentes scrapear ZonaProp en Fase 1 — eso es Fase 2 cuando tengamos infra de proxies.
- No publiques datos scrapeados a terceros ni los uses para nada que no sea uso interno.
- No te metas a hacer features pedidos por el dueño que no estén en el plan sin avisar primero.

---

## Cosas a SÍ hacer

- Si encontrás una decisión técnica que no está acá, **decidí y documentala** en este CLAUDE.md o en `docs/decisions/`.
- Si una librería que usábamos quedó obsoleta, sugerí reemplazo.
- Si un scraper se rompe, escribí un test que repro el caso antes de arreglarlo.
- Cuando completes una feature, actualizá la sección "Fase actual" de este archivo.
- Si el dueño te pide algo fuera del scope, recordale el plan amablemente y proponé agregarlo como Fase futura.

---

## Contacto y dueño del proyecto

- **Dueño**: Mati
- **Cliente final del producto**: equipo de inmobiliaria Zamboni (Mar del Plata + CABA)
- **Documentación viva**: este archivo + `../plan-app-scraper-inmobiliario.md`

---

> **Última actualización**: setup inicial. Actualizá esta nota cuando avancen fases.
