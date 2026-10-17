param(
    [Parameter(Mandatory = $true)]
    [string]$SessionFile
)

$ErrorActionPreference = 'Stop'
$resolvedSession = (Resolve-Path -LiteralPath $SessionFile).Path
$tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
if (-not $resolvedSession.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to stop processes using a session file outside the current user temporary directory.'
}
$session = Get-Content -LiteralPath $resolvedSession -Raw | ConvertFrom-Json
$checks = @(
    @{ pid = [int]$session.api_pid; pattern = "uvicorn backend.app.main:app.*--port $([int]$session.api_port)" },
    @{ pid = [int]$session.dashboard_pid; pattern = "vite.js.*--port $([int]$session.dashboard_port)" }
)
foreach ($check in $checks) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($check.pid)" -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.CommandLine -notmatch $check.pattern) {
        throw "PID $($check.pid) no longer matches the demo process recorded in the session. It was left running."
    }
    & taskkill.exe /PID $check.pid /T /F | Out-Null
    Write-Output "Stopped demo process tree rooted at PID $($check.pid)."
}
Write-Output "Demo files and database were preserved at $([IO.Path]::GetDirectoryName($resolvedSession))."
