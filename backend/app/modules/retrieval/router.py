"""Authenticated hybrid-search endpoint scoped to one knowledge base."""

from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency
from app.modules.indexing.providers import EmbeddingProvider
from app.modules.operations.metrics import OperationsMetrics
from app.modules.retrieval.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResultResponse,
)
from app.modules.retrieval.service import hybrid_search

router = APIRouter()


@router.post("/{knowledge_base_id}/search", response_model=HybridSearchResponse)
async def search_knowledge_base(
    knowledge_base_id: UUID,
    data: HybridSearchRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> HybridSearchResponse:
    settings: Settings = request.app.state.settings
    embedding_provider: EmbeddingProvider = request.app.state.embedding_provider
    operations_metrics: OperationsMetrics = request.app.state.operations_metrics
    started = perf_counter()
    try:
        results = await hybrid_search(
            session,
            current_user,
            knowledge_base_id,
            data.query,
            top_k=data.top_k,
            candidate_limit=settings.retrieval_candidate_limit,
            rank_constant=settings.retrieval_rrf_k,
            embedding_provider=embedding_provider,
        )
    finally:
        operations_metrics.observe_retrieval(perf_counter() - started)
    return HybridSearchResponse(
        knowledge_base_id=knowledge_base_id,
        query=data.query,
        embedding_model=embedding_provider.name,
        results=[HybridSearchResultResponse.from_fused(item) for item in results],
    )
