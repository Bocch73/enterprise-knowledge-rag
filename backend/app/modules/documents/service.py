"""Document authorization, immutable versioning, and storage coordination."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import anyio
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.storage import ObjectStorage
from app.modules.documents.models import Document, DocumentVersion, ParsedDocument
from app.modules.documents.upload_validation import StagedUpload, stage_and_validate_upload
from app.modules.identity.models import User
from app.modules.indexing.models import DocumentChunk
from app.modules.ingestion.models import IngestionJob
from app.modules.knowledge_bases.models import KnowledgeBaseMembership
from app.modules.knowledge_bases.service import get_accessible_knowledge_base

EDIT_ACCESS = {"owner", "editor"}


def _clean_title(title: str | None, filename: str) -> str:
    raw_title = title if title is not None else filename.rsplit(".", maxsplit=1)[0]
    cleaned = " ".join(raw_title.split())
    if not 2 <= len(cleaned) <= 200:
        raise AppError(
            code="invalid_document_title",
            message="Document title must contain 2 to 200 visible characters",
            status_code=422,
        )
    return cleaned


def _require_edit_access(access_level: str) -> None:
    if access_level not in EDIT_ACCESS:
        raise AppError(
            code="permission_denied",
            message="Knowledge base editor permission is required",
            status_code=403,
        )


async def get_accessible_document(
    session: AsyncSession,
    user: User,
    document_id: UUID,
) -> tuple[Document, str]:
    """Load a document only through the caller's knowledge-base membership."""
    result = await session.execute(
        select(Document, KnowledgeBaseMembership.access_level)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == Document.knowledge_base_id,
        )
        .where(
            Document.id == document_id,
            KnowledgeBaseMembership.user_id == user.id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            code="document_not_found",
            message="Document was not found",
            status_code=404,
        )
    return row[0], row[1]


async def list_documents(
    session: AsyncSession,
    user: User,
    knowledge_base_id: UUID,
) -> list[Document]:
    await get_accessible_knowledge_base(session, user, knowledge_base_id)
    result = await session.scalars(
        select(Document)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .order_by(Document.created_at, Document.id)
    )
    return list(result.unique().all())


async def get_document_detail(
    session: AsyncSession,
    user: User,
    document_id: UUID,
) -> Document:
    document, _access = await get_accessible_document(session, user, document_id)
    return document


def _build_version_and_job(
    *,
    document: Document,
    version_number: int,
    staged: StagedUpload,
    user: User,
    settings: Settings,
) -> tuple[DocumentVersion, IngestionJob]:
    version_id = uuid4()
    version_hex = version_id.hex
    storage_key = f"sources/{version_hex[:2]}/{version_hex}{staged.extension}"
    version = DocumentVersion(
        id=version_id,
        document_id=document.id,
        version_number=version_number,
        original_filename=staged.filename,
        media_type=staged.media_type,
        size_bytes=staged.size_bytes,
        sha256=staged.sha256,
        storage_key=storage_key,
        uploaded_by_id=user.id,
    )
    job = IngestionJob(
        document_version_id=version_id,
        status="queued",
        stage="queued",
        progress=0,
        attempt_count=0,
        max_attempts=settings.ingestion_max_attempts,
        manual_retry_count=0,
        retryable=True,
        available_at=datetime.now(UTC),
    )
    return version, job


async def _persist_source_and_rows(
    session: AsyncSession,
    storage: ObjectStorage,
    staged: StagedUpload,
    document: Document,
    version: DocumentVersion,
    job: IngestionJob,
) -> None:
    stored = False
    try:
        await anyio.to_thread.run_sync(storage.put_file, version.storage_key, staged.path)
        stored = True
        session.add(document)
        await session.flush()
        session.add(version)
        await session.flush()
        session.add(job)
        await session.commit()
    except IntegrityError as exception:
        await session.rollback()
        if stored:
            await anyio.to_thread.run_sync(storage.delete, version.storage_key)
        diagnostic = getattr(exception.orig, "diag", None)
        if getattr(diagnostic, "constraint_name", None) == "uq_document_version_sha256":
            raise AppError(
                code="duplicate_document_version",
                message="This exact content already exists as a version of the document",
                status_code=409,
            ) from exception
        raise
    except Exception:
        await session.rollback()
        if stored:
            await anyio.to_thread.run_sync(storage.delete, version.storage_key)
        raise


