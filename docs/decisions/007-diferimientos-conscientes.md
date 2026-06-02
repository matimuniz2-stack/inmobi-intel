# 007 — Diferimientos conscientes (qué NO construimos todavía y por qué)

> Estado: vigente · Fecha: 2026-06-01 · Contexto: auditoría + mega-plan nocturno (ver `docs/plans/overnight-2026-06-01-megaplan.md`).

La auditoría del 2026-06-01 confirmó varias piezas del plan maestro que todavía no
existen. Para que no parezcan olvidos, las documentamos acá con su razón y la fase
objetivo. Principio rector: **sin overengineering** — no construir lo que no se usa
todavía, pero dejar registrado el porqué.

## Diferido a propósito

| Pieza | Por qué se difiere | Cuándo |
|---|---|---|
| **PostGIS / lat-lng como geometría** | `lat`/`lng` se mantienen como `Decimal` simples. PostGIS sólo aporta cuando exista la **vista mapa**; activarlo antes es complejidad muerta. | Cuando se construya la vista mapa (Fase 3). |
| **`zone_price_stats` (pricing engine materializado)** | El scorer calcula cohortes on-the-fly y alcanza para el volumen actual. Una tabla materializada de stats de zona sólo se justifica cuando la **búsqueda reversa** necesite mostrar "X% vs mediana" en caliente o cuando el dataset crezca lo suficiente para que el cálculo on-the-fly sea lento. | Cuando la búsqueda lo necesite / medición de `<200ms` (T23) lo exija. |
| **`saved_searches` + alertas por email** | Requieren un modelo de usuario primero (hoy no hay auth real — ver T22). | Fase 3, después de auth. |
| **Export a Excel / PDF (ficha para el cliente)** | Feature de presentación; no bloquea las 2 funciones críticas. | Fase 3. |
| **Vista mapa (Leaflet + OSM, clusters)** | Depende de tener lat/lng poblados (hoy no se persisten) y de dedup para no clusterizar duplicados. | Después de persistir geo (T11) + dedup (T15). |
| **Tag "ya está en nuestra base" (match con CRM Zamboni)** | Depende de integrar el CRM externo de Zamboni — dependencia fuera de este repo. | Cuando se defina la integración con el CRM. |
| **Dedup cross-portal** | Es pre-requisito de escalar volumen (lo exigen los 3 jueces del mega-plan). Necesita un esquema de `listing_group_id` + una migración aplicada a una DB. Se hace cuando haya acceso a una DB para aplicar y validar la migración (no a ciegas). | Próxima sesión con DB (T15). |
| **`rooms` separado de `bedrooms`** | Hoy `bedrooms` mezcla ambientes y dormitorios. Separarlos necesita migración de schema + re-scrape para poblar. Se hace junto con la próxima ventana de DB. | Próxima sesión con DB (T13). |

## Por qué "cuando haya DB" y no ahora

El trabajo de la noche del 2026-06-01 se hizo en una rama (`overnight/cobertura-calidad-2026-06-01`)
sin Postgres local levantado y sin tocar la DB de prod (Supabase). Las migraciones de
Prisma (T13 `rooms`, T15 `listing_group_id`) **se escriben y aplican cuando hay una DB
para correrlas y verificarlas** — shipear una migración sin poder aplicarla viola el
principio "data correcta pesimista > optimista incorrecta".

Ver el mega-plan para el detalle de cada tarea (T1–T32) y la secuencia.
