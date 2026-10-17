import logging
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.helmets import router as helmets_router
from backend.app.api.analytics import router as analytics_router
from backend.app.api.events import router as events_router
from backend.app.api.incidents import router as incidents_router
from backend.app.api.telemetry import router as telemetry_router
from backend.app.api.workplaces import router as workplaces_router
from backend.app.api.auth import router as auth_router
from backend.app.auth import AuthenticationUnavailable, LocalAuthService
from backend.app.services import HelmetService
from backend.app.safety.config import WorkplaceProfileRegistry
from backend.app.storage.errors import StorageError
from backend.app.storage.interface import Storage
from backend.app.storage.sqlite import SQLiteStorage

request_logger = logging.getLogger("backend.request")


def create_app(
    storage: Storage | None = None,
    safety_profiles: WorkplaceProfileRegistry | None = None,
    auth_service: LocalAuthService | None = None,
) -> FastAPI:
    application = FastAPI(
        title="Smart Safety Helmet API",
        description=(
            "Local Phase 1 API using the shared contracts.v1 data models. "
            "Bearer authentication is required for all data routes. Local development authentication uses configured bootstrap hashes."
        ),
        version="1.0.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    if storage is None:
        database_path = Path(
            os.environ.get("HELMET_DB_PATH", "data/smart_safety_helmet.sqlite3")
        )
        storage = SQLiteStorage(database_path)
    if safety_profiles is None:
        profile_path = os.environ.get("SAFETY_PROFILES_PATH")
        safety_profiles = (
            WorkplaceProfileRegistry.from_file(profile_path)
            if profile_path
            else WorkplaceProfileRegistry()
        )
    application.state.service = HelmetService(storage, safety_profiles)
    if auth_service is not None:
        application.state.auth = auth_service
    else:
        try:
            application.state.auth = LocalAuthService.from_environment()
        except AuthenticationUnavailable:
            application.state.auth = None

    @application.middleware("http")
    async def log_request_summary(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            route = request.scope.get("route")
            request_logger.error(
                "request_exception",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_route": getattr(route, "path", "unmatched"),
                    "status_code": 500,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
            )
            raise
        route = request.scope.get("route")
        request_logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "http_route": getattr(route, "path", "unmatched"),
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    application.include_router(auth_router)
    application.include_router(telemetry_router)
    application.include_router(workplaces_router)
    application.include_router(events_router)
    application.include_router(analytics_router)
    application.include_router(helmets_router)
    application.include_router(incidents_router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        try:
            application.state.service.storage.health_check()
        except StorageError as exc:
            raise HTTPException(status_code=503, detail="local storage unavailable") from exc
        return {"status": "ok", "storage": "ready"}

    @application.exception_handler(StorageError)
    async def handle_storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "storage operation failed"},
            headers={"X-Request-ID": getattr(request.state, "request_id", uuid4().hex)},
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error"},
            headers={"X-Request-ID": getattr(request.state, "request_id", uuid4().hex)},
        )

    return application


app = create_app()
