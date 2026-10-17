from fastapi import Request

from backend.app.services import HelmetService


def get_service(request: Request) -> HelmetService:
    return request.app.state.service
