"""Database-backed ingestion worker with idempotency and crash recovery."""

from __future__ import annotations

import logging
import math
import socket
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID, uuid5

import anyio
from sqlalchemy import delete, select

from app.core.config import Settings
from app.db.session import Database
from app.infrastructure.storage import LocalObjectStorage, ObjectStorage
from app.modules.documents.models import DocumentVersion, ParsedDocument
from app.modules.indexing.chunking import TextChunk, split_text
from app.modules.indexing.models import DocumentChunk
from app.modules.indexing.providers import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProvider,
    EmbeddingProviderError,
    create_embedding_provider,
)
from app.modules.ingestion.models import IngestionJob
from app.modules.ingestion.parsers import DocumentParsingError, ParsedResult, parse_document

logger = logging.getLogger(__name__)


async def recover_stale_jobs(database: Database, settings: Settings) -> int:
    """Return abandoned running jobs to the queue or fail them at their limit."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.ingestion_stale_after_seconds)
    async with database.session_factory() as session:
        result = await session.scalars(
            select(IngestionJob)
            .where(
                IngestionJob.status == "running",
                IngestionJob.locked_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.all())
        for job in jobs:
            job.worker_id = None
            job.locked_at = None
            job.error_code = "worker_lost"
            job.error_message = "The previous worker stopped before finishing the job"
            if job.attempt_count < job.max_attempts:
                job.status = "queued"
                job.stage = "queued"
                job.progress = 0
                job.available_at = now
            else:
                job.status = "failed"
                job.stage = "failed"
                job.finished_at = now
                job.retryable = True
        await session.commit()
        return len(jobs)


async def claim_next_job(database: Database, worker_id: str) -> UUID | None:
    """Atomically claim one due job so concurrent workers do not duplicate work."""
    now = datetime.now(UTC)
    async with database.session_factory() as session:
        job = await session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.status == "queued",
                IngestionJob.available_at <= now,
            )
            .order_by(IngestionJob.available_at, IngestionJob.created_at, IngestionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.stage = "parsing"
        job.progress = 10
        job.attempt_count += 1
        job.started_at = now
        job.finished_at = None
        job.locked_at = now
        job.worker_id = worker_id
        job.error_code = None
        job.error_message = None
        await session.commit()
        return job.id


async def _load_and_parse(
    database: Database,
    storage: ObjectStorage,
    job_id: UUID,
    settings: Settings,
) -> ParsedResult:
    async with database.session_factory() as session:
        row = await session.execute(
            select(DocumentVersion.storage_key, DocumentVersion.media_type)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .where(IngestionJob.id == job_id)
        )
        storage_key, media_type = row.one()

    def parse_from_storage() -> ParsedResult:
        with storage.open_binary(storage_key) as source:
            return parse_document(source, media_type, settings)

    return await anyio.to_thread.run_sync(parse_from_storage)


async def _update_job_stage(
    database: Database,
    job_id: UUID,
    *,
    stage: str,
    progress: int,
) -> None:
    """Persist observable progress and refresh the worker heartbeat."""
    async with database.session_factory() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None or job.status != "running":
            return
        job.stage = stage
        job.progress = progress
        job.locked_at = datetime.now(UTC)
        await session.commit()


async def _chunk_parsed_document(parsed: ParsedResult, settings: Settings) -> list[TextChunk]:
    chunk_operation = partial(
        split_text,
        parsed.content,
        chunk_size=settings.chunk_size_characters,
        overlap=settings.chunk_overlap_characters,
    )
    return await anyio.to_thread.run_sync(chunk_operation)


def _validate_embedding_batch(
    chunks: Sequence[TextChunk],
    embeddings: Sequence[Sequence[float]],
    provider: EmbeddingProvider,
) -> None:
    if provider.dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            "embedding_dimension_mismatch",
            f"The embedding provider must return {EMBEDDING_DIMENSIONS} dimensions",
            retryable=False,
        )
    if len(chunks) != len(embeddings):
        raise EmbeddingProviderError(
            "embedding_count_mismatch",
            "The embedding provider returned a different number of vectors than chunks",
            retryable=False,
        )
    for embedding in embeddings:
        if len(embedding) != EMBEDDING_DIMENSIONS or not all(
            math.isfinite(value) for value in embedding
        ):
            raise EmbeddingProviderError(
                "embedding_value_invalid",
                "The embedding provider returned an invalid vector",
                retryable=False,
            )


async def _complete_job(
    database: Database,
    job_id: UUID,
    parsed: ParsedResult,
    chunks: Sequence[TextChunk],
    embeddings: Sequence[Sequence[float]],
    provider: EmbeddingProvider,
) -> None:
    async with database.session_factory() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None or job.status == "completed":
            return
        existing = await session.get(ParsedDocument, job.document_version_id)
        if existing is None:
            existing = ParsedDocument(document_version_id=job.document_version_id)
            session.add(existing)
        existing.content = parsed.content
        existing.character_count = len(parsed.content)
        existing.page_count = parsed.page_count
        existing.parser_name = parsed.parser_name
        existing.parser_version = parsed.parser_version
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_version_id == job.document_version_id
            )
        )
        session.add_all(
            [
                DocumentChunk(
                    id=uuid5(
                        job.document_version_id,
                        f"chunk:{chunk.index}:{chunk.content_sha256}",
                    ),
                    document_version_id=job.document_version_id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    character_count=len(chunk.content),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    content_sha256=chunk.content_sha256,
                    embedding_model=provider.name,
                    embedding_dimensions=provider.dimensions,
                    embedding=list(embedding),
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
        )
        now = datetime.now(UTC)
        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.retryable = False
        job.finished_at = now
        job.locked_at = None
        job.worker_id = None
        job.error_code = None
        job.error_message = None
        await session.commit()


async def _fail_job(
    database: Database,
    job_id: UUID,
    *,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    async with database.session_factory() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None or job.status == "completed":
            return
        now = datetime.now(UTC)
        job.error_code = code
        job.error_message = message[:1000]
        job.locked_at = None
        job.worker_id = None
        if retryable and job.attempt_count < job.max_attempts:
            delay_seconds = 2 ** max(0, job.attempt_count - 1)
            job.status = "queued"
            job.stage = "queued"
            job.progress = 0
            job.available_at = now + timedelta(seconds=delay_seconds)
        else:
            job.status = "failed"
            job.stage = "failed"
            job.progress = 100
            job.retryable = retryable
            job.finished_at = now
        await session.commit()


async def process_next_job(
    database: Database,
    settings: Settings,
    *,
    storage: ObjectStorage | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    worker_id: str | None = None,
) -> UUID | None:
    """Claim and process at most one job, returning its identifier when found."""
    selected_storage = storage or LocalObjectStorage(settings.object_storage_path)
    selected_embedding_provider = embedding_provider or create_embedding_provider(settings)
    selected_worker_id = worker_id or f"{socket.gethostname()}-{id(database)}"
    job_id = await claim_next_job(database, selected_worker_id)
    if job_id is None:
        return None
    try:
        parsed = await _load_and_parse(database, selected_storage, job_id, settings)
        await _update_job_stage(database, job_id, stage="chunking", progress=35)
        chunks = await _chunk_parsed_document(parsed, settings)
        await _update_job_stage(database, job_id, stage="embedding", progress=60)
        embeddings = await selected_embedding_provider.embed_documents(
            [chunk.content for chunk in chunks]
        )
        _validate_embedding_batch(chunks, embeddings, selected_embedding_provider)
        await _update_job_stage(database, job_id, stage="indexing", progress=85)
        await _complete_job(
            database,
            job_id,
            parsed,
            chunks,
            embeddings,
            selected_embedding_provider,
        )
    except DocumentParsingError as exception:
        await _fail_job(
            database,
            job_id,
            code=exception.code,
            message=exception.message,
            retryable=False,
        )
    except EmbeddingProviderError as exception:
        await _fail_job(
            database,
            job_id,
            code=exception.code,
            message=exception.message,
            retryable=exception.retryable,
        )
    except OSError:
        logger.exception("ingestion_storage_error", extra={"job_id": str(job_id)})
        await _fail_job(
            database,
            job_id,
            code="storage_temporarily_unavailable",
            message="The source file could not be read from storage",
            retryable=True,
        )
    except Exception:
        logger.exception("ingestion_unexpected_error", extra={"job_id": str(job_id)})
        await _fail_job(
            database,
            job_id,
            code="ingestion_internal_error",
            message="Document ingestion failed unexpectedly",
            retryable=False,
        )
    return job_id
