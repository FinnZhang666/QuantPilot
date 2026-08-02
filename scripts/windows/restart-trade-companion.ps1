param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("api", "runtime", "telegram")]
    [string]$Component
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "stop-trade-companion.ps1") -Component $Component
& (Join-Path $PSScriptRoot "start-trade-companion.ps1") -Component $Component
