from datetime import datetime, timedelta, timezone
from typing import Iterable

from pydantic import BaseModel, ConfigDict

from contracts.v1 import DeviceTelemetry, RiskLevel, SensorReading
from .config import RuleOperator, SafetyRule, WorkplaceProfileRegistry, WorkplaceSafetyProfile


RISK_RANK = {
    RiskLevel.NORMAL.value: 0,
    RiskLevel.UNKNOWN.value: 1,
    RiskLevel.ADVISORY.value: 2,
    RiskLevel.WARNING.value: 3,
    RiskLevel.CRITICAL.value: 4,
}


class RiskEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    workplace_id: str
    telemetry_event_id: str
    evaluated_at: datetime
    risk_level: RiskLevel
    score: int
    reasons: list[str]
    matched_rule_ids: list[str]
    source_reading_ids: list[str]
    quality_issue_codes: list[str]


def _matches(rule: SafetyRule, value: float) -> bool:
    if rule.operator == RuleOperator.GT:
        return value > rule.threshold
    if rule.operator == RuleOperator.GTE:
        return value >= rule.threshold
    if rule.operator == RuleOperator.LT:
        return value < rule.threshold
    return value <= rule.threshold


def _worst_level(levels: Iterable[RiskLevel]) -> RiskLevel:
    return max(levels, key=lambda level: RISK_RANK[level.value], default=RiskLevel.NORMAL)


