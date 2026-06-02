<#
.SYNOPSIS
  Runs the three portal scrapers against the production (Supabase) DB.

.DESCRIPTION
  Meant to be driven by the daily Windows Scheduled Task (see
  register-scrape-task.ps1). Runs from a residential IP, which avoids the
  DataDome 403 / bot-wall blocks that hit GitHub Actions' datacenter IPs.

  Reads the production connection string from apps/scrapers/.env.production.local
  (gitignored) so the Supabase password never lands in the repo. That file must
  contain a single line:
      DATABASE_URL=postgresql://...supabase...

  Exit code: 0 if at least one portal scraped >0 items, 1 if every portal came
  back empty (all blocked / all failed). Each scraper already exits 3 on an
  empty run (see scrapers/base.py: EXIT_SCRAPED_NOTHING).
#>

param(
    # Smoke-test the whole pipeline without touching any DB: passes
    # --dry-run --limit 1 to each scraper and skips the Supabase env-file check.
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# apps/scrapers = parent of this script's folder
$scrapersDir = Split-Path -Parent $PSScriptRoot
Set-Location $scrapersDir

# --- Load production DATABASE_URL (Supabase) from the gitignored env file ---
# Skipped under -DryRun: the scrapers do no DB writes in that mode.
if (-not $DryRun) {
    $envFile = Join-Path $scrapersDir ".env.production.local"
    if (-not (Test-Path $envFile)) {
        Write-Error "Missing $envFile. Create it with one line: DATABASE_URL=postgresql://...supabase..."
        exit 2
    }
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') {
            $env:DATABASE_URL = $Matches[1].Trim('"').Trim("'")
        }
    }
    if (-not $env:DATABASE_URL) {
        Write-Error "DATABASE_URL not found in $envFile"
        exit 2
    }
}

# --- Locate poetry (installed under the user's Roaming Python Scripts) ---
$poetry = Get-Command poetry -ErrorAction SilentlyContinue
if ($poetry) {
    $poetryExe = $poetry.Source
} else {
    $poetryExe = Join-Path $env:APPDATA "Python\Python312\Scripts\poetry.exe"
}
if (-not (Test-Path $poetryExe)) {
    Write-Error "poetry not found (looked at $poetryExe). Install it or add it to PATH."
    exit 2
}

# --- Log file ---
$logDir = Join-Path $scrapersDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "scrape-$stamp.log"
"=== scrape-all $stamp ===" | Tee-Object -FilePath $log

# The scrapers log via structlog to stderr. In Windows PowerShell 5.1, piping a
# native exe's stderr through 2>&1 wraps each line as an error record; under
# "Stop" that would abort on the first log line. Switch to "Continue" so the
# scrapers run to completion and $LASTEXITCODE still carries the real code.
$ErrorActionPreference = "Continue"

$extraArgs = @()
if ($DryRun) { $extraArgs = @("--dry-run", "--limit", "1", "--skip-usd") }

# Property types to scrape. ML returns every type in its generic inmuebles listing
# (the parser infers each card's type), so it needs no --type. Argenprop and ZonaProp
# default to departamentos only — without --type, houses/PH/locals/land are 0% of
# their data, which is the single biggest coverage gap (see megaplan T3).
$ALL_TYPES = "APT,HOUSE,PH,LOCAL,TERRENO"
$portalArgs = @{
    "mercadolibre" = @()                      # type inferred per card from the listing
    "argenprop"    = @("--type", $ALL_TYPES)
    "zonaprop"     = @("--type", $ALL_TYPES)
}

$portals = @("mercadolibre", "argenprop", "zonaprop")
$anyOk = $false
foreach ($p in $portals) {
    "--- $p ---" | Tee-Object -FilePath $log -Append
    $typeArgs = $portalArgs[$p]
    & $poetryExe run python -m "scrapers.$p" --zone "mar-del-plata" --op "SALE,RENT" @typeArgs @extraArgs 2>&1 |
        Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "$p exit code: $code" | Tee-Object -FilePath $log -Append
    if ($code -eq 0) { $anyOk = $true }
}

# --- Score opportunities over the freshly-scraped data ---
# Skipped under -DryRun (no DB creds loaded, nothing new written). Idempotent, so
# re-runs are safe. A scorer failure is logged but doesn't change the task's exit
# code, which reflects the scrape itself.
if (-not $DryRun) {
    "--- opportunity scorer ---" | Tee-Object -FilePath $log -Append
    & $poetryExe run python -m opportunity 2>&1 | Tee-Object -FilePath $log -Append
    $scoreCode = $LASTEXITCODE
    "scorer exit code: $scoreCode" | Tee-Object -FilePath $log -Append
    if ($scoreCode -ne 0) {
        "WARN: scorer failed (exit $scoreCode) - opportunities not refreshed." |
            Tee-Object -FilePath $log -Append
    }
}

if ($anyOk) {
    "DONE: at least one portal scraped data." | Tee-Object -FilePath $log -Append
    exit 0
} else {
    "FAIL: every portal came back empty (all blocked or errored)." | Tee-Object -FilePath $log -Append
    exit 1
}
