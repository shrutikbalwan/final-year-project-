"""Benchmark one loaded analytics model over held-out dataset rows."""

import argparse
import json
import statistics
import time
from pathlib import Path

from .data import DatasetManifest, load_samples
from .pipeline import AnalyticsPredictor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--preprocessing", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()
    if args.samples < 1 or args.warmup < 0:
        parser.error("--samples must be positive and --warmup cannot be negative")

    manifest = DatasetManifest.model_validate_json(args.manifest.read_text(encoding="utf-8-sig"))
    held_out = load_samples(args.csv, manifest)["test"]
    if not held_out:
        parser.error("the manifest's test partition has no rows")
    predictor = AnalyticsPredictor(args.model, args.preprocessing)
    feature_names = [feature.name for feature in manifest.features]

    def predict(index: int) -> None:
        row = held_out[index % len(held_out)]
        predictor.predict_event(
            device_id="synthetic-benchmark-device",
            workplace_id="synthetic-benchmark-workplace",
            source_event_id=f"synthetic-benchmark-event-{index}",
            observed_at=row.observed_at,
            features=dict(zip(feature_names, row.features)),
        )

    for index in range(args.warmup):
        predict(index)

    samples_ms = []
    for index in range(args.samples):
        started = time.perf_counter()
        predict(args.warmup + index)
        samples_ms.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples_ms)
    print(
        json.dumps(
            {
                "workload": (
                    f"{args.warmup} warm-up and {args.samples} AnalyticsPredictor.predict_event calls "
                    f"cycling through {min(len(held_out), args.samples)} held-out SKAB rows; "
                    "includes input validation, scaling, model scoring, and analytics event construction"
                ),
                "mean_ms": round(statistics.mean(samples_ms), 4),
                "p50_ms": round(statistics.median(samples_ms), 4),
                "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 4),
                "max_ms": round(max(samples_ms), 4),
                "inference_calls": len(samples_ms),
                "held_out_rows": len(held_out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
