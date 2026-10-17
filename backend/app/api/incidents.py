from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from backend.app.api.dependencies import get_service
from backend.app.api.responses import Page
from backend.app.services import HelmetService
from backend.app.storage.errors import IncidentTransitionError
from contracts.v1 import Incident, IncidentHistoryEntry
from contracts.v1.models import Identifier
from backend.app.auth import Principal, require_roles

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"],
                    dependencies=[Depends(require_roles("viewer", "supervisor", "administrator"))])


class AcknowledgeIncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged_by: Identifier


@router.get("", response_model=Page[Incident])
def list_incidents(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: HelmetService = Depends(get_service),
) -> Page[Incident]:
    return service.list_incidents(limit=limit, offset=offset)


@router.get("/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: str,
    service: HelmetService = Depends(get_service),
) -> Incident:
    incident = service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@router.get("/{incident_id}/history", response_model=list[IncidentHistoryEntry])
def get_incident_history(
    incident_id: str,
    service: HelmetService = Depends(get_service),
) -> list[IncidentHistoryEntry]:
    incident = service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident.history


@router.post("/{incident_id}/acknowledge", response_model=Incident)
def acknowledge_incident(
    incident_id: str,
    payload: AcknowledgeIncidentRequest,
    service: HelmetService = Depends(get_service),
    principal: Principal = Depends(require_roles("supervisor", "administrator")),
) -> Incident:
    try:
        # The authenticated principal is authoritative; never trust a client-supplied actor ID.
        incident = service.acknowledge_incident(incident_id, principal.user_id)
    except IncidentTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident
