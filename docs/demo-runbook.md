# Local demonstration runbook

This supervised demonstration uses synthetic data and the local development API. It is not an industrial deployment or safety test. Read [the demo/industrial boundary](demo-industrial-boundary.md) first.

## Prerequisites

- Windows 10/11, project Python virtual environment, Node.js/npm, and installed dashboard packages.
- API and dashboard ports available. The commands below use API `8012` and dashboard `5173`.
- No AWS account, physical helmet, worker identity, or camera is required.

From the repository root, prepare dependencies if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
Set-Location .\web-dashboard
npm ci
Set-Location ..
```

## Run the end-to-end demonstration

```powershell
.\tests\start-demo.ps1 -ApiPort 8012 -DashboardPort 5173
```

The script refuses to reuse occupied ports, creates an isolated temporary SQLite file under `%TEMP%`, generates a temporary local account and signing key, loads `config/workplace_profiles.example.json`, authenticates, posts one telemetry message (`demo-helmet-001`), checks the resulting `Critical` evaluation, and starts Vite configured for the temporary API.

1. Open the printed dashboard address in a browser.
2. Sign in as `demo-supervisor` with the temporary password printed by the launcher. The API verifies the account and assigns its role; the password is not written to the session file.
3. Verify the API shows online, the fleet contains `demo-helmet-001`, risk is `Critical`, and an active incident explains the matched example rules.
4. Open the **Incidents** section and inspect the stored record/history.
5. Open the printed API `/docs` URL to inspect the generated OpenAPI documentation.

The Critical result is generated from example values and example thresholds. It is only a demonstration of message validation, persistence, rule evaluation, incident creation, and API-backed dashboard rendering.

## Optional direct API checks

Replace `<API>` with the printed base URL:

```powershell
Invoke-RestMethod "<API>/health"
$securePassword = Read-Host "Temporary demo-supervisor password" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $login = Invoke-RestMethod -Uri "<API>/api/v1/auth/login" -Method Post `
        -ContentType "application/json" -Body (@{ username = "demo-supervisor"; password = $password } | ConvertTo-Json)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $password = $null
    $securePassword.Dispose()
}
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "<API>/api/v1/helmets/demo-helmet-001/risk" -Headers $headers
Invoke-RestMethod "<API>/api/v1/incidents" -Headers $headers
$login = $null
$headers = $null
```

These reads use the same isolated service and database as the dashboard.

## Stop and preserve evidence

Use the exact session file printed by the start script:

```powershell
.\tests\stop-demo.ps1 -SessionFile "$env:TEMP\smart-helmet-demo-<session-id>\session.json"
```

The cleanup script verifies each PID still matches the recorded API/Vite command before stopping its process tree. It preserves logs and SQLite data; inspect these files, then remove the temporary folder manually if it is no longer needed. Never point the demo at a production database or use production credentials.

## Evidence captured for the report

The latest clean-start run has date-stamped screenshots and test output in [demo verification evidence](testing/demo-verification-2026-10-17.md). The older screenshots `docs/screenshots/dashboard-development-sign-in.png`, `docs/screenshots/dashboard-live-synthetic-overview.png`, and `docs/screenshots/dashboard-synthetic-incident-list.png` were also captured from Edge and show the live local API, not physical device measurements. Repeat the automated integration check with:

```powershell
.\tests\run-live-dashboard-e2e.ps1
```

It uses a temporary database and a synthetic workplace fixture, then verifies that React renders the backend's risk and incident response.
