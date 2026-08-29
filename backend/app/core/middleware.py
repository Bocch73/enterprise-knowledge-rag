"""ASGI middleware for request correlation and safe failures."""

import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import build_error_response
from app.core.logging import reset_request_id, set_request_id
from app.modules.operations.metrics import OperationsMetrics

logger = logging.getLogger(__name__)

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_METRIC_ROUTES: tuple[tuple[re.Pattern[str], str | None], ...] = (
    (re.compile(r"^/api/v1/health/(?:live|ready)$"), None),
    (re.compile(r"^/api/v1/auth/(?:register|login|me)$"), None),
    (re.compile(r"^/api/v1/admin/(?:users|audit-events|ingestion-jobs)$"), None),
    (re.compile(r"^/api/v1/knowledge-bases$"), None),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}",
    ),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+/members$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/members",
    ),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+/documents$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/documents",
    ),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+/search$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/search",
    ),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+/answers$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/answers",
    ),
    (
        re.compile(r"^/api/v1/knowledge-bases/[^/]+/answers/stream$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/answers/stream",
    ),
    (re.compile(r"^/api/v1/documents/[^/]+$"), "/api/v1/documents/{document_id}"),
    (
        re.compile(r"^/api/v1/documents/[^/]+/versions$"),
        "/api/v1/documents/{document_id}/versions",
    ),
    (
        re.compile(r"^/api/v1/documents/versions/[^/]+/preview$"),
        "/api/v1/documents/versions/{version_id}/preview",
    ),
    (
        re.compile(r"^/api/v1/documents/versions/[^/]+/chunks$"),
        "/api/v1/documents/versions/{version_id}/chunks",
    ),
    (
        re.compile(r"^/api/v1/ingestion-jobs/[^/]+$"),
        "/api/v1/ingestion-jobs/{job_id}",
    ),
    (
        re.compile(r"^/api/v1/ingestion-jobs/[^/]+/retry$"),
        "/api/v1/ingestion-jobs/{job_id}/retry",
    ),
    (re.compile(r"^/metrics$"), None),
)


class RequestContextMiddleware:
    """Add a safe request identifier and structured access log to each HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = "X-Request-ID",
        metrics: OperationsMetrics | None = None,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._resolve_request_id(Headers(scope=scope).get(self.header_name))
        context_token = set_request_id(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[self.header_name] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            logger.exception("unhandled_exception")
            response = build_error_response(
                code="internal_server_error",
                message="Unexpected server error",
                status_code=500,
            )
            await response(scope, receive, send_with_context)
        finally:
            duration_seconds = perf_counter() - started_at
            duration_ms = round(duration_seconds * 1000, 3)
            route_template = self._metric_route(str(scope.get("path", "")))
            if self.metrics is not None:
                self.metrics.observe_http(
                    method=str(scope.get("method", "-")),
                    route=str(route_template),
                    status_code=status_code,
                    duration_seconds=duration_seconds,
                )
            logger.info(
                "request_completed",
                extra={
                    "http_method": scope.get("method", "-"),
                    "http_path": scope.get("path", "-"),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(context_token)

    @staticmethod
    def _resolve_request_id(candidate: str | None) -> str:
        if candidate is not None and _VALID_REQUEST_ID.fullmatch(candidate):
            return candidate
        return str(uuid4())

    @staticmethod
    def _metric_route(path: str) -> str:
        for pattern, template in _METRIC_ROUTES:
            if pattern.fullmatch(path):
                return path if template is None else template
        return "unmatched"
