# 003 — Playwright entra a Fase 1 (MercadoLibre cerró su API pública)

**Estado**: aceptada
**Fecha**: 2026-05-27

## Contexto

El kickoff y el plan maestro asumían que para Fase 1 alcanzaba con OAuth público de MercadoLibre (sin token). En M3 verificamos que:

- `/sites/MLA/search`, `/items/{id}`, `/sites/MLA`, `/trends/*` → todos devuelven `403 forbidden` sin Authorization.
- El error es `PA_UNAUTHORIZED_RESULT_FROM_POLICIES` (PolicyAgent), claramente intencional.
- Solo `/classified_locations/*` y `/categories/{id}` siguen abiertos (los usamos en M2 para resolver IDs).
- Las páginas HTML del frontend (`inmuebles.mercadolibre.com.ar`, `listado.mercadolibre.com.ar`) están detrás de CloudFront con WAF que devuelve `403` a `curl` con UA y headers de browser. Hace falta browser real para pasar.
- Argenprop y Properati también están detrás de WAF similar.

Sin acceso a la API ni a HTML simple, las únicas dos opciones reales son:
- Obtener credenciales OAuth de ML (requiere registro manual del usuario).
- Usar Playwright (browser headless) para scrapear el HTML evadiendo el WAF.

## Decisión

**Sumamos Playwright a Fase 1.** El usuario eligió esta opción para no depender de un paso de registro externo y mantener autonomía del scraper.

Detalles:
- `playwright` como dep main de `apps/scrapers`
- `playwright install chromium` como paso de bootstrap (documentado en README)
- Extracción: primero intentar leer el JSON embebido en la página (típicamente `window.MELI_INITIAL_STATE` o `__NEXT_DATA__`). Si no está disponible, parsear DOM con selectores estables (`data-testid`).
- Pagination: navegar a `?page=N` o seguir el link "Siguiente"
- Anti-bot: configurar UA real, viewport razonable, timeouts amplios. Sin proxies por ahora; si nos bloquean, revisamos en Fase 2.
- Performance esperada: ~5s por página, ~10 páginas por zona × 52 zonas × 2 operaciones = ~80 min por corrida full. OK para cron nocturno.

## Alternativas consideradas

- **OAuth de ML**: limpio, rápido a la corrida (<1 min para toda la cobertura), pero requiere acción manual del usuario para registrar la app. Si en Fase 2 el costo de mantener Playwright sube, volvemos a esta opción.
- **Cambiar de portal** (Argenprop/Properati): ambos también están detrás de WAF, no resuelve el problema.
- **Esperar y armar M3 mockeado**: Posponía el problema sin resolverlo y dejaba el frontend de M4 sin datos reales para testear.

## Consecuencias

- ✅ Scraper anda end-to-end sin acción manual del usuario.
- ✅ Cuando agreguemos ZonaProp/Argenprop en Fase 2, ya tenemos la infra de Playwright lista.
- ⚠️ Performance: 80 min por corrida nocturna vs <1 min con API. Aceptable para 1×/día.
- ⚠️ Fragilidad: si ML cambia el HTML, el scraper rompe. Mitigación: tests con fixtures HTML que detectan los breaks.
- ⚠️ Riesgo de bot-detection. Si nos bloquean, sumamos proxies en Fase 2 (~USD 30-80/mes para residenciales rotativos).
- ⚠️ Suma ~300MB al setup local (browser chromium) y al CI.
