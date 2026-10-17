# Supervisor dashboard (Task 9)

Responsive React and TypeScript dashboard for the local Smart Safety Helmet API.
It uses live API calls for helmets, current rule evaluations, incidents,
historical telemetry, camera safety events, and read-only workplace profiles.
It does not contain seeded cards or response mocks. Fixtures exist only in
component/API tests.

## Start on Windows PowerShell

In one terminal, start the backend from the repository root:

First set up the signing secret and at least one Argon2-hash bootstrap account
in this PowerShell session using the
[authentication guide](../docs/authentication-and-authorization.md). There are
no default credentials.

```powershell
.\.venv\Scripts\Activate.ps1
$env:HELMET_DB_PATH = ".\data\smart_safety_helmet.sqlite3"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location .\web-dashboard
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`).
The local API URL can be changed with `VITE_API_BASE_URL` in `.env.local`.
Only `localhost` and `127.0.0.1` development origins are enabled by backend
CORS configuration.

Run checks and build a static production bundle:

```powershell
npm test
npm run build
```

## API integration and current boundaries

The reusable client in `src/api.ts` validates JSON responses with Zod and gives
separate errors for network failures, HTTP errors, expired authentication, and
invalid response shapes. It does not embed API keys, tokens, or other secrets.
The dashboard uses these backend paths:

- `GET /health`, `/api/v1/helmets`, `/api/v1/helmets/{id}`, and `/api/v1/helmets/{id}/risk`
- `GET /api/v1/incidents`, `/api/v1/incidents/{id}`, incident history, and the acknowledgement POST
- `GET /api/v1/telemetry` for filtered charts
- `GET /api/v1/events` for saved camera safety events
- `GET /api/v1/workplaces/profiles` for active profile and rule review

The dashboard uses `POST /api/v1/auth/login`, receives a signed expiring bearer
token, and keeps it in memory only. The API enforces roles on every data route:
viewers read; supervisors read and acknowledge; administrators can also submit
telemetry/events and replace safety profiles. The server derives the
acknowledging identity from the verified token. Configure local accounts using
[`docs/authentication-and-authorization.md`](../docs/authentication-and-authorization.md).
This is local development authentication; it is not a production identity
provider.

Workplace profiles are read-only in the dashboard because the API has no profile
editing endpoint. Detection events are stored structured events; the dashboard
does not stream, display, or persist camera footage. The reports view exports a
current fleet snapshot rather than a compliance report. Rule profiles may
contain development thresholds; these are not certified industrial limits.

If the API lacks a risk profile, risk display remains `Unknown`. Missing or
invalid readings are not plotted as zero. Empty databases show empty states.
