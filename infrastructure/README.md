# Infrastructure

Servicios locales para desarrollo levantados con Docker Compose.

## Servicios

- **postgres**: PostgreSQL 16 + PostGIS 3.4 (imagen `postgis/postgis:16-3.4`)
  - Puerto: `5432`
  - User/pass: `inmobi` / `inmobi_dev`
  - Database: `inmobi_intel`
  - Volumen persistente: `inmobi-pg-data`

> La extensión PostGIS viene preinstalada pero **no se habilita** en Fase 1. Se activa cuando agreguemos la vista mapa (Fase 2/3).

## Comandos rápidos

Desde la raíz del monorepo:

```bash
pnpm db:up      # levanta postgres en background
pnpm db:logs    # sigue los logs
pnpm db:down    # detiene el servicio (preserva volumen)
pnpm db:reset   # detiene + borra volumen + vuelve a levantar (CUIDADO: data se pierde)
```

## Connection string para Prisma / scrapers

```
postgresql://inmobi:inmobi_dev@localhost:5432/inmobi_intel
```
