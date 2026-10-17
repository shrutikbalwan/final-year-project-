# Task 12: Security, Deployment and Performance Review (Draft)

**Status:** Supporting security/performance review. Its findings and measurements are summarized in [the final-year project report](final-year-project-report.md). This is not a production-readiness or safety-certification claim.
**Review date:** 2026-10-17

## Scope and evidence

The repository guide and the review are aligned on local development and demonstration as the current scope. The project guide says AWS is optional and no cloud path is implemented; the README also labels dashboard login as a UI preview. I added [demo-industrial-boundary.md](demo-industrial-boundary.md) to make this separation explicit: synthetic/permissioned demo data and loopback services stay isolated, while any real industrial pilot requires a distinct environment, security and privacy controls, site-specific validation, human procedures, and written stakeholder approval.


Reviewed the repository's backend, shared contracts, local persistence, rule engine, cloud proposal, CV and ML modules, web dashboard, Flutter app, configuration and ignore rules. Ran local tests and dependency checks. The repository currently has no Git commits or remote, so this review could not inspect historical committed content; all current files show as untracked in Git. There are no deployed AWS resources in this workspace.

## Findings

### High: local authentication is not production identity management

The FastAPI service now validates local Argon2 password hashes, signs short-lived bearer tokens, and enforces roles on data routes, incident acknowledgement, and profile changes. This local bootstrap-user store does not provide account lifecycle, lockout/rate limiting, token revocation, audit controls, or managed identity federation. CORS restrictions are not an authentication control. Keep the API loopback-only; before shared or production access add TLS, managed identity, credential policy, secret rotation, auditing, and rate limits. Cognito is not configured.

### High: persistent records have no retention lifecycle

Local SQLite stores telemetry, helmet state and incidents without expiry. No configured TTL, automated deletion, backup/restore process, or at-rest encryption policy is present. Define retention by data type, add tested cleanup/archival, and protect backups before collecting real worker or workplace data. Current CV processing handles frames in memory and does not save footage by default, which reduces footage exposure; it does not remove privacy concerns around live camera access and detections.

### Medium: local operational controls are not production controls

The API has no rate limits, explicit request-body size limit, production TLS configuration, or hardened deployment profile. Run locally on loopback as documented. Before deployment, place it behind a maintained TLS reverse proxy or managed ingress, cap payload and upload sizes, apply rate limits, restrict network access, and configure a process supervisor and backups. Health endpoint checks local storage availability; it is a useful local readiness check, not a full dependency/alerting system.

### Medium: supply-chain reproducibility needs improvement

Python requirements use version ranges; there is no complete lockfile with hashes. Flutter has a committed package lock, and npm has a lockfile. Generate and review a Python lock/constraints file, automate audits in CI, and update dependencies through reviewed changes. Audits are point-in-time checks, not a guarantee against unknown or newly disclosed issues.

### Low: source history and secret review are limited

The current working tree has no commits, so there are no historical commits to scan. Scanning visible files found no AWS access key patterns, private-key blocks, or apparent real credentials. The ignored `web-dashboard/.env.local` contains local configuration only; it was not disclosed. No credential-bearing file was removed because none was found. Continue to keep real `.env` files and certificates outside Git and rotate credentials if any were previously shared outside the repository.

### Cloud/IAM

`cloud/` contains only a placeholder; there are no IAM policies, deployed resources, credentials, or AWS account integration to audit. The cloud architecture is a proposal, not an implementation. Before deployment, review the concrete policy documents and resource ARNs, use separate device and service roles, scope IoT topic permissions and DynamoDB table/index actions, encrypt data, enable audit logs, configure alarms and budgets, and verify that teardown does not delete retained evidence accidentally.

### Logging and video privacy

Backend request logging now emits request ID, method, route template, response status and elapsed time. It omits request bodies, query values, device/workplace identifiers, bearer tokens and exception text; response includes `X-Request-ID`. A regression test checks the route-template and omission behavior. Avoid adding payload logging. CV currently processes frames in memory without writing or streaming footage by default. RTSP URLs containing credentials can be exposed in command-line process listings; use a local protected config/secret store and never put camera passwords in command arguments or logs. Define camera access, notice/consent, access audit, and retention rules before real footage is used.

## Dependency and secret checks

Checks run on 2026-10-17:

