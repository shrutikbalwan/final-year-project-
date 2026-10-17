import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.storage.errors import StorageError
from backend.app.storage.sqlite import SQLiteStorage
from conftest import authenticate
from contracts.v1 import Incident
from machine_learning.models import AnalyticsEvent

ROOT = Path(__file__).parents[1]


@pytest.fixture
def telemetry_payload():
    payload = json.loads(
        (ROOT / "contracts" / "v1" / "examples" / "telemetry.valid.json").read_text(
            encoding="utf-8"
        )
    )
    # Keep integration test identities obviously synthetic; never use worker data.
    payload["event_id"] = "evt-synthetic-000001"
    payload["device_id"] = "synthetic-helmet-001"
    payload["workplace_id"] = "synthetic-workplace-001"
    payload["health"]["device_id"] = payload["device_id"]
    payload["health"]["workplace_id"] = payload["workplace_id"]
    return payload


@pytest.fixture
def api(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.sqlite3")
    app = create_app(storage)
    client = TestClient(app)
    client.headers.update(authenticate(client))
    return client, storage


def test_health_and_generated_openapi_are_available(api):
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "ready"}

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert set(paths) >= {
        "/api/v1/telemetry",
        "/api/v1/events",
        "/api/v1/helmets",
        "/api/v1/helmets/{helmet_id}",
        "/api/v1/incidents",
        "/api/v1/incidents/{incident_id}",
        "/api/v1/analytics/events",
        "/api/v1/helmets/{helmet_id}/risk",
        "/api/v1/workplaces/profiles",
    }
    telemetry_schema = openapi.json()["components"]["schemas"]["DeviceTelemetry"]
    assert telemetry_schema["properties"]["schema_version"]["const"] == "1.0.0"


