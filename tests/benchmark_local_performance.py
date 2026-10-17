"""Repeatable synthetic local API latency sample; not a production load test."""

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.main import create_app
from backend.app.safety.config import (
    RuleOperator,
    SafetyRule,
    ScoreBands,
    WorkplaceProfileRegistry,
    WorkplaceSafetyProfile,
)
from backend.app.storage.sqlite import SQLiteStorage

WORKPLACE_ID = "synthetic-benchmark-workplace"


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "mean_ms": round(statistics.mean(samples), 3),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
        "max_ms": round(max(samples), 3),
    }


def _profile() -> WorkplaceProfileRegistry:
    profile = WorkplaceSafetyProfile(
        workplace_id=WORKPLACE_ID,
        profile_name="Synthetic local performance profile",
        max_telemetry_age_seconds=3600,
        max_reading_age_seconds=3600,
        required_measurements=["temperature"],
        score_bands=ScoreBands(advisory=20, warning=50, critical=80),
        rules=[
            SafetyRule(
                rule_id="synthetic-benchmark-critical",
                measurement_type="temperature",
                unit_code="Cel",
                operator=RuleOperator.GTE,
                threshold=35,
                weight=90,
                risk_level="Critical",
                reason="Synthetic benchmark rule matched",
            )
        ],
    )
    return WorkplaceProfileRegistry([profile])


def _payload(template: dict, index: int) -> dict:
    payload = json.loads(json.dumps(template))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    device_id = f"synthetic-benchmark-helmet-{index % 10:02d}"
    payload.update(
        event_id=f"synthetic-benchmark-event-{index:05d}",
        device_id=device_id,
        workplace_id=WORKPLACE_ID,
        observed_at=now,
    )
    payload["health"].update(
        device_id=device_id,
        workplace_id=WORKPLACE_ID,
        observed_at=now,
        last_seen_at=now,
    )
    payload["health"]["battery_reading"]["observed_at"] = now
    payload["readings"] = [payload["readings"][0]]
    payload["readings"][0].update(
        value=40.0,
        reading_status="valid",
        observed_at=now,
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()
    if args.samples < 10:
        parser.error("--samples must be at least 10")

    template_path = ROOT / "contracts/v1/examples/telemetry.valid.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    post_times: list[float] = []
    risk_times: list[float] = []
    with tempfile.TemporaryDirectory(prefix="smart-helmet-api-bench-") as directory:
        storage = SQLiteStorage(Path(directory) / "benchmark.sqlite3")
        client = TestClient(create_app(storage, _profile()))
        try:
            for index in range(args.samples):
                payload = _payload(template, index)
                started = time.perf_counter()
                response = client.post("/api/v1/telemetry", json=payload)
                post_times.append((time.perf_counter() - started) * 1000)
                if response.status_code != 201:
                    raise RuntimeError(f"synthetic telemetry POST failed: HTTP {response.status_code}")

                started = time.perf_counter()
                risk = client.get(f"/api/v1/helmets/{payload['device_id']}/risk")
                risk_times.append((time.perf_counter() - started) * 1000)
                if risk.status_code != 200 or risk.json()["risk_level"] != "Critical":
                    raise RuntimeError("synthetic risk evaluation did not return Critical")
        finally:
            client.close()

    print(
        json.dumps(
            {
                "workload": (
                    f"{args.samples} serial synthetic valid telemetry POSTs across 10 device IDs; "
                    "one configured workplace; each POST followed by risk GET; "
                    "FastAPI TestClient and temporary SQLite; one process; no network hop/concurrency"
                ),
                "telemetry_post": _percentiles(post_times),
                "risk_get": _percentiles(risk_times),
                "accepted_posts": args.samples,
                "critical_risk_responses": len(risk_times),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
