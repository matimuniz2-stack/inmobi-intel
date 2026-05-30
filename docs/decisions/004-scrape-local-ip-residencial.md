# 004 — Scrape desde IP residencial local en vez de proxies pagos

**Estado**: aceptada
**Fecha**: 2026-05-30

## Contexto

El cron de GitHub Actions (`scrape-daily.yml`) corre desde IPs de **datacenter**. Los tres portales bloquean ese rango de forma intermitente. Verificado en el run manual #5 (2026-05-30), los tres devolvieron 0 ítems en la misma corrida:

- **ZonaProp**: `datadome_challenge ... status=403` (bloqueo explícito de DataDome).
- **MercadoLibre**: `page_did_not_render_listings html_size=33907` (bot-wall / interstitial).
- **Argenprop**: `no_cards_break html_size=923` (página vacía).

El dueño no quiere pagar proxies residenciales (la opción de Fase 2, ~USD 30-80/mes).

Observación clave: el mismo scraper, corrido desde la **IP residencial** de la máquina del dueño, pasa sin problemas (dry-run 2026-05-30: ML found=100, Argenprop found=40, ZonaProp found=55, **cero DataDome**). El unlock que dan los proxies residenciales —una IP residencial— ya está disponible gratis: la de casa.

## Decisión

**El scrapeo confiable corre como tarea programada local en la máquina del dueño, contra Supabase.** El cron de GitHub Actions se mantiene como best-effort gratuito (puebla data los días que la IP no está bloqueada).

- `apps/scrapers/scripts/scrape-all.ps1`: corre los 3 portales secuencialmente. Lee el `DATABASE_URL` de Supabase desde `apps/scrapers/.env.production.local` (gitignored), así el password nunca entra al repo. Soporta `-DryRun` para probar el pipeline sin escribir. Exit 0 si al menos un portal trajo data, 1 si todos volvieron vacíos.
- `apps/scrapers/scripts/register-scrape-task.ps1`: registra la tarea diaria `InmobiIntel-ScrapeDaily` (one-time). Con `StartWhenAvailable` para que, si la PC estaba apagada a la hora pactada, corra al próximo arranque — no depende de tener la máquina prendida a una hora exacta.
- Observabilidad (commit 581030f): cada scraper sale con código ≠0 (`EXIT_SCRAPED_NOTHING=3`) si scrapeó 0 ítems, para que un bloqueo no se disfrace de corrida verde.

## Alternativas consideradas

- **Proxies residenciales pagos** (Fase 2): la solución de fondo y la más robusta, pero el dueño descartó el costo por ahora. Queda como upgrade futuro si la corrida local se vuelve molesta.
- **Self-hosted GitHub Actions runner** en la máquina del dueño: daría la IP residencial manteniendo el workflow, pero el repo es **público** y un runner self-hosted en repo público es un agujero de seguridad conocido (un PR de un fork puede ejecutar código arbitrario en la máquina). Descartado.
- **Dejar solo el cron de GHA**: inaceptable como única fuente — falla de forma intermitente y silenciosa.

## Consecuencias

- ✅ Costo: $0. Usa la IP residencial que ya tenemos.
- ✅ Confiabilidad alta: validado que los 3 portales pasan desde la IP de casa.
- ✅ La data va a Supabase, la misma DB que lee la app en Vercel.
- ⚠️ Depende de que la PC del dueño se prenda al menos una vez al día. Mitigado con `StartWhenAvailable` (corre al próximo boot si se saltó).
- ⚠️ Setup manual una vez: crear `.env.production.local` con el string de Supabase + correr `register-scrape-task.ps1`. Documentado en el `.env.production.local.example`.
- ⚠️ Específico de Windows (Task Scheduler). Si se migra a otra máquina/SO, hay que rehacer la tarea (el runner en sí es portable salvo la parte de scheduling).
