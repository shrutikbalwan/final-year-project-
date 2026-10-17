# API browser and endpoint check — 2026-10-16

## Browser access

- Server started with Uvicorn at `http://127.0.0.1:8000`.
- Chrome automation was denied before navigation: the browser security gate reported that the user declined permission for network egress to `http://127.0.0.1:8000`.
- No retry through another browser or indirect browser route was made.

## Endpoint checks

Executed the in-process FastAPI endpoint tests with `python -m pytest -q`.

........................                                                 [100%]
24 passed in 1.26s

## Risk level and incident reason check — 2026-10-16

Executed telemetry through the FastAPI `TestClient` using an isolated temporary SQLite database and a test-only workplace profile. All example rule thresholds are development values and are not certified industrial safety limits.

| Expected level | Result | Incident reason inspection |
|---|---|---|
| Normal | Confirmed; no incident created | Readings were valid and within configured rules. |
| Advisory | Confirmed; score 10 | `Development advisory temperature rule exceeded.` (rule `temperature-advisory`, weight 10). |
| Warning | Confirmed; score 40 | Advisory and warning temperature rule reasons were recorded with weights 10 and 30. |
| Critical | Confirmed; score 60 | `Development critical gas rule exceeded.` (rule `gas-critical`, weight 60). |
| Unknown | Confirmed; score 0 | Missing gas reading reason recorded: `Reading 'reading-0002' for 'gas_concentration' is missing.` |

The first attempt returned `Unknown` for the Normal case because the fixture's battery reading timestamp was stale. This was expected fail-safe behavior. The verification payload was corrected to refresh the battery timestamp along with all other readings, then the five-case check passed. No backend behavior change was needed.

The Unknown case confirms a missing required reading creates a review incident rather than a safe/Normal result. Each non-Normal incident's severity, score, and non-empty reason were read back from `GET /api/v1/incidents`.
