# Task 8: sensor anomaly benchmark evaluation

Evaluation date: 2026-10-16. This is an experimental **industrial process
anomaly benchmark**, not a Smart Safety Helmet safety evaluation.

## Selected task and dataset

The initial task is binary classification of SKAB's supplied per-row normal and
anomaly labels from eight synchronous process sensor readings. A flagged row
means it resembles a marked anomaly in the SKAB water-circulation testbed. It
does not identify a hazard, predict worker health, or establish workplace risk.

The selected public dataset is the [Skoltech Anomaly Benchmark (SKAB)](https://github.com/waico/SKAB).
Its repository describes multivariate readings from an instrumented water-loop
testbed and provides row labels. The source repository carries a GPL-3.0
license; the local checkout's `LICENSE` is retained with the ignored dataset.
This project uses it for academic evaluation and does not redistribute its raw
data. Cite Katser and Kozitsin (2020), DOI `10.34740/KAGGLE/DSV/1693952`.

The reviewed revision is `b2c0d46c2971dcbfe71e26087b6d231998bb91c2`. The clone
is under `machine-learning/private-datasets/SKAB/` and is ignored by Git. The
dataset README says SKAB v0.9 has 34 labeled experimental runs and describes
the measured channels and labels. We selected all 34 runs: 20 train, 7
validation, and 7 test. A whole run is the split group, represented in the
generic manifest's `device_id` field only to enforce group disjointness; these
are **not device IDs**. Runs from the same testbed and process categories occur
across partitions, so this does not measure transfer to a new sensor or site.

The source timestamps have no timezone. The adapter retains row order and
creates ordinal UTC timestamps only for the generic CSV parser; they are
metadata and are not features. Eight numeric channels are evaluated with
source units: two accelerometer RMS channels (`g`), current (`A`), pressure
(`bar`), two temperatures (`Cel`), voltage (`V`), and volume flow rate RMS
(`L/min`). Labels are taken directly from SKAB, not generated from this
project's safety rules.

## Training and evaluation protocol

The baseline is the maximum absolute robust z-score across features, with
median/MAD scale fitted on normal rows in the training runs. Isolation Forest
uses a `RobustScaler` fitted on those same normal training rows. Each method's
threshold is chosen by validation F1 (ties prefer precision, then the higher
threshold). The test runs are evaluated once using these fixed thresholds.
All samples from a run stay in its single partition. The configured random seed
is 42 and Isolation Forest uses 200 trees.

## Held-out test results

| Method | TP | FP | TN | FN | Precision | Recall | F1 | False-positive rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Robust z-score baseline | 2,295 | 3,124 | 1,842 | 234 | 0.4235 | 0.9075 | **0.5775** | 0.6291 |
| Isolation Forest | 2,333 | 3,498 | 1,468 | 196 | 0.4001 | **0.9225** | 0.5581 | 0.7044 |

The test partition contains 7,495 rows from seven runs: 2,529 anomalous and
4,966 normal. Isolation Forest missed 196 labeled anomaly rows and falsely
flagged 3,498 normal rows. The baseline missed 234 anomaly rows and falsely
flagged 3,124 normal rows. The selected Isolation Forest has higher recall but
lower F1 and more false alarms than the baseline on this split. Row scores are
temporally correlated, and seven held-out runs are a small number of
independent experiments; these figures are a benchmark result, not a stable
generalization estimate.

Full-precision validation/test metrics and decision thresholds are preserved
in [ml_skab_evaluation_metrics.json](ml_skab_evaluation_metrics.json) and in the local ignored
`machine-learning/artifacts/skab-anomaly-v1/metrics.json`. The local artifact
directory also contains `model.joblib` and `preprocessing.json`; the serialized
model is not committed. Only load trusted joblib artifacts.

## Limits and interpretation

- SKAB measures a water-circulation testbed, not a wearable helmet.
- Its anomaly labels represent process anomalies, not heat stress, fatigue,
  falls, gas exposure, PPE compliance, or worker injury.
- The result does not validate the feature set, sensor placement, sampling,
  threshold, or model for any helmet installation.
- The anomaly prevalence in this selected test set is 33.7%; operational event
  rates may differ substantially. Precision and false-alarm rate can change
  with prevalence and conditions.
- High false-positive counts make the current model unsuitable as an automatic
  safety or alert decision system.
- The detector emits a separate `AnalyticsEvent`; it does not alter the
  rule-based safety engine or create incidents. `not_flagged` never means safe.

Before making a helmet-related claim, collect appropriately approved and
independently labeled helmet telemetry, define a task-specific label guide, and
evaluate with held-out devices, workers/sites as applicable. Keep analytics
outputs advisory until such evaluation supports a narrowly stated use.

## Reproduction

From PowerShell at the project root:

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

The source checkout, prepared rows, manifest, and model artifacts are ignored
local files. The versioned report and metrics JSON preserve the evaluation
evidence for the final-year report.
