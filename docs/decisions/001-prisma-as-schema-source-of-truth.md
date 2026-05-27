# 001 — Prisma como fuente de verdad del schema

**Estado**: aceptada
**Fecha**: 2026-05-27

## Contexto

El proyecto tiene dos consumidores de la DB:

1. **Frontend / API** (`apps/web`, Next.js + TypeScript) — necesita type-safety end-to-end, lo más cómodo es Prisma Client.
2. **Scrapers** (`apps/scrapers`, Python) — escriben masivamente a `properties`, `scrape_jobs`, `usd_rates`.

Hay que decidir cómo coexisten.

## Decisión

**El schema vive en `packages/db/prisma/schema.prisma`. Es la única fuente de verdad.**

- Las migrations se generan con `prisma migrate` y se commitean en `packages/db/prisma/migrations/`.
- `apps/web` consume el cliente tipado vía `@inmobi/db`.
- `apps/scrapers` (Python) usa **`psycopg` con SQL/Pydantic plano**. No usa Prisma Client Python (deprecado y poco mantenido). Mantiene un modelo Pydantic que espeja la tabla `properties`; cuando el schema cambia, se actualiza el modelo Python a mano.

## Alternativas consideradas

- **SQLAlchemy en Python + introspección desde Prisma**: doble fuente, fricción al sincronizar.
- **Prisma Client Python**: el proyecto está poco mantenido, no recomendado por su autor para producción nueva.
- **Schema en SQL puro, sin ORM**: más liviano pero pierde type-safety en el frontend.

## Consecuencias

- ✅ Type-safety end-to-end en TS sin trabajo extra.
- ✅ Una sola convención de migrations para todo el equipo.
- ⚠️ Los scrapers tienen que mantener su modelo Pydantic en sync a mano. Mitigación: tests de integración en M3 que insertan una fila real y validan que matchea Prisma.
- ⚠️ Si la migration cambia un nombre de columna o tipo, hay que actualizar el código Python en el mismo PR.
