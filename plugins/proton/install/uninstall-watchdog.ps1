<#
.SYNOPSIS
  Stop and remove the Proton watchdog logon task.
#>
param([string]$TaskName = 'EmailAssistant-ProtonWatchdog')
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
} else {
    Write-Host "'$TaskName' isn't installed."
}
