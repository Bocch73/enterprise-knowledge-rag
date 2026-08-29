"""Administrator-only filtered audit queries."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.audit.schemas import AuditEventPage, AuditEventResponse
from app.modules.audit.service import list_audit_events
from app.modules.identity.dependencies import AdminUserDependency, SessionDependency

router = APIRouter()


@router.get("/audit-events", response_model=AuditEventPage)
async def audit_events(
    _admin: AdminUserDependency,
    session: SessionDependency,
    actor_user_id: UUID | None = None,
    action: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    resource_type: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    resource_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditEventPage:
    events, total = await list_audit_events(
        session,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        offset=offset,
        limit=limit,
    )
    return AuditEventPage(
        items=[AuditEventResponse.from_model(event) for event in events],
        offset=offset,
        limit=limit,
        total=total,
    )
