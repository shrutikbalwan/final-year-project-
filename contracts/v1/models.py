"""Pydantic models for the versioned Smart Safety Helmet data contract.

The models intentionally describe reported measurements and events without
encoding industry safety limits or assumptions about the sensor hardware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]

MeasurementName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]

UnitCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9%._/\[\]-]+$",
    ),
]

UtcDateTime = Annotated[
    datetime,
    Field(
        json_schema_extra={
            "pattern": r"(?:Z|\+00:00)$",
            "description": "RFC 3339 timestamp in UTC, ending in Z or +00:00.",
        }
    ),
]


def _validate_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC timezone")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be UTC (Z or +00:00)")
    return value.astimezone(timezone.utc)


class ReadingStatus(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"


class ConnectivityStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    INTERMITTENT = "intermittent"
    UNKNOWN = "unknown"


class LastSeenStatus(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"


class EventType(str, Enum):
    IMPACT_DETECTED = "impact_detected"
    FALL_DETECTED = "fall_detected"
    HAZARD_DETECTED = "hazard_detected"
    MANUAL_SOS = "manual_sos"
    NEAR_MISS = "near_miss"
    OTHER = "other"


class EventSeverity(str, Enum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RiskLevel(str, Enum):
    NORMAL = "Normal"
    ADVISORY = "Advisory"
    WARNING = "Warning"
    CRITICAL = "Critical"
    UNKNOWN = "Unknown"


class IncidentAction(str, Enum):
    CREATED = "created"
    REPEATED = "repeated"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentSource(ContractModel):
    """Traceable origin references for a generated incident."""

    telemetry_event_id: Identifier
    rule_ids: Annotated[list[Identifier], Field(max_length=64)] = Field(default_factory=list)
    reading_ids: Annotated[list[Identifier], Field(max_length=256)] = Field(default_factory=list)


class IncidentHistoryEntry(ContractModel):
    entry_id: Identifier
    action: IncidentAction
    timestamp: UtcDateTime
    actor: Identifier | None = None
    target: Annotated[str, StringConstraints(max_length=128)] | None = None
    note: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class SensorReading(ContractModel):
    """One reported measurement with explicit unit and quality state."""

    reading_id: Identifier
    sensor_id: Identifier
    measurement_type: MeasurementName = Field(
        description="Stable quantity name, for example temperature or gas_concentration."
    )
    unit_code: UnitCode = Field(
        description="Machine-readable unit token; producers must document and use it consistently."
    )
    value: Annotated[float, Field(allow_inf_nan=False)] | None = Field(
        description="Finite measurement value, or null only when reading_status is missing."
    )
    reading_status: ReadingStatus
    observed_at: UtcDateTime

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_utc(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def status_matches_value(self) -> "SensorReading":
        if self.reading_status == ReadingStatus.MISSING and self.value is not None:
            raise ValueError("missing readings must have value=null")
        if self.reading_status != ReadingStatus.MISSING and self.value is None:
            raise ValueError("null values must use reading_status=missing")
        return self


class DeviceHealth(ContractModel):
    """Point-in-time device health, including explicit unknown/missing states."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    device_id: Identifier
    workplace_id: Identifier
    observed_at: UtcDateTime
    battery_reading: SensorReading = Field(
        description="Battery percentage reading; value is 0..100 when present, in unit_code %."
    )
    connectivity_status: ConnectivityStatus
    last_seen_at: UtcDateTime | None = Field(
        description="Most recent confirmed device contact, or null when not known."
    )
    last_seen_status: LastSeenStatus

    @field_validator("observed_at", "last_seen_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _validate_utc(value) if value is not None else None

    @model_validator(mode="after")
    def health_values_are_consistent(self) -> "DeviceHealth":
        if (
            self.battery_reading.measurement_type != "battery_charge"
            or self.battery_reading.unit_code != "%"
        ):
            raise ValueError("battery_reading must use measurement_type=battery_charge and unit_code=%")
        if self.battery_reading.value is not None and not 0 <= self.battery_reading.value <= 100:
            raise ValueError("battery percentage must be between 0 and 100")
        if self.last_seen_status == LastSeenStatus.MISSING and self.last_seen_at is not None:
            raise ValueError("missing last-seen information must have last_seen_at=null")
        if self.last_seen_status != LastSeenStatus.MISSING and self.last_seen_at is None:
            raise ValueError("known or stale last-seen information requires last_seen_at")
        if self.last_seen_at is not None and self.last_seen_at > self.observed_at:
            raise ValueError("last_seen_at cannot be later than observed_at")
        return self


class DeviceTelemetry(ContractModel):
    """A device telemetry message containing readings and a health snapshot."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: Identifier
    device_id: Identifier
    workplace_id: Identifier
    observed_at: UtcDateTime
    readings: Annotated[list[SensorReading], Field(min_length=1, max_length=256)]
    health: DeviceHealth

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_utc(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def embedded_health_matches_message(self) -> "DeviceTelemetry":
        if self.health.device_id != self.device_id:
            raise ValueError("health.device_id must match telemetry device_id")
        if self.health.workplace_id != self.workplace_id:
            raise ValueError("health.workplace_id must match telemetry workplace_id")
        if self.health.observed_at > self.observed_at:
            raise ValueError("health.observed_at cannot be later than telemetry observed_at")
        return self


class SafetyEvent(ContractModel):
    """A safety-related event report; severity is descriptive, not a threshold."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: Identifier
    incident_id: Identifier | None = None
    device_id: Identifier
    workplace_id: Identifier
    event_type: EventType
    severity: EventSeverity
    occurred_at: UtcDateTime
    reported_at: UtcDateTime
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    related_reading_ids: Annotated[list[Identifier], Field(max_length=64)] = Field(
        default_factory=list
    )

    @field_validator("occurred_at", "reported_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def report_not_before_occurrence(self) -> "SafetyEvent":
        if self.reported_at < self.occurred_at:
            raise ValueError("reported_at cannot be earlier than occurred_at")
        return self


class Incident(ContractModel):
    """An incident record that groups one or more safety event IDs."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Identifier
    device_id: Identifier
    workplace_id: Identifier
    status: IncidentStatus
    severity: RiskLevel
    risk_score: Annotated[int, Field(ge=0)]
    opened_at: UtcDateTime
    updated_at: UtcDateTime
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    source: IncidentSource
    event_ids: Annotated[list[Identifier], Field(max_length=256)] = Field(default_factory=list)
    occurrence_count: Annotated[int, Field(ge=1)] = 1
    acknowledged_at: UtcDateTime | None = None
    acknowledged_by: Identifier | None = None
    history: Annotated[list[IncidentHistoryEntry], Field(min_length=1, max_length=512)]

    @field_validator("opened_at", "updated_at", "acknowledged_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _validate_utc(value) if value is not None else None

    @model_validator(mode="after")
    def update_not_before_opening(self) -> "Incident":
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at cannot be earlier than opened_at")
        if self.status == IncidentStatus.OPEN and (
            self.acknowledged_at is not None or self.acknowledged_by is not None
        ):
            raise ValueError("open incidents cannot have acknowledgement fields")
        if self.status == IncidentStatus.ACKNOWLEDGED and (
            self.acknowledged_at is None or self.acknowledged_by is None
        ):
            raise ValueError("acknowledged incidents require acknowledged_at and acknowledged_by")
        history_times = [entry.timestamp for entry in self.history]
        if history_times != sorted(history_times):
            raise ValueError("incident history timestamps must be ordered")
        if history_times[0] < self.opened_at or history_times[-1] > self.updated_at:
            raise ValueError("incident history timestamps must fall within opened_at and updated_at")
        return self
