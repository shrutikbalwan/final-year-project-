"""Convert the public SKAB run files to the project's reproducible CSV manifest format."""

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import DatasetManifest


FEATURE_MAP = {
    "Accelerometer1RMS": ("accelerometer1_rms", "g"),
    "Accelerometer2RMS": ("accelerometer2_rms", "g"),
    "Current": ("current", "A"),
    "Pressure": ("pressure", "bar"),
    "Temperature": ("temperature", "Cel"),
    "Thermocouple": ("thermocouple_temperature", "Cel"),
    "Voltage": ("voltage", "V"),
    "Volume Flow RateRMS": ("volume_flow_rate_rms", "L/min"),
}

SPLIT_RUNS = {
    "train": [*(f"valve1-{n}" for n in range(10)), *(f"valve2-{n}" for n in range(4)), *(f"other-{n}" for n in range(1, 7))],
    "validation": [*(f"valve1-{n}" for n in range(10, 13)), *(f"other-{n}" for n in range(7, 11))],
    "test": [*(f"valve1-{n}" for n in range(13, 16)), *(f"other-{n}" for n in range(11, 15))],
}


def prepare(source_root: Path, output_dir: Path) -> tuple[Path, Path]:
    run_files = {
        f"{path.parent.name}-{path.stem}": path
        for path in source_root.glob("*/*.csv")
        if path.parent.name in {"valve1", "valve2", "other"}
    }
    selected = [run for runs in SPLIT_RUNS.values() for run in runs]
    missing = sorted(set(selected) - set(run_files))
    if missing:
        raise ValueError(f"SKAB checkout is missing expected run files: {missing}")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "skab-runs.csv"
    fields = ["source_event_id", "device_id", "workplace_id", "observed_at", "anomaly_label", *[v[0] for v in FEATURE_MAP.values()]]
    base_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for run in selected:
            path = run_files[run]
            group_id = f"skab-{run}"
            with path.open("r", newline="", encoding="utf-8-sig") as raw:
                reader = csv.DictReader(raw, delimiter=";")
                missing_columns = {"anomaly", *FEATURE_MAP} - set(reader.fieldnames or [])
                if missing_columns:
                    raise ValueError(f"{path} is missing expected columns: {sorted(missing_columns)}")
                count = 0
                for index, row in enumerate(reader):
                    output = {
                        "source_event_id": f"{group_id}-row-{index:05d}",
                        # For this public benchmark, the independent experiment run is
                        # the split group. It is not an actual helmet/device identifier.
                        "device_id": group_id,
                        "workplace_id": "skab-water-circulation-testbed",
                        # SKAB timestamps have no timezone. Use an ordinal UTC timestamp
                        # only to satisfy the shared parser; it is not a model feature.
                        "observed_at": (base_time + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
                        "anomaly_label": int(float(row["anomaly"])),
                    }
                    for source_name, (feature_name, _unit) in FEATURE_MAP.items():
                        output[feature_name] = row[source_name]
                    writer.writerow(output)
                    count += 1
                if count == 0:
                    raise ValueError(f"{path} contains no samples")

    manifest = DatasetManifest(
        dataset_name="Skoltech Anomaly Benchmark (SKAB) v0.9 selected runs",
        source="https://github.com/waico/SKAB",
        license="GPL-3.0-only (repository license)",
        attribution="Katser and Kozitsin, Skoltech Anomaly Benchmark, 2020; cite repository DOI 10.34740/KAGGLE/DSV/1693952",
        intended_use="academic_evaluation",
        label_definition="SKAB per-row anomaly label: 0 normal, 1 anomalous as supplied by dataset; this denotes benchmark process anomaly only.",
        features=[{"name": name, "unit_code": unit} for name, unit in FEATURE_MAP.values()],
        partitions={
            name: [f"skab-{run}" for run in runs]
            for name, runs in SPLIT_RUNS.items()
        },
        random_seed=42,
        n_estimators=200,
        contamination=0.05,
    )
    manifest_path = output_dir / "skab-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return csv_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="SKAB checkout's data/ directory")
    parser.add_argument("--output", type=Path, required=True, help="ignored local output directory")
    args = parser.parse_args()
    csv_path, manifest_path = prepare(args.source, args.output)
    print(json.dumps({"csv": str(csv_path), "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
