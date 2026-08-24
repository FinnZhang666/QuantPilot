#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-TailscaleExe {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if (Test-Path $candidate) { return $candidate }
    return $null
}

Write-Step "Checking Tailscale"
$tailscaleExe = Get-TailscaleExe
if (-not $tailscaleExe) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Tailscale is not installed and winget is unavailable. Install Tailscale from https://tailscale.com/download/windows, then rerun this script."
    }
    & $winget.Source install --id Tailscale.Tailscale --exact --accept-package-agreements --accept-source-agreements
    $tailscaleExe = Get-TailscaleExe
}
if (-not $tailscaleExe) { throw "Tailscale installation could not be verified." }

$tailscaleService = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
if ($tailscaleService -and $tailscaleService.Status -ne "Running") {
    Start-Service -Name Tailscale
}

Write-Step "Checking OpenSSH Server"
$sshCapability = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
if (-not $sshCapability) { throw "OpenSSH Server capability was not found on this Windows installation." }
if ($sshCapability.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $sshCapability.Name | Out-Null
}
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service -Name sshd).Status -ne "Running") { Start-Service -Name sshd }

Write-Step "Checking Windows Firewall SSH rule"
$firewallRule = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if (-not $firewallRule) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
} elseif ($firewallRule.Enabled -ne "True") {
    Enable-NetFirewallRule -Name "OpenSSH-Server-In-TCP"
}

Write-Step "Remote access summary"
$tailscaleIPv4 = & $tailscaleExe ip -4 2>$null
[PSCustomObject]@{
    WindowsUsername = $env:USERNAME
    Hostname = $env:COMPUTERNAME
    TailscaleIPv4 = if ($tailscaleIPv4) { $tailscaleIPv4.Trim() } else { "NOT_LOGGED_IN" }
    SshdStatus = (Get-Service -Name sshd).Status
    SshdStartupType = (Get-CimInstance Win32_Service -Filter "Name='sshd'").StartMode
} | Format-List

Write-Host "Tailscale status:" -ForegroundColor Yellow
& $tailscaleExe status
if (-not $tailscaleIPv4) {
    Write-Warning "Tailscale needs login. Open the Tailscale app and sign in to the same tailnet as the Mac, then rerun this script."
}

Write-Host "`nNo Broker, OpenD, QuantPilot database, trading configuration, or public port was modified." -ForegroundColor Green
