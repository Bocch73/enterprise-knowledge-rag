"""Stable error response models shared by all API endpoints."""

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Machine-readable code plus a safe human-readable explanation."""

    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Top-level error envelope."""

    error: ErrorDetail
