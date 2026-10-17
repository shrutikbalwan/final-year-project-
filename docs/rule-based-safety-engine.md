# Rule-based safety engine and incident workflow

The engine is in `backend/app/safety/` and has no FastAPI dependency. A caller
provides a shared `DeviceTelemetry` model and an evaluation time; the engine
returns a `RiskEvaluation` with a risk level, integer score, matched rule IDs,
source reading IDs, quality issue codes, and human-readable reasons.

## Workplace profiles

Profiles are validated Pydantic configuration objects indexed by `workplace_id`.
To load a profile file when starting the local API, set:

```powershell
$env:SAFETY_PROFILES_PATH = ".\config\workplace_profiles.json"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

`config/workplace_profiles.example.json` demonstrates the file shape. Copy it to
`workplace_profiles.json`, replace the example workplace and rules with values
approved for the actual site, and keep the example values out of operational
use. If there is no profile for a workplace, evaluation is `Unknown` and a
review incident is created. A profile requires at least one rule and a rule for
each required measurement.

Each rule declares a rule ID, measurement and unit code, comparator (`gt`,
`gte`, `lt`, `lte`), threshold, weight from 1 to 100, minimum risk level, and
reason. A matching rule contributes its weight once per telemetry message.
Weights are summed and compared with the profile's strictly increasing
`score_bands`. The computed level is the higher of the score band and the
highest level assigned to a matched rule, so one explicit Critical rule cannot
be diluted by lower-weight matches.

Risk levels are `Normal`, `Advisory`, `Warning`, `Critical`, and `Unknown`.
Every result explains its matched rules, weights, score, and data-quality
issues. This is a configurable weighted rule system; it is **not machine
learning**. The example sensor thresholds and score bands are development
values, are not certified industrial safety limits, and must be replaced and
approved before operational use.

## Data quality and fail-safe behavior

The engine detects telemetry older than `max_telemetry_age_seconds`, individual
readings older than `max_reading_age_seconds`, readings explicitly marked
`missing`, `stale`, or `invalid`, missing required measurements, unknown or
disconnected connectivity, missing/stale last-seen information, and measurement
unit mismatches. A valid reading with no configured rule also makes the
assessment `Unknown`. These conditions include a reason and quality issue code.

Quality uncertainty cannot produce `Normal`: if there is no higher risk rule
match, any detected data-quality issue sets the result to `Unknown`. If a valid
reading independently matches a Warning/Critical rule while another input is
faulty, the higher rule level is retained and the fault is still included in
the reasons. Consumers must never interpret Unknown, Missing, Stale, or Invalid
data as a safe workplace.

## Incident lifecycle

Every non-Normal evaluation creates an incident with a UUID, opened/updated UTC
time, risk severity, weighted score, explanation, source telemetry event and
reading/rule IDs, open status, occurrence count, and a history entry. Repeated
messages with the same device, workplace, matched rules, and quality issue
categories merge into the active open/acknowledged incident; the occurrence
count, latest source, score/severity, and history are updated. Closed or
resolved incidents do not block a later new incident.

`POST /api/v1/incidents/{incident_id}/acknowledge` accepts
`{"acknowledged_by":"supervisor-id"}`. Acknowledgement records its UTC time,
actor, status, and history entry. Repeating an acknowledgement is idempotent.
`GET /api/v1/incidents/{incident_id}/history` returns the ordered history
entries, also included on incident detail.

Escalation steps specify minimum risk (including `Unknown`), delay, target, and
optional repeat interval. `IncidentWorkflow.process_escalations()` appends due escalation
history entries; the local service checks for due steps when telemetry arrives.
A scheduled local worker or future Lambda can call the same workflow method.
This Phase 1 implementation records escalation targets; it does not send
notifications or integrate AWS.

## Validation

Run all checks with:

```powershell
python -m pytest -q
```

Tests cover normal readings, weighted threshold matches, missing and stale data,
sensor faults, profile/unit uncertainty, incident deduplication, acknowledgement,
and escalation timing.
