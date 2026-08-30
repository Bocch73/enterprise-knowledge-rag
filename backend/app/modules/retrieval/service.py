"""Authorized hybrid retrieval, semantic reranking, and evidence gating."""

from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.core.errors import AppError
from app.modules.documents.models import Document, DocumentVersion
from app.modules.identity.models import User
from app.modules.indexing.models import DocumentChunk
from app.modules.indexing.providers import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProvider,
    EmbeddingProviderError,
)
from app.modules.ingestion.models import IngestionJob
from app.modules.knowledge_bases.service import get_accessible_knowledge_base
from app.modules.retrieval.fusion import (
    FusedCandidate,
    RankedCandidate,
    RetrievalCandidate,
    reciprocal_rank_fusion,
)
from app.modules.retrieval.providers import RerankProvider, RerankProviderError


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    candidates: list[FusedCandidate]
    rerank_model: str
    rerank_request_id: str | None
    top_rerank_score: float | None
    evidence_sufficient: bool


def _latest_completed_versions() -> Subquery:
    return (
        select(
            DocumentVersion.id.label("version_id"),
            func.row_number()
            .over(
                partition_by=DocumentVersion.document_id,
                order_by=(DocumentVersion.version_number.desc(), DocumentVersion.id.desc()),
            )
            .label("version_rank"),
        )
        .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
        .where(IngestionJob.status == "completed")
        .subquery("latest_completed_versions")
    )


def _candidate(
    chunk: DocumentChunk,
    document: Document,
    version: DocumentVersion,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk.id,
        document_id=document.id,
        document_title=document.title,
        document_version_id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
    )


async def _vector_candidates(
    session: AsyncSession,
    knowledge_base_id: UUID,
    query_embedding: list[float],
    provider: EmbeddingProvider,
    candidate_limit: int,
) -> list[RankedCandidate]:
    latest_versions = _latest_completed_versions()
    vector_distance = DocumentChunk.embedding.cosine_distance(query_embedding).label(
        "vector_distance"
    )
    rows = await session.execute(
        select(DocumentChunk, Document, DocumentVersion, vector_distance)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(latest_versions, latest_versions.c.version_id == DocumentVersion.id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            latest_versions.c.version_rank == 1,
            DocumentChunk.embedding_model == provider.name,
        )
        .order_by(vector_distance, DocumentChunk.id)
        .limit(candidate_limit)
    )
    return [
        RankedCandidate(
            candidate=_candidate(chunk, document, version),
            raw_score=float(distance),
        )
        for chunk, document, version, distance in rows.all()
    ]


async def _keyword_candidates(
    session: AsyncSession,
    knowledge_base_id: UUID,
    query: str,
    candidate_limit: int,
) -> list[RankedCandidate]:
    latest_versions = _latest_completed_versions()
    search_configuration: ColumnElement[object] = literal_column("'simple'::regconfig")
    text_query = func.websearch_to_tsquery(search_configuration, query)
    keyword_score = func.ts_rank_cd(DocumentChunk.search_vector, text_query).label("keyword_score")
    rows = await session.execute(
        select(DocumentChunk, Document, DocumentVersion, keyword_score)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(latest_versions, latest_versions.c.version_id == DocumentVersion.id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            latest_versions.c.version_rank == 1,
            DocumentChunk.search_vector.bool_op("@@")(text_query),
        )
        .order_by(keyword_score.desc(), DocumentChunk.id)
        .limit(candidate_limit)
    )
    return [
        RankedCandidate(
            candidate=_candidate(chunk, document, version),
            raw_score=float(score),
        )
        for chunk, document, version, score in rows.all()
    ]


async def hybrid_search(
    session: AsyncSession,
    user: User,
    knowledge_base_id: UUID,
    query: str,
    *,
    top_k: int,
    candidate_limit: int,
    rank_constant: int,
    embedding_provider: EmbeddingProvider,
    rerank_provider: RerankProvider,
    evidence_min_score: float,
) -> RetrievalOutcome:
    """Search only one authorized knowledge base and its latest completed versions."""
    await get_accessible_knowledge_base(session, user, knowledge_base_id)
    try:
        query_embedding = await embedding_provider.embed_query(query)
    except EmbeddingProviderError as exception:
        unavailable_codes = {
            "embedding_authentication_failed",
            "embedding_provider_unavailable",
            "embedding_rate_limited",
        }
        raise AppError(
            code=exception.code,
            message=exception.message,
            status_code=503 if exception.code in unavailable_codes else 502,
        ) from exception
    if (
        embedding_provider.dimensions != EMBEDDING_DIMENSIONS
        or len(query_embedding) != EMBEDDING_DIMENSIONS
    ):
        raise RuntimeError("embedding provider returned an invalid query vector")

    vector_candidates = await _vector_candidates(
        session,
        knowledge_base_id,
        query_embedding,
        embedding_provider,
        candidate_limit,
    )
    keyword_candidates = await _keyword_candidates(
        session,
        knowledge_base_id,
        query,
        candidate_limit,
    )
    fused = reciprocal_rank_fusion(
        vector_candidates,
        keyword_candidates,
        rank_constant=rank_constant,
        limit=candidate_limit,
    )
    try:
        reranked = await rerank_provider.rerank(
            query=query,
            documents=[item.candidate.content for item in fused],
            top_n=top_k,
        )
    except RerankProviderError as exception:
        unavailable_codes = {
            "rerank_authentication_failed",
            "rerank_circuit_open",
            "rerank_provider_unavailable",
            "rerank_rate_limited",
            "rerank_timeout",
        }
        raise AppError(
            code=exception.code,
            message=exception.message,
            status_code=503 if exception.code in unavailable_codes else 502,
        ) from exception

    ordered = [
        replace(
            fused[item.index],
            rerank_rank=rank,
            rerank_score=item.relevance_score,
        )
        for rank, item in enumerate(reranked.items, start=1)
    ]
    top_score = ordered[0].rerank_score if ordered else None
    evidence_sufficient = top_score is not None and top_score >= evidence_min_score
    accepted = (
        [
            item
            for item in ordered
            if item.rerank_score is not None and item.rerank_score >= evidence_min_score
        ]
        if evidence_sufficient
        else []
    )
    return RetrievalOutcome(
        candidates=accepted,
        rerank_model=reranked.model,
        rerank_request_id=reranked.request_id,
        top_rerank_score=top_score,
        evidence_sufficient=evidence_sufficient,
    )
