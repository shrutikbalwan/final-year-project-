# Smart Safety Helmet

AI-Based Multi-Industry Smart Safety Helmet Using IoT, Artificial Intelligence, Computer Vision and AWS Cloud.

> **Demonstration boundary:** this repository is an academic development/demo platform. It is not certified or validated for industrial safety decisions. Keep demo data, devices, camera feeds, accounts, networks, and notifications separate from real operations. See [the demonstration and industrial deployment boundary](docs/demo-industrial-boundary.md).

## Objectives

This project is intended to develop a safety-helmet platform that can support multiple industries by combining helmet-mounted sensing, IoT connectivity, computer vision, machine-learning analysis, and a web/mobile interface. The planned foundation separates shared data contracts, backend services, cloud integrations, vision and ML components, user interfaces, tests, and documentation.

AWS is an optional future deployment target. Core development can proceed locally without an AWS account. The simulator is not the primary application; any simulator added later will support development and testing of the helmet system.

## Project structure

- `contracts/` — shared event and API schemas
- `backend/` — application services and APIs
- `cloud/` — optional cloud adapters and deployment configuration
- `computer-vision/` — image/video processing components
- `machine-learning/` — model code and training/inference assets
- `web-dashboard/` — browser dashboard
- `mobile-app/` — mobile client
- `tests/` — automated checks
- `docs/` — design and setup documentation

## Experimental ML analytics (Task 8)

The optional `machine_learning` Python package contains an evaluated sensor
anomaly pipeline. On the public SKAB industrial testbed benchmark, the robust
z-score baseline achieved test F1 0.578 and Isolation Forest achieved 0.558.
These results are not helmet performance: the project has no labeled helmet
telemetry. Full metrics, missed detections, data provenance, and limits are in
[the evaluation report](docs/testing/ml-evaluation-readiness.md) and
[ML workflow](machine-learning/README.md). Install optional packages with
`python -m pip install -r requirements-ml.txt`.

## Prerequisites

- Windows 10 or 11
- Git for Windows
- Python 3.10 or newer (Python 3.13 is currently available in the inspected environment)
- Visual Studio Code with the Python extension

## Setup (Windows PowerShell)

Run these commands from the project root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation for this session, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again. Alternatively, use the environment directly without activation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In VS Code, open this folder and select `.venv\Scripts\python.exe` using **Python: Select Interpreter**.

## Optional AWS dependencies

No AWS account or AWS credentials are required for local development. When cloud integration work begins, install the optional packages with:

```powershell
python -m pip install -r requirements-aws.txt
```

Do not commit credentials. Store local configuration in an ignored `.env` file and provide a safe `.env.example` when configuration keys are introduced.

## Local backend API (Phase 1)

The backend uses the shared versioned contract and SQLite for local persistence.
See [docs/backend-local-api.md](docs/backend-local-api.md) for the PowerShell
commands, endpoint list, storage behavior, and API checks. The OpenAPI document
is generated at `/openapi.json` when the API is running. No AWS integration is
implemented.

The API uses Argon2 password hashes and expiring signed bearer tokens. Set up a
local account and role configuration using
[the authentication guide](docs/authentication-and-authorization.md) before
starting the backend; there is no default account or secret.

## React supervisor dashboard (Task 9)

The responsive React and TypeScript dashboard runs in `web-dashboard/` and reads
live data from the local backend. Windows setup, routes, and development-only
login instructions are documented in [web-dashboard/README.md](web-dashboard/README.md).
It includes history charts, risk reasons, incidents, stored camera events,
read-only workplace profiles, and a fleet CSV snapshot. Dashboard login uses
the local API account and backend-enforced roles; it is not a production identity
provider.

## Flutter mobile app (Task 10)

The Flutter client in `mobile-app/` consumes the same versioned telemetry and
incident API. Setup and Android run/build commands are in
[mobile-app/README.md](mobile-app/README.md). The local API authenticates users
and enforces roles; worker/device assignment and push notifications are not
implemented.

## Local computer vision (Task 7)

The optional `computer_vision` Python package processes images, recorded video,
webcams, and configured RTSP sources locally with OpenCV and optional YOLOv8
weights. Install `requirements-cv.txt` for Ultralytics inference. See
[computer-vision/README.md](computer-vision/README.md) for supported class
behavior, privacy notes, event delivery, and labeled evaluation. No weights or
footage are bundled, and no PPE model accuracy is claimed.

## Demonstration versus industrial deployment

Use only synthetic or explicitly permitted test data in the local demonstration environment. Do not connect the demo to real worker monitoring or use its status to decide whether a workplace is safe. Industrial use would require a separately designed, secured, site-validated and independently reviewed deployment. Details and the separation checklist are in [docs/demo-industrial-boundary.md](docs/demo-industrial-boundary.md).

The implementation-based final-year report and reproducible synthetic demo steps are in [docs/final-year-project-report.md](docs/final-year-project-report.md) and [docs/demo-runbook.md](docs/demo-runbook.md).

## Checks

```powershell
python --version
python -m pip --version
python -m pip check
python -m pytest
```

The Flutter client has its own analysis, unit-test, and build commands in
`mobile-app/README.md`.
