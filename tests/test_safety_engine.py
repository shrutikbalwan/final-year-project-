import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.safety.config import WorkplaceProfileRegistry, WorkplaceSafetyProfile
from backend.app.safety.engine import SafetyEngine
from backend.app.safety.workflow import IncidentWorkflow
from backend.app.storage.sqlite import SQLiteStorage
from contracts.v1 import DeviceTelemetry, IncidentAction, IncidentStatus, RiskLevel

ROOT = Path(__file__).parents[1]
BASE_TIME = datetime(2026, 10, 16, 12, 30, 5, tzinfo=timezone.utc)


def profile(escalation_steps=None):
    return WorkplaceSafetyProfile.model_validate(
        {
            "workplace_id": "synthetic-workplace-001",
            "profile_name": "test-development-profile",
            "max_telemetry_age_seconds": 120,
            "max_reading_age_seconds": 120,
            "required_measurements": ["temperature", "gas_concentration"],
            "score_bands": {"advisory": 10, "warning": 30, "critical": 60},
            "rules": [
                {
                    "rule_id": "temperature-high",
                    "measurement_type": "temperature",
                    "unit_code": "Cel",
                    "operator": "gt",
                    "threshold": 40,
                    "weight": 20,
                    "risk_level": "Warning",
                    "reason": "Development temperature rule exceeded.",
                },
                {
                    "rule_id": "gas-high",
                    "measurement_type": "gas_concentration",
                    "unit_code": "ppm",
                    "operator": "gt",
                    "threshold": 100,
                    "weight": 60,
                    "risk_level": "Critical",
                    "reason": "Development gas rule exceeded.",
                },
            ],
            "escalation_steps": escalation_steps or [],
        }
    )


def telemetry():
    payload = json.loads(
        (ROOT / "contracts" / "v1" / "examples" / "telemetry.valid.json").read_text(
            encoding="utf-8"
        )
    )
    payload["event_id"] = "evt-synthetic-safety-000001"
    payload["device_id"] = "synthetic-helmet-safety-001"
    payload["workplace_id"] = "synthetic-workplace-001"
    payload["health"]["device_id"] = payload["device_id"]
    payload["health"]["workplace_id"] = payload["workplace_id"]
    payload["readings"][1].update(value=20.0, reading_status="valid")
    return DeviceTelemetry.model_validate(payload)


def evaluate(payload=None, configured_profile=None, at=BASE_TIME):
    registry = WorkplaceProfileRegistry([configured_profile or profile()])
    return SafetyEngine(registry).evaluate(payload or telemetry(), at)


def test_normal_readings_produce_normal_with_explanation():
    result = evaluate()
    assert result.risk_level == RiskLevel.NORMAL
    assert result.score == 0
    assert "within the configured development rules" in result.reasons[0]


def test_advisory_rule_weight_and_reason_are_reported():
    config = profile().model_dump(mode="python")
    config["rules"].append(
        {
            "rule_id": "temperature-advisory",
            "measurement_type": "temperature",
            "unit_code": "Cel",
            "operator": "gt",
            "threshold": 30,
            "weight": 10,
            "risk_level": "Advisory",
            "reason": "Synthetic advisory rule exceeded.",
        }
    )
    configured = WorkplaceSafetyProfile.model_validate(config)
    payload = telemetry().model_dump(mode="json")
    payload["readings"][0]["value"] = 35

    result = evaluate(DeviceTelemetry.model_validate(payload), configured)

    assert result.risk_level == RiskLevel.ADVISORY
    assert result.score == 10
    assert result.matched_rule_ids == ["temperature-advisory"]
    assert any("Synthetic advisory rule" in reason and "weight 10" in reason for reason in result.reasons)


def test_threshold_violation_uses_rule_weight_and_reason():
    payload = telemetry().model_dump(mode="json")
    payload["readings"][0]["value"] = 45
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.WARNING
    assert result.score == 20
    assert result.matched_rule_ids == ["temperature-high"]
    assert any("weight 20" in reason and "Development temperature rule" in reason for reason in result.reasons)


def test_multiple_weighted_violations_raise_score_band():
    payload = telemetry().model_dump(mode="json")
    payload["readings"][0]["value"] = 45
    payload["readings"][1]["value"] = 150
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.score == 80
    assert result.risk_level == RiskLevel.CRITICAL
    assert set(result.matched_rule_ids) == {"temperature-high", "gas-high"}


def test_missing_readings_produce_unknown_not_normal():
    payload = telemetry().model_dump(mode="json")
    payload["readings"][1].update(value=None, reading_status="missing")
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert any("is missing" in reason for reason in result.reasons)
    assert any(code.startswith("reading_missing") for code in result.quality_issue_codes)


def test_absent_required_measurement_produces_unknown():
    payload = telemetry().model_dump(mode="json")
    payload["readings"].pop()
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "measurement_missing:gas_concentration" in result.quality_issue_codes


def test_marked_or_age_based_stale_readings_produce_unknown():
    payload = telemetry().model_dump(mode="json")
    payload["readings"][1].update(value=20, reading_status="stale")
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert any("marked stale" in reason for reason in result.reasons)

    payload = telemetry().model_dump(mode="json")
    payload["readings"][1]["observed_at"] = "2026-10-16T12:20:00Z"
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert any("stale by age" in reason for reason in result.reasons)


