# Reproducible SKAB anomaly evaluation

Reproduced locally on 2026-10-17 from the repository's existing SKAB checkout. No data was downloaded during this run. The dataset is the public Skoltech Anomaly Benchmark (SKAB), source `https://github.com/waico/SKAB`, revision `b2c0d46c2971dcbfe71e26087b6d231998bb91c2`. The checked-out repository contains a GPL-3.0 license. The project does not commit or redistribute raw SKAB data; developers obtaining it should review that license and cite Katser and Kozitsin (2020), DOI `10.34740/KAGGLE/DSV/1693952`.

This is a process anomaly benchmark on a water-circulation testbed. It is not a helmet-safety evaluation or a validated safety decision model.

## Reproduction environment and inputs

- Python 3.13.15 (Windows x64)
- NumPy 2.5.4, scikit-learn 1.9.1, joblib 1.6.0
- Dataset source revision above; local checkout was clean
- 34 selected runs: 20 train, 7 validation, 7 test. The checkout contains 35 CSV files because it also has one `anomaly-free` file; the adapter selects the 34 runs listed by the companion manifest.
- Eight numeric features and units, run-to-partition assignments, seed, estimator count, and contamination are recorded in [the exact manifest](skab-reproduction-manifest.json).

`prepare_skab.py` maps the SKAB labels as supplied (`0` normal, `1` anomalous), maps the eight source channels to named features with units, and preserves row order. SKAB timestamps have no timezone, so the adapter creates ordinal UTC metadata timestamps; timestamps are not model features. Each run is represented as a group ID, and all rows from each run remain in one split. It is not a physical device identifier.

The baseline is maximum absolute robust z-score, with median and MAD scale fit using only normal training rows. Isolation Forest uses a `RobustScaler` fit on the same normal training rows, 200 trees, seed 42, and one worker. Each method's threshold is selected on validation F1; ties favor precision and then the higher threshold. The held-out test set is only scored using those fixed thresholds. No test rows are used to fit preprocessing, fit the detector, or select thresholds.

## Commands

The local data was already available, so this run did not download it. To reproduce from scratch, first inspect and accept the dataset's GPL-3.0 terms, then obtain the precise source revision:

```powershell
git clone https://github.com/waico/SKAB.git .\machine-learning\private-datasets\SKAB
git -C .\machine-learning\private-datasets\SKAB checkout b2c0d46c2971dcbfe71e26087b6d231998bb91c2
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe -m machine_learning.prepare_skab `
  --source .\machine-learning\private-datasets\SKAB\data `
  --output .\machine-learning\private-datasets\prepared-repro
.\.venv\Scripts\python.exe -m machine_learning.cli `
  --csv .\machine-learning\private-datasets\prepared-repro\skab-runs.csv `
  --manifest .\machine-learning\private-datasets\prepared-repro\skab-manifest.json `
  --output .\machine-learning\artifacts\skab-anomaly-reproduced
.\.venv\Scripts\python.exe -m pytest -q tests\test_machine_learning.py tests\test_safety_engine.py
```

The actual run used unique ignored output paths `prepared-repro-20261017` and `skab-anomaly-v1-repro-20261017`; existing artifacts were not overwritten. Its exact metrics are preserved in [the metrics JSON](ml-reproduction-2026-10-17.json). The saved model, scaler, and preprocessing output remain local under the ignored artifacts directory.

## Results and comparison

All test metrics and thresholds exactly match the historical values in `ml_skab_evaluation_metrics.json`; there were no differences to explain. The robust z-score baseline test F1 is 0.5775037745 (rounded 0.5775), recall 0.9074733096, and false-positive rate 0.6290777286. Isolation Forest test F1 is 0.5581339713 (0.5581), recall 0.9224990115, and false-positive rate 0.7043898510. Both were evaluated on 7,495 rows from seven test runs. Isolation Forest produced 3,498 false positives and missed 196 labeled anomaly rows; the baseline produced 3,124 false positives and missed 234.

Relevant automated tests: `tests/test_machine_learning.py` and `tests/test_safety_engine.py` — **19 passed**. The ML output remains a separate `AnalyticsEvent`; the rule-based safety engine and its risk decisions were not changed.

## Limitations

Rows are temporally correlated, there are only seven held-out runs, and train/validation/test runs come from the same benchmark/testbed. These metrics do not establish generalization to a different process, device, site, helmet sensor, worker, or safety condition. The model does not predict heat stress, fatigue, falls, gas danger, PPE compliance, injury, or workplace safety. A `not_flagged` result never means safe.

