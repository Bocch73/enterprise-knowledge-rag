"""Application exceptions and HTTP exception handlers."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """A known business failure that is safe to return to the caller."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def build_error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the single error shape used by every endpoint."""
    content = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=get_request_id(),
            details=details,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=content.model_dump(mode="json"),
        headers=headers,
    )


async def handle_app_error(_request: Request, exception: Exception) -> JSONResponse:
    """Translate a known application error into the public error model."""
    if not isinstance(exception, AppError):
        raise TypeError("handle_app_error received an unexpected exception type")

    logger.info(
        "application_error",
        extra={"error_code": exception.code, "status_code": exception.status_code},
    )
    return build_error_response(
        code=exception.code,
        message=exception.message,
        status_code=exception.status_code,
        details=exception.details,
        headers={"WWW-Authenticate": "Bearer"} if exception.status_code == 401 else None,
    )


async def handle_validation_error(_request: Request, exception: Exception) -> JSONResponse:
    """Return validation details without echoing potentially sensitive input."""
    if not isinstance(exception, RequestValidationError):
        raise TypeError("handle_validation_error received an unexpected exception type")

    details = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exception.errors()
    ]
    return build_error_response(
        code="request_validation_error",
        message="Request validation failed",
        status_code=422,
        details=details,
    )


async def handle_http_error(_request: Request, exception: Exception) -> JSONResponse:
    """Normalize framework-generated errors such as 404 and 405."""
    if not isinstance(exception, StarletteHTTPException):
        raise TypeError("handle_http_error received an unexpected exception type")

    reason = HTTPStatus(exception.status_code).phrase
    message = exception.detail if isinstance(exception.detail, str) else reason
    return build_error_response(
        code=f"http_{exception.status_code}",
        message=message,
        status_code=exception.status_code,
        headers=dict(exception.headers) if exception.headers is not None else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all public exception translations in one place."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