def test_stale_telemetry_is_detected():
    payload = telemetry().model_dump(mode="json")
    payload["observed_at"] = "2026-10-16T12:20:00Z"
    payload["health"]["observed_at"] = "2026-10-16T12:19:59Z"
    payload["health"]["last_seen_at"] = "2026-10-16T12:19:59Z"
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "telemetry_stale" in result.quality_issue_codes


def test_invalid_sensor_reading_is_a_fault_and_never_normal():
    payload = telemetry().model_dump(mode="json")
    payload["readings"][1].update(value=20, reading_status="invalid")
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "sensor_fault:gas_concentration" in result.quality_issue_codes
    assert any("Sensor fault" in reason for reason in result.reasons)


def test_missing_profile_and_unit_mismatch_are_unknown():
    unprofiled = SafetyEngine(WorkplaceProfileRegistry()).evaluate(telemetry(), BASE_TIME)
    assert unprofiled.risk_level == RiskLevel.UNKNOWN
    assert "profile_missing" in unprofiled.quality_issue_codes

    payload = telemetry().model_dump(mode="json")
    payload["readings"][1]["unit_code"] = "mg/m3"
    result = evaluate(DeviceTelemetry.model_validate(payload))
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "unit_mismatch:gas_concentration" in result.quality_issue_codes


def test_repeated_trigger_merges_into_one_incident_with_history(tmp_path):
    telemetry_one = telemetry()
    data_one = telemetry_one.model_dump(mode="json")
    data_one["readings"][0]["value"] = 45
    telemetry_one = DeviceTelemetry.model_validate(data_one)
    result_one = evaluate(telemetry_one)
    storage = SQLiteStorage(tmp_path / "workflow.sqlite3")
    workflow = IncidentWorkflow(storage, WorkplaceProfileRegistry([profile()]))

    first, created = workflow.record_evaluation(result_one)
    assert created is True
    assert first is not None and first.status == IncidentStatus.OPEN

    telemetry_two_data = telemetry_one.model_dump(mode="json")
    telemetry_two_data["event_id"] = "evt-2026-000099"
    telemetry_two = DeviceTelemetry.model_validate(telemetry_two_data)
    second_eval = evaluate(telemetry_two, at=BASE_TIME + timedelta(seconds=5))
    second, created = workflow.record_evaluation(second_eval)
    assert created is False
    assert second is not None and second.incident_id == first.incident_id
    assert second.occurrence_count == 2
    assert second.source.telemetry_event_id == telemetry_two.event_id
    assert [entry.action for entry in second.history][-1] == IncidentAction.REPEATED
    assert storage.list_incidents(20, 0)[1] == 1


def test_acknowledgement_is_persisted_and_idempotent(tmp_path):
    payload = telemetry().model_dump(mode="json")
    payload["readings"][0]["value"] = 45
    result = evaluate(DeviceTelemetry.model_validate(payload))
    storage = SQLiteStorage(tmp_path / "ack.sqlite3")
    workflow = IncidentWorkflow(storage, WorkplaceProfileRegistry([profile()]))
    incident, _ = workflow.record_evaluation(result)

    ack_time = BASE_TIME + timedelta(seconds=10)
    acknowledged = workflow.acknowledge(incident.incident_id, "supervisor-7", ack_time)
    assert acknowledged.status == IncidentStatus.ACKNOWLEDGED
    assert acknowledged.acknowledged_by == "supervisor-7"
    assert acknowledged.acknowledged_at == ack_time
    assert acknowledged.history[-1].action == IncidentAction.ACKNOWLEDGED
    repeated = workflow.acknowledge(incident.incident_id, "supervisor-7", ack_time)
    assert len(repeated.history) == len(acknowledged.history)


def test_escalation_steps_append_configured_history(tmp_path):
    configured = profile(
        [
            {
                "minimum_risk_level": "Warning",
                "after_seconds": 60,
                "target": "site-safety-lead",
            }
        ]
    )
    payload = telemetry().model_dump(mode="json")
    payload["readings"][0]["value"] = 45
    result = evaluate(DeviceTelemetry.model_validate(payload), configured)
    storage = SQLiteStorage(tmp_path / "escalation.sqlite3")
    workflow = IncidentWorkflow(storage, WorkplaceProfileRegistry([configured]))
    incident, _ = workflow.record_evaluation(result)

    early = workflow.process_escalations(
        "synthetic-workplace-001", BASE_TIME + timedelta(seconds=59)
    )
    assert early == []
    due = workflow.process_escalations(
        "synthetic-workplace-001", BASE_TIME + timedelta(seconds=60)
    )
    assert len(due) == 1
    assert due[0].history[-1].action == IncidentAction.ESCALATED
    assert due[0].history[-1].target == "site-safety-lead"


def test_unknown_data_can_have_its_own_escalation_rule(tmp_path):
    configured = profile(
        [
            {
                "minimum_risk_level": "Unknown",
                "after_seconds": 0,
                "target": "data-quality-reviewer",
            }
        ]
    )
    payload = telemetry().model_dump(mode="json")
    payload["readings"][1].update(value=None, reading_status="missing")
    result = evaluate(DeviceTelemetry.model_validate(payload), configured)
    storage = SQLiteStorage(tmp_path / "unknown-escalation.sqlite3")
    workflow = IncidentWorkflow(storage, WorkplaceProfileRegistry([configured]))
    incident, _ = workflow.record_evaluation(result)

    due = workflow.process_escalations(
        "synthetic-workplace-001", BASE_TIME
    )
    assert len(due) == 1
    assert due[0].incident_id == incident.incident_id
    assert due[0].history[-1].target == "data-quality-reviewer"
