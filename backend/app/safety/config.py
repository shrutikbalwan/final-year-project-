import json
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.v1 import RiskLevel
from contracts.v1.models import Identifier, MeasurementName, UnitCode


class RuleOperator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


ActionableRisk = Literal["Unknown", "Advisory", "Warning", "Critical"]


class SafetyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: Identifier
    measurement_type: MeasurementName
    unit_code: UnitCode
    operator: RuleOperator
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    weight: Annotated[int, Field(ge=1, le=100)]
    risk_level: ActionableRisk
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class ScoreBands(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisory: Annotated[int, Field(ge=1)]
    warning: Annotated[int, Field(ge=1)]
    critical: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def bands_must_increase(self) -> "ScoreBands":
        if not self.advisory < self.warning < self.critical:
            raise ValueError("score bands must satisfy advisory < warning < critical")
        return self


class EscalationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_risk_level: ActionableRisk
    after_seconds: Annotated[int, Field(ge=0)]
    target: Annotated[str, Field(min_length=1, max_length=128)]
    repeat_every_seconds: Annotated[int, Field(ge=1)] | None = None


class WorkplaceSafetyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workplace_id: Identifier
    profile_name: Annotated[str, Field(min_length=1, max_length=128)]
    max_telemetry_age_seconds: Annotated[int, Field(ge=1)]
    max_reading_age_seconds: Annotated[int, Field(ge=1)]
    required_measurements: Annotated[list[MeasurementName], Field(min_length=1, max_length=64)]
    score_bands: ScoreBands
    rules: Annotated[list[SafetyRule], Field(min_length=1, max_length=256)]
    escalation_steps: Annotated[list[EscalationStep], Field(max_length=32)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def profile_has_coverage(self) -> "WorkplaceSafetyProfile":
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule_id values must be unique within a workplace profile")
        covered = {rule.measurement_type for rule in self.rules}
        uncovered = set(self.required_measurements) - covered
        if uncovered:
            raise ValueError(f"required measurements need at least one rule: {sorted(uncovered)}")
        return self


class WorkplaceProfileRegistry:
    """Immutable in-process index of validated, workplace-specific rule profiles."""

    def __init__(self, profiles: list[WorkplaceSafetyProfile] | None = None) -> None:
        profiles = profiles or []
        indexed = {profile.workplace_id: profile for profile in profiles}
        if len(indexed) != len(profiles):
            raise ValueError("workplace_id values must be unique in the profile registry")
        self._profiles = indexed

    def get(self, workplace_id: str) -> WorkplaceSafetyProfile | None:
        return self._profiles.get(workplace_id)

    def replace(self, profile: WorkplaceSafetyProfile) -> None:
        """Replace one validated in-process profile; persistence is deployment-configured."""
        self._profiles[profile.workplace_id] = profile

    def list_profiles(self) -> list[WorkplaceSafetyProfile]:
        """Return configured profiles in stable workplace-ID order for read-only API use."""
        return [self._profiles[key] for key in sorted(self._profiles)]

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkplaceProfileRegistry":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(config, dict) or set(config) != {"profiles"}:
            raise ValueError("profile configuration must contain only a 'profiles' array")
        profiles = [WorkplaceSafetyProfile.model_validate(item) for item in config["profiles"]]
        return cls(profiles)
