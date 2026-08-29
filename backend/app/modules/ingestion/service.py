"""Ingestion-job visibility and bounded operator retry rules."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.documents.models import Document, DocumentVersion
from app.modules.documents.service import EDIT_ACCESS
from app.modules.identity.models import User
from app.modules.ingestion.models import IngestionJob
from app.modules.knowledge_bases.models import KnowledgeBaseMembership


async def get_accessible_job(
    session: AsyncSession,
    user: User,
    job_id: UUID,
) -> tuple[IngestionJob, str]:
    """Resolve a job through the caller's resource membership."""
    result = await session.execute(
        select(IngestionJob, KnowledgeBaseMembership.access_level)
        .join(DocumentVersion, DocumentVersion.id == IngestionJob.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == Document.knowledge_base_id,
        )
        .where(
            IngestionJob.id == job_id,
            KnowledgeBaseMembership.user_id == user.id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            code="ingestion_job_not_found",
            message="Ingestion job was not found",
            status_code=404,
        )
    return row[0], row[1]


async def retry_failed_job(
    session: AsyncSession,
    user: User,
    job_id: UUID,
) -> IngestionJob:
    """Allow one explicit retry after automatic attempts are exhausted."""
    visible_job, access = await get_accessible_job(session, user, job_id)
    if access not in EDIT_ACCESS:
        raise AppError(
            code="permission_denied",
            message="Knowledge base editor permission is required",
            status_code=403,
        )
    job = await session.scalar(
        select(IngestionJob).where(IngestionJob.id == visible_job.id).with_for_update()
    )
    if job is None:
        raise AppError(
            code="ingestion_job_not_found",
            message="Ingestion job was not found",
            status_code=404,
        )
    if job.status != "failed":
        raise AppError(
            code="ingestion_job_not_failed",
            message="Only a failed ingestion job can be retried",
            status_code=409,
        )
    if not job.retryable:
        raise AppError(
            code="ingestion_failure_not_retryable",
            message="This permanent document error cannot be retried",
            status_code=409,
        )
    if job.manual_retry_count >= 1:
        raise AppError(
            code="manual_retry_limit_reached",
            message="The manual retry limit has been reached",
            status_code=409,
        )
    job.manual_retry_count += 1
    job.max_attempts += 1
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.available_at = datetime.now(UTC)
    job.started_at = None
    job.finished_at = None
    job.error_code = None
    job.error_message = None
    await session.commit()
    await session.refresh(job)
    return job
