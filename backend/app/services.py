from datetime import datetime

from backend.app.api.responses import HelmetSummary, Page
from backend.app.safety.config import WorkplaceProfileRegistry
from backend.app.safety.engine import RiskEvaluation, SafetyEngine
from backend.app.safety.workflow import IncidentWorkflow
from backend.app.storage.errors import DuplicateEventError, StorageError
from backend.app.storage.interface import Storage
from contracts.v1 import DeviceTelemetry, Incident, SafetyEvent
from machine_learning.models import AnalyticsEvent
from backend.app.safety.config import WorkplaceSafetyProfile


class HelmetService:
    """Application operations between the HTTP layer and persistence adapter."""

    def __init__(
        self,
        storage: Storage,
        profiles: WorkplaceProfileRegistry | None = None,
    ) -> None:
        self.storage = storage
        self.profiles = profiles or WorkplaceProfileRegistry()
        self.safety_engine = SafetyEngine(self.profiles)
        self.incident_workflow = IncidentWorkflow(storage, self.profiles)

    def accept_telemetry(self, telemetry: DeviceTelemetry) -> DeviceTelemetry:
        self.storage.save_telemetry(telemetry)
        self.incident_workflow.process_escalations(telemetry.workplace_id)
        evaluation = self.safety_engine.evaluate(telemetry)
        self.incident_workflow.record_evaluation(evaluation)
        return telemetry

    def list_telemetry(
        self, limit: int, offset: int, device_id: str | None = None,
        start: datetime | None = None, end: datetime | None = None,
    ) -> Page[DeviceTelemetry]:
        items, total = self.storage.list_telemetry(limit, offset, device_id, start, end)
        return Page(items=items, limit=limit, offset=offset, total=total)

    def evaluate_helmet_risk(self, helmet_id: str) -> RiskEvaluation | None:
        helmet = self.storage.get_helmet(helmet_id)
        if helmet is None:
            return None
        return self.safety_engine.evaluate(helmet.latest_telemetry)

    def list_workplace_profiles(self) -> list[WorkplaceSafetyProfile]:
        return self.profiles.list_profiles()

    def replace_workplace_profile(self, profile: WorkplaceSafetyProfile) -> WorkplaceSafetyProfile:
        self.profiles.replace(profile)
        # Engines share the same registry today; re-create to keep that invariant explicit.
        self.safety_engine = SafetyEngine(self.profiles)
        self.incident_workflow = IncidentWorkflow(self.storage, self.profiles)
        return profile

    def accept_event(self, event: SafetyEvent) -> SafetyEvent:
        self.storage.save_event(event)
        return event

    def list_events(
        self, limit: int, offset: int, device_id: str | None = None,
        start: datetime | None = None, end: datetime | None = None,
    ) -> Page[SafetyEvent]:
        items, total = self.storage.list_events(limit, offset, device_id, start, end)
        return Page(items=items, limit=limit, offset=offset, total=total)

    def accept_analytics_event(self, event: AnalyticsEvent) -> AnalyticsEvent:
        self.storage.save_analytics_event(event)
        return event

    def list_analytics_events(self, limit: int, offset: int) -> Page[AnalyticsEvent]:
        items, total = self.storage.list_analytics_events(limit, offset)
        return Page(items=items, limit=limit, offset=offset, total=total)

    def list_helmets(self, limit: int, offset: int) -> Page[HelmetSummary]:
        items, total = self.storage.list_helmets(limit, offset)
        return Page(items=items, limit=limit, offset=offset, total=total)

    def get_helmet(self, helmet_id: str) -> HelmetSummary | None:
        return self.storage.get_helmet(helmet_id)

    def list_incidents(self, limit: int, offset: int) -> Page[Incident]:
        items, total = self.storage.list_incidents(limit, offset)
        return Page(items=items, limit=limit, offset=offset, total=total)

    def get_incident(self, incident_id: str) -> Incident | None:
        return self.storage.get_incident(incident_id)

    def acknowledge_incident(
        self, incident_id: str, acknowledged_by: str, acknowledged_at: datetime | None = None
    ) -> Incident | None:
        return self.incident_workflow.acknowledge(incident_id, acknowledged_by, acknowledged_at)
