from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import get_service
from backend.app.safety.config import WorkplaceSafetyProfile
from backend.app.services import HelmetService
from backend.app.auth import Principal, require_roles


router = APIRouter(prefix="/api/v1/workplaces/profiles", tags=["workplaces"],
                    dependencies=[Depends(require_roles("viewer", "supervisor", "administrator"))])


@router.get("", response_model=list[WorkplaceSafetyProfile])
def list_workplace_profiles(
    service: HelmetService = Depends(get_service),
) -> list[WorkplaceSafetyProfile]:
    """Expose the active, validated configuration read-only for dashboard review."""
    return service.list_workplace_profiles()


@router.put("/{workplace_id}", response_model=WorkplaceSafetyProfile)
def replace_workplace_profile(
    workplace_id: str,
    profile: WorkplaceSafetyProfile,
    service: HelmetService = Depends(get_service),
    _principal: Principal = Depends(require_roles("administrator")),
) -> WorkplaceSafetyProfile:
    if profile.workplace_id != workplace_id:
        raise HTTPException(status_code=422, detail="path and profile workplace_id must match")
    return service.replace_workplace_profile(profile)
