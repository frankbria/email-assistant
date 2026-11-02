<#
.SYNOPSIS
  Start the Proton watchdog at logon (Windows). The watchdog then keeps Bridge and the
  plugin running. Bridge runs in your session, so this is a logon task, not a service.
.PARAMETER EnvFile
  The plugin's settings file (MAILBOX_* lines). Default: %APPDATA%\email-assistant\proton.env
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install-watchdog.ps1
#>
param(
    [string]$EnvFile = (Join-Path $env:APPDATA 'email-assistant\proton.env'),
    [string]$TaskName = 'EmailAssistant-ProtonWatchdog'
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $EnvFile)) { throw "Settings file not found: $EnvFile (copy proton.env.example there and fill it in)." }
$uv = (Get-Command uv -ErrorAction Stop).Source
$pluginDirectory = Split-Path -Parent $PSScriptRoot

# Hidden PowerShell sets MAILBOX_ENV_FILE, then runs the watchdog from the plugin project.
# Values go inside single-quoted strings, so their own single quotes are doubled.
function Quote([string]$value) { "'" + ($value -replace "'", "''") + "'" }
$command = "`$env:MAILBOX_ENV_FILE = $(Quote $EnvFile); & $(Quote $uv) run --directory $(Quote $pluginDirectory) python -m proton_plugin.watchdog"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -Command $command"

# At this user's logon, a minute later so Bridge (which starts with the session) goes first.
$user = "$env:USERDOMAIN\$env:USERNAME"  # run the installer as that user, not as another admin
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT1M'

# Keep running indefinitely. The watchdog only exits by failing (non-zero), and Task
# Scheduler restarts a failed task every minute.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Keeps Proton Bridge and the email-assistant plugin running.' -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed and started '$TaskName'. It starts at every logon from now on."
Write-Host "Optional: for unattended reboots, turn on Windows auto-logon (Sysinternals Autologon)."
