"""Liveness and readiness endpoints."""

from collections.abc import Mapping
from typing import cast

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.core.readiness import ReadinessCheck, run_readiness_checks
from app.schemas.health import LiveHealthResponse, ReadyHealthResponse

router = APIRouter()


@router.get("/live", response_model=LiveHealthResponse)
async def liveness(request: Request) -> LiveHealthResponse:
    """Report whether the application process can answer requests."""
    settings = cast(Settings, request.app.state.settings)
    return LiveHealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyHealthResponse}},
)
async def readiness(request: Request, response: Response) -> ReadyHealthResponse:
    """Report whether every required dependency can serve traffic."""
    settings = cast(Settings, request.app.state.settings)
    checks = cast(Mapping[str, ReadinessCheck], request.app.state.readiness_checks)
    check_results = await run_readiness_checks(
        checks,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    is_ready = all(result == "up" for result in check_results.values())
    response.status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyHealthResponse(
        status="ready" if is_ready else "not_ready",
        checks=check_results,
    )
