$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$dashboardPath = Join-Path $projectRoot 'web-dashboard'
$workPath = Join-Path $env:TEMP ("smart-helmet-dashboard-e2e-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workPath | Out-Null
$databasePath = Join-Path $workPath 'integration.sqlite3'
$stdoutPath = Join-Path $workPath 'api.stdout.log'
$stderrPath = Join-Path $workPath 'api.stderr.log'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$profilePath = Join-Path $PSScriptRoot 'fixtures\workplace-profile-dashboard-e2e.json'
$port = 8011

$oldDbPath = $env:HELMET_DB_PATH
$oldProfilePath = $env:SAFETY_PROFILES_PATH
$oldLiveUrl = $env:VITE_LIVE_API_URL
$oldViteApiUrl = $env:VITE_API_BASE_URL
$oldAuthSecret = $env:HELMET_AUTH_SECRET
$oldBootstrapUsers = $env:HELMET_BOOTSTRAP_USERS
$oldTestPassword = $env:HELMET_TEST_PASSWORD
$apiProcess = $null

try {
    $env:HELMET_DB_PATH = $databasePath
    $env:SAFETY_PROFILES_PATH = $profilePath
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $secretBytes = New-Object byte[] 48
    $rng.GetBytes($secretBytes)
    $env:HELMET_AUTH_SECRET = [Convert]::ToBase64String($secretBytes)
    $env:HELMET_TEST_PASSWORD = 'synthetic-e2e-password-2026'
    $hash = (& $pythonPath -c "import os; from backend.app.auth import hash_password; print(hash_password(os.environ['HELMET_TEST_PASSWORD']))").Trim()
    $env:HELMET_BOOTSTRAP_USERS = ConvertTo-Json -InputObject @(@{ username = 'synthetic-supervisor'; password_hash = $hash; role = 'supervisor' }) -Compress
    $apiProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$port") `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

    $apiUrl = "http://127.0.0.1:$port"
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $health = Invoke-RestMethod "$apiUrl/health" -TimeoutSec 1
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        Get-Content $stderrPath -ErrorAction SilentlyContinue
        throw "Temporary API did not become ready. Logs are in $workPath"
    }

    $env:VITE_LIVE_API_URL = $apiUrl
    $env:VITE_API_BASE_URL = $apiUrl
    Push-Location $dashboardPath
    try {
        $vitestPath = Join-Path $dashboardPath 'node_modules\.bin\vitest.cmd'
        & $vitestPath run src/test/liveWorkflow.test.tsx --reporter=verbose
        if ($LASTEXITCODE -ne 0) { throw "Live dashboard integration test failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
    Write-Output "Synthetic telemetry-to-dashboard workflow passed. API logs and temporary SQLite evidence: $workPath"
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
    $env:HELMET_DB_PATH = $oldDbPath
    $env:SAFETY_PROFILES_PATH = $oldProfilePath
    $env:VITE_LIVE_API_URL = $oldLiveUrl
    $env:VITE_API_BASE_URL = $oldViteApiUrl
    $env:HELMET_AUTH_SECRET = $oldAuthSecret
    $env:HELMET_BOOTSTRAP_USERS = $oldBootstrapUsers
    $env:HELMET_TEST_PASSWORD = $oldTestPassword
}
