# Inmobi Intel

App interna de inteligencia inmobiliaria para Mar del Plata + CABA. Dos funciones críticas:

1. **Búsqueda reversa multi-portal** — el cliente busca algo que no tenemos en stock, tiramos filtros, vemos todas las propiedades del mercado con la inmobiliaria que las tiene.
2. **Detector de oportunidades** — lista diaria de propiedades con score 0-100 y razones explicadas.

Contexto completo en [`CLAUDE.md`](./CLAUDE.md). Plan maestro en [`../plan-app-scraper-inmobiliario.md`](../plan-app-scraper-inmobiliario.md).

---

## Estructura del repo

```
app-inmobi/
├── apps/
│   ├── web/          # Next.js 14 + tRPC (frontend + API) — M4
│   └── scrapers/     # Python + Poetry (workers de scraping) — M3
├── packages/
│   ├── db/           # Prisma schema + cliente — M2
│   └── shared-types/ # Zonas + tipos compartidos — M2
├── infrastructure/   # docker-compose para dev local
├── docs/
│   └── decisions/    # ADRs livianos
└── CLAUDE.md         # contexto persistente del proyecto
```

---

## Requisitos

| Tool | Versión mínima |
|------|----------------|
| Node | 20+ (recomendado 22) |
| pnpm | 10+ |
| Docker | con Compose v2 |
| Python | 3.11+ (a partir de M3) |
| Poetry | 1.8+ (a partir de M3) |
| git | 2.x |

> **Windows + OneDrive**: el repo vive en una carpeta sincronizada con OneDrive. Si ves problemas de file locking al instalar `node_modules`, pausá la sincronización mientras trabajás, o movemos el repo más adelante.

> **Puerto Postgres**: usamos `5433` (no `5432`) para no chocar con otros proyectos locales (ej. `zamboni-postgres`).

---

## Bootstrap (Fase 1, M1)

```bash
# 1. Cloná / posicionate en el directorio
cd app-inmobi

# 2. Levantá Postgres local
pnpm db:up

# 3. Copiá las env vars de ejemplo
cp .env.example .env

# 4. Verificá que Postgres está sano
docker exec inmobi-postgres pg_isready -U inmobi -d inmobi_intel
# → /var/run/postgresql:5432 - accepting connections
```

A partir de acá, cada milestone agrega su parte. Mirá la sección **Estado actual** abajo.

---

## Comandos comunes

```bash
# Infra
pnpm db:up        # levanta postgres en background
pnpm db:logs      # sigue los logs
pnpm db:down      # detiene el servicio (preserva volumen)
pnpm db:reset     # destruye y recrea el volumen (CUIDADO)

# Schema / DB
pnpm db:generate  # regenera el Prisma Client (cuando cambia schema.prisma)
pnpm db:migrate   # crea + aplica una migration nueva (dev)
pnpm db:studio    # abre Prisma Studio en el browser

# Zonas (config-driven)
pnpm zones:resolve            # llena mlStateId/mlCityId/mlNeighborhoodId desde la API de ML
pnpm zones:resolve -- --force # fuerza re-resolución incluso si ya estaban

# Workspace
pnpm typecheck    # tsc --noEmit en todos los packages
pnpm format       # prettier --write
pnpm format:check
```

---

## Estado actual

**Fase 1 en curso** — milestones:

- [x] **M1**: monorepo + docker-compose
- [x] **M2**: schema Prisma + 52 zonas resueltas (MdP region + 48 barrios CABA)
- [x] **M3**: scraper MercadoLibre con Playwright + cotización USD blue
- [x] **M4**: frontend Next.js + tRPC + búsqueda reversa funcional
- [x] **M5**: workflows GitHub Actions (cron diario + CI typecheck/tests)
- [ ] **M6**: deploy a Supabase + Vercel

Mirá [`CLAUDE.md`](./CLAUDE.md) para el plan completo de fases.

---

## GitHub Actions

Dos workflows en `.github/workflows/`:

- **`ci.yml`** — corre en cada push/PR. Hace `pnpm install`, `prisma generate`, `pnpm typecheck` + `pytest` del scraper. ~2 min.
- **`scrape-daily.yml`** — cron a las **3am ART** (6:00 UTC). Levanta Chromium, scrapea MdP venta+alquiler, guarda log como artifact y corre smoke test. También se dispara manualmente desde la pestaña Actions con inputs personalizados (zona, ops, limit).

Para activar el cron hace falta configurar el secret **`DATABASE_URL`** en GitHub Settings → Secrets → Actions (apunta a la DB de Supabase que se crea en M6).

```bash
# Disparar manualmente desde CLI:
gh workflow run scrape-daily.yml -f zone=mar-del-plata -f ops=SALE

# Ver el log:
gh run list --workflow scrape-daily.yml
gh run view <run-id> --log
```

## Convenciones

Convenciones de código, commits y arquitectura están en [`CLAUDE.md`](./CLAUDE.md).
