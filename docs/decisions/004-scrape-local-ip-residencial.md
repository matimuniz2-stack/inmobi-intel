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
- ⚠️ **SPOF físico**: toda la pipeline confiable depende de UNA PC Windows personal. Si esa máquina muere, el ingest se corta hasta rehacer el setup en otra (runbook abajo). El heartbeat (ver más abajo) convierte "PC apagada/muerta" de invisible a notificado.

## Runbook — re-setup del ingest en una máquina nueva (~5 min)

Si hay que rehacer la pipeline en otra PC Windows (o tras un reinstalar):

1. **Clonar el repo** y, desde `apps/scrapers/`, instalar deps: `poetry install` y luego `poetry run playwright install chromium`.
2. **Crear `apps/scrapers/.env.production.local`** (gitignored) con una sola línea:
   ```
   DATABASE_URL=postgresql://...supabase... (session pooler, puerto 5432)
   ```
   El string está en el dashboard de Supabase del proyecto **inmobi-intel** (ref `fsrdscqnyufkfxkjfuun`) → Connect. Ver `.env.production.local.example`.
3. **Probar el pipeline sin escribir**: `pwsh apps/scrapers/scripts/scrape-all.ps1 -DryRun`. Debe traer >0 de al menos un portal desde la IP residencial.
4. **(Opcional) Heartbeat**: setear la variable de entorno `SCRAPE_HEARTBEAT_URL` (de healthchecks.io o Better Stack) a nivel usuario, para que un fallo nocturno notifique. Sin ella, el scrape corre igual pero un fallo queda silencioso.
5. **Registrar la tarea diaria**: `pwsh apps/scrapers/scripts/register-scrape-task.ps1` (decidir la hora — ver D2 del mega-plan; default 09:00 local).
6. **Verificar**: `Get-ScheduledTaskInfo -TaskName 'InmobiIntel-ScrapeDaily'` debe reportar `LastTaskResult` y `NextRunTime`.

El cron de GitHub Actions queda como red de seguridad gratuita los días que la IP de datacenter no esté bloqueada.
