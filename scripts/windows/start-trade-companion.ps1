param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("api", "runtime", "telegram")]
    [string]$Component
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EnvFile = Join-Path $ProjectRoot ".env"
$RuntimeRoot = Join-Path $ProjectRoot ".runtime"
$PidRoot = Join-Path $RuntimeRoot "pids"
$LogRoot = Join-Path $RuntimeRoot "logs"
$PidFile = Join-Path $PidRoot ("{0}.pid" -f $Component)

if (-not (Test-Path -LiteralPath $Python)) { throw "Project Python not found: $Python" }
if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Local .env not found: $EnvFile" }
New-Item -ItemType Directory -Force -Path $PidRoot, $LogRoot | Out-Null

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    if (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue) {
        throw "$Component is already running with PID $ExistingPid"
    }
    Remove-Item -LiteralPath $PidFile
}

$Scripts = @{
    api = "scripts\run_dashboard_service.py"
    runtime = "scripts\run_paper_runtime_worker.py"
    telegram = "scripts\run_telegram_runtime_worker.py"
}
$EntryPoint = Join-Path $ProjectRoot $Scripts[$Component]
$Stdout = Join-Path $LogRoot ("{0}.out.log" -f $Component)
$Stderr = Join-Path $LogRoot ("{0}.error.log" -f $Component)
$Process = Start-Process -FilePath $Python -ArgumentList $EntryPoint `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
[IO.File]::WriteAllText($PidFile, [string]$Process.Id)
Write-Output "$Component started with PID $($Process.Id)"
