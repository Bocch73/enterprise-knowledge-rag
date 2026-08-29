"""Authenticated ingestion-job status and retry endpoints."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.modules.documents.schemas import IngestionJobResponse
from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency
from app.modules.ingestion.service import get_accessible_job, retry_failed_job

router = APIRouter()


@router.get("/{job_id}", response_model=IngestionJobResponse)
async def get_job(
    job_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> IngestionJobResponse:
    job, _access = await get_accessible_job(session, current_user, job_id)
    return IngestionJobResponse.from_model(job)


@router.post("/{job_id}/retry", response_model=IngestionJobResponse)
async def retry_job(
    job_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> IngestionJobResponse:
    job = await retry_failed_job(session, current_user, job_id)
    request.state.audit_resource_id = job.id
    return IngestionJobResponse.from_model(job)
