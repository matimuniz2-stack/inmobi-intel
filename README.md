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

# Workspace (cuando haya código en los packages)
pnpm typecheck
pnpm lint
pnpm format       # prettier --write
pnpm format:check
```

---

## Estado actual

**Fase 1 en curso** — milestones:

- [x] **M1**: monorepo + docker-compose
- [ ] **M2**: schema Prisma + zonas config-driven
- [ ] **M3**: scraper MercadoLibre + cotización USD
- [ ] **M4**: frontend Next.js con búsqueda reversa
- [ ] **M5**: cron diario en GitHub Actions
- [ ] **M6**: deploy a Supabase + Vercel

Mirá [`CLAUDE.md`](./CLAUDE.md) para el plan completo de fases.

---

## Convenciones

Convenciones de código, commits y arquitectura están en [`CLAUDE.md`](./CLAUDE.md).
