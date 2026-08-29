"""Public request and response models for document ingestion."""

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from app.modules.documents.models import Document, DocumentVersion, ParsedDocument
from app.modules.indexing.models import DocumentChunk
from app.modules.ingestion.models import IngestionJob

JobStatus = Literal["queued", "running", "completed", "failed"]
JobStage = Literal[
    "queued",
    "parsing",
    "chunking",
    "embedding",
    "indexing",
    "completed",
    "failed",
]


class DocumentResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    title: str
    created_by_id: UUID
    created_at: datetime

    @classmethod
    def from_model(cls, document: Document) -> "DocumentResponse":
        return cls(
            id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            title=document.title,
            created_by_id=document.created_by_id,
            created_at=document.created_at,
        )


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    uploaded_by_id: UUID
    created_at: datetime

    @classmethod
    def from_model(cls, version: DocumentVersion) -> "DocumentVersionResponse":
        return cls(
            id=version.id,
            document_id=version.document_id,
            version_number=version.version_number,
            original_filename=version.original_filename,
            media_type=version.media_type,
            size_bytes=version.size_bytes,
            sha256=version.sha256,
            uploaded_by_id=version.uploaded_by_id,
            created_at=version.created_at,
        )


class IngestionJobResponse(BaseModel):
    id: UUID
    document_version_id: UUID
    status: JobStatus
    stage: JobStage
    progress: int
    attempt_count: int
    max_attempts: int
    retryable: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_model(cls, job: IngestionJob) -> "IngestionJobResponse":
        return cls(
            id=job.id,
            document_version_id=job.document_version_id,
            status=cast(JobStatus, job.status),
            stage=cast(JobStage, job.stage),
            progress=job.progress,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            retryable=job.retryable,
            error_code=job.error_code,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    version: DocumentVersionResponse
    ingestion_job: IngestionJobResponse


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    versions: list[DocumentVersionResponse]


class ParsedPreviewResponse(BaseModel):
    document_version_id: UUID
    content: str
    offset: int
    returned_characters: int
    total_characters: int
    page_count: int | None
    parser_name: str
    parser_version: str

    @classmethod
    def from_model(
        cls,
        parsed: ParsedDocument,
        *,
        offset: int = 0,
        limit: int = 2000,
    ) -> "ParsedPreviewResponse":
        content = parsed.content[offset : offset + limit]
        return cls(
            document_version_id=parsed.document_version_id,
            content=content,
            offset=offset,
            returned_characters=len(content),
            total_characters=parsed.character_count,
            page_count=parsed.page_count,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
        )


class DocumentChunkResponse(BaseModel):
    id: UUID
    document_version_id: UUID
    chunk_index: int
    content: str
    character_count: int
    start_offset: int
    end_offset: int
    content_sha256: str
    embedding_model: str
    embedding_dimensions: int

    @classmethod
    def from_model(cls, chunk: DocumentChunk) -> "DocumentChunkResponse":
        return cls(
            id=chunk.id,
            document_version_id=chunk.document_version_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            character_count=chunk.character_count,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            content_sha256=chunk.content_sha256,
            embedding_model=chunk.embedding_model,
            embedding_dimensions=chunk.embedding_dimensions,
        )


class DocumentChunkPageResponse(BaseModel):
    document_version_id: UUID
    items: list[DocumentChunkResponse]
    offset: int
    limit: int
    total: int
