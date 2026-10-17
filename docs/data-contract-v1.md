# Smart Safety Helmet data contract, version 1

The hardware-independent contract lives in `contracts/v1/`. Pydantic models in
`models.py` are the source of truth. The JSON Schemas in `contracts/v1/schemas/`
are exported from those models with:

```powershell
python -m contracts.v1.export_schemas
```

The same schema files are copied into `docs/contracts/v1/schemas/` for use as
the Phase 2 hardware integration reference. The tests check that this copy
matches the generated contract schemas.

Schema files use JSON Schema Draft 2020-12. Keep the `1.0.0` model discriminator,
schema directory, examples, and tests in step when making a compatible change.
Breaking field or meaning changes require a new contract version.

## Message types

- **SensorReading** — `reading_id`, stable `sensor_id`, `measurement_type`,
  `unit_code`, nullable numeric `value`, `reading_status`, and UTC `observed_at`.
- **DeviceHealth** — stable device and workplace IDs, schema version, health
  snapshot time, `battery_reading` as a percentage SensorReading,
  `connectivity_status`, and the last confirmed contact with a
  `last_seen_status`.
- **DeviceTelemetry** — unique message `event_id`, device/workplace IDs,
  timestamp, one or more SensorReading records, and a matching health snapshot.
- **SafetyEvent** — unique `event_id`, optional `incident_id`, source IDs,
  event type, descriptive severity, occurrence/report timestamps, optional
  description, and related reading IDs.
- **Incident** — stable incident/device/workplace IDs, lifecycle status and
  severity, weighted score, reason, source references, event IDs, acknowledgement
  fields, occurrence count, timestamps, and ordered history entries.

IDs are opaque stable strings (1–128 ASCII letters, numbers, `.`, `_`, `:`, or
`-`); producers may use their own registry format. Timestamps must include UTC
(`Z` or `+00:00`). `unit_code` is a non-empty, machine-readable token. Examples
in this contract are `Cel`, `ppm`, `m/s`, `m/s2`, `Pa`, `V`, `%`, and `count`.
The schema validates its syntax, not an external units registry. Document the
exact unit meaning for each `measurement_type`, use the same code consistently,
and convert device-native readings before sending them if needed.

## Reading state and safety interpretation

`reading_status=valid` means the producer considers the value usable;
`reading_status=stale` means a value is present but too old for the producer's
declared freshness policy; `reading_status=invalid` means a value was received
but failed producer-side quality checks; `reading_status=missing` means no
value is available and **requires `value: null`**. Every non-missing
reading requires a finite numeric value. Zero is an ordinary value and is never
used to represent missing data.

Missing, stale, invalid, or unknown data does not indicate a safe workplace.
Consumers must preserve these states and apply their separately approved
operational policies. This schema defines no industrial alarm limits. Battery
percentage is constrained to its representation range of 0–100; this is a unit
range, not an operational alarm threshold. Last-seen can be missing (`null`) or
present and classified as valid/stale; stale classification is determined by
the application policy, not by a hardcoded age in this contract.

## Examples

Valid messages are in `contracts/v1/examples/*.valid.json`. For example,
`telemetry.valid.json` carries a valid temperature and an explicitly missing
gas reading. `device_health.valid.json` shows unknown connectivity and missing
battery/last-seen information. Both are valid messages; neither implies safety.

`invalid_reading_null_with_valid_status.json` is rejected because null must use
`reading_status: "missing"`. `invalid_reading_local_timestamp.json` is rejected because
timestamps must be UTC. Other enforced rules include required identifiers,
schema version and timestamps; strict object fields; known enum values; finite
numeric values; battery range; event/report and incident/update time ordering;
and matching device/workplace IDs between telemetry and its health snapshot.

Pydantic adds semantic cross-field checks that JSON Schema cannot express
portably, such as matching IDs and status/value relationships. Validate with the
Pydantic models at application boundaries and use JSON Schema for language-neutral
structural validation. The tests validate the same examples against both.

## Hardware integration

ESP32 firmware, another embedded device, a gateway, or a simulator can map its
native sensor output to these messages. A producer assigns stable IDs, maps raw
sensor units into explicit unit codes, records UTC observation times, and marks
unavailable data as null/missing. Firmware details, pin mappings, transport,
calibration, and safety thresholds belong in their respective hardware or
application layers and do not change the shared message shape by themselves.
