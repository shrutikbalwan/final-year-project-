# SKAB evaluation reproduction verification — 2026-10-17

## Dataset and provenance

This run used the existing local clone of the public [Skoltech Anomaly
Benchmark (SKAB)](https://github.com/waico/SKAB), checked out at
`b2c0d46c2971dcbfe71e26087b6d231998bb91c2`. The checkout includes the
repository's GPL-3.0 license. SKAB v0.9 describes 34 labeled experimental
water-circulation test runs and a separate anomaly-free file. The adapter
selects the 34 runs listed in
[`skab-reproduction-manifest.json`](skab-reproduction-manifest.json).
Check the license and attribution requirements before obtaining or reusing the
data. Cite Katser and Kozitsin (2020), DOI `10.34740/KAGGLE/DSV/1693952`.

Source documentation says `anomaly` is a per-row 0/1 anomaly label; this is the
water-loop benchmark's process anomaly label. The selected eight features and
units are recorded in the manifest. The adapter preserves source row order,
maps labels directly, and synthesizes ordinal UTC timestamps because the
source timestamps are timezone-naive. These timestamps are parser metadata,
not features. Each experimental run stays wholly within one split: 20 training,
7 validation, and 7 test runs. All 35 source CSV files were present; 34 were
selected by design.

The preprocessing and evaluation protocol is implemented in
`machine_learning/prepare_skab.py`, `machine_learning/data.py`, and
`machine_learning/pipeline.py`:

- Fit both methods using only normal-labeled rows in training runs.
- Robust z-score baseline: per-feature median and MAD scale, with IQR fallback
  and `1.0` for constant dimensions; row score is maximum absolute scaled
  feature deviation.
- Isolation Forest: `RobustScaler`, 200 estimators, seed 42, one worker, and
  contamination 0.05.
- Choose each threshold on validation labels by F1; ties prefer precision,
  then the higher threshold. Apply the fixed thresholds to test once.
- The source split groups are disjoint. Preprocessing, fitting, and threshold
  selection do not use test rows. Since each run is a distinct experiment,
  this prevents run-level leakage; it does not establish independent site or
  process generalization.

## Verification run

Environment: Windows x64, CPython 3.13.15, NumPy 2.5.4, scikit-learn 1.9.1,
joblib 1.6.0. The source clone was already present, at the exact revision,
with clean Git status. No data was downloaded. Training used the prepared
CSV and manifest produced by the documented adapter. Output was written to a
new ignored directory, `machine-learning/artifacts/skab-anomaly-v1-verify-20261017/`;
the existing model artifacts were not overwritten.

The run command was:

```powershell
.\.venv\Scripts\python.exe -m machine_learning.cli `
  --csv .\machine-learning\private-datasets\prepared-repro-20261017\skab-runs.csv `
  --manifest .\machine-learning\private-datasets\prepared-repro-20261017\skab-manifest.json `
  --output .\machine-learning\artifacts\skab-anomaly-v1-verify-20261017
```

I independently loaded the newly written model and preprocessing config,
scored validation and test rows, and recalculated confusion matrices and
metrics using scikit-learn's `confusion_matrix`, `precision_score`,
`recall_score`, and `f1_score`. This independently recalculated the metrics
from the saved model's scores and thresholds; it did not simply read the
pipeline's `metrics.json`.

## Actual results

| Method / split | TP | FP | TN | FN | Precision | Recall | F1 | False-positive rate | Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Robust z-score / validation | 2,760 | 2,997 | 2,202 | 176 | 0.4794 | 0.9401 | 0.6350 | 0.5765 | 8,135 |
| Isolation Forest / validation | 2,763 | 3,530 | 1,669 | 173 | 0.4391 | 0.9411 | 0.5988 | 0.6790 | 8,135 |
| Robust z-score / test | 2,295 | 3,124 | 1,842 | 234 | 0.4235 | 0.9075 | 0.5775 | 0.6291 | 7,495 |
| Isolation Forest / test | 2,333 | 3,498 | 1,468 | 196 | 0.4001 | 0.9225 | 0.5581 | 0.7044 | 7,495 |

The test confusion counts and four-decimal metrics reproduce the historical
report exactly. The independent F1 recalculation differs from the pipeline's
full-precision Isolation Forest validation F1 only in the final floating-point
bit (`0.5987647632462889` vs. `0.5987647632462888`); rounded results and
confusion counts are identical. The prior historical test values remain
unchanged: baseline F1/recall/FPR `0.5775 / 0.9075 / 0.6291`, Isolation Forest
`0.5581 / 0.9225 / 0.7044`.

The results JSON is `docs/testing/ml-reproduction-2026-10-17.json`; the local
run's exact output, model and preprocessing config are under the ignored
artifact directory noted above. The source dataset and prepared CSV remain
local and ignored. Reproduce from scratch with the documented acquisition and
adapter commands in [the ML reproduction report](ml-reproduction-2026-10-17.md).

Relevant automated checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The new test checks metric arithmetic against known synthetic confusion
counts; it is software validation only, not additional model-performance
evidence.

## Scope and limitations

This is an experimental anomaly-classification result for one public water-loop
benchmark. It is not helmet data, not a validated industrial safety predictor,
and not a substitute for the separate rule-based safety engine. It does not
predict worker health, PPE compliance, falls, gas hazards, or safety. Large
false-positive rates, temporal correlation between rows, and only seven held-out
runs limit interpretation. A `not_flagged` model outcome never means safe.
