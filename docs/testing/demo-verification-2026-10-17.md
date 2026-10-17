# Clean-start demonstration verification — 2026-10-17

## Result

**Passed in the local synthetic demonstration environment.** This is software integration evidence, not physical-helmet, industrial-site, or production evidence.

## Clean start and end-to-end workflow

Command from the project root:

```powershell
.\tests\start-demo.ps1 -ApiPort 8012 -DashboardPort 5173
```

The script started a new API process with an isolated temporary SQLite database, loaded the example development workplace profile, POSTed one generated synthetic telemetry event, read its risk, verified the expected `Critical` result, and started the dashboard against that API.

- Synthetic event: `demo-event-716f9dfffcc3484f872879dad29775c5`
- Synthetic device: `demo-helmet-001`
- Synthetic incident: `b26ecc71-4c63-40b6-b60a-eb7b0a6114c4`
- Temporary database: `C:\Users\shrut\AppData\Local\Temp\smart-helmet-demo-9d52b866c2944fae9725723112163d32\demo.sqlite3`
- Session log/database directory preserved after cleanup: `C:\Users\shrut\AppData\Local\Temp\smart-helmet-demo-9d52b866c2944fae9725723112163d32`

Microsoft Edge opened the live dashboard. The walkthrough verified API online, the synthetic helmet, `Critical`, the example rule reason, and the incident list. Screenshots were captured directly from the browser without editing:

![Fresh sign-in page from the clean-start run.](../screenshots/demo-2026-10-17-sign-in.png)

![Fresh live overview from the clean-start run.](../screenshots/demo-2026-10-17-overview.png)

![Fresh incident list from the clean-start run.](../screenshots/demo-2026-10-17-incidents.png)

After capture, `tests/stop-demo.ps1` stopped the process trees recorded for this session. Ports 8012 and 5173 were no longer listening. The temporary database and logs were preserved for review.

## Automated test results

Commands and results from this clean verification:

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q` | **74 passed** (8.80 s) |
| `npm test -- --run` in `web-dashboard/` | **9 passed, 1 skipped**; skipped test requires the separately configured live API URL |
| `npm run build` in `web-dashboard/` | **Passed**; TypeScript and Vite production build completed |
| `.\tests\run-live-dashboard-e2e.ps1` | **1 passed**; synthetic telemetry was POSTed to temporary FastAPI/SQLite and rendered in React with its risk and incident |
| `flutter test` in `mobile-app/` | **19 passed** |
| `.\.venv\Scripts\python.exe -m pip check` | **No broken requirements found** |

The live browser walkthrough is additional to the automated component tests. All message content and device/workplace identifiers were synthetic. No physical helmet, worker, or industrial camera was involved.

## Department report format and submission requirements

The repository and its documentation folders contain no department handbook, report template, assessment rubric, or submission checklist. The project report is currently Markdown and its headings reflect the requested project topics; this does **not** confirm that it matches a department's required order, page layout, citation style, declaration pages, binding/PDF format, or submission process. Those requirements cannot be verified without the institution/department and its current template or guidelines.
