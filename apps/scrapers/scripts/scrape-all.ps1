<#
.SYNOPSIS
  Runs the three portal scrapers against the production (Supabase) DB,
  partitioned by barrio so portal result caps don't silently truncate coverage.

.DESCRIPTION
  Meant to be driven by the daily Windows Scheduled Task (see
  register-scrape-task.ps1). Runs from a residential IP, which avoids the
  DataDome 403 / bot-wall blocks that hit GitHub Actions' datacenter IPs.

  Coverage strategy (megaplan T4/T5): each portal caps how many results one
  search returns (Argenprop ~200 per zone/op/type, ZonaProp ~600, ML ~2500).
  A single city-wide "mar-del-plata" query therefore misses most of the
  market. Instead we iterate every Mar del Plata-region zone in zones.json:
  the 4 city-level zones plus each barrio (ML resolves barrios natively via
  mlNeighborhood; Argenprop/ZonaProp need argenpropSlug/zonapropSlug to be
  present on the zone — barrios without them are skipped for that portal).
  Re-scraping a listing that appears in both the barrio and the city query is
  harmless: the upsert dedupes by (portal, portal_id).

  Checkpoint/resume: each completed (portal, zone) is appended to
  logs/checkpoint-<yyyyMMdd>.json. Re-running the script the same day skips
  completed pairs, so a crash or a DataDome block mid-run resumes where it
  left off instead of starting over. Use -Fresh to ignore the checkpoint.

  Reads the production connection string from apps/scrapers/.env.production.local
  (gitignored) so the Supabase password never lands in the repo. That file must
  contain a single line:
      DATABASE_URL=postgresql://...supabase...

  Exit code: 0 if at least one (portal, zone) scraped >0 items, 1 if every
  combination came back empty (all blocked / all failed). Each scraper exits 3
  on an empty run (see scrapers/base.py: EXIT_SCRAPED_NOTHING) — for a small
  barrio that's a legitimate result, so 0 and 3 both count as "completed" for
  the checkpoint; only crashes (other codes) are retried on resume.
#>

param(
    # Smoke-test the whole pipeline without touching any DB: passes
    # --dry-run --limit 1 to each scraper and skips the Supabase env-file check.
    # Dry runs don't write checkpoints.
    [switch]$DryRun,
    # Ignore today's checkpoint and re-scrape every (portal, zone).
    [switch]$Fresh,
    # Comma-separated subset of portals to run.
    [string]$Portals = "mercadolibre,argenprop,zonaprop",
    # Cap the number of zones per portal (testing aid). 0 = no cap.
    [int]$MaxZones = 0
)

$ErrorActionPreference = "Stop"

# apps/scrapers = parent of this script's folder
$scrapersDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $scrapersDir)
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

# --- Zone matrix from zones.json (single source of truth) ---
# MdP region = province "Buenos Aires" (CABA zones carry province "CABA").
# Sorted by priority so the most important barrios run first — if the night
# gets cut short, the valuable zones are already in.
$zonesFile = Join-Path $repoRoot "packages\shared-types\src\data\zones.json"
$allZones = (Get-Content $zonesFile -Raw -Encoding UTF8 | ConvertFrom-Json).zones
$mdpZones = @($allZones | Where-Object { $_.province -eq "Buenos Aires" } |
    Sort-Object -Property priority -Descending)

function Get-PortalZones([string]$portal) {
    switch ($portal) {
        # ML builds barrio URLs from mlNeighborhood. Only send barrios that were
        # resolved against ML's location API (mlNeighborhoodId via `pnpm
        # zones:resolve`) — an unrecognized barrio path risks ML silently
        # falling back to city-wide results under the wrong zone_slug.
        "mercadolibre" {
            return @($mdpZones | Where-Object {
                (-not $_.mlNeighborhood) -or $_.mlNeighborhoodId })
        }
        # Argenprop/ZonaProp only know how to reach a barrio if the canonical
        # portal slug was discovered (scripts/discover_barrio_slugs.py) and
        # saved on the zone. City-level zones always work via zone.slug.
        "argenprop" {
            return @($mdpZones | Where-Object {
                (-not $_.mlNeighborhood) -or $_.argenpropSlug })
        }
        "zonaprop" {
            return @($mdpZones | Where-Object {
                (-not $_.mlNeighborhood) -or $_.zonapropSlug })
        }
    }
    return @()
}

# --- Checkpoint (resume within the same day) ---
$ckptFile = Join-Path $logDir ("checkpoint-" + (Get-Date -Format "yyyyMMdd") + ".json")
$done = New-Object System.Collections.ArrayList
if ((Test-Path $ckptFile) -and -not $Fresh -and -not $DryRun) {
    try {
        (Get-Content $ckptFile -Raw | ConvertFrom-Json) | ForEach-Object { [void]$done.Add([string]$_) }
        "checkpoint loaded: $($done.Count) (portal, zone) pairs already done today" | Tee-Object -FilePath $log -Append
    } catch {
        "WARN: unreadable checkpoint $ckptFile - starting fresh" | Tee-Object -FilePath $log -Append
    }
}

function Save-Checkpoint {
    if ($DryRun) { return }
    ConvertTo-Json -InputObject @($done) | Set-Content -Path $ckptFile -Encoding utf8
}

# The scrapers log via structlog to stderr. In Windows PowerShell 5.1, piping a
# native exe's stderr through 2>&1 wraps each line as an error record; under
# "Stop" that would abort on the first log line. Switch to "Continue" so the
# scrapers run to completion and $LASTEXITCODE still carries the real code.
$ErrorActionPreference = "Continue"

