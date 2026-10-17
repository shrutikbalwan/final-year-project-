"""Synthetic, in-process integration coverage across validation, storage and rules.

These tests exercise local API authentication and backend boundaries with
synthetic identities. They do not represent a real identity provider, physical
helmet, deployed AWS, or real camera/model measurements.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.safety.config import (
    RuleOperator,
    SafetyRule,
    ScoreBands,
    WorkplaceProfileRegistry,
    WorkplaceSafetyProfile,
)
from backend.app.storage.sqlite import SQLiteStorage
from conftest import authenticate

ROOT = Path(__file__).parents[1]


def _profiles():
    return WorkplaceProfileRegistry([
        WorkplaceSafetyProfile(
            workplace_id="synthetic-workplace-hot",
            profile_name="Synthetic integration profile",
            max_telemetry_age_seconds=3600,
            max_reading_age_seconds=3600,
            required_measurements=["temperature"],
            score_bands=ScoreBands(advisory=20, warning=50, critical=80),
            rules=[SafetyRule(
                rule_id="synthetic-temp-critical",
                measurement_type="temperature",
                unit_code="Cel",
                operator=RuleOperator.GTE,
                threshold=35,
                weight=90,
                risk_level="Critical",
                reason="Synthetic integration temperature rule matched.",
            )],
        )
    ])


@pytest.fixture
def integration_api(tmp_path):
    client = TestClient(create_app(
        SQLiteStorage(tmp_path / "integration.sqlite3"), _profiles()
    ))
    client.headers.update(authenticate(client))
    yield client
    client.close()


def _telemetry(device_id, workplace_id, event_id, *, temperature=25.0, status="valid"):
    payload = json.loads((ROOT / "contracts/v1/examples/telemetry.valid.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload.update(event_id=event_id, device_id=device_id, workplace_id=workplace_id, observed_at=now)
    payload["health"].update(device_id=device_id, workplace_id=workplace_id, observed_at=now,
                             last_seen_at=now)
    payload["readings"] = [payload["readings"][0]]
    reading = payload["readings"][0]
    reading.update(value=temperature, reading_status=status, observed_at=now)
    payload["health"]["battery_reading"]["observed_at"] = now
    return payload


def test_telemetry_to_persisted_risk_incident_ack_and_duplicate(integration_api):
    client = integration_api
    hot = _telemetry("synthetic-helmet-hot-01", "synthetic-workplace-hot",
                     "synthetic-telemetry-hot-01", temperature=40)

    assert client.post("/api/v1/telemetry", json=hot).status_code == 201
    risk = client.get(f"/api/v1/helmets/{hot['device_id']}/risk")
    assert risk.status_code == 200
    assert risk.json()["risk_level"] == "Critical"
    assert "Synthetic integration temperature rule matched." in " ".join(risk.json()["reasons"])

    page = client.get("/api/v1/incidents?limit=10").json()
    assert page["total"] == 1
    incident = page["items"][0]
    assert incident["device_id"] == hot["device_id"]
    assert incident["severity"] == "Critical"
    assert incident["source"]["telemetry_event_id"] == hot["event_id"]

    duplicate = client.post("/api/v1/telemetry", json=hot)
    assert duplicate.status_code == 409
    # A telemetry delivery retry with a fresh transport event still merges into
    # the open incident when the same configured rule set fires again.
    repeat = {**hot, "event_id": "synthetic-telemetry-hot-02"}
    assert client.post("/api/v1/telemetry", json=repeat).status_code == 201
    repeated_incident = client.get(f"/api/v1/incidents/{incident['incident_id']}").json()
    assert repeated_incident["occurrence_count"] == 2

    ack = client.post(f"/api/v1/incidents/{incident['incident_id']}/acknowledge",
                      json={"acknowledged_by": "synthetic-supervisor"})
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] == "supervisor-test"
    history = client.get(f"/api/v1/incidents/{incident['incident_id']}/history").json()
    assert any(item["action"] == "acknowledged" for item in history)


def test_multiple_workplaces_missing_stale_invalid_and_invalid_payloads(integration_api):
    client = integration_api
    cases = [
        _telemetry("synthetic-helmet-hot-02", "synthetic-workplace-hot",
                   "synthetic-missing-01", temperature=None, status="missing"),
        _telemetry("synthetic-helmet-hot-03", "synthetic-workplace-hot",
                   "synthetic-stale-01", temperature=40, status="stale"),
        _telemetry("synthetic-helmet-no-profile", "synthetic-workplace-unknown",
                   "synthetic-unknown-workplace-01", temperature=25),
    ]
    for payload in cases:
        assert client.post("/api/v1/telemetry", json=payload).status_code == 201
        risk = client.get(f"/api/v1/helmets/{payload['device_id']}/risk").json()
        assert risk["risk_level"] == "Unknown"
        assert risk["quality_issue_codes"]

    bad = _telemetry("synthetic-helmet-hot-04", "synthetic-workplace-hot",
                     "synthetic-invalid-01", temperature=0)
    bad["readings"][0]["value"] = "not-a-number"
    assert client.post("/api/v1/telemetry", json=bad).status_code == 422
    assert client.get("/api/v1/helmets?limit=100").json()["total"] == 3

    # A configured workplace profile that does not match an explicit device
    # identity still cannot turn missing inputs into a Normal conclusion.
    assert client.get("/api/v1/helmets/synthetic-does-not-exist").status_code == 404


def test_camera_event_validation_and_persistence(integration_api):
    client = integration_api
    event = json.loads((ROOT / "contracts/v1/examples/safety_event.valid.json").read_text(encoding="utf-8"))
    event.update(event_id="synthetic-camera-event-01",
                 device_id="synthetic-camera-01",
                 workplace_id="synthetic-workplace-hot",
                 incident_id=None)
    assert client.post("/api/v1/events", json=event).status_code == 201
    assert client.post("/api/v1/events", json=event).status_code == 409
    assert client.get("/api/v1/events?device_id=synthetic-camera-01").json()["total"] == 1

    malformed = {**event, "event_id": "synthetic-camera-event-invalid", "occurred_at": "yesterday"}
    assert client.post("/api/v1/events", json=malformed).status_code == 422
    # Camera events are persisted independently today; they are not yet mapped
    # through the rule engine into incidents (reported as a workflow limitation).
    assert client.get("/api/v1/incidents?limit=100").json()["total"] == 0

