# Backend test report

**Run date:** 2026-10-16  
**Command:** `\.venv\Scripts\python.exe -m pytest -q`  
**Result:** 49 passed, 0 failed.

The suite uses pytest and FastAPI's `TestClient`, temporary SQLite databases, contract examples, and identities explicitly marked `synthetic-*`. It covers valid telemetry; explicit null/missing readings and missing required fields; malformed and non-UTC timestamps; stale readings and telemetry; duplicate event IDs and repeated incident triggers; unknown helmet/incident IDs; storage failures without leaking internal details; weighted rule scoring and all risk states; incident creation, acknowledgement, and escalation; bounded limits and pagination for helmets and incidents.

The first expanded run exposed a test-fixture error: its missing-value case retained the original `value`. The test now removes that field, and the API correctly rejects the payload with HTTP 422. No production defect or known failing test remains from this run.

## Scope limits

- API tests run in-process through `TestClient`; no live Uvicorn/browser integration check was repeated.
- SQLite is the only implemented storage adapter. AWS/DynamoDB and concurrent load behavior are not tested or implemented.
- Example safety thresholds are development-only and are not certified industrial safety limits.

## Captured test output — 2026-10-16

Command run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Complete terminal output:

```text
.................................................                        [100%]
49 passed in 1.88s
```

Process exit code: `0`.
