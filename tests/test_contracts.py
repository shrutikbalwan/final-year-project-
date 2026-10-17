import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError as JSONSchemaValidationError
from pydantic import ValidationError

from contracts.v1 import DeviceHealth, DeviceTelemetry, Incident, SafetyEvent, SensorReading
from contracts.v1.export_schemas import MODELS, build_schemas


ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "contracts" / "v1" / "examples"
SCHEMA_DIR = ROOT / "contracts" / "v1" / "schemas"
DOC_SCHEMA_DIR = ROOT / "docs" / "contracts" / "v1" / "schemas"
MODEL_TYPES = {
    "sensor_reading": SensorReading,
    "device_health": DeviceHealth,
    "device_telemetry": DeviceTelemetry,
    "safety_event": SafetyEvent,
    "incident": Incident,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("name", "filename"),
    [
        ("device_telemetry", "telemetry.valid.json"),
        ("device_health", "device_health.valid.json"),
        ("safety_event", "safety_event.valid.json"),
        ("incident", "incident.valid.json"),
    ],
)
def test_valid_examples_pass_pydantic_and_json_schema(name, filename):
    instance = load_json(EXAMPLES / filename)
    MODEL_TYPES[name].model_validate(instance)
    schema = load_json(SCHEMA_DIR / f"{name}.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


@pytest.mark.parametrize(
    ("filename", "schema_name"),
    [
        ("invalid_reading_null_with_valid_status.json", "sensor_reading"),
        ("invalid_reading_local_timestamp.json", "sensor_reading"),
    ],
)
def test_invalid_examples_fail_both_validators(filename, schema_name):
    instance = load_json(EXAMPLES / filename)
    with pytest.raises(ValidationError):
        SensorReading.model_validate(instance)
    schema = load_json(SCHEMA_DIR / f"{schema_name}.schema.json")
    with pytest.raises(JSONSchemaValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def test_exported_schemas_match_pydantic_models_and_are_valid():
    exported = build_schemas()
    assert set(exported) == set(MODELS)
    for name, schema in exported.items():
        Draft202012Validator.check_schema(schema)
        assert schema == load_json(SCHEMA_DIR / f"{name}.schema.json")
        assert schema == load_json(DOC_SCHEMA_DIR / f"{name}.schema.json")


def test_null_reading_is_explicitly_missing_and_zero_is_valid():
    example = load_json(EXAMPLES / "invalid_reading_null_with_valid_status.json")
    example.update(value=0, reading_status="valid")
    reading = SensorReading.model_validate(example)
    assert reading.value == 0
    example.update(value=None, reading_status="missing")
    assert SensorReading.model_validate(example).value is None


@pytest.mark.parametrize("status", ["stale", "invalid"])
def test_stale_and_invalid_readings_are_distinct_and_require_a_value(status):
    example = load_json(EXAMPLES / "invalid_reading_null_with_valid_status.json")
    example.update(value=12.5, reading_status=status)
    reading = SensorReading.model_validate(example)
    assert reading.reading_status == status
    schema = load_json(SCHEMA_DIR / "sensor_reading.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)

    example["value"] = None
    with pytest.raises(ValidationError):
        SensorReading.model_validate(example)
    with pytest.raises(JSONSchemaValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)


def test_health_rejects_out_of_range_battery_and_missing_last_seen_mismatch():
    health = load_json(EXAMPLES / "device_health.valid.json")
    health["battery_reading"].update(value=101, reading_status="valid")
    with pytest.raises(ValidationError):
        DeviceHealth.model_validate(health)
    schema = load_json(SCHEMA_DIR / "device_health.schema.json")
    with pytest.raises(JSONSchemaValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(health)

    health = load_json(EXAMPLES / "device_health.valid.json")
    health["last_seen_at"] = "2026-10-16T12:29:00Z"
    with pytest.raises(ValidationError):
        DeviceHealth.model_validate(health)
    with pytest.raises(JSONSchemaValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(health)


def test_telemetry_rejects_mismatched_embedded_health_identity():
    telemetry = load_json(EXAMPLES / "telemetry.valid.json")
    telemetry["health"]["workplace_id"] = "another-workplace"
    with pytest.raises(ValidationError):
        DeviceTelemetry.model_validate(telemetry)


def test_event_and_incident_reject_non_utc_or_reversed_timestamps():
    event = load_json(EXAMPLES / "safety_event.valid.json")
    event["reported_at"] = "2026-10-16T12:30:00Z"
    with pytest.raises(ValidationError):
        SafetyEvent.model_validate(event)
    incident = load_json(EXAMPLES / "incident.valid.json")
    incident["updated_at"] = "2026-10-16T12:30:00Z"
    with pytest.raises(ValidationError):
        Incident.model_validate(incident)
