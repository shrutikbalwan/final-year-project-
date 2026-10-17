import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from contracts.v1.models import Identifier, UnitCode

class FeatureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$")
    unit_code: UnitCode


class DevicePartitions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train: list[str] = Field(min_length=1)
    validation: list[str] = Field(min_length=1)
    test: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def disjoint_partitions(self) -> "DevicePartitions":
        groups = [set(self.train), set(self.validation), set(self.test)]
        if any(not group for group in groups):
            raise ValueError("each device partition must contain at least one device")
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("device IDs must be exclusive to one partition to prevent leakage")
        if any(not device.strip() for group in groups for device in group):
            raise ValueError("device IDs cannot be empty")
        return self


class DatasetManifest(BaseModel):
    """Provenance and explicit device-disjoint split for a labeled telemetry CSV."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=200)
    attribution: str = Field(min_length=1, max_length=1000)
    intended_use: Literal["academic_evaluation", "internal_research"]
    label_definition: str = Field(min_length=1, max_length=1000)
    features: list[FeatureDefinition] = Field(min_length=1, max_length=64)
    partitions: DevicePartitions
    random_seed: int = 42
    n_estimators: int = Field(default=200, ge=10, le=2000)
    contamination: float = Field(default=0.05, gt=0, le=0.5)

    @field_validator("features")
    @classmethod
    def unique_feature_names(cls, value: list[FeatureDefinition]) -> list[FeatureDefinition]:
        names = [feature.name for feature in value]
        if len(names) != len(set(names)):
            raise ValueError("feature names must be unique")
        return value


@dataclass(frozen=True)
class TelemetrySample:
    source_event_id: str
    device_id: str
    workplace_id: str
    observed_at: datetime
    label: int
    features: tuple[float, ...]

def _parse_timestamp(value: str, row_number: int) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"row {row_number}: observed_at must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"row {row_number}: observed_at must include a UTC timezone")
    return parsed.astimezone(timezone.utc)


def load_samples(csv_path: str | Path, manifest: DatasetManifest) -> dict[str, list[TelemetrySample]]:
    """Validate labeled telemetry; missing/invalid feature values are never imputed."""
    partitions = {
        device: name
        for name, devices in (
            ("train", manifest.partitions.train),
            ("validation", manifest.partitions.validation),
            ("test", manifest.partitions.test),
        )
        for device in devices
    }
    loaded: dict[str, list[TelemetrySample]] = {"train": [], "validation": [], "test": []}
    seen_events: set[str] = set()
    seen_device_times: set[tuple[str, str]] = set()
    identifier_adapter = TypeAdapter(Identifier)
    required = {
        "source_event_id", "device_id", "workplace_id", "observed_at", "anomaly_label",
        *(feature.name for feature in manifest.features),
    }
    try:
        with Path(csv_path).open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError("CSV header is missing")
            missing_columns = sorted(required - set(reader.fieldnames))
            if missing_columns:
                raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")
            for row_number, row in enumerate(reader, start=2):
                device_id = row.get("device_id", "").strip()
                identifier_adapter.validate_python(device_id)
                partition = partitions.get(device_id)
                if partition is None:
                    raise ValueError(f"row {row_number}: device_id is absent from the split manifest")
                event_id = row.get("source_event_id", "").strip()
                identifier_adapter.validate_python(event_id)
                if not event_id or event_id in seen_events:
                    raise ValueError(f"row {row_number}: source_event_id is empty or duplicated")
                seen_events.add(event_id)
                observed_raw = row.get("observed_at", "").strip()
                observed_at = _parse_timestamp(observed_raw, row_number)
                time_key = (device_id, observed_at.isoformat())
                if time_key in seen_device_times:
                    raise ValueError(f"row {row_number}: duplicate device/timestamp sample")
                seen_device_times.add(time_key)
                workplace_id = row.get("workplace_id", "").strip()
                identifier_adapter.validate_python(workplace_id)
                try:
                    label = int(row.get("anomaly_label", ""))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"row {row_number}: anomaly_label must be 0 or 1") from exc
                if label not in (0, 1):
                    raise ValueError(f"row {row_number}: anomaly_label must be 0 or 1")
                values: list[float] = []
                for feature in manifest.features:
                    raw = row.get(feature.name)
                    try:
                        value = float(raw) if raw is not None and raw.strip() else math.nan
                    except ValueError as exc:
                        raise ValueError(f"row {row_number}: feature '{feature.name}' is not numeric") from exc
                    if not math.isfinite(value):
                        raise ValueError(f"row {row_number}: feature '{feature.name}' is missing or non-finite")
                    values.append(value)
                loaded[partition].append(TelemetrySample(
                    source_event_id=event_id,
                    device_id=device_id,
                    workplace_id=workplace_id,
                    observed_at=observed_at,
                    label=label,
                    features=tuple(values),
                ))
    except OSError as exc:
        raise ValueError(f"could not read telemetry CSV: {csv_path}") from exc
    for name, samples in loaded.items():
        if not samples:
            raise ValueError(f"CSV has no rows assigned to {name} partition")
        if {sample.label for sample in samples} != {0, 1}:
            raise ValueError(f"{name} partition must contain labeled normal and anomaly examples")
    if sum(sample.label == 0 for sample in loaded["train"]) < 10:
        raise ValueError("training split requires at least 10 labeled normal rows")
    return loaded
