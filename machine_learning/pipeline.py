import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from .data import DatasetManifest, TelemetrySample, load_samples
from .models import AnalyticsEvent


MODEL_NAME = "isolation-forest-sensor-anomaly"
MODEL_VERSION = "0.1.0"


@dataclass(frozen=True)
class BinaryMetrics:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    sample_count: int


@dataclass(frozen=True)
class EvaluationReport:
    task: str
    dataset_name: str
    feature_names: tuple[str, ...]
    split_counts: dict[str, int]
    baseline_threshold: float
    model_threshold: float
    baseline_validation: BinaryMetrics
    model_validation: BinaryMetrics
    baseline_test: BinaryMetrics
    model_test: BinaryMetrics


def _binary_metrics(labels: np.ndarray, scores: np.ndarray, threshold: float) -> BinaryMetrics:
    predicted = scores >= threshold
    actual = labels.astype(bool)
    tp = int(np.count_nonzero(predicted & actual))
    fp = int(np.count_nonzero(predicted & ~actual))
    tn = int(np.count_nonzero(~predicted & ~actual))
    fn = int(np.count_nonzero(~predicted & actual))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return BinaryMetrics(tp, fp, tn, fn, precision, recall, f1, fpr, int(labels.size))


def _choose_threshold(labels: np.ndarray, scores: np.ndarray) -> float:
    candidates = np.unique(scores)
    candidates = np.concatenate(([float(np.min(scores)) - 1e-12], candidates, [float(np.max(scores)) + 1e-12]))
    evaluated = [(_binary_metrics(labels, scores, float(value)), float(value)) for value in candidates]
    # Optimize F1 on validation only; deterministic ties favor fewer false alarms.
    best, threshold = max(evaluated, key=lambda pair: (pair[0].f1, pair[0].precision, pair[1]))
    return threshold


