import csv
from datetime import datetime, timezone

import pytest
import numpy as np

from machine_learning.data import DatasetManifest, DevicePartitions, FeatureDefinition, load_samples
from machine_learning.pipeline import AnalyticsPredictor, _binary_metrics, train_evaluate_and_save
from machine_learning.prepare_skab import FEATURE_MAP, SPLIT_RUNS, prepare


def _manifest():
    return DatasetManifest(
        dataset_name="synthetic mechanics fixture",
        source="temporary pytest fixture; not project evaluation data",
        license="generated for tests",
        attribution="none",
        intended_use="academic_evaluation",
        label_definition="fixture labels generated deterministically for software tests",
        features=[FeatureDefinition(name="temperature_c", unit_code="Cel")],
        partitions=DevicePartitions(train=["synthetic-train"], validation=["synthetic-validation"], test=["synthetic-test"]),
        n_estimators=10,
    )


def _write_csv(path, *, missing_feature=False, malformed_time=False):
    fields = ["source_event_id", "device_id", "workplace_id", "observed_at", "anomaly_label", "temperature_c"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        index = 0
        for split, device in (("train", "synthetic-train"), ("validation", "synthetic-validation"), ("test", "synthetic-test")):
            labels = [0] * (12 if split == "train" else 6) + [1, 1]
            for label in labels:
                value = 20 + ((index % 5) * .1) if not label else 42 + (index % 3)
                writer.writerow({
                    "source_event_id": f"synthetic-event-{index:03d}",
                    "device_id": device,
                    "workplace_id": "synthetic-workplace",
                    "observed_at": "bad-time" if malformed_time and index == 0 else f"2026-01-01T00:{index:02d}:00Z",
                    "anomaly_label": label,
                    "temperature_c": "" if missing_feature and index == 0 else value,
                })
                index += 1


def test_binary_metrics_are_recalculated_from_confusion_counts():
    # TP=3, FP=1, TN=4, FN=2 gives precision=.75, recall=.60,
    # F1=2/3 and FPR=.20. This is synthetic metric math, not dataset evidence.
    metrics = _binary_metrics(
        np.asarray([1, 1, 1, 0, 0, 0, 0, 1, 1, 0]),
        np.asarray([1, 1, 1, 1, 0, 0, 0, 0, 0, 0]),
        0.5,
    )

    assert (metrics.true_positives, metrics.false_positives) == (3, 1)
    assert (metrics.true_negatives, metrics.false_negatives) == (4, 2)
    assert metrics.precision == pytest.approx(0.75)
    assert metrics.recall == pytest.approx(0.6)
    assert metrics.f1 == pytest.approx(2 / 3)
    assert metrics.false_positive_rate == pytest.approx(0.2)
    assert metrics.sample_count == 10


def test_load_samples_rejects_malformed_timestamp_and_missing_feature(tmp_path):
    path = tmp_path / "synthetic.csv"
    _write_csv(path, malformed_time=True)
    with pytest.raises(ValueError, match="ISO-8601 UTC"):
        load_samples(path, _manifest())
    _write_csv(path, missing_feature=True)
    with pytest.raises(ValueError, match="missing or non-finite"):
        load_samples(path, _manifest())


def test_device_partitions_reject_overlap():
    with pytest.raises(ValueError, match="exclusive"):
        DevicePartitions(train=["synthetic-device"], validation=["synthetic-device"], test=["synthetic-test"])


def test_train_save_load_and_predict_separate_analytics_event(tmp_path):
    csv_path = tmp_path / "synthetic.csv"
    manifest_path = tmp_path / "manifest.json"
    output = tmp_path / "artifacts"
    _write_csv(csv_path)
    manifest_path.write_text(_manifest().model_dump_json(), encoding="utf-8")

    report = train_evaluate_and_save(csv_path, manifest_path, output)
    assert report.dataset_name == "synthetic mechanics fixture"
    assert report.model_test.sample_count == 8
    assert {"model.joblib", "preprocessing.json", "metrics.json"} == {p.name for p in output.iterdir()}

    predictor = AnalyticsPredictor(output / "model.joblib", output / "preprocessing.json")
    event = predictor.predict_event(
        device_id="synthetic-helmet", workplace_id="synthetic-workplace",
        source_event_id="synthetic-source-event", observed_at=datetime.now(timezone.utc),
        features={"temperature_c": 41.0},
    )
    assert event.event_type == "sensor_anomaly_prediction"
    assert event.outcome in {"anomaly", "not_flagged"}
    if event.outcome == "not_flagged":
        assert "does not establish safety" in event.explanation
    with pytest.raises(ValueError, match="feature set mismatch"):
        predictor.predict_event(
            device_id="synthetic-helmet", workplace_id="synthetic-workplace",
            source_event_id="synthetic-source-event-2", observed_at=datetime.now(timezone.utc), features={},
        )
    with pytest.raises(ValueError, match="finite number"):
        predictor.predict_event(
            device_id="synthetic-helmet", workplace_id="synthetic-workplace",
            source_event_id="synthetic-source-event-3", observed_at=datetime.now(timezone.utc),
            features={"temperature_c": float("nan")},
        )


def test_predictor_requires_model_and_configuration(tmp_path):
    with pytest.raises(FileNotFoundError):
        AnalyticsPredictor(tmp_path / "missing.joblib", tmp_path / "missing.json")


def test_skab_adapter_creates_experiment_disjoint_manifest(tmp_path):
    source = tmp_path / "source"
    for run in (run for groups in SPLIT_RUNS.values() for run in groups):
        category, number = run.rsplit("-", 1)
        run_dir = source / category
        run_dir.mkdir(parents=True, exist_ok=True)
        source_path = run_dir / f"{number}.csv"
        with source_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["datetime", *FEATURE_MAP, "anomaly"], delimiter=";")
            writer.writeheader()
            for index, label in enumerate((0, 1)):
                writer.writerow({"datetime": f"2020-01-01 00:00:0{index}", "anomaly": label, **{name: index + 1 for name in FEATURE_MAP}})

    csv_path, manifest_path = prepare(source, tmp_path / "prepared")
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    samples = load_samples(csv_path, manifest)
    assert [len(samples[name]) for name in ("train", "validation", "test")] == [40, 14, 14]
    assert len(manifest.partitions.train) == 20
    assert len(manifest.partitions.validation) == 7
    assert len(manifest.partitions.test) == 7