async def create_document(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    user: User,
    knowledge_base_id: UUID,
    upload: UploadFile,
    title: str | None,
) -> tuple[Document, DocumentVersion, IngestionJob]:
    """Validate and store a new logical document with version one."""
    _knowledge_base, access = await get_accessible_knowledge_base(session, user, knowledge_base_id)
    _require_edit_access(access)
    staged = await stage_and_validate_upload(upload, settings)
    try:
        document = Document(
            id=uuid4(),
            knowledge_base_id=knowledge_base_id,
            title=_clean_title(title, staged.filename),
            created_by_id=user.id,
        )
        version, job = _build_version_and_job(
            document=document,
            version_number=1,
            staged=staged,
            user=user,
            settings=settings,
        )
        await _persist_source_and_rows(session, storage, staged, document, version, job)
        await session.refresh(document)
        await session.refresh(version)
        await session.refresh(job)
        return document, version, job
    finally:
        staged.cleanup()


async def add_document_version(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    user: User,
    document_id: UUID,
    upload: UploadFile,
) -> tuple[Document, DocumentVersion, IngestionJob]:
    """Append a source version while locking its logical document."""
    existing, access = await get_accessible_document(session, user, document_id)
    _require_edit_access(access)
    staged = await stage_and_validate_upload(upload, settings)
    try:
        result = await session.execute(
            select(Document).where(Document.id == existing.id).with_for_update()
        )
        document = result.scalar_one()
        duplicate = await session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.sha256 == staged.sha256,
            )
        )
        if duplicate is not None:
            raise AppError(
                code="duplicate_document_version",
                message="This exact content already exists as a version of the document",
                status_code=409,
            )
        latest_number = await session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        version, job = _build_version_and_job(
            document=document,
            version_number=(latest_number or 0) + 1,
            staged=staged,
            user=user,
            settings=settings,
        )
        await _persist_source_and_rows(session, storage, staged, document, version, job)
        await session.refresh(version)
        await session.refresh(job)
        return document, version, job
    finally:
        staged.cleanup()


async def get_parsed_preview(
    session: AsyncSession,
    user: User,
    version_id: UUID,
) -> ParsedDocument:
    """Return parsed text only to members allowed to edit source documents."""
    result = await session.execute(
        select(ParsedDocument, KnowledgeBaseMembership.access_level)
        .join(DocumentVersion, DocumentVersion.id == ParsedDocument.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == Document.knowledge_base_id,
        )
        .where(
            ParsedDocument.document_version_id == version_id,
            KnowledgeBaseMembership.user_id == user.id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            code="parsed_document_not_found",
            message="Parsed document content was not found",
            status_code=404,
        )
    _require_edit_access(row[1])
    return cast(ParsedDocument, row[0])


async def list_document_chunks(
    session: AsyncSession,
    user: User,
    version_id: UUID,
    *,
    offset: int,
    limit: int,
) -> tuple[list[DocumentChunk], int]:
    """List ordered chunks only after resolving document-level authorization."""
    access_row = await session.execute(
        select(DocumentVersion.id, KnowledgeBaseMembership.access_level)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == Document.knowledge_base_id,
        )
        .where(
            DocumentVersion.id == version_id,
            KnowledgeBaseMembership.user_id == user.id,
        )
    )
    row = access_row.one_or_none()
    if row is None:
        raise AppError(
            code="document_version_not_found",
            message="Document version was not found",
            status_code=404,
        )
    _require_edit_access(row[1])

    total = await session.scalar(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.document_version_id == version_id)
    )
    chunks = await session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
        .offset(offset)
        .limit(limit)
    )
    return list(chunks.all()), total or 0
