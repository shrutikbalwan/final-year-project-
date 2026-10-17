from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.app.auth import require_roles

from backend.app.api.dependencies import get_service
from backend.app.api.responses import Page
from backend.app.services import DuplicateEventError, HelmetService
from contracts.v1 import SafetyEvent

router = APIRouter(prefix="/api/v1/events", tags=["events"],
                    dependencies=[Depends(require_roles("viewer", "supervisor", "administrator"))])


@router.get("", response_model=Page[SafetyEvent])
def list_events(
    device_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: HelmetService = Depends(get_service),
) -> Page[SafetyEvent]:
    if any(value and (value.tzinfo is None or value.utcoffset() != timedelta(0)) for value in (start, end)):
        raise HTTPException(status_code=422, detail="start and end timestamps must include UTC timezone")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be earlier than or equal to end")
    return service.list_events(limit, offset, device_id, start, end)


@router.post("", response_model=SafetyEvent, status_code=status.HTTP_201_CREATED)
def ingest_event(
    payload: SafetyEvent,
    service: HelmetService = Depends(get_service),
    _principal=Depends(require_roles("supervisor", "administrator")),
) -> SafetyEvent:
    try:
        return service.accept_event(payload)
    except DuplicateEventError as exc:
        raise HTTPException(status_code=409, detail="event_id has already been accepted") from exc
