# Phase 2 hardware integration reference

Use the versioned contract in `contracts/v1/models.py` and its JSON Schema copy
in `docs/contracts/v1/schemas/`. Regenerate both schema locations together with:

```powershell
python -m contracts.v1.export_schemas
```

## Field-name review

The names describe meaning rather than a specific board or sensor:

| Field | Meaning for a device/gateway adapter |
| --- | --- |
| `device_id` | Stable registered helmet/device identifier |
| `workplace_id` | Stable site, facility, or zone identifier |
| `schema_version` | Version of the payload contract (`1.0.0`) |
| `event_id` | Unique telemetry or safety-event message identifier |
| `reading_id` | Unique identifier for one emitted reading |
| `sensor_id` | Stable identifier for the logical sensor, independent of pin/bus |
| `measurement_type` | Quantity name such as `temperature` or `gas_concentration` |
| `unit_code` | Explicit machine-readable token for the value's unit |
| `value` | Finite numeric value, or null only for a missing reading |
| `reading_status` | `valid`, `missing`, `stale`, or `invalid` |
| `observed_at` | UTC time the device/gateway observed the value or snapshot |
| `connectivity_status` | Reported link state; `unknown` is allowed |
| `last_seen_at` | UTC time of last confirmed contact, or null if unknown |

`battery_reading` uses the same SensorReading shape as other measurements,
with `measurement_type=battery_charge` and `unit_code=%`. `SafetyEvent` uses
`occurred_at` for the occurrence time and `reported_at` for the send/report
time. An `Incident` groups one or more `event_ids`.

## Unit mapping starting point

Use a consistent unit for each quantity and convert raw sensor output in the
device adapter when needed. These are project examples, not mandated sensor
hardware or safety limits:

| `measurement_type` | Suggested `unit_code` | Notes |
| --- | --- | --- |
| `temperature` | `Cel` | Degrees Celsius |
| `relative_humidity` | `%` | Relative humidity percentage |
| `gas_concentration` | `ppm` | Record the gas species in device configuration/metadata |
| `pressure` | `kPa` | Pressure in kilopascals |
| `linear_acceleration` | `m/s2` | Acceleration in metres per second squared |
| `speed` | `m/s` | Speed in metres per second |
| `battery_charge` | `%` | 0–100 representation range |
| `voltage` | `V` | Volts |
| `current` | `A` | Amperes |

The schema checks the token's character/length shape and enforces `%` for the
battery reading; it does not consult a units registry or prove dimensional
correctness. Keep a hardware mapping table for the actual sensor model,
calibration, resolution, native output, converted output, and unit. Do not put
alarm cutoffs into `unit_code` or the shared contract.

## Missing and quality data

If a sensor is unavailable, send `value: null` and `reading_status: "missing"`.
Do not send zero as a placeholder. Use `stale` when a previous value exists but
fails the producer's freshness policy, and `invalid` when a received value
fails a producer-side quality check. Missing or unknown values do not mean a
hazard is absent or that a workplace is safe.

All timestamps are UTC (`Z` or `+00:00`). Firmware may use a device clock, but a
gateway can normalize the timestamp and attach stable IDs before forwarding.
Pin numbers, buses, calibration coefficients, transport framing, and approved
operational thresholds belong in hardware/gateway configuration or a later
application policy, not in these shared data fields.
