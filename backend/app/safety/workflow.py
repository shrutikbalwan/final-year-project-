from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from contracts.v1 import (
    Incident,
    IncidentAction,
    IncidentHistoryEntry,
    IncidentSource,
    IncidentStatus,
    RiskLevel,
)
from backend.app.storage.errors import IncidentTransitionError
from backend.app.storage.interface import Storage

from .config import WorkplaceProfileRegistry
from .engine import RISK_RANK, RiskEvaluation


class IncidentWorkflow:
    """Incident creation, deduplication, acknowledgement, history and escalation."""

    def __init__(self, storage: Storage, profiles: WorkplaceProfileRegistry) -> None:
        self.storage = storage
        self.profiles = profiles

    def record_evaluation(self, evaluation: RiskEvaluation) -> tuple[Incident | None, bool]:
        if evaluation.risk_level == RiskLevel.NORMAL:
            return None, False

        now = evaluation.evaluated_at.astimezone(timezone.utc)
        incident_id = str(uuid4())
        explanation = " ".join(evaluation.reasons)[:2000]
        incident = Incident(
            schema_version="1.0.0",
            incident_id=incident_id,
            device_id=evaluation.device_id,
            workplace_id=evaluation.workplace_id,
            status=IncidentStatus.OPEN,
            severity=evaluation.risk_level,
            risk_score=evaluation.score,
            opened_at=now,
            updated_at=now,
            reason=explanation,
            source=IncidentSource(
                telemetry_event_id=evaluation.telemetry_event_id,
                rule_ids=evaluation.matched_rule_ids,
                reading_ids=evaluation.source_reading_ids,
            ),
            event_ids=[],
            occurrence_count=1,
            history=[
                IncidentHistoryEntry(
                    entry_id=f"created-{uuid4().hex}",
                    action=IncidentAction.CREATED,
                    timestamp=now,
                    note="Incident created by the configurable rule-based safety engine.",
                )
            ],
        )
        key_parts = [
            evaluation.workplace_id,
            evaluation.device_id,
            *evaluation.matched_rule_ids,
            *evaluation.quality_issue_codes,
        ]
        dedupe_key = sha256("|".join(sorted(key_parts)).encode("utf-8")).hexdigest()
        return self.storage.save_or_merge_incident(incident, dedupe_key)

    def acknowledge(
        self,
        incident_id: str,
        acknowledged_by: str,
        acknowledged_at: datetime | None = None,
    ) -> Incident | None:
        at = acknowledged_at or datetime.now(timezone.utc)
        if at.tzinfo is None or at.utcoffset() != timedelta(0):
            raise ValueError("acknowledged_at must be timezone-aware UTC")
        return self.storage.acknowledge_incident(
            incident_id,
            acknowledged_by,
            at.astimezone(timezone.utc),
        )

    def process_escalations(
        self,
        workplace_id: str | None = None,
        evaluated_at: datetime | None = None,
    ) -> list[Incident]:
        now = evaluated_at or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("evaluated_at must be timezone-aware UTC")
        now = now.astimezone(timezone.utc)
        updated_incidents: list[Incident] = []
        for incident in self.storage.list_active_incidents(workplace_id):
            profile = self.profiles.get(incident.workplace_id)
            if profile is None:
                continue
            history = list(incident.history)
            new_entries: list[IncidentHistoryEntry] = []
            for step in profile.escalation_steps:
                current_level = (
                    incident.severity.value
                    if isinstance(incident.severity, RiskLevel)
                    else incident.severity
                )
                if RISK_RANK[current_level] < RISK_RANK[RiskLevel(step.minimum_risk_level).value]:
                    continue
                prior = [
                    entry
                    for entry in history + new_entries
                    if entry.action == IncidentAction.ESCALATED and entry.target == step.target
                ]
                last_step = prior[-1] if prior else None
                if last_step is None:
                    due_at = incident.opened_at + timedelta(seconds=step.after_seconds)
                elif step.repeat_every_seconds is not None:
                    due_at = last_step.timestamp + timedelta(seconds=step.repeat_every_seconds)
                else:
                    continue
                if now < due_at:
                    continue
                new_entries.append(
                    IncidentHistoryEntry(
                        entry_id=f"escalated-{uuid4().hex}",
                        action=IncidentAction.ESCALATED,
                        timestamp=now,
                        target=step.target,
                        note=f"Escalation rule for {step.minimum_risk_level} reached its configured time.",
                    )
                )

            if not new_entries:
                continue
            updated = Incident.model_validate(
                {
                    **incident.model_dump(),
                    "updated_at": now,
                    "history": [*history, *new_entries],
                }
            )
            self.storage.update_incident(updated)
            updated_incidents.append(updated)
        return updated_incidents


__all__ = ["IncidentTransitionError", "IncidentWorkflow"]