def _feature_matrix(samples: list[TelemetrySample]) -> np.ndarray:
    matrix = np.asarray([sample.features for sample in samples], dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("feature matrix must contain finite numeric values")
    return matrix


def _baseline_fit(train_normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = np.median(train_normal, axis=0)
    mad = np.median(np.abs(train_normal - center), axis=0) * 1.4826
    # Constant dimensions use their IQR scale, then 1.0 if fully constant.
    q25, q75 = np.percentile(train_normal, [25, 75], axis=0)
    iqr_scale = (q75 - q25) / 1.349
    scale = np.where(mad > 1e-12, mad, np.where(iqr_scale > 1e-12, iqr_scale, 1.0))
    return center, scale


def _baseline_score(matrix: np.ndarray, center: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return np.max(np.abs((matrix - center) / scale), axis=1)


def train_evaluate_and_save(
    csv_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
) -> EvaluationReport:
    """Fit a normal-only IsolationForest, tune on validation, report test once, then save artifacts."""
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import RobustScaler
        import joblib
    except ImportError as exc:
        raise RuntimeError("Install the optional ML dependencies with requirements-ml.txt") from exc

    manifest = DatasetManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8-sig"))
    samples = load_samples(csv_path, manifest)
    train, validation, test = (samples[name] for name in ("train", "validation", "test"))
    train_all = _feature_matrix(train)
    train_labels = np.asarray([row.label for row in train], dtype=np.int64)
    train_normal = train_all[train_labels == 0]
    scaler = RobustScaler()
    scaled_normal = scaler.fit_transform(train_normal)
    detector = IsolationForest(
        n_estimators=manifest.n_estimators,
        contamination=manifest.contamination,
        random_state=manifest.random_seed,
        n_jobs=1,
    ).fit(scaled_normal)

    val_matrix = _feature_matrix(validation)
    val_labels = np.asarray([row.label for row in validation], dtype=np.int64)
    test_matrix = _feature_matrix(test)
    test_labels = np.asarray([row.label for row in test], dtype=np.int64)
    val_model_scores = -detector.score_samples(scaler.transform(val_matrix))
    test_model_scores = -detector.score_samples(scaler.transform(test_matrix))

    center, scale = _baseline_fit(train_normal)
    val_baseline_scores = _baseline_score(val_matrix, center, scale)
    test_baseline_scores = _baseline_score(test_matrix, center, scale)
    model_threshold = _choose_threshold(val_labels, val_model_scores)
    baseline_threshold = _choose_threshold(val_labels, val_baseline_scores)

    report = EvaluationReport(
        task="binary labeled sensor anomaly classification",
        dataset_name=manifest.dataset_name,
        feature_names=tuple(feature.name for feature in manifest.features),
        split_counts={name: len(values) for name, values in samples.items()},
        baseline_threshold=baseline_threshold,
        model_threshold=model_threshold,
        baseline_validation=_binary_metrics(val_labels, val_baseline_scores, baseline_threshold),
        model_validation=_binary_metrics(val_labels, val_model_scores, model_threshold),
        baseline_test=_binary_metrics(test_labels, test_baseline_scores, baseline_threshold),
        model_test=_binary_metrics(test_labels, test_model_scores, model_threshold),
    )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": detector,
        "scaler": scaler,
        "feature_names": [feature.name for feature in manifest.features],
        "threshold": model_threshold,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
    }
    joblib.dump(artifact, destination / "model.joblib")
    preprocessing = {
        "schema_version": "1.0.0",
        "task": "sensor_anomaly_detection",
        "dataset_name": manifest.dataset_name,
        "dataset_source": manifest.source,
        "dataset_license": manifest.license,
        "attribution": manifest.attribution,
        "features": [feature.model_dump() for feature in manifest.features],
        "partition_device_ids": manifest.partitions.model_dump(),
        "random_seed": manifest.random_seed,
        "n_estimators": manifest.n_estimators,
        "contamination": manifest.contamination,
        "threshold_selection": "validation F1; ties favor precision, then higher threshold",
        "model_threshold": model_threshold,
        "baseline_threshold": baseline_threshold,
        "baseline_center": center.tolist(),
        "baseline_scale": scale.tolist(),
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "interpretation": "An anomaly score is a statistical pattern flag, not a safety or health conclusion.",
    }
    (destination / "preprocessing.json").write_text(json.dumps(preprocessing, indent=2) + "\n", encoding="utf-8")
    (destination / "metrics.json").write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    return report


class AnalyticsPredictor:
    """Loads only locally produced artifacts and emits a separate analytics event."""

    def __init__(self, model_path: str | Path, preprocessing_path: str | Path) -> None:
        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError("Install the optional ML dependencies with requirements-ml.txt") from exc
        model_file, config_file = Path(model_path), Path(preprocessing_path)
        if not model_file.is_file() or not config_file.is_file():
            raise FileNotFoundError("trained model and preprocessing.json must both exist")
        try:
            self.artifact: dict[str, Any] = joblib.load(model_file)
            self.config = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("could not load analytics model artifacts") from exc
        required_artifact = {"model", "scaler", "feature_names", "threshold", "model_name", "model_version"}
        if not required_artifact.issubset(self.artifact):
            raise ValueError("model artifact is missing required components")
        configured_features = [feature["name"] for feature in self.config.get("features", [])]
        if configured_features != self.artifact["feature_names"]:
            raise ValueError("model and preprocessing feature names do not match")

    def predict_event(
        self,
        *,
        device_id: str,
        workplace_id: str,
        source_event_id: str,
        observed_at: datetime,
        features: dict[str, float],
    ) -> AnalyticsEvent:
        expected = set(self.artifact["feature_names"])
        if set(features) != expected:
            missing, extra = sorted(expected - set(features)), sorted(set(features) - expected)
            raise ValueError(f"feature set mismatch; missing={missing}, extra={extra}")
        values = []
        for name in self.artifact["feature_names"]:
            try:
                value = float(features[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"feature '{name}' must be a finite number") from exc
            if not math.isfinite(value):
                raise ValueError(f"feature '{name}' must be a finite number")
            values.append(value)
        if observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
            raise ValueError("observed_at must include a UTC timezone")
        matrix = np.asarray([values], dtype=np.float64)
        score = float(-self.artifact["model"].score_samples(self.artifact["scaler"].transform(matrix))[0])
        threshold = float(self.artifact["threshold"])
        outcome = "anomaly" if score >= threshold else "not_flagged"
        generated_at = datetime.now(timezone.utc)
        explanation = (
            "Statistical anomaly score crossed the validation-selected model threshold; human review is required."
            if outcome == "anomaly"
            else "The model did not flag a statistical anomaly; this does not establish safety."
        )
        return AnalyticsEvent(
            analytics_event_id=f"an-{uuid4().hex}",
            device_id=device_id,
            workplace_id=workplace_id,
            source_event_id=source_event_id,
            observed_at=observed_at,
            generated_at=generated_at,
            model_name=self.artifact["model_name"],
            model_version=self.artifact["model_version"],
            outcome=outcome,
            anomaly_score=score,
            decision_threshold=threshold,
            explanation=explanation,
        )