- `pip-audit` over `requirements.txt`, `requirements-dev.txt`, `requirements-ml.txt`, `requirements-cv.txt`, and `requirements-aws.txt`: no known vulnerabilities reported in the resolved installed dependency sets. `pip-audit` uses advisory data that changes over time; rerun in CI and before deployment ([pip-audit](https://github.com/pypa/pip-audit), [PyPA advisory database](https://github.com/pypa/advisory-database)).
- `npm audit --omit=dev`: 0 vulnerabilities. A broader dashboard audit also reported 0 vulnerabilities at review time ([GitHub Advisory Database](https://github.com/advisories)).
- `dart pub audit` is unavailable in the installed Dart CLI (unknown subcommand). `flutter pub outdated --json` showed no current dependency flagged as affected by the advisory metadata available to that command. This is not equivalent to a successful dedicated Pub audit.
- `.venv` `pip check`: no broken requirements.
- No actual cloud IAM policy could be audited because none exists in the project.

## Configuration and reproducible local operation

Run from the repository root in PowerShell. Python 3.11 and a project virtual environment are expected. AWS is not required.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
$env:HELMET_DB_PATH = ".\data\smart_safety_helmet.sqlite3"
$env:SAFETY_PROFILES_PATH = ".\config\workplace_profiles.json"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` and `http://127.0.0.1:8000/health`. The OpenAPI page does not imply authentication. Keep the local server bound to `127.0.0.1`.

Dashboard configuration: copy `web-dashboard/.env.example` to ignored `.env.local`; configure `VITE_API_BASE_URL`. Sign in using an account configured with `HELMET_AUTH_SECRET` and `HELMET_BOOTSTRAP_USERS`. In PowerShell run `cd web-dashboard; npm ci; npm run dev`.

Mobile configuration uses Dart defines, for example `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=AUTH_TOKEN_URL=http://10.0.2.2:8000/api/v1/auth/login --dart-define=SERVER_ENFORCES_AUTHORIZATION=true`. A real device must use a reachable protected API URL; do not use cleartext HTTP over an untrusted network.

Backend configuration variables: `HELMET_DB_PATH` selects the local SQLite file; `SAFETY_PROFILES_PATH` selects workplace rules. CV model/source options are CLI/config inputs. ML training/evaluation takes explicit dataset and output paths. AWS is optional and no AWS credentials are needed for local workflows.

## Health, logs and troubleshooting

`GET /health` checks whether the API and local storage can answer. Each API response carries an `X-Request-ID`; request logs report route template, status and duration. Use this ID to correlate a client report with server logs. Do not log a telemetry body to debug a request; reproduce with synthetic fixtures and inspect validation errors.

Troubleshooting sequence:

1. Confirm the API is bound to `127.0.0.1:8000`, then query `/health`.
2. Confirm `HELMET_DB_PATH` parent directory exists and is writable; stop the process before moving/replacing SQLite files.
3. Check `SAFETY_PROFILES_PATH` points to valid JSON; without a matching workplace profile risk may be `Unknown`.
4. For dashboard failures, check `VITE_API_BASE_URL`, browser network errors and CORS origin. Do not treat demo login as server identity.
5. For CV failures, verify model path and video source. Do not include RTSP credentials in a command line or issue report.
6. For mobile emulator access, use the emulator's host bridge address; `/health` should be reachable before investigating app parsing.

## Performance measurements

Measurements are local development measurements on the current machine, not cloud, multi-user, physical helmet, CCTV, or production measurements. Timings vary with CPU, disk, loaded dependencies, and background work. No concurrency or network latency was included unless stated.

- API workload: `python .\tests\benchmark_local_performance.py --samples 100`. This creates a temporary SQLite database and sequentially submits 100 synthetic telemetry messages across 10 synthetic device IDs, then reads computed status for each; 100 posts accepted and all 100 risk reads returned Critical. POST latency: mean 15.029 ms, p50 14.388 ms, p95 17.163 ms, max 64.889 ms. Risk GET: mean 5.145 ms, p50 4.925 ms, p95 5.535 ms, max 18.175 ms. FastAPI TestClient avoids a real socket/network and this is not a throughput result.
- ML inference workload: `python -m machine_learning.benchmark_inference --csv .\machine-learning\private-datasets\prepared\skab-runs.csv --manifest .\machine-learning\private-datasets\prepared\skab-manifest.json --model <trained-model.joblib> --preprocessing <preprocessing.json> --samples 1000 --warmup 10`. It cycles held-out SKAB rows and includes feature validation, scaling, model scoring and event construction: 1,000 calls, mean 9.125 ms, p50 9.050 ms, p95 9.602 ms, max 15.526 ms. This is anomaly analytics for the selected SKAB dataset, not a helmet danger prediction.
- CV evaluation: the existing labelled evaluation run used six images, Hardhat and NO-Hardhat classes, IoU 0.5; 19 TP, 0 FP, 1 FN, precision 1.00, recall 0.95, mean 561.410 ms/image. This small sample is not representative of workplaces. One helmet was missed. The referenced dataset license/attribution is recorded in `docs/testing/computer-vision-evaluation.md`.

For CV latency, the prior local microbenchmark used two warm-ups and ten repeated single-image ONNX CPU inferences at 640 input size including image load: mean 452.581 ms, p50 455.063 ms, p95 481.143 ms, min 413.588 ms, max 497.100 ms. Repeated inference on one image is a latency microbenchmark, not an accuracy or throughput result. Re-run the labelled evaluation before making model claims.

## Tests and checks rerun

- Python: `python -m pytest -q` — **74 passed**.
- Dashboard: `npm test -- --run` — **8 passed, 1 skipped** (live API integration test skipped without its live-service configuration); `npm run build` succeeded.
- Dashboard production dependency audit: `npm audit --omit=dev` — **0 vulnerabilities**.
- Flutter: `flutter test` — **19 passed**.
- Python dependency consistency: `python -m pip check` — no broken requirements.
- Performance scripts: API and ML measurements above completed.
- The later real-browser demo run found that the default API client passed the browser's `fetch` function without its required global context. This caused actual browser requests to fail despite mocked component tests. The client now binds `globalThis.fetch`, a regression test covers that behavior, and the rerun live browser walkthrough displayed the backend telemetry/risk/incident. Dashboard tests now report 9 passed and 1 live-only skipped in the default run; the separate live integration test passed.

These checks do not establish production readiness or safety certification.

## Deployment and safeguards

The supported demonstration environment and the future industrial boundary are documented separately in [demo-industrial-boundary.md](demo-industrial-boundary.md). Do not promote this demonstration setup into an industrial environment by merely changing its host or database URL.


The reproducible supported deployment at this stage is local development on loopback. For an externally reachable deployment, first implement identity and server-side role enforcement, TLS, secrets management, request limits/rate controls, durable storage operations and backup/restore, retention/deletion, monitoring/alerting, and security review of concrete infrastructure. Do not deploy the dashboard with simulated login as access control. Do not expose debug/dev servers. No AWS resources are currently deployed, so no cloud deployment can be verified.

Known limitations include no server authentication/authorization, no retention automation or database encryption policy, no production deployment manifest, no real-world device evaluation, no comprehensive privacy policy, no dedicated Pub audit command, no concrete IAM policy, and small CV/ML datasets that limit generalization.

## AWS cleanup procedure (only if resources are added later)

No resources exist to clean up now. When deploying in the future, use the actual stack inventory and execute a reviewed teardown in dependency order:

1. Disable device publishing and stop clients; preserve any evidence required by the project.
2. Disable IoT Rules and detach/disable certificates before deleting device identities, policies, and certificates. Revoke credentials that were issued.
3. Disable API Gateway routes/stages and Lambda event sources/triggers; then remove Lambda functions, versions, log subscriptions and execution roles after confirming no other workload uses them.
4. Disable SNS subscriptions/topics after exporting needed configuration; remove alarms, dashboards and log groups according to the selected retention requirement.
5. Export required DynamoDB data first. Delete tables, indexes, backups and streams only after confirming retention and backup needs.
6. Remove IoT policies, roles, log groups, alarms and supporting resources after checking for dependencies; inspect the billing console after teardown for residual charges.
7. Re-run infrastructure inventory and confirm no resources remain. Do not delete shared account resources or records subject to retention obligations.

Use a stack-specific deployment and cleanup tool (for example, CloudFormation) once infrastructure is defined, and review its change set before applying. This is a future procedure, not a claim that AWS deployment exists.

## Report relationship

This technical review preserves the detailed findings and measurement methods; the final-year report provides the broader project narrative and refers back here. Neither document claims production readiness or safety certification.