class SafetyEngine:
    """Pure rule evaluator; it performs no I/O and has no FastAPI dependencies."""

    def __init__(self, profiles: WorkplaceProfileRegistry) -> None:
        self.profiles = profiles

    def evaluate(
        self,
        telemetry: DeviceTelemetry,
        evaluated_at: datetime | None = None,
    ) -> RiskEvaluation:
        now = evaluated_at or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("evaluated_at must be timezone-aware UTC")
        now = now.astimezone(timezone.utc)
        profile = self.profiles.get(telemetry.workplace_id)
        reasons: list[str] = []
        quality_codes: set[str] = set()
        matches: dict[str, SafetyRule] = {}
        source_reading_ids: set[str] = set()

        if profile is None:
            reasons.append(
                f"No safety profile is configured for workplace {telemetry.workplace_id}; risk cannot be assessed."
            )
            quality_codes.add("profile_missing")
            return self._result(telemetry, now, RiskLevel.UNKNOWN, 0, reasons, matches, source_reading_ids, quality_codes)

        if now - telemetry.observed_at > timedelta(seconds=profile.max_telemetry_age_seconds):
            reasons.append(
                f"Telemetry is stale: age exceeds the configured {profile.max_telemetry_age_seconds} second limit."
            )
            quality_codes.add("telemetry_stale")

        seen_measurements = {reading.measurement_type for reading in telemetry.readings}
        for measurement in profile.required_measurements:
            if measurement not in seen_measurements:
                reasons.append(f"Required measurement '{measurement}' is missing from telemetry.")
                quality_codes.add(f"measurement_missing:{measurement}")

        for reading in telemetry.readings:
            self._check_reading(reading, profile, now, reasons, quality_codes)
            if reading.reading_status != "valid":
                continue
            matching_rules = [rule for rule in profile.rules if rule.measurement_type == reading.measurement_type]
            if not matching_rules:
                reasons.append(
                    f"Measurement '{reading.measurement_type}' has no configured safety rule; risk cannot be assessed."
                )
                quality_codes.add(f"rule_missing:{reading.measurement_type}")
                continue
            unit_rules = [rule for rule in matching_rules if rule.unit_code == reading.unit_code]
            if not unit_rules:
                configured_units = sorted({rule.unit_code for rule in matching_rules})
                reasons.append(
                    f"Measurement '{reading.measurement_type}' uses unit '{reading.unit_code}', "
                    f"but this profile expects {', '.join(configured_units)}."
                )
                quality_codes.add(f"unit_mismatch:{reading.measurement_type}")
                continue
            if reading.value is None:
                continue
            for rule in unit_rules:
                if _matches(rule, reading.value):
                    matches[rule.rule_id] = rule
                    source_reading_ids.add(reading.reading_id)
                    reason = f"{rule.reason} (rule {rule.rule_id}, weight {rule.weight})."
                    if reason not in reasons:
                        reasons.append(reason)

        self._check_reading(telemetry.health.battery_reading, profile, now, reasons, quality_codes)
        if telemetry.health.connectivity_status in {"unknown", "disconnected"}:
            reasons.append(f"Device connectivity is {telemetry.health.connectivity_status}.")
            quality_codes.add(f"connectivity_{telemetry.health.connectivity_status}")
        if telemetry.health.last_seen_status in {"missing", "stale"}:
            reasons.append(f"Device last-seen information is {telemetry.health.last_seen_status}.")
            quality_codes.add(f"last_seen_{telemetry.health.last_seen_status}")

        score = sum(rule.weight for rule in matches.values())
        score_level = RiskLevel.NORMAL
        if score >= profile.score_bands.critical:
            score_level = RiskLevel.CRITICAL
        elif score >= profile.score_bands.warning:
            score_level = RiskLevel.WARNING
        elif score >= profile.score_bands.advisory:
            score_level = RiskLevel.ADVISORY
        rule_level = _worst_level(
            RiskLevel(rule.risk_level) for rule in matches.values()
        )
        result_level = _worst_level((score_level, rule_level))
        if quality_codes and result_level == RiskLevel.NORMAL:
            result_level = RiskLevel.UNKNOWN
        if not reasons:
            reasons.append("All required readings are valid and within the configured development rules.")
        return self._result(
            telemetry,
            now,
            result_level,
            score,
            reasons,
            matches,
            source_reading_ids,
            quality_codes,
        )

    @staticmethod
    def _check_reading(
        reading: SensorReading,
        profile: WorkplaceSafetyProfile,
        now: datetime,
        reasons: list[str],
        quality_codes: set[str],
    ) -> None:
        if reading.reading_status == "missing":
            reasons.append(f"Reading '{reading.reading_id}' for '{reading.measurement_type}' is missing.")
            quality_codes.add(f"reading_missing:{reading.measurement_type}")
        elif reading.reading_status == "stale":
            reasons.append(f"Reading '{reading.reading_id}' for '{reading.measurement_type}' is marked stale.")
            quality_codes.add(f"reading_stale:{reading.measurement_type}")
        elif reading.reading_status == "invalid":
            reasons.append(f"Sensor fault: reading '{reading.reading_id}' for '{reading.measurement_type}' is invalid.")
            quality_codes.add(f"sensor_fault:{reading.measurement_type}")
        elif now - reading.observed_at > timedelta(seconds=profile.max_reading_age_seconds):
            reasons.append(
                f"Reading '{reading.reading_id}' for '{reading.measurement_type}' is stale by age "
                f"(limit {profile.max_reading_age_seconds} seconds)."
            )
            quality_codes.add(f"reading_stale:{reading.measurement_type}")

    @staticmethod
    def _result(
        telemetry: DeviceTelemetry,
        now: datetime,
        level: RiskLevel,
        score: int,
        reasons: list[str],
        matches: dict[str, SafetyRule],
        reading_ids: set[str],
        quality_codes: set[str],
    ) -> RiskEvaluation:
        return RiskEvaluation(
            device_id=telemetry.device_id,
            workplace_id=telemetry.workplace_id,
            telemetry_event_id=telemetry.event_id,
            evaluated_at=now,
            risk_level=level,
            score=score,
            reasons=reasons,
            matched_rule_ids=sorted(matches),
            source_reading_ids=sorted(reading_ids),
            quality_issue_codes=sorted(quality_codes),
        )
