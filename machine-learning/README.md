# Experimental sensor analytics (Task 8)

This module defines one experimental task: **binary statistical anomaly
classification for valid, labeled multivariate telemetry rows**. It compares a
robust per-feature z-score baseline against an Isolation Forest. The threshold
for each is selected on the validation devices by F1; the test devices are
scored once after threshold selection. A model flag is only an unusual-pattern
signal. A `not_flagged` output does not establish that a workplace is safe.

The analytics code is separate from `backend/app/safety/` and never changes its
rule evaluation, risk levels, incidents, or thresholds. The analytics output
uses its own `AnalyticsEvent` schema and `/api/v1/analytics/events` storage path;
it does not become a `SafetyEvent` or trigger an incident.

## Dataset review and benchmark result

The project SQLite database still has no telemetry rows. For an initial
experimental benchmark, this project uses selected runs from the public SKAB
industrial water-circulation testbed dataset under its repository GPL-3.0
license. The test partition contains seven held-out runs. Isolation Forest
achieved 0.922 recall, 0.558 F1, and a 0.704 false-positive rate; the robust
z-score baseline achieved 0.907 recall, 0.578 F1, and a 0.629 false-positive
rate. The detector missed 196 labeled test rows and falsely flagged 3,498
normal rows. These are row-level benchmark results from SKAB, not helmet
performance or safety predictions. Full protocol and results are in the
[evaluation report](../docs/testing/ml-evaluation-readiness.md) and
[metrics JSON](../docs/testing/ml_skab_evaluation_metrics.json).

## Input data contract

The CSV needs these columns:

```text
source_event_id,device_id,workplace_id,observed_at,anomaly_label,<feature columns...>
```

`observed_at` must be ISO-8601 UTC. `anomaly_label` is `0` for independently
reviewed non-anomalous data and `1` for independently reviewed anomalous data.
Each feature name and unit code is specified in a JSON manifest. Null, missing,
non-numeric, NaN, and infinite feature values are rejected; no silent imputation
to zero is performed. Do not derive labels from the rule engine's risk output.

The split manifest explicitly assigns whole device IDs (or experiment run IDs
for SKAB) to train, validation, and test. Groups cannot cross partitions. The
code fits preprocessing and the model using only normal (`0`) rows from
training groups. Validation labels select thresholds; test data does not
influence fitting or threshold selection. Each partition must contain both
labels. At least ten training normal rows is only a mechanical guard, not a
recommendation for scientific adequacy.

## Reproduce the SKAB evaluation

Install optional dependencies from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
```

Clone the reviewed source revision, prepare the checked-in run split, and train:

```powershell
git clone https://github.com/waico/SKAB.git .\machine-learning\private-datasets\SKAB
git -C .\machine-learning\private-datasets\SKAB checkout b2c0d46c2971dcbfe71e26087b6d231998bb91c2
.\.venv\Scripts\python.exe -m machine_learning.prepare_skab `
  --source .\machine-learning\private-datasets\SKAB\data `
  --output .\machine-learning\private-datasets\prepared
.\.venv\Scripts\python.exe -m machine_learning.cli `
  --csv .\machine-learning\private-datasets\prepared\skab-runs.csv `
  --manifest .\machine-learning\private-datasets\prepared\skab-manifest.json `
  --output .\machine-learning\artifacts\skab-anomaly-v1
```

The exact source revision, full metrics, and explicit limits are in the linked
evaluation report. To adapt the pipeline to future helmet telemetry, use an
independently labeled dataset and device-exclusive splits; do not treat SKAB as
helmet ground truth.

The run writes `model.joblib`, `preprocessing.json`, and `metrics.json` locally.
Artifacts and private datasets are Git-ignored. `metrics.json` reports confusion
counts, precision, recall, F1, and false-positive rate for both validation and
test sets. `preprocessing.json` records features/units, device splits, seed,
thresholds, provenance, and interpretation. `AnalyticsPredictor` loads these
artifacts and requires the exact configured feature set.

Only load `joblib` artifacts produced by a trusted local run; pickle-based model
artifacts can execute code when loaded. A model result is stored separately by
`POST /api/v1/analytics/events` (or retrieved with `GET /api/v1/analytics/events`).
The local backend requires a bearer token and should remain loopback-only.

## Tests

The tests use small, explicitly synthetic fixtures only to test splitting,
training mechanics, save/load, event generation, malformed input, and required
feature handling. Their toy metrics are never reported as project evaluation.
Run the full suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
