from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Iterator

from backend.app.api.responses import HelmetDetail, HelmetSummary
from backend.app.storage.errors import (
    DuplicateEventError,
    IncidentTransitionError,
    StorageError,
)
from contracts.v1 import DeviceTelemetry, Incident, SafetyEvent
from contracts.v1 import IncidentAction, IncidentHistoryEntry, IncidentStatus, RiskLevel
from machine_learning.models import AnalyticsEvent


_RISK_RANK = {
    RiskLevel.NORMAL.value: 0,
    RiskLevel.UNKNOWN.value: 1,
    RiskLevel.ADVISORY.value: 2,
    RiskLevel.WARNING.value: 3,
    RiskLevel.CRITICAL.value: 4,
}


class SQLiteStorage:
    """Durable local storage; implements the same boundary planned for DynamoDB."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        if str(database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        try:
            with self._connection() as connection:
                connection.executescript(
                    """
                    PRAGMA journal_mode=WAL;
                    CREATE TABLE IF NOT EXISTS telemetry (
                        event_id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        workplace_id TEXT NOT NULL,
                        observed_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_telemetry_device_time
                        ON telemetry(device_id, observed_at DESC, event_id DESC);
                    CREATE TABLE IF NOT EXISTS safety_events (
                        event_id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        workplace_id TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        reported_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_safety_events_workplace_time
                        ON safety_events(workplace_id, occurred_at DESC, event_id DESC);
                    CREATE TABLE IF NOT EXISTS analytics_events (
                        analytics_event_id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        workplace_id TEXT NOT NULL,
                        observed_at TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_analytics_events_workplace_time
                        ON analytics_events(workplace_id, observed_at DESC, analytics_event_id DESC);
                    CREATE TABLE IF NOT EXISTS incidents (
                        incident_id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        workplace_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        opened_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        dedupe_key TEXT,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_incidents_updated
                        ON incidents(updated_at DESC, incident_id DESC);
                    """
                )
                incident_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(incidents)")
                }
                if "dedupe_key" not in incident_columns:
                    connection.execute("ALTER TABLE incidents ADD COLUMN dedupe_key TEXT")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS ix_incidents_active_dedupe "
                    "ON incidents(workplace_id, device_id, dedupe_key, status)"
                )
        except sqlite3.Error as exc:
            raise StorageError("local database initialization failed") from exc

    def health_check(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise StorageError("local database is unavailable") from exc

    def save_telemetry(self, telemetry: DeviceTelemetry) -> None:
        payload = telemetry.model_dump_json()
        observed_at = telemetry.observed_at.isoformat()
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO telemetry(event_id, device_id, workplace_id, observed_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        telemetry.event_id,
                        telemetry.device_id,
                        telemetry.workplace_id,
                        observed_at,
                        payload,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "telemetry.event_id" in str(exc) or "UNIQUE constraint failed" in str(exc):
                raise DuplicateEventError(telemetry.event_id) from exc
            raise StorageError("could not persist telemetry") from exc
        except sqlite3.Error as exc:
            raise StorageError("could not persist telemetry") from exc

    def list_telemetry(
        self, limit: int, offset: int, device_id: str | None = None,
        start=None, end=None,
    ) -> tuple[list[DeviceTelemetry], int]:
        clauses: list[str] = []
        parameters: list[object] = []
        if device_id is not None:
            clauses.append("device_id = ?")
            parameters.append(device_id)
        if start is not None:
            clauses.append("observed_at >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("observed_at <= ?")
            parameters.append(end.isoformat())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        try:
            with self._connection() as connection:
                total = connection.execute("SELECT COUNT(*) FROM telemetry" + where, parameters).fetchone()[0]
                rows = connection.execute(
                    "SELECT payload_json FROM telemetry" + where
                    + " ORDER BY observed_at DESC, event_id ASC LIMIT ? OFFSET ?",
                    [*parameters, limit, offset],
                ).fetchall()
            return [DeviceTelemetry.model_validate_json(row["payload_json"]) for row in rows], total
        except sqlite3.Error as exc:
            raise StorageError("could not list telemetry history") from exc

    def save_event(self, event: SafetyEvent) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO safety_events(event_id, device_id, workplace_id, occurred_at, reported_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.device_id,
                        event.workplace_id,
                        event.occurred_at.isoformat(),
                        event.reported_at.isoformat(),
                        event.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "safety_events.event_id" in str(exc) or "UNIQUE constraint failed" in str(exc):
                raise DuplicateEventError(event.event_id) from exc
            raise StorageError("could not persist safety event") from exc
        except sqlite3.Error as exc:
            raise StorageError("could not persist safety event") from exc

    def get_event(self, event_id: str) -> SafetyEvent | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM safety_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
            return SafetyEvent.model_validate_json(row["payload_json"]) if row else None
        except sqlite3.Error as exc:
            raise StorageError("could not read safety event") from exc

    def list_events(
        self, limit: int, offset: int, device_id: str | None = None,
        start=None, end=None,
    ) -> tuple[list[SafetyEvent], int]:
        clauses: list[str] = []
        parameters: list[object] = []
        if device_id is not None:
            clauses.append("device_id = ?")
            parameters.append(device_id)
        if start is not None:
            clauses.append("occurred_at >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("occurred_at <= ?")
            parameters.append(end.isoformat())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        try:
            with self._connection() as connection:
                total = connection.execute("SELECT COUNT(*) FROM safety_events" + where, parameters).fetchone()[0]
                rows = connection.execute(
                    "SELECT payload_json FROM safety_events" + where
                    + " ORDER BY occurred_at DESC, event_id ASC LIMIT ? OFFSET ?",
                    [*parameters, limit, offset],
                ).fetchall()
            return [SafetyEvent.model_validate_json(row["payload_json"]) for row in rows], total
        except sqlite3.Error as exc:
            raise StorageError("could not list safety events") from exc

    def save_analytics_event(self, event: AnalyticsEvent) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO analytics_events(analytics_event_id, device_id, workplace_id, observed_at, generated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event.analytics_event_id,
                        event.device_id,
                        event.workplace_id,
                        event.observed_at.isoformat(),
                        event.generated_at.isoformat(),
                        event.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "analytics_events.analytics_event_id" in str(exc) or "UNIQUE constraint failed" in str(exc):
                raise DuplicateEventError(event.analytics_event_id) from exc
            raise StorageError("could not persist analytics event") from exc
        except sqlite3.Error as exc:
            raise StorageError("could not persist analytics event") from exc

    def get_analytics_event(self, event_id: str) -> AnalyticsEvent | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM analytics_events WHERE analytics_event_id = ?", (event_id,)
                ).fetchone()
            return AnalyticsEvent.model_validate_json(row["payload_json"]) if row else None
        except sqlite3.Error as exc:
            raise StorageError("could not read analytics event") from exc

    def list_analytics_events(self, limit: int, offset: int) -> tuple[list[AnalyticsEvent], int]:
        try:
            with self._connection() as connection:
                total = connection.execute("SELECT COUNT(*) FROM analytics_events").fetchone()[0]
                rows = connection.execute(
                    "SELECT payload_json FROM analytics_events ORDER BY observed_at DESC, analytics_event_id ASC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [AnalyticsEvent.model_validate_json(row["payload_json"]) for row in rows], total
        except sqlite3.Error as exc:
            raise StorageError("could not list analytics events") from exc

    def _latest_telemetry(self, device_id: str) -> DeviceTelemetry | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM telemetry WHERE device_id = ? "
                    "ORDER BY observed_at DESC, event_id DESC LIMIT 1",
                    (device_id,),
                ).fetchone()
            return DeviceTelemetry.model_validate_json(row["payload_json"]) if row else None
        except sqlite3.Error as exc:
            raise StorageError("could not read helmet data") from exc

    def list_helmets(self, limit: int, offset: int) -> tuple[list[HelmetSummary], int]:
        try:
            with self._connection() as connection:
                total = connection.execute(
                    "SELECT COUNT(DISTINCT device_id) FROM telemetry"
                ).fetchone()[0]
                rows = connection.execute(
                    "SELECT t.payload_json FROM telemetry AS t "
                    "WHERE t.event_id = (SELECT t2.event_id FROM telemetry AS t2 "
                    "WHERE t2.device_id = t.device_id ORDER BY t2.observed_at DESC, t2.event_id DESC LIMIT 1) "
                    "ORDER BY t.observed_at DESC, t.device_id ASC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            items = [
                HelmetSummary.from_telemetry(DeviceTelemetry.model_validate_json(row["payload_json"]))
                for row in rows
            ]
            return items, total
        except sqlite3.Error as exc:
            raise StorageError("could not list helmets") from exc

    def get_helmet(self, helmet_id: str) -> HelmetDetail | None:
        telemetry = self._latest_telemetry(helmet_id)
        return HelmetDetail.from_telemetry(telemetry) if telemetry else None

    def list_incidents(self, limit: int, offset: int) -> tuple[list[Incident], int]:
        try:
            with self._connection() as connection:
                total = connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
                rows = connection.execute(
                    "SELECT payload_json FROM incidents ORDER BY updated_at DESC, incident_id ASC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [Incident.model_validate_json(row["payload_json"]) for row in rows], total
        except sqlite3.Error as exc:
            raise StorageError("could not list incidents") from exc

    def get_incident(self, incident_id: str) -> Incident | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM incidents WHERE incident_id = ?",
                    (incident_id,),
                ).fetchone()
            return Incident.model_validate_json(row["payload_json"]) if row else None
        except sqlite3.Error as exc:
            raise StorageError("could not read incident") from exc

    def save_incident(self, incident: Incident) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO incidents(incident_id, device_id, workplace_id, status, opened_at, updated_at, dedupe_key, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                    (
                        incident.incident_id,
                        incident.device_id,
                        incident.workplace_id,
                        incident.status,
                        incident.opened_at.isoformat(),
                        incident.updated_at.isoformat(),
                        incident.model_dump_json(),
                    ),
                )
        except sqlite3.Error as exc:
            raise StorageError("could not persist incident") from exc

    def save_or_merge_incident(self, incident: Incident, dedupe_key: str) -> tuple[Incident, bool]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM incidents WHERE workplace_id = ? AND device_id = ? "
                    "AND dedupe_key = ? AND status IN ('open', 'acknowledged') "
                    "ORDER BY opened_at DESC LIMIT 1",
                    (incident.workplace_id, incident.device_id, dedupe_key),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO incidents(incident_id, device_id, workplace_id, status, opened_at, updated_at, dedupe_key, payload_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            incident.incident_id,
                            incident.device_id,
                            incident.workplace_id,
                            incident.status,
                            incident.opened_at.isoformat(),
                            incident.updated_at.isoformat(),
                            dedupe_key,
                            incident.model_dump_json(),
                        ),
                    )
                    return incident, True

                previous = Incident.model_validate_json(row["payload_json"])
                severity = max(
                    (previous.severity, incident.severity),
                    key=lambda level: _RISK_RANK[level.value if isinstance(level, RiskLevel) else level],
                )
                action = (
                    IncidentAction.ESCALATED
                    if _RISK_RANK[severity.value if isinstance(severity, RiskLevel) else severity]
                    > _RISK_RANK[previous.severity.value if isinstance(previous.severity, RiskLevel) else previous.severity]
                    else IncidentAction.REPEATED
                )
                entry = IncidentHistoryEntry(
                    entry_id=f"hist-{incident.incident_id}",
                    action=action,
                    timestamp=incident.opened_at,
                    note=f"Repeated trigger observed: {incident.reason}",
                )
                merged = Incident.model_validate(
                    {
                        **previous.model_dump(),
                        "severity": severity,
                        "risk_score": max(previous.risk_score, incident.risk_score),
                        "reason": incident.reason,
                        "source": incident.source,
                        "updated_at": incident.updated_at,
                        "occurrence_count": previous.occurrence_count + 1,
                        "history": [*previous.history, entry],
                    }
                )
                connection.execute(
                    "UPDATE incidents SET updated_at = ?, payload_json = ? WHERE incident_id = ?",
                    (merged.updated_at.isoformat(), merged.model_dump_json(), merged.incident_id),
                )
                return merged, False
        except sqlite3.Error as exc:
            raise StorageError("could not persist incident") from exc

    def update_incident(self, incident: Incident) -> None:
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE incidents SET status = ?, updated_at = ?, payload_json = ? WHERE incident_id = ?",
                    (
                        incident.status,
                        incident.updated_at.isoformat(),
                        incident.model_dump_json(),
                        incident.incident_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise StorageError("incident not found")
        except sqlite3.Error as exc:
            raise StorageError("could not update incident") from exc

    def acknowledge_incident(
        self, incident_id: str, acknowledged_by: str, acknowledged_at
    ) -> Incident | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM incidents WHERE incident_id = ?", (incident_id,)
                ).fetchone()
                if row is None:
                    return None
                incident = Incident.model_validate_json(row["payload_json"])
                if incident.status == IncidentStatus.ACKNOWLEDGED:
                    return incident
                if incident.status != IncidentStatus.OPEN:
                    raise IncidentTransitionError("only open incidents can be acknowledged")
                updated = Incident.model_validate(
                    {
                        **incident.model_dump(),
                        "status": IncidentStatus.ACKNOWLEDGED,
                        "updated_at": acknowledged_at,
                        "acknowledged_at": acknowledged_at,
                        "acknowledged_by": acknowledged_by,
                        "history": [
                            *incident.history,
                            IncidentHistoryEntry(
                                entry_id=f"ack-{incident_id}",
                                action=IncidentAction.ACKNOWLEDGED,
                                timestamp=acknowledged_at,
                                actor=acknowledged_by,
                                note="Incident acknowledged.",
                            ),
                        ],
                    }
                )
                connection.execute(
                    "UPDATE incidents SET status = ?, updated_at = ?, payload_json = ? WHERE incident_id = ?",
                    (updated.status, updated.updated_at.isoformat(), updated.model_dump_json(), incident_id),
                )
                return updated
        except IncidentTransitionError:
            raise
        except sqlite3.Error as exc:
            raise StorageError("could not acknowledge incident") from exc

    def list_active_incidents(self, workplace_id: str | None = None) -> list[Incident]:
        try:
            with self._connection() as connection:
                if workplace_id is None:
                    rows = connection.execute(
                        "SELECT payload_json FROM incidents WHERE status IN ('open', 'acknowledged') "
                        "ORDER BY opened_at ASC"
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT payload_json FROM incidents WHERE status IN ('open', 'acknowledged') "
                        "AND workplace_id = ? ORDER BY opened_at ASC",
                        (workplace_id,),
                    ).fetchall()
            return [Incident.model_validate_json(row["payload_json"]) for row in rows]
        except sqlite3.Error as exc:
            raise StorageError("could not list active incidents") from exc
