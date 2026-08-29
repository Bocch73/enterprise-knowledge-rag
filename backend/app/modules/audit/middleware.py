"""Record selected security and management HTTP operations after completion."""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_request_id
from app.db.session import Database
from app.modules.audit.service import append_audit_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _AuditedRoute:
    action: str
    resource_type: str


_AUDITED_ROUTES: tuple[
    tuple[str, re.Pattern[str], str, _AuditedRoute],
    ...,
] = (
    (
        "POST",
        re.compile(r"^/api/v1/auth/register$"),
        "/api/v1/auth/register",
        _AuditedRoute("auth.register", "user"),
    ),
    (
        "POST",
        re.compile(r"^/api/v1/auth/login$"),
        "/api/v1/auth/login",
        _AuditedRoute("auth.login", "user"),
    ),
    (
        "POST",
        re.compile(r"^/api/v1/knowledge-bases$"),
        "/api/v1/knowledge-bases",
        _AuditedRoute("knowledge_base.create", "knowledge_base"),
    ),
    (
        "PUT",
        re.compile(r"^/api/v1/knowledge-bases/(?P<resource_id>[^/]+)/members$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/members",
        _AuditedRoute("knowledge_base.membership.upsert", "knowledge_base"),
    ),
    (
        "POST",
        re.compile(r"^/api/v1/knowledge-bases/(?P<resource_id>[^/]+)/documents$"),
        "/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        _AuditedRoute("document.upload", "document"),
    ),
    (
        "POST",
        re.compile(r"^/api/v1/documents/(?P<resource_id>[^/]+)/versions$"),
        "/api/v1/documents/{document_id}/versions",
        _AuditedRoute("document.version.upload", "document"),
    ),
    (
        "POST",
        re.compile(r"^/api/v1/ingestion-jobs/(?P<resource_id>[^/]+)/retry$"),
        "/api/v1/ingestion-jobs/{job_id}/retry",
        _AuditedRoute("ingestion.retry", "ingestion_job"),
    ),
)


class AuditMiddleware:
    """Persist audit outcomes without reading or retaining request bodies."""

    def __init__(self, app: ASGIApp, *, database: Database) -> None:
        self.app = app
        self.database = database

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        await self.app(scope, receive, capture_status)
        matched = _match_audited_route(
            str(scope.get("method", "")),
            str(scope.get("path", "")),
        )
        if matched is None:
            return
        descriptor, route_template, matched_resource_id = matched
        state = scope.get("state", {})
        actor_user_id = _optional_uuid(state.get("actor_user_id"))
        resource_id = state.get("audit_resource_id")
        if resource_id is None:
            resource_id = matched_resource_id
        outcome = (
            "success"
            if status_code < 400
            else "denied"
            if status_code in {401, 403, 404, 429}
            else "failure"
        )
        try:
            await append_audit_event(
                self.database,
                actor_user_id=actor_user_id,
                action=descriptor.action,
                resource_type=str(state.get("audit_resource_type", descriptor.resource_type)),
                resource_id=str(resource_id) if resource_id is not None else None,
                outcome=outcome,
                status_code=status_code,
                request_id=get_request_id(),
                details={"method": str(scope.get("method", "")), "route": route_template},
            )
        except Exception:
            logger.exception("audit_persistence_failed")


def _optional_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _match_audited_route(
    method: str,
    path: str,
) -> tuple[_AuditedRoute, str, str | None] | None:
    for expected_method, pattern, route_template, descriptor in _AUDITED_ROUTES:
        if method != expected_method:
            continue
        match = pattern.fullmatch(path)
        if match is not None:
            return descriptor, route_template, match.groupdict().get("resource_id")
    return None
