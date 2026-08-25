# 011 — Desactivación de avisos caídos (T14)

**Fecha**: 2026-08-12 (criterio revisado 2026-08-25)
**Estado**: aceptada

## Contexto

El UPSERT de los scrapers crea/actualiza propiedades y las revive
(`is_active = true`) cuando reaparecen, pero nada las desactivaba: la DB tenía
20.829 propiedades, todas activas, con 12.181 sin verse hace más de 30 días.
El mapa y la búsqueda mostraban avisos vendidos/retirados hace semanas (el
usuario lo notó en /mapa). Era el T14 del megaplan, diferido porque necesitaba
DB en vivo.

## Decisión

Nuevo CLI `python -m deactivate` (espejo de `-m geocode` / `-m opportunity`),
cableado en `scrape-all.ps1` después del scrape y **antes** del scorer.

Criterio (revisado 2026-08-25): se desactiva una propiedad sólo si

1. su par `(portal, zone_slug)` tiene al menos un `scrape_job` **SUCCEEDED con
   `items_found > 0`**, y
2. `last_seen_at` es anterior a **`max(completed_at)` de ese último job exitoso
   menos N días** (default N=7).

Es decir: *"la última vez que miramos esa zona, el aviso ya llevaba más de N
días sin aparecer"*. Zonas bloqueadas (DataDome), nunca corridas (CABA hoy no
entra en `scrape-all`) o que devolvieron 0 items no desactivan nada — ante la
duda, la propiedad queda viva. No hay hard delete (regla del proyecto): sólo
`is_active = false`, y el UPSERT la revive si reaparece.

**Por qué se comparó contra el último job y no contra `now()`** (revisión
2026-08-25): el criterio original exigía un job exitoso *dentro de los últimos
N días*, lo que lo ataba a la cadencia. En la práctica las corridas fueron
espaciadas (semanas) y las tres posteriores al cableado se interrumpieron antes
de llegar al paso de desactivación, así que **nunca corrió** y se acumularon
~15.600 avisos muertos activos (el usuario los veía en la app). Comparar contra
la fecha del último scrape exitoso de cada zona hace el criterio independiente
de la cadencia: se puede correr suelto en cualquier momento y una corrida vieja
sigue sirviendo de evidencia. Además `scrape-all.ps1` ahora corre el paso **dos
veces**: una pasada temprana al inicio (salda la deuda de la corrida anterior
aunque la nueva se corte a la mitad) y la pasada normal post-scrape. Primera
ejecución real 2026-08-25: 15.642 desactivadas (ML 8.266, AP 5.134, ZP 2.242),
7.406 quedaron activas.

## Trade-off aceptado

En zonas donde el portal capea resultados (Argenprop ~200 por zona/op/tipo),
un aviso vigente pero más allá del cap deja de verse y termina desactivado.
Preferimos ocultar un aviso vivo que no podemos verificar antes que mostrar
cientos de avisos muertos (principio: "data correcta pesimista > data
optimista incorrecta"). La palanca real contra esto es más partición
(ambientes/precio), no aflojar la desactivación.

## Alternativas descartadas

- **Verificar cada URL (HEAD/GET)**: preciso pero ~20k requests extra por
  corrida contra portales con WAF; caro y frágil.
- **Desactivar por umbral global de `last_seen_at` sin mirar `scrape_jobs`**:
  una noche bloqueada desactivaría media DB.
- **Hard delete**: prohibido por convención (se pierde `price_history`).
