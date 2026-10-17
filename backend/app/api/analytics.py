from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.app.auth import require_roles

from backend.app.api.dependencies import get_service
from backend.app.services import DuplicateEventError, HelmetService
from machine_learning.models import AnalyticsEvent

router = APIRouter(prefix="/api/v1/analytics/events", tags=["analytics"],
                    dependencies=[Depends(require_roles("viewer", "supervisor", "administrator"))])


@router.post("", response_model=AnalyticsEvent, status_code=status.HTTP_201_CREATED)
def ingest_analytics_event(
    payload: AnalyticsEvent,
    service: HelmetService = Depends(get_service),
    _principal=Depends(require_roles("supervisor", "administrator")),
) -> AnalyticsEvent:
    try:
        return service.accept_analytics_event(payload)
    except DuplicateEventError as exc:
        raise HTTPException(status_code=409, detail="analytics_event_id has already been accepted") from exc


@router.get("")
def list_analytics_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: HelmetService = Depends(get_service),
) -> dict:
    return service.list_analytics_events(limit, offset).model_dump()
