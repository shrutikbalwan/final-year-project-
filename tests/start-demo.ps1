param(
    [int]$ApiPort = 8000,
    [int]$DashboardPort = 5173
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$dashboardPath = Join-Path $projectRoot 'web-dashboard'
$sessionRoot = Join-Path $env:TEMP ("smart-helmet-demo-" + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $sessionRoot
$databasePath = Join-Path $sessionRoot 'demo.sqlite3'
$apiOut = Join-Path $sessionRoot 'api.stdout.log'
$apiErr = Join-Path $sessionRoot 'api.stderr.log'
$webOut = Join-Path $sessionRoot 'dashboard.stdout.log'
$webErr = Join-Path $sessionRoot 'dashboard.stderr.log'
$sessionFile = Join-Path $sessionRoot 'session.json'

foreach ($port in @($ApiPort, $DashboardPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing process or select another supported port before starting the demo."
    }
}
if (-not (Test-Path $pythonPath)) { throw "Project virtual environment not found: $pythonPath" }

$oldDbPath = $env:HELMET_DB_PATH
$oldProfilePath = $env:SAFETY_PROFILES_PATH
$oldApiUrl = $env:VITE_API_BASE_URL
$oldAuthSecret = $env:HELMET_AUTH_SECRET
$oldBootstrapUsers = $env:HELMET_BOOTSTRAP_USERS
$oldBootstrapPassword = $env:HELMET_BOOTSTRAP_PASSWORD
$apiProcess = $null
$webProcess = $null
try {
    $env:HELMET_DB_PATH = $databasePath
    $env:SAFETY_PROFILES_PATH = Join-Path $projectRoot 'config\workplace_profiles.example.json'
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $secretBytes = New-Object byte[] 48
    $passwordBytes = New-Object byte[] 32
    $rng.GetBytes($secretBytes)
    $rng.GetBytes($passwordBytes)
    $env:HELMET_AUTH_SECRET = [Convert]::ToBase64String($secretBytes)
    $demoPassword = [Convert]::ToBase64String($passwordBytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B')
    $env:HELMET_BOOTSTRAP_PASSWORD = $demoPassword
    $passwordHash = (& $pythonPath -c "import os; from backend.app.auth import hash_password; print(hash_password(os.environ['HELMET_BOOTSTRAP_PASSWORD']))").Trim()
    $env:HELMET_BOOTSTRAP_USERS = ConvertTo-Json -InputObject @(@{ username = 'demo-supervisor'; password_hash = $passwordHash; role = 'supervisor' }) -Compress
    $apiProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr

    $apiUrl = "http://127.0.0.1:$ApiPort"
    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        try {
            $health = Invoke-RestMethod "$apiUrl/health" -TimeoutSec 1
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $ready) { throw "Demo API did not become ready. Inspect $apiErr" }

    $login = Invoke-RestMethod -Uri "$apiUrl/api/v1/auth/login" -Method Post `
        -ContentType 'application/json' -Body (@{ username = 'demo-supervisor'; password = $demoPassword } | ConvertTo-Json)
    $authHeaders = @{ Authorization = "Bearer $($login.access_token)" }

    $now = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $telemetry = @{
        schema_version = '1.0.0'
        event_id = "demo-event-$([Guid]::NewGuid().ToString('N'))"
        device_id = 'demo-helmet-001'
        workplace_id = 'plant7-zone-c'
        observed_at = $now
        readings = @(
            @{ reading_id = 'demo-temp-001'; sensor_id = 'demo-temp-sensor'; measurement_type = 'temperature'; unit_code = 'Cel'; value = 45.0; reading_status = 'valid'; observed_at = $now },
            @{ reading_id = 'demo-gas-001'; sensor_id = 'demo-gas-sensor'; measurement_type = 'gas_concentration'; unit_code = 'ppm'; value = 150.0; reading_status = 'valid'; observed_at = $now }
        )
        health = @{
            schema_version = '1.0.0'; device_id = 'demo-helmet-001'; workplace_id = 'plant7-zone-c'; observed_at = $now
            battery_reading = @{ reading_id = 'demo-battery-001'; sensor_id = 'demo-power-monitor'; measurement_type = 'battery_charge'; unit_code = '%'; value = 82.0; reading_status = 'valid'; observed_at = $now }
            connectivity_status = 'connected'; last_seen_at = $now; last_seen_status = 'valid'
        }
    }
    $accepted = Invoke-RestMethod -Uri "$apiUrl/api/v1/telemetry" -Method Post `
        -Headers $authHeaders -ContentType 'application/json' -Body ($telemetry | ConvertTo-Json -Depth 10)
    $risk = Invoke-RestMethod "$apiUrl/api/v1/helmets/demo-helmet-001/risk" -Headers $authHeaders
    if ($risk.risk_level -ne 'Critical') { throw "Expected demo rule evaluation Critical; received $($risk.risk_level)." }

    $env:VITE_API_BASE_URL = $apiUrl
    $viteEntry = Join-Path $dashboardPath 'node_modules\vite\bin\vite.js'
    $webProcess = Start-Process -FilePath $nodePath `
        -ArgumentList @("`"$viteEntry`"", '--host', '127.0.0.1', '--port', "$DashboardPort", '--strictPort') `
        -WorkingDirectory $dashboardPath -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $webOut -RedirectStandardError $webErr
    $dashboardUrl = "http://127.0.0.1:$DashboardPort"
    $webReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $page = Invoke-RestMethod $dashboardUrl -TimeoutSec 1
            if ($page -match '<div id="root"></div>') { $webReady = $true; break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $webReady) { throw "Dashboard did not become ready. Inspect $webErr" }

    $incidentPage = Invoke-RestMethod "$apiUrl/api/v1/incidents" -Headers $authHeaders
    $session = @{
        api_pid = $apiProcess.Id; dashboard_pid = $webProcess.Id
        api_port = $ApiPort; dashboard_port = $DashboardPort
        database_path = $databasePath; event_id = $accepted.event_id
        incident_id = $incidentPage.items[0].incident_id
        api_url = $apiUrl; dashboard_url = $dashboardUrl
        api_stdout = $apiOut; api_stderr = $apiErr
        dashboard_stdout = $webOut; dashboard_stderr = $webErr
    }
    $session | ConvertTo-Json | Set-Content -LiteralPath $sessionFile -Encoding utf8
    Write-Output "Demo workflow seeded successfully: $($accepted.event_id) -> Critical risk -> $($session.incident_id)"
    Write-Output "Dashboard: $dashboardUrl (sign in as demo-supervisor with the temporary password below)"
    Write-Output "Temporary demo password: $demoPassword"
    Write-Output "API docs: $apiUrl/docs"
    Write-Output "Temporary database: $databasePath"
    Write-Output "Session file for cleanup: $sessionFile"
} catch {
    if ($webProcess -and -not $webProcess.HasExited) { & taskkill.exe /PID $webProcess.Id /T /F | Out-Null }
    if ($apiProcess -and -not $apiProcess.HasExited) { & taskkill.exe /PID $apiProcess.Id /T /F | Out-Null }
    throw
} finally {
    $env:HELMET_DB_PATH = $oldDbPath
    $env:SAFETY_PROFILES_PATH = $oldProfilePath
    $env:VITE_API_BASE_URL = $oldApiUrl
    $env:HELMET_AUTH_SECRET = $oldAuthSecret
    $env:HELMET_BOOTSTRAP_USERS = $oldBootstrapUsers
    $env:HELMET_BOOTSTRAP_PASSWORD = $oldBootstrapPassword
}
