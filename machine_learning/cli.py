import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .pipeline import train_evaluate_and_save


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train and evaluate a device-held-out statistical sensor anomaly detector"
    )
    parser.add_argument("--csv", required=True, type=Path, help="labeled telemetry CSV")
    parser.add_argument("--manifest", required=True, type=Path, help="provenance and device split JSON")
    parser.add_argument("--output", required=True, type=Path, help="local output directory for model and metrics")
    args = parser.parse_args()
    result = train_evaluate_and_save(args.csv, args.manifest, args.output)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
