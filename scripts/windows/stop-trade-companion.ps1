param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("api", "runtime", "telegram")]
    [string]$Component
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PidFile = Join-Path $ProjectRoot (".runtime\pids\{0}.pid" -f $Component)
$EntryPoints = @{
    api = "run_dashboard_service.py"
    runtime = "run_paper_runtime_worker.py"
    telegram = "run_telegram_runtime_worker.py"
}

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Output "$Component is not running (PID file absent)"
    exit 0
}
$TargetPid = [int](Get-Content -LiteralPath $PidFile -Raw)
$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$TargetPid" -ErrorAction SilentlyContinue
if ($null -eq $Process) {
    Remove-Item -LiteralPath $PidFile
    Write-Output "$Component process is absent; stale PID file removed"
    exit 0
}
if ($Process.CommandLine -notlike ("*{0}*" -f $EntryPoints[$Component])) {
    throw "PID $TargetPid does not match the expected $Component entry point; refusing to stop it"
}
Stop-Process -Id $TargetPid
Remove-Item -LiteralPath $PidFile
Write-Output "$Component stopped"
