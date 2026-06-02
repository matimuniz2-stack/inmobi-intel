# 006 — Calidad/estado en el detector de oportunidades

**Estado**: en progreso (Nivel 1 arrancado)
**Fecha**: 2026-05-31

## Contexto

El dueño planteó el límite de fondo del v1 (señal "bajo precio"): **barato por m² no
es lo mismo que oportunidad**. Dos deptos de 2 ambientes en el mismo barrio, mismos m²
y prestaciones, pueden tener precios muy distintos porque uno es un edificio a refaccionar
y el otro está a estrenar. El barato **no es ganga**: está bien de precio para su estado.
El US$/m² no ve estado / antigüedad / piso / orientación.

## Decisión

Atacarlo en dos niveles. El detector nunca va a afirmar "esto ES una ganga" solo: su
trabajo es **achicar de miles a un puñado de candidatos, con el contexto al lado**, para
que un humano (o la IA del Nivel 2) cierre rápido.

### Nivel 1 — Capturar antigüedad + estado del aviso (en curso)
Inferir del texto y meterlo en el score/razón:
- **Antigüedad** ("50 años" vs "a estrenar") — explica la mayor parte de la variación de
  precio dentro de un barrio.
- **Estado** — "a refaccionar / a reciclar / a demoler" ⇒ la baja está **explicada por
  el estado**, no es ganga para entrar a vivir: **no se marca**. "a estrenar / reciclado /
  impecable" ⇒ señal más fuerte.
- **Piso / luz / amenities** (cochera, ascensor, balcón, contrafrente, planta baja) —
  futuro, completan el contexto.

Hecho hasta ahora (commit de esta sesión): `extract_condition(text)` en `scorer.py`
(antigüedad, a_estrenar, needs_work) + integrado en `signal_low_price` (excluye
needs_work, suma "A estrenar." / "Antigüedad ~N años." a la razón). 26 tests.

**Pendiente del Nivel 1 (la parte de datos):** hoy lee el `title`, que es la fuente más
pobre e incompleta (y para las propiedades ya scrapeadas está NULL hasta el próximo
scrape). El dato confiable y estructurado (antigüedad, estado, amenities, descripción
completa) está en la **página de detalle** de cada aviso. El plan es scrapear el detalle
**de los candidatos** (≈ las ~340 que dan oportunidad, no las 4800), porque ahí es donde
importa y es un scrape chico. Eso requiere parsers de detalle por portal (ML, Argenprop,
ZonaProp).

### Nivel 2 — IA de visión sobre las fotos (futuro)
La respuesta de fondo a "¿cómo verifico el estado sin ir?": una IA que mira las **fotos**
del aviso (las URLs ya las guardamos) y clasifica estado (a estrenar / reciclado / a
refaccionar / destruido). No es perfecta, pero descarta los casos obvios y afina el
ranking. El scrape de detalle del Nivel 1 además trae más fotos para esto.

## Alternativas consideradas

- **Cohortear por antigüedad** (comparar viejo-vs-viejo): mejor aún, pero necesita la
  antigüedad cargada en toda la cohorte (todo el barrio), no sólo el candidato → depende
  del scrape de detalle masivo. Por ahora se usa la antigüedad del candidato como contexto.
- **Excluir vs etiquetar "a refaccionar"**: hoy se excluye (el usuario default busca para
  entrar a vivir). Futuro: categoría aparte "para refaccionar" para el perfil inversor/flip.

## Consecuencias

- ✅ "Barato porque está para refaccionar" deja de aparecer como ganga; "barato Y a
  estrenar" se distingue como la señal fuerte. Más confiabilidad, menos falsos positivos.
- ⚠️ El v1 de la lógica está construido pero **dormido** hasta que haya texto (el `title`
  del próximo scrape; o el scrape de detalle). No cambia las ~338 actuales hasta entonces.
- ⚠️ El Nivel 1 "completo" (datos de detalle) y el Nivel 2 (visión) son trabajo de scraping
  e IA todavía por hacer. El detector seguirá necesitando criterio humano sobre el candidato.

## Actualización 2026-06-01 — "a refaccionar": haircut en vez de exclusión

Revisado en el mega-plan nocturno (T19 / D5). Antes, "a refaccionar" **suprimía** del todo
la señal de bajo precio. Cambio: ahora **no se suprime** — se le aplica un *haircut* (mitad
de puntos, `NEEDS_WORK_HAIRCUT = 0.5`) y la razón lo aclara ("parte del precio bajo se
explica por el estado"). Motivo: un depto 20% bajo mediana a refaccionar **sigue siendo
negocio** para un inversor/flip; suprimirlo le esconde oportunidades reales al agente. El
default por entrar-a-vivir lo da el contexto en la razón, no la supresión. **D5 resuelta: el
dueño confirmó el haircut el 2026-06-01.** Ver `signal_low_price` en `scorer.py`.
