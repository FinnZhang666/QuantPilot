#Requires -RunAsAdministrator
[CmdletBinding()]
param([switch]$DisableRealtime)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$OpenD = Join-Path $env:APPDATA "moomoo_OpenD\moomoo_OpenD.exe"
$TailscaleIP = (& "$env:ProgramFiles\Tailscale\tailscale.exe" ip -4).Trim()
if (-not (Test-Path $Python)) { throw "Project Python is missing: $Python" }
if (-not $TailscaleIP) { throw "Tailscale is not logged in" }

netsh interface portproxy delete v4tov4 listenaddress=$TailscaleIP listenport=8000 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenaddress=$TailscaleIP listenport=8000 connectaddress=127.0.0.1 connectport=8000 | Out-Null
Get-NetFirewallRule -Name "TradeCompanion-LocalAPI-Tailscale" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name "TradeCompanion-LocalAPI-Tailscale" -DisplayName "Trade Companion Local API (Tailscale only)" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $TailscaleIP -LocalPort 8000 -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null

function Register-NodeTask([string]$Name, [string]$Arguments, [int]$DelaySeconds) {
    $action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT${DelaySeconds}S"
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}

if (Test-Path $OpenD) {
    $action = New-ScheduledTaskAction -Execute $OpenD -WorkingDirectory (Split-Path $OpenD)
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName "TradeCompanion-OpenD" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}
Register-NodeTask "TradeCompanion-API" "-m scripts.run_dashboard_service" 30
Register-NodeTask "TradeCompanion-Paper" "-m scripts.run_paper_runtime_worker" 90
Register-NodeTask "TradeCompanion-Telegram" "-m scripts.run_telegram_runtime_worker" 60
Register-NodeTask "TradeCompanion-Realtime" "-m scripts.start_realtime" 120
if ($DisableRealtime) { Disable-ScheduledTask -TaskName "TradeCompanion-Realtime" | Out-Null }

Get-ScheduledTask -TaskName "TradeCompanion-*" | Select-Object TaskName,State
Write-Host "Local API: http://$TailscaleIP`:8000/health"
Write-Host "Realtime task enabled: $(-not [bool]$DisableRealtime)"
