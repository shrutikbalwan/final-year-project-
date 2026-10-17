from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from contracts.v1 import DeviceTelemetry, SensorReading
from contracts.v1.models import ConnectivityStatus, LastSeenStatus

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    total: int


class HelmetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    helmet_id: str = Field(description="The shared contract device_id for this helmet.")
    workplace_id: str
    last_telemetry_at: datetime
    connectivity_status: ConnectivityStatus
    battery_reading: SensorReading
    last_seen_at: datetime | None
    last_seen_status: LastSeenStatus

    @classmethod
    def from_telemetry(cls, telemetry: DeviceTelemetry) -> "HelmetSummary":
        return cls(
            helmet_id=telemetry.device_id,
            workplace_id=telemetry.workplace_id,
            last_telemetry_at=telemetry.observed_at,
            connectivity_status=telemetry.health.connectivity_status,
            battery_reading=telemetry.health.battery_reading,
            last_seen_at=telemetry.health.last_seen_at,
            last_seen_status=telemetry.health.last_seen_status,
        )


class HelmetDetail(HelmetSummary):
    latest_telemetry: DeviceTelemetry

    @classmethod
    def from_telemetry(cls, telemetry: DeviceTelemetry) -> "HelmetDetail":
        return cls(
            **HelmetSummary.from_telemetry(telemetry).model_dump(),
            latest_telemetry=telemetry,
        )
