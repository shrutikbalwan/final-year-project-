from datetime import datetime, timezone
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from contracts.v1.models import ContractModel, Identifier


class AnalyticsEvent(ContractModel):
    """Stored analytics output; it is not a safety incident or rule evaluation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    analytics_event_id: Identifier
    event_type: Literal["sensor_anomaly_prediction"] = "sensor_anomaly_prediction"
    task: Literal["sensor_anomaly_detection"] = "sensor_anomaly_detection"
    device_id: Identifier
    workplace_id: Identifier
    source_event_id: Identifier
    observed_at: datetime
    generated_at: datetime
    model_name: Identifier
    model_version: Identifier
    outcome: Literal["anomaly", "not_flagged"]
    anomaly_score: float = Field(allow_inf_nan=False)
    decision_threshold: float = Field(allow_inf_nan=False)
    explanation: str = Field(min_length=1, max_length=2000)

    @field_validator("observed_at", "generated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("analytics timestamps must include UTC timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def generated_after_observed(self) -> "AnalyticsEvent":
        if self.generated_at < self.observed_at:
            raise ValueError("generated_at cannot be earlier than observed_at")
        return self
