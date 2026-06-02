<#
.SYNOPSIS
  Registers (or updates) the daily Windows Scheduled Task that runs the scrapers.

.DESCRIPTION
  Run this ONCE to set up the daily scrape. It creates a per-user task named
  "InmobiIntel-ScrapeDaily" that runs scrape-all.ps1 every day at -At time.

  Key behaviours:
   * StartWhenAvailable  -> if the PC was off at the scheduled time, it runs as
                            soon as the PC is next on (no fixed "must be awake").
   * Battery flags       -> still runs on laptop battery.
   * Runs only when you are logged on (no stored password needed).

  No admin rights required. Re-run any time to change the time; it overwrites.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register-scrape-task.ps1
  powershell -ExecutionPolicy Bypass -File scripts\register-scrape-task.ps1 -At 21:30
  # Todos los días en vez de sólo días hábiles:
  powershell -ExecutionPolicy Bypass -File scripts\register-scrape-task.ps1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday
#>

param(
    [string]$At = "10:00",
    # Por defecto días hábiles (la inmobiliaria opera lun-vie). El mercado no cambia
    # tanto el finde como para justificar el riesgo anti-bot de scrapear 7 días.
    [string[]]$DaysOfWeek = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
    [string]$TaskName = "InmobiIntel-ScrapeDaily"
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "scrape-all.ps1"
if (-not (Test-Path $scriptPath)) {
    Write-Error "Cannot find $scriptPath"
    exit 2
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DaysOfWeek -At $At

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Inmobi Intel: scrape ML + Argenprop + ZonaProp into Supabase (residential IP)." `
    -Force | Out-Null

Write-Host "Registered task '$TaskName' - $($DaysOfWeek -join ',') at $At (catches up on next boot if missed)."
Write-Host "Run now to test:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "See status:       Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host ("Remove:           Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:" + '$false')
