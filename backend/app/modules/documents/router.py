"""Authenticated document upload, version, listing, and preview endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status

from app.core.config import Settings
from app.infrastructure.storage import ObjectStorage
from app.modules.documents.schemas import (
    DocumentChunkPageResponse,
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    IngestionJobResponse,
    ParsedPreviewResponse,
)
from app.modules.documents.service import (
    add_document_version,
    create_document,
    get_document_detail,
    get_parsed_preview,
    list_document_chunks,
    list_documents,
)
from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency

knowledge_base_router = APIRouter()
document_router = APIRouter()


@knowledge_base_router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
) -> DocumentUploadResponse:
    settings: Settings = request.app.state.settings
    storage: ObjectStorage = request.app.state.object_storage
    document, version, job = await create_document(
        session,
        storage,
        settings,
        current_user,
        knowledge_base_id,
        file,
        title,
    )
    request.state.audit_resource_id = document.id
    return DocumentUploadResponse(
        document=DocumentResponse.from_model(document),
        version=DocumentVersionResponse.from_model(version),
        ingestion_job=IngestionJobResponse.from_model(job),
    )


@knowledge_base_router.get(
    "/{knowledge_base_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_knowledge_base_documents(
    knowledge_base_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> list[DocumentResponse]:
    documents = await list_documents(session, current_user, knowledge_base_id)
    return [DocumentResponse.from_model(document) for document in documents]


@document_router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DocumentDetailResponse:
    document = await get_document_detail(session, current_user, document_id)
    return DocumentDetailResponse(
        document=DocumentResponse.from_model(document),
        versions=[DocumentVersionResponse.from_model(version) for version in document.versions],
    )


@document_router.post(
    "/{document_id}/versions",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_new_version(
    document_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> DocumentUploadResponse:
    settings: Settings = request.app.state.settings
    storage: ObjectStorage = request.app.state.object_storage
    document, version, job = await add_document_version(
        session,
        storage,
        settings,
        current_user,
        document_id,
        file,
    )
    request.state.audit_resource_id = document.id
    return DocumentUploadResponse(
        document=DocumentResponse.from_model(document),
        version=DocumentVersionResponse.from_model(version),
        ingestion_job=IngestionJobResponse.from_model(job),
    )


@document_router.get(
    "/versions/{version_id}/preview",
    response_model=ParsedPreviewResponse,
)
async def preview_parsed_document(
    version_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=2000, ge=1, le=10_000),
) -> ParsedPreviewResponse:
    parsed = await get_parsed_preview(session, current_user, version_id)
    return ParsedPreviewResponse.from_model(parsed, offset=offset, limit=limit)


@document_router.get(
    "/versions/{version_id}/chunks",
    response_model=DocumentChunkPageResponse,
)
async def get_document_chunks(
    version_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> DocumentChunkPageResponse:
    chunks, total = await list_document_chunks(
        session,
        current_user,
        version_id,
        offset=offset,
        limit=limit,
    )
    return DocumentChunkPageResponse(
        document_version_id=version_id,
        items=[DocumentChunkResponse.from_model(chunk) for chunk in chunks],
        offset=offset,
        limit=limit,
        total=total,
    )
