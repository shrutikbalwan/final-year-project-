from fastapi import APIRouter, HTTPException, Request

from backend.app.auth import LoginRequest, LoginResponse, LocalAuthService

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    auth: LocalAuthService | None = getattr(request.app.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    result = auth.login(payload.username, payload.password.get_secret_value())
    if result is None:
        raise HTTPException(status_code=401, detail="invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return result
