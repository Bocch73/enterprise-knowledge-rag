"""Health endpoint response models."""

from typing import Literal

from pydantic import BaseModel

from app.core.config import Environment
from app.core.readiness import CheckState


class LiveHealthResponse(BaseModel):
    """Process-level liveness information."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: Environment


class ReadyHealthResponse(BaseModel):
    """Dependency-level readiness information."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckState]
