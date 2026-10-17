# Task 11 integration test plan and evidence (review draft)

**Status:** Draft for review; final project documentation is pending approval.  
**Run date:** 2026-10-17  
**Data:** Synthetic IDs and payloads only, except the separately attributed PPE dataset sample referenced below. No physical helmet or worker data was used.

## Workflow plan and coverage

| Stage or failure | Available check | Result and boundary |
| --- | --- | --- |
| Telemetry validation -> SQLite -> risk -> incident -> history -> acknowledgement | `tests/test_integration_workflows.py::test_telemetry_to_persisted_risk_incident_ack_and_duplicate`; profile uses explicitly synthetic thresholds | Passed: Critical risk and reason persisted; exact duplicate returned 409; repeated event merged into one incident; history recorded acknowledgement. Acknowledgement was accepted without credentials (HTTP 200), so authorization is a known security gap, not a passing access-control result. |
| Multiple devices/workplaces; missing, stale, malformed readings; unknown device | `test_multiple_workplaces_missing_stale_invalid_and_invalid_payloads` plus backend/contract tests | Passed: missing/stale/unknown-profile status remained Unknown; malformed input returned 422; nonexistent helmet returned 404. |
| Camera event -> validation -> storage -> duplicate handling | `test_camera_event_validation_and_persistence` and computer-vision tests | Passed for event conversion/storage, duplicate 409, malformed 422. Camera events currently do not enter the rule engine or create incidents. No real camera was exercised in this run. |
| Camera/model errors and delivery retry | `tests/test_computer_vision.py` | Passed with synthetic images/video and detector/network doubles. A transient retry with the same event ID is mocked; this is not a real network interruption or deployed model run. |
| Storage interruption | Backend API tests inject storage exceptions | Passed for generic 500/503 responses. Actual disk failure and recovery after storage reconnection were not exercised. |
| Dashboard loading, empty and error states; API client contract/network failures | React/Vitest component and API tests; `tests/run-live-dashboard-e2e.ps1` | Passed: mocked UI states passed, and the live React/jsdom scenario posted telemetry to a temporary FastAPI/SQLite instance then rendered the Critical helmet and generated incident from actual HTTP reads. No interactive browser automation was available. Production auth is not implemented. |
| Flutter parsing, session/error states and UI logic | Flutter analyzer and unit/widget tests | Passed (19 tests). The emulator app/API smoke was recorded separately on 2026-10-17; this run did not perform a UI automation scenario or authorized acknowledgement. |
| ML analytics event | Backend and ML tests in the Python suite | Passed for schema/storage and evaluation pipeline tests. Model analytics are kept separate from safety incidents. No new end-to-end model inference was run in this integration pass. |
| Unauthorized API access | At the time of the Task 11 run, acknowledgement returned HTTP 200 without credentials. | Historical finding; the Task 12 auth task added server-side bearer verification and role checks. Current coverage is in `tests/test_auth.py`. |
| Notifications | Repository inspection | Not testable: no SNS/provider or local notification delivery integration exists. Failure/retry behavior remains unimplemented. |
| AWS path | Repository inspection (`cloud/` contains only `.gitkeep`) | Not deployed or tested. No AWS resources or billable services were created. |

## Automated results

- Python backend/contracts/rules/CV/ML and new integration tests: **73 passed, 0 failed** (`.venv` Python, pytest; 7.40 s).
- React dashboard: **8 passed, 0 failed, 1 live-only test skipped** in the default run; production TypeScript/Vite build succeeded. The explicit live integration test passed separately (**1 passed**).
- Flutter: `flutter analyze` reported no issues; **19 tests passed**.
- Android emulator was connected (`emulator-5554`), but no mobile UI automation was run in this task.
- The live dashboard integration uncovered a contract mismatch: the web client expected `last_seen_status: "known"`, while contract v1 returns `"valid"`; the web client also omitted `"intermittent"` connectivity. Both enums now match the shared backend contract, and the live workflow passes.
- Existing CV evaluation evidence is a previous, small six-image CPU sample in [computer-vision-evaluation.md](computer-vision-evaluation.md): 19 TP, 0 FP, 1 FN, precision 1.00, recall 0.95, mean 482.90 ms/image. Those values are from that six-image labeled sample, are not measurements from this integration run or physical hardware, and are too small to establish deployment performance.

## Local performance sample

Workload: 100 serial synthetic telemetry POSTs, across 10 device IDs at one configured synthetic workplace, each followed by a risk GET; FastAPI `TestClient`, temporary SQLite database, one process, no network hop or concurrent clients. All 100 posts were accepted and all risk results were Critical. This also exercised incident merge/deduplication.

| Operation | Mean | p50 | p95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Telemetry POST, including persistence and rule/incident processing | 15.172 ms | 14.396 ms | 16.412 ms | 79.754 ms |
| Risk GET | 5.160 ms | 4.919 ms | 5.785 ms | 12.184 ms |

This is a local in-process synthetic sample, not production capacity evidence or a concurrent-load test. Timing depends on the development machine and should be rerun on the intended host before making a performance claim.

## Reproduce

From the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q

Set-Location .\web-dashboard
npm test -- --reporter=dot
npm run build
Set-Location ..

Set-Location .\mobile-app
flutter analyze
flutter test
Set-Location ..
```

Flutter may need its SDK bin added to the current shell PATH first:

```powershell
$env:Path = "D:\tools\flutter\bin;$env:Path"
```

To run only the new backend workflow checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_integration_workflows.py
```

To run the actual telemetry -> API -> dashboard test, which starts a temporary
backend on port 8011, uses a synthetic-only workplace rule profile and SQLite
database, posts a synthetic 40 Cel reading, and asserts the helmet risk and
created incident appear in the rendered dashboard:

```powershell
.\tests\run-live-dashboard-e2e.ps1
```

The script keeps its temporary database and server logs under the current
user's `%TEMP%` directory and stops the temporary API when it exits.

## Open limitations before final report

1. At the time of this dated integration run, the API was unauthenticated. The later authentication implementation now has dedicated 401/403 and authorized acknowledgement tests; this local auth is still not production identity management.
2. Camera events do not currently create incidents, and camera-event-to-dashboard is only covered at the API storage boundary.
3. AWS and notifications are design-only/unavailable; transient delivery retry is tested with mocks only.
4. Actual network outage/reconnection, disk failure/recovery, concurrent load, and interactive browser UI driven by live backend data were not measured. The live dashboard check renders React in jsdom while issuing real HTTP requests.
5. No current real-time model inference or new labeled-set detection evaluation was included in this run; the previous six-image CV sample is limited evidence only.