def test_request_log_uses_route_template_and_omits_query_and_device_values(api, caplog):
    client, _ = api
    caplog.set_level(logging.INFO, logger="backend.request")
    private_device_id = "synthetic-private-device-id"
    response = client.get(
        f"/api/v1/helmets/{private_device_id}?marker=synthetic-private-query"
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"]
    record = next(record for record in caplog.records if record.name == "backend.request")
    assert record.getMessage() == "request_complete"
    assert record.http_route == "/api/v1/helmets/{helmet_id}"
    assert record.status_code == 404
    assert isinstance(record.duration_ms, float)
    assert private_device_id not in record.getMessage()
    assert "synthetic-private-query" not in record.getMessage()


def test_analytics_events_are_validated_stored_separately_and_paginated(api):
    client, _ = api
    observed = datetime.now(timezone.utc).isoformat()
    payload = AnalyticsEvent(
        analytics_event_id="synthetic-analytics-001",
        device_id="synthetic-helmet-001",
        workplace_id="synthetic-workplace-001",
        source_event_id="synthetic-source-001",
        observed_at=observed,
        generated_at=observed,
        model_name="synthetic-anomaly-model",
        model_version="0.1.0",
        outcome="not_flagged",
        anomaly_score=0.1,
        decision_threshold=0.5,
        explanation="Synthetic fixture; not a safety conclusion.",
    ).model_dump(mode="json")

    accepted = client.post("/api/v1/analytics/events", json=payload)
    assert accepted.status_code == 201
    assert accepted.json()["event_type"] == "sensor_anomaly_prediction"
    assert client.post("/api/v1/analytics/events", json=payload).status_code == 409

    listed = client.get("/api/v1/analytics/events?limit=1&offset=0")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["analytics_event_id"] == payload["analytics_event_id"]

    malformed = {**payload, "generated_at": "not-a-timestamp", "analytics_event_id": "synthetic-analytics-002"}
    assert client.post("/api/v1/analytics/events", json=malformed).status_code == 422


def test_accepts_valid_telemetry_and_makes_helmet_retrievable(api, telemetry_payload):
    client, _ = api
    accepted = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert accepted.status_code == 201
    assert accepted.json()["event_id"] == telemetry_payload["event_id"]

    listed = client.get("/api/v1/helmets")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    helmet = listed.json()["items"][0]
    assert helmet["helmet_id"] == telemetry_payload["device_id"]
    assert helmet["workplace_id"] == telemetry_payload["workplace_id"]
    assert helmet["battery_reading"]["unit_code"] == "%"
    assert helmet["battery_reading"]["value"] == 86.0

    detail = client.get(f"/api/v1/helmets/{telemetry_payload['device_id']}")
    assert detail.status_code == 200
    assert detail.json()["helmet_id"] == helmet["helmet_id"]
    assert detail.json()["latest_telemetry"]["event_id"] == telemetry_payload["event_id"]
    assert detail.json()["latest_telemetry"]["readings"][1]["value"] is None
    assert detail.json()["latest_telemetry"]["readings"][1]["reading_status"] == "missing"

    history = client.get(f"/api/v1/telemetry?device_id={telemetry_payload['device_id']}&limit=10")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["event_id"] == telemetry_payload["event_id"]
    assert client.get(f"/api/v1/telemetry?start=2026-10-16T00:00:00").status_code == 422

    risk = client.get(f"/api/v1/helmets/{telemetry_payload['device_id']}/risk")
    assert risk.status_code == 200
    assert risk.json()["risk_level"] == "Unknown"
    assert "profile_missing" in risk.json()["quality_issue_codes"]
    assert client.get("/api/v1/workplaces/profiles").json() == []


def test_camera_detection_event_history_is_filtered_and_paginated(api):
    client, _ = api
    event = json.loads((ROOT / "contracts" / "v1" / "examples" / "safety_event.valid.json").read_text())
    event["event_id"] = "evt-synthetic-camera-001"
    event["device_id"] = "synthetic-helmet-camera"
    event["workplace_id"] = "synthetic-workplace-camera"
    event["incident_id"] = None
    assert client.post("/api/v1/events", json=event).status_code == 201
    listed = client.get("/api/v1/events?device_id=synthetic-helmet-camera&limit=1")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["event_id"] == event["event_id"]


def test_telemetry_is_persisted_across_app_instances(tmp_path, telemetry_payload):
    database = tmp_path / "persistent.sqlite3"
    first = TestClient(create_app(SQLiteStorage(database)))
    first.headers.update(authenticate(first))
    assert first.post("/api/v1/telemetry", json=telemetry_payload).status_code == 201
    first.close()

    second = TestClient(create_app(SQLiteStorage(database)))
    second.headers.update(authenticate(second))
    result = second.get(f"/api/v1/helmets/{telemetry_payload['device_id']}")
    assert result.status_code == 200
    assert result.json()["helmet_id"] == telemetry_payload["device_id"]


def test_latest_telemetry_is_returned_for_a_helmet(api, telemetry_payload):
    client, _ = api
    assert client.post("/api/v1/telemetry", json=telemetry_payload).status_code == 201
    newer = json.loads(json.dumps(telemetry_payload))
    newer["event_id"] = "evt-2026-000044"
    newer["observed_at"] = "2026-10-16T12:32:00Z"
    newer["health"]["observed_at"] = "2026-10-16T12:31:59Z"
    newer["health"]["last_seen_at"] = "2026-10-16T12:31:59Z"
    assert client.post("/api/v1/telemetry", json=newer).status_code == 201
    detail = client.get(f"/api/v1/helmets/{telemetry_payload['device_id']}")
    assert detail.json()["latest_telemetry"]["event_id"] == newer["event_id"]


def test_helmet_list_paginates_distinct_devices(api, telemetry_payload):
    client, _ = api
    assert client.post("/api/v1/telemetry", json=telemetry_payload).status_code == 201
    another = json.loads(json.dumps(telemetry_payload))
    another["event_id"] = "evt-synthetic-000002"
    another["device_id"] = "synthetic-helmet-002"
    another["health"]["device_id"] = another["device_id"]
    assert client.post("/api/v1/telemetry", json=another).status_code == 201
    first_page = client.get("/api/v1/helmets?limit=1&offset=0").json()
    second_page = client.get("/api/v1/helmets?limit=1&offset=1").json()
    assert first_page["total"] == 2
    assert len(first_page["items"]) == len(second_page["items"]) == 1
    assert first_page["items"][0]["helmet_id"] != second_page["items"][0]["helmet_id"]


def test_invalid_telemetry_is_rejected_and_not_stored(api, telemetry_payload):
    client, _ = api
    telemetry_payload["readings"][1]["value"] = 0
    response = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert response.status_code == 422
    assert client.get("/api/v1/helmets").json()["total"] == 0


def test_safety_event_contract_is_accepted_and_duplicate_is_conflict(api):
    client, storage = api
    event_path = ROOT / "contracts" / "v1" / "examples" / "safety_event.valid.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event.update(
        event_id="evt-synthetic-vision-000001",
        device_id="synthetic-camera-001",
        workplace_id="synthetic-workplace-001",
        occurred_at="2026-10-16T12:31:00Z",
        reported_at="2026-10-16T12:31:02Z",
    )
    event["description"] = "Synthetic restricted-zone event for API test."

    accepted = client.post("/api/v1/events", json=event)
    assert accepted.status_code == 201
    assert accepted.json()["event_id"] == event["event_id"]
    assert storage.get_event(event["event_id"]).event_id == event["event_id"]

    duplicate = client.post("/api/v1/events", json=event)
    assert duplicate.status_code == 409


def test_invalid_safety_event_is_rejected(api):
    client, _ = api
    response = client.post("/api/v1/events", json={"event_type": "fall_detected"})
    assert response.status_code == 422


def test_duplicate_event_id_returns_conflict(api, telemetry_payload):
    client, _ = api
    assert client.post("/api/v1/telemetry", json=telemetry_payload).status_code == 201
    duplicate = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "event_id has already been accepted"}
    assert client.get("/api/v1/helmets").json()["total"] == 1


@pytest.mark.parametrize(
    "reading_change",
    [
        {"value": None, "reading_status": "valid"},
        {"value": 10.0, "reading_status": "missing"},
        {"reading_status": "valid"},
    ],
)
def test_null_or_inconsistent_readings_are_rejected_by_api(api, telemetry_payload, reading_change):
    client, _ = api
    reading = telemetry_payload["readings"][0]
    reading.update(reading_change)
    if "value" not in reading_change:
        reading.pop("value")
    response = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert response.status_code == 422
    assert client.get("/api/v1/helmets").json()["total"] == 0


