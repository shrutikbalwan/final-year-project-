# Local API authentication and authorization

The API requires a signed bearer access token for every `/api/v1` data route.
`GET /health`, OpenAPI documentation, and `POST /api/v1/auth/login` stay public.
Tokens use HS256, issuer, subject, role, issue and expiry times, and expire after
30 minutes by default (configurable up to 24 hours). The server does not log
request bodies, passwords, or bearer tokens.

Passwords are hashed with Argon2id via `pwdlib`. Bootstrap configuration
contains hashes only. There are no default users or fallback signing keys. If
auth configuration is absent, requests without credentials get 401 and login
reports 503. Authentication configuration errors fail closed.

## Role matrix

| Operation | viewer | supervisor | administrator |
| --- | --- | --- | --- |
| Read telemetry, helmets/risk, incidents/history, camera/analytics events, profiles | Yes | Yes | Yes |
| Submit telemetry, safety events, analytics events | No | Yes | Yes |
| Acknowledge incidents | No | Yes | Yes |
| Add or replace a workplace rule profile (`PUT /api/v1/workplaces/profiles/{workplace_id}`) | No | No | Yes |

Acknowledgement identity comes from the verified token subject. The client’s
`acknowledged_by` value is ignored. Profile replacement validates the complete
profile and updates the running process. These changes are in-memory; use a
reviewed `SAFETY_PROFILES_PATH` configuration for durable settings and restart
the service after configuration updates. The local account store is not a
multi-user identity-management service.

## Configure a local account (Windows PowerShell)

Run from the repository root in the same PowerShell session that launches the
API. It creates a random signing key in process memory and prompts for a
password without displaying it. The helper outputs only its Argon2 hash.

```powershell
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$secretBytes = New-Object byte[] 48
$rng.GetBytes($secretBytes)
$env:HELMET_AUTH_SECRET = [Convert]::ToBase64String($secretBytes)
$username = Read-Host "Local administrator username"
$passwordHash = .\.venv\Scripts\python.exe -m backend.app.auth_bootstrap
$user = @{ username = $username; password_hash = $passwordHash.Trim(); role = "administrator" }
$env:HELMET_BOOTSTRAP_USERS = ConvertTo-Json -InputObject @($user) -Compress
$env:HELMET_ACCESS_TOKEN_MINUTES = "30"
$env:HELMET_DB_PATH = ".\data\smart_safety_helmet.sqlite3"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

For additional accounts, hash each password with the helper and add only hashes
to the JSON array. Keep the generated secret and JSON out of source control and
logs. These variables are session-scoped, so configure each server session.
Generating a new signing key expires existing tokens. Use a secret manager for
any shared host.

Login uses `POST /api/v1/auth/login` with `username` and `password`. The
response returns `access_token`, `token_type`, `expires_at`, `user_id`, and
`role`. Send `Authorization: Bearer <access_token>` on protected requests. The
React client keeps the token in memory; Flutter uses platform secure storage.

## Future identity provider

`Principal(user_id, role)` is the server authorization boundary. A future
Cognito or other identity provider should replace local token verification
with issuer, audience, signature/JWKS, expiry, and claim validation while
preserving the role policy. Cognito is not configured. Before deployment, add
HTTPS, managed identity and account lifecycle controls, secret rotation,
auditing, and request limits.