$extraArgs = @()
if ($DryRun) { $extraArgs = @("--dry-run", "--limit", "1") }

# Property types to scrape. ML returns every type in its generic inmuebles listing
# (the parser infers each card's type), so it needs no --type. Argenprop and ZonaProp
# default to departamentos only — without --type, houses/PH/locals/land are 0% of
# their data (megaplan T3).
$ALL_TYPES = "APT,HOUSE,PH,LOCAL,TERRENO"
$portalArgs = @{
    "mercadolibre" = @()                      # type inferred per card from the listing
    "argenprop"    = @("--type", $ALL_TYPES)
    "zonaprop"     = @("--type", $ALL_TYPES)
}
# Pause between zones: ZonaProp gets the long one (DataDome rate-limits), the
# others just a polite gap. Within a zone the scrapers already pace themselves.
$portalPause = @{
    "mercadolibre" = @(5, 15)
    "argenprop"    = @(5, 15)
    "zonaprop"     = @(45, 90)
}

# NB: don't reuse the $Portals name — PS variables are case-insensitive and the
# param's [string] constraint would cast the array back to one joined string.
$portalList = @($Portals.Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ })
$anyOk = $false
$usdRefreshed = $false

foreach ($p in $portalList) {
    $zones = Get-PortalZones $p
    if ($MaxZones -gt 0 -and $zones.Count -gt $MaxZones) { $zones = $zones[0..($MaxZones - 1)] }
    "--- $p ($($zones.Count) zones) ---" | Tee-Object -FilePath $log -Append

    foreach ($z in $zones) {
        $key = "$p|$($z.slug)"
        if (-not $Fresh -and $done.Contains($key)) {
            "skip (checkpoint): $key" | Tee-Object -FilePath $log -Append
            continue
        }

        # Refresh the blue rate once per run; every later invocation reuses the
        # DB value instead of hammering dolarapi ~80 times a night. Dry runs
        # always skip (no DB writes anyway).
        $usdArgs = @("--skip-usd")
        if (-not $usdRefreshed -and -not $DryRun) { $usdArgs = @() }

        $typeArgs = $portalArgs[$p]
        "run: $key" | Tee-Object -FilePath $log -Append
        & $poetryExe run python -m "scrapers.$p" --zone $z.slug --op "SALE,RENT" @typeArgs @usdArgs @extraArgs 2>&1 |
            Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
        "$key exit code: $code" | Tee-Object -FilePath $log -Append

        if ($code -eq 0) {
            $anyOk = $true
            if (-not $DryRun) { $usdRefreshed = $true }
        }
        # 0 = scraped data; 3 = ran clean but found nothing (legit for a small
        # barrio x type). Both mean "don't redo this zone today". Crashes
        # (anything else) stay out of the checkpoint so -resume retries them.
        if ($code -eq 0 -or $code -eq 3) {
            [void]$done.Add($key)
            Save-Checkpoint
        }

        $range = $portalPause[$p]
        $pause = Get-Random -Minimum $range[0] -Maximum $range[1]
        if (-not $DryRun) { Start-Sleep -Seconds $pause }
    }
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

# --- Geocode new properties (fills lat/lng for the map at /mapa) ---
# Skipped under -DryRun. Idempotent: only touches active rows missing lat/lng, and a
# local cache avoids re-hitting Nominatim for addresses already resolved. Nominatim's
# 1 req/s policy makes this slow, so we cap each run with --limit; coverage fills in
# over successive nightly runs. A geocoder failure is logged but doesn't change the
# task's exit code (the scrape itself is what matters).
if (-not $DryRun) {
    "--- geocoder ---" | Tee-Object -FilePath $log -Append
    & $poetryExe run python -m geocode --limit 500 2>&1 | Tee-Object -FilePath $log -Append
    $geoCode = $LASTEXITCODE
    "geocoder exit code: $geoCode" | Tee-Object -FilePath $log -Append
    if ($geoCode -ne 0) {
        "WARN: geocoder failed (exit $geoCode) - some properties left without coords." |
            Tee-Object -FilePath $log -Append
    }
}

# --- Rotate old logs and checkpoints (this runs daily; logs/ would grow without bound) ---
Get-ChildItem -Path $logDir -Filter "scrape-*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $logDir -Filter "checkpoint-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# --- Heartbeat ping (so a silent overnight failure becomes visible) ---
# Set SCRAPE_HEARTBEAT_URL to a healthchecks.io (or Better Stack) check URL. On
# success we ping the URL; on failure we ping "<url>/fail". If unset, we skip
# silently — the ping is opt-in and the URL is the owner's to provision (D4).
$heartbeat = $env:SCRAPE_HEARTBEAT_URL
if ($heartbeat) {
    $pingUrl = if ($anyOk) { $heartbeat } else { ($heartbeat.TrimEnd('/') + "/fail") }
    try {
        Invoke-RestMethod -Uri $pingUrl -Method Get -TimeoutSec 15 | Out-Null
        "heartbeat pinged: $pingUrl" | Tee-Object -FilePath $log -Append
    } catch {
        "WARN: heartbeat ping failed: $($_.Exception.Message)" | Tee-Object -FilePath $log -Append
    }
}

if ($anyOk) {
    "DONE: at least one (portal, zone) scraped data." | Tee-Object -FilePath $log -Append
    exit 0
} else {
    "FAIL: every (portal, zone) came back empty (all blocked or errored)." | Tee-Object -FilePath $log -Append
    exit 1
}
