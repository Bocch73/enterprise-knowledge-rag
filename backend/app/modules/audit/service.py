"""Audit persistence and filtered administrator queries."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.audit.models import AuditEvent


async def append_audit_event(
    database: Database,
    *,
    actor_user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    status_code: int,
    request_id: str,
    details: dict[str, object],
) -> None:
    """Commit independently so denied and failed operations remain visible."""
    async with database.session_factory() as session:
        session.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                status_code=status_code,
                request_id=request_id,
                details=details,
            )
        )
        await session.commit()


async def list_audit_events(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    action: str | None,
    resource_type: str | None,
    resource_id: str | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    offset: int,
    limit: int,
) -> tuple[list[AuditEvent], int]:
    filters = []
    if actor_user_id is not None:
        filters.append(AuditEvent.actor_user_id == actor_user_id)
    if action is not None:
        filters.append(AuditEvent.action == action)
    if resource_type is not None:
        filters.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        filters.append(AuditEvent.resource_id == resource_id)
    if occurred_from is not None:
        filters.append(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        filters.append(AuditEvent.occurred_at <= occurred_to)

    total = await session.scalar(select(func.count(AuditEvent.id)).where(*filters))
    rows = await session.scalars(
        select(AuditEvent)
        .where(*filters)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows), int(total or 0)
