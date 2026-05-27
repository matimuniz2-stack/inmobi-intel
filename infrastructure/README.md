# Infrastructure

Servicios locales para desarrollo levantados con Docker Compose.

## Servicios

- **postgres**: PostgreSQL 16 Alpine (imagen `postgres:16-alpine`). PostGIS llega cuando lo necesitemos para vista mapa (Fase 2/3).
  - Puerto host: `5433` (mapeado al `5432` interno; cambiado para no chocar con otros proyectos que ya usen 5432 en localhost)
  - User/pass: `inmobi` / `inmobi_dev`
  - Database: `inmobi_intel`
  - Volumen persistente: `inmobi-pg-data`

> PostGIS no se incluye en Fase 1. Al habilitar vista mapa (Fase 2/3) cambiamos a `postgis/postgis:16-3.4` y agregamos la extensión en una migration.

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
postgresql://inmobi:inmobi_dev@localhost:5433/inmobi_intel
```
