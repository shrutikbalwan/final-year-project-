"""Export JSON Schemas from the Pydantic models in this package."""

import json
from pathlib import Path

from .models import DeviceHealth, DeviceTelemetry, Incident, SafetyEvent, SensorReading


SCHEMA_DIR = Path(__file__).parent / "schemas"
DOC_SCHEMA_DIR = Path(__file__).parents[2] / "docs" / "contracts" / "v1" / "schemas"
MODELS = {
    "sensor_reading": SensorReading,
    "device_health": DeviceHealth,
    "device_telemetry": DeviceTelemetry,
    "safety_event": SafetyEvent,
    "incident": Incident,
}


def _add_cross_field_schema_rules(name: str, schema: dict) -> None:
    """Express portable cross-field rules in JSON Schema where possible."""
    if name == "sensor_reading":
        schema["allOf"] = [
            {
                "if": {"properties": {"reading_status": {"const": "missing"}}},
                "then": {"properties": {"value": {"type": "null"}}},
            },
            {
                "if": {
                    "properties": {
                        "reading_status": {"enum": ["valid", "stale", "invalid"]}
                    }
                },
                "then": {"properties": {"value": {"type": "number"}}},
            },
        ]
    elif name == "device_health":
        schema["allOf"] = [
            {
                "properties": {
                    "battery_reading": {
                        "properties": {
                            "measurement_type": {"const": "battery_charge"},
                            "unit_code": {"const": "%"},
                            "value": {
                                "anyOf": [
                                    {"type": "null"},
                                    {"type": "number", "minimum": 0, "maximum": 100},
                                ]
                            },
                        }
                    }
                }
            },
            {
                "if": {
                    "properties": {
                        "last_seen_status": {"const": "missing"}
                    }
                },
                "then": {"properties": {"last_seen_at": {"type": "null"}}},
            },
            {
                "if": {
                    "properties": {
                        "last_seen_status": {"enum": ["valid", "stale"]}
                    }
                },
                "then": {"properties": {"last_seen_at": {"type": "string"}}},
            },
        ]


def build_schemas() -> dict[str, dict]:
    """Return exported schemas, including portable model-level constraints."""
    schemas = {}
    for name, model in MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://smartsafetyhelmet.example/contracts/v1/{name}.schema.json"
        _add_cross_field_schema_rules(name, schema)
        schemas[name] = schema
    for schema in schemas.values():
        definitions = schema.get("$defs", {})
        if "SensorReading" in definitions:
            _add_cross_field_schema_rules("sensor_reading", definitions["SensorReading"])
        if "DeviceHealth" in definitions:
            _add_cross_field_schema_rules("device_health", definitions["DeviceHealth"])
    return schemas


def export_schemas() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, schema in build_schemas().items():
        serialized = json.dumps(schema, indent=2) + "\n"
        (SCHEMA_DIR / f"{name}.schema.json").write_text(serialized, encoding="utf-8")
        (DOC_SCHEMA_DIR / f"{name}.schema.json").write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    export_schemas()
