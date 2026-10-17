from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.dependencies import get_service
from backend.app.api.responses import HelmetDetail, HelmetSummary, Page
from backend.app.services import HelmetService
from backend.app.safety.engine import RiskEvaluation

from backend.app.auth import require_roles

router = APIRouter(prefix="/api/v1/helmets", tags=["helmets"],
                    dependencies=[Depends(require_roles("viewer", "supervisor", "administrator"))])


@router.get("/{helmet_id}/risk", response_model=RiskEvaluation)
def get_helmet_risk(
    helmet_id: str,
    service: HelmetService = Depends(get_service),
) -> RiskEvaluation:
    evaluation = service.evaluate_helmet_risk(helmet_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="helmet not found")
    return evaluation


@router.get("", response_model=Page[HelmetSummary])
def list_helmets(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: HelmetService = Depends(get_service),
) -> Page[HelmetSummary]:
    return service.list_helmets(limit=limit, offset=offset)


@router.get("/{helmet_id}", response_model=HelmetDetail)
def get_helmet(
    helmet_id: str,
    service: HelmetService = Depends(get_service),
) -> HelmetDetail:
    helmet = service.get_helmet(helmet_id)
    if helmet is None:
        raise HTTPException(status_code=404, detail="helmet not found")
    return helmet
