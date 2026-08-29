"""Safe administrator-facing audit response schemas."""

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from app.modules.audit.models import AuditEvent


class AuditEventResponse(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: Literal["success", "denied", "failure"]
    status_code: int
    request_id: str
    details: dict[str, object]

    @classmethod
    def from_model(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=event.id,
            occurred_at=event.occurred_at,
            actor_user_id=event.actor_user_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            outcome=cast(Literal["success", "denied", "failure"], event.outcome),
            status_code=event.status_code,
            request_id=event.request_id,
            details=event.details,
        )


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    offset: int
    limit: int
    total: int
