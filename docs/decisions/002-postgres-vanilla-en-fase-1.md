# 002 — Postgres vanilla en Fase 1, PostGIS llega después

**Estado**: aceptada
**Fecha**: 2026-05-27

## Contexto

CLAUDE.md mencionaba "PostgreSQL + PostGIS" como stack. En M1 elegí la imagen `postgis/postgis:16-3.4`.

Al correr `prisma migrate dev` en M2, Prisma se quedaba pidiendo confirmación de "reset" porque la imagen precarga decenas de tablas (`tiger.*`, `topology.*`, `public.spatial_ref_sys`) en su init script. No-interactivo en CI también rompía.

## Decisión

**Usar `postgres:16-alpine` (vanilla) hasta que necesitemos PostGIS en serio (vista mapa, búsqueda por radio).** Cuando llegue ese momento:

1. Cambiar la imagen a `postgis/postgis:16-3.4` en `docker-compose.yml`.
2. Agregar una migration de Prisma con `CREATE EXTENSION IF NOT EXISTS postgis;`.
3. Migrar columnas `lat` / `lng` (hoy `Decimal`) a `geography(Point, 4326)` o a un campo PostGIS dedicado.

## Alternativas consideradas

- **Excluir las tablas precargadas del schema introspect de Prisma**: posible vía `multiSchema` o filtros, pero complica el setup y agrega ruido.
- **Eliminar el init script de PostGIS dentro de la imagen**: requiere mantener nuestra propia variante de la imagen.

## Consecuencias

- ✅ `prisma migrate dev` corre sin prompts en local y CI.
- ✅ Imagen Alpine es mucho más liviana (~80MB vs ~850MB).
- ⚠️ La columna `lat`/`lng` queda como `Decimal(9,6)` y no se puede indexar geográficamente todavía. Para Fase 1 alcanza (no hay queries por radio).
- ⚠️ Hay que recordar habilitar la extensión cuando llegue el momento. Ver issue/TODO en M de mapa.