@pytest.mark.parametrize("timestamp", ["not-a-timestamp", "2026-10-16T12:30:00+05:30"])
def test_malformed_or_non_utc_timestamp_is_rejected_by_api(api, telemetry_payload, timestamp):
    client, _ = api
    telemetry_payload["observed_at"] = timestamp
    response = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert response.status_code == 422
    assert client.get("/api/v1/helmets").json()["total"] == 0


def test_missing_helmet_and_incident_return_404(api):
    client, _ = api
    assert client.get("/api/v1/helmets/not-registered").status_code == 404
    assert client.get("/api/v1/incidents/not-open").status_code == 404


def test_incident_list_and_detail_use_shared_contract(api):
    client, storage = api
    payload = json.loads(
        (ROOT / "contracts" / "v1" / "examples" / "incident.valid.json").read_text(
            encoding="utf-8"
        )
    )
    incident = Incident.model_validate(payload)
    storage.save_incident(incident)

    page = client.get("/api/v1/incidents?limit=10&offset=0")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["incident_id"] == incident.incident_id
    detail = client.get(f"/api/v1/incidents/{incident.incident_id}")
    assert detail.status_code == 200
    assert detail.json()["event_ids"] == incident.event_ids


def test_unconfigured_workplace_creates_unknown_incident_and_api_acknowledges(api, telemetry_payload):
    client, _ = api
    assert client.post("/api/v1/telemetry", json=telemetry_payload).status_code == 201
    incidents = client.get("/api/v1/incidents").json()
    assert incidents["total"] == 1
    incident_id = incidents["items"][0]["incident_id"]
    incident = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert incident["severity"] == "Unknown"
    assert "No safety profile is configured" in incident["reason"]

    acknowledged = client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge",
        json={"acknowledged_by": "supervisor-2"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["acknowledged_by"] == "supervisor-test"
    history = client.get(f"/api/v1/incidents/{incident_id}/history")
    assert history.status_code == 200
    assert [entry["action"] for entry in history.json()] == ["created", "acknowledged"]
    repeated_ack = client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge",
        json={"acknowledged_by": "synthetic-supervisor"},
    )
    assert repeated_ack.status_code == 200
    assert len(repeated_ack.json()["history"]) == 2


def test_list_pagination_is_bounded(api, telemetry_payload):
    client, _ = api
    assert client.get("/api/v1/helmets?limit=0").status_code == 422
    assert client.get("/api/v1/helmets?limit=501").status_code == 422
    assert client.get("/api/v1/incidents?offset=-1").status_code == 422


def test_incident_list_paginates_saved_incidents(api):
    client, storage = api
    example_path = ROOT / "contracts" / "v1" / "examples" / "incident.valid.json"
    for index in range(3):
        payload = json.loads(example_path.read_text(encoding="utf-8"))
        payload["incident_id"] = f"synthetic-incident-{index:03d}"
        payload["device_id"] = f"synthetic-helmet-{index:03d}"
        payload["workplace_id"] = "synthetic-workplace-001"
        payload["source"]["telemetry_event_id"] = f"evt-synthetic-incident-{index:03d}"
        storage.save_incident(Incident.model_validate(payload))

    first = client.get("/api/v1/incidents?limit=2&offset=0").json()
    second = client.get("/api/v1/incidents?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert not set(item["incident_id"] for item in first["items"]) & set(
        item["incident_id"] for item in second["items"]
    )


class FailingStorage:
    def health_check(self):
        raise StorageError("database password or path must not leak")

    def save_telemetry(self, telemetry):
        raise StorageError("database password or path must not leak")


def test_storage_failures_return_generic_server_error(telemetry_payload):
    client = TestClient(create_app(FailingStorage()), raise_server_exceptions=False)
    client.headers.update(authenticate(client))
    health = client.get("/health")
    assert health.status_code == 503
    assert health.json() == {"detail": "local storage unavailable"}
    failure = client.post("/api/v1/telemetry", json=telemetry_payload)
    assert failure.status_code == 500
    assert failure.json() == {"detail": "storage operation failed"}


@pytest.mark.parametrize(
    ("method_name", "path"),
    [
        ("list_helmets", "/api/v1/helmets"),
        ("get_helmet", "/api/v1/helmets/synthetic-helmet-404"),
        ("list_incidents", "/api/v1/incidents"),
        ("get_incident", "/api/v1/incidents/synthetic-incident-404"),
    ],
)
def test_storage_read_failures_return_generic_server_error(api, monkeypatch, method_name, path):
    client, storage = api

    def fail(*args, **kwargs):
        raise StorageError("synthetic storage failure containing private details")

    monkeypatch.setattr(storage, method_name, fail)
    response = client.get(path)
    assert response.status_code == 500
    assert response.json() == {"detail": "storage operation failed"}
    assert "private details" not in response.text

