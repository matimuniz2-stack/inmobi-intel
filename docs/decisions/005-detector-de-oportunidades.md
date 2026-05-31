# 005 — Detector de oportunidades: modelo de scoring

**Estado**: aceptada
**Fecha**: 2026-05-31

## Contexto

El detector de oportunidades es una de las dos features críticas del producto
(CLAUDE.md): cada mañana, una lista curada de propiedades que matchean al menos
una señal de oportunidad, con **score 0-100 y razones en lenguaje natural**. Hasta
ahora no existía (`opportunity/` estaba vacía).

Las 4 señales del plan son: bajo precio, baja reciente, mucho tiempo publicada,
urgencia en el texto. Dos restricciones de datos importantes al arrancar:

1. El schema no guardaba historial de precios (el upsert pisaba el precio), así que
   "baja reciente" no tenía de dónde leer.
2. Los scrapers parsean **páginas de listado**, no de detalle: nunca persistían
   `description` (queda NULL) ni `title` (se parseaba y se descartaba). Sin texto,
   "urgencia" no tenía combustible.

## Decisión

**Scorer en Python, puntaje persistido, que corre después del scrape.** Encaja con
"cada mañana lista curada" y con la estructura objetivo (`opportunity/scorer.py`).

- **Lógica pura y testeable** (`opportunity/scorer.py`): el reloj se inyecta, sin
  I/O, como los parsers. 21 tests con fixtures. La cáscara de DB
  (`opportunity/repository.py`) y el CLP (`opportunity/__main__.py`, `python -m
  opportunity`) quedan separados. Dependencia opportunity → scrapers, nunca al revés.
- **Cohortes para "bajo precio"**: US$/m² contra la **mediana** (robusta a outliers)
  de comparables del **mismo barrio** (operación, tipo, ciudad, `neighborhood`), no de
  toda la ciudad. **Solo APT** (casas/terrenos tienen US$/m² muy ruidoso porque el lote
  pesa más que lo construido). Mínimo 8 comparables. Dispara entre **10% y 30%** debajo;
  un descuento >30% casi siempre es dato malo o no comparable y no se marca. Excluye
  barrios catch-all ("Otros Barrios", neighborhood = ciudad).
  > Esto se ajustó **validando contra datos reales** antes de poblar: cohortear por
  > ciudad (la versión inicial usaba `zone_slug`, que en MdP es el catch-all
  > "mar-del-plata") generaba ~1395 oportunidades, muchas falsas (un depto de un barrio
  > barato marcado "60% bajo la mediana de la ciudad"). Cohortear por barrio + APT +
  > banda 10-30% lo bajó a ~333 confiables. Principio "data correcta pesimista".
- **Historial de precios** (tabla `price_history`): el upsert inserta un punto sólo
  cuando el precio se mueve respecto de la última observación. La migración hace un
  backfill idempotente del precio actual (fechado en `first_seen_at`) para que la
  señal de baja tenga una referencia desde el día uno.
- **`title` persistido**: el card ya lo traía en los 3 portales; ahora se guarda y
  la señal de urgencia lo lee (regex de términos fuertes/débiles, sin acentos).
  `description` se sumará cuando scrapeemos páginas de detalle (futuro).
- **Pesos** (topes por señal): bajo precio 45, baja reciente 30, mucho tiempo 15,
  urgencia 20. Score = suma capeada a 100. Mínimo 15 para listar. Las razones se
  ordenan por peso (la más fuerte primero) y citan números/frases concretas
  (principio #4, explicabilidad).
- **Persistencia** (`opportunities`, 1-1 con `Property`): upsert por `property_id`
  + borrado de las que dejaron de calificar. Idempotente. La app lee de acá
  (router tRPC `opportunities.list`, página `/oportunidades`).
- El scorer corre al final de `scrape-all.ps1` (tarea local) y como step del cron de
  GHA. Como sólo toca la DB (no portales), refresca oportunidades aun los días que
  el datacenter IP bloquea los 3 scrapers.

## Alternativas consideradas

- **Calcular en la query (TypeScript) en vez de persistir**: siempre fresco, sin
  tabla extra, pero las cohortes + razones por request chocan con el principio de
  <200ms y con "lista curada de la mañana". Descartado para v1.
- **Comparar por precio absoluto en vez de US$/m²**: más simple pero injusto entre
  tamaños. US$/m² normaliza y deja la cohorte más grande.
- **Media en vez de mediana**: la media se va con un par de avisos de lujo o de
  data sucia. Mediana + recorte de descuentos absurdos es más robusto.
- **Scrapear detalle ahora para tener `description`**: 2000+ páginas extra, rate
  limits y anti-bot por página. Demasiado para esta sesión; la urgencia ya arranca
  con `title`. Queda como mejora.

## Consecuencias

- ✅ La feature crítica existe end-to-end: schema → scrapers → scorer → API → UI.
- ✅ Explicable: cada oportunidad trae razones en español que el usuario le lee al
  cliente.
- ⚠️ **Bootstrap**: hoy las que tienen dientes son "bajo precio" (con cohorte
  suficiente) y "urgencia" (vía title). "baja reciente" se activa cuando el historial
  acumule cambios; "mucho tiempo" cuando los avisos lleven >60 días detectados
  (empezamos a scrapear a mediados de mayo). El scorer ya las calcula bien; ganan
  fuerza con el tiempo. No es un bug, es falta de historia.
- ⚠️ El umbral "mucho tiempo" mide desde que **nosotros** vimos el aviso, no desde
  su publicación real en el portal. Se podría mejorar capturando la antigüedad del
  aviso si el portal la expone.
- ✅ **Live en prod** (2026-05-31): migración aplicada a Supabase (vía SQL Editor, no
  `migrate deploy` — el `_prisma_migrations` no la registra, marcar con `migrate resolve
  --applied` cuando haya creds), página deployada (`vercel --prod`), y **333 oportunidades
  pobladas**. El scorer Python no se pudo correr (la contraseña de la DB está oculta en
  Vercel como "Sensitive"; resetearla rompe la app — el dueño lo pausó), así que el
  bootstrap de oportunidades se hizo con un INSERT SQL que replica la lógica de
  `signal_low_price`. El código Python ya quedó alineado con esa lógica (cohorte por
  barrio) para que el scoreo diario, cuando corra, no regrese a la versión ruidosa.
- ⚠️ **v1 limitado, ser honesto con el dueño**: hoy solo la señal "bajo precio", solo
  departamentos, solo barrios definidos. US$/m² no captura estado/antigüedad/piso, así
  que algunas de las 333 son baratas por una razón (no gangas) — el agente filtra con
  criterio (la razón explica exactamente qué es). Casas/terrenos (otra metodología) y
  las otras 3 señales (ganan datos con el tiempo) son trabajo futuro.
