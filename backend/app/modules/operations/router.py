"""Prometheus exposition endpoint with optional bearer protection."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import Database
from app.modules.documents.schemas import IngestionJobResponse, JobStatus
from app.modules.identity.dependencies import AdminUserDependency, SessionDependency
from app.modules.ingestion.models import IngestionJob
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.schemas import IngestionJobPage

router = APIRouter()
admin_router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    settings: Settings = request.app.state.settings
    if not settings.metrics_enabled:
        raise AppError(code="metrics_disabled", message="Metrics are disabled", status_code=404)
    _require_metrics_token(settings, authorization)

    database: Database = request.app.state.database
    operations_metrics: OperationsMetrics = request.app.state.operations_metrics
    async with database.session_factory() as session:
        rows = await session.execute(
            select(IngestionJob.status, func.count(IngestionJob.id)).group_by(IngestionJob.status)
        )
    operations_metrics.set_ingestion_jobs({status: int(count) for status, count in rows.all()})
    return Response(
        content=operations_metrics.render(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store"},
    )


def _require_metrics_token(settings: Settings, authorization: str | None) -> None:
    configured = settings.metrics_bearer_token
    if configured is None:
        return
    expected = f"Bearer {configured.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise AppError(
            code="metrics_authentication_required",
            message="Metrics authentication is required",
            status_code=401,
        )


@admin_router.get("/ingestion-jobs", response_model=IngestionJobPage)
async def ingestion_jobs(
    _admin: AdminUserDependency,
    session: SessionDependency,
    status: JobStatus | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> IngestionJobPage:
    filters = [IngestionJob.status == status] if status is not None else []
    total = await session.scalar(select(func.count(IngestionJob.id)).where(*filters))
    rows = await session.scalars(
        select(IngestionJob)
        .where(*filters)
        .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return IngestionJobPage(
        items=[IngestionJobResponse.from_model(job) for job in rows],
        offset=offset,
        limit=limit,
        total=int(total or 0),
    )
