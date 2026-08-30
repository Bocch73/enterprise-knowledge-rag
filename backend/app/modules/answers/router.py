"""Authenticated grounded-answer endpoint scoped to one knowledge base."""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.modules.answers.schemas import GroundedAnswerRequest, GroundedAnswerResponse
from app.modules.answers.service import create_grounded_answer
from app.modules.generation.providers import GenerationProvider
from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency
from app.modules.indexing.providers import EmbeddingProvider
from app.modules.operations.metrics import OperationsMetrics
from app.modules.retrieval.providers import RerankProvider

router = APIRouter()


@router.post("/{knowledge_base_id}/answers", response_model=GroundedAnswerResponse, status_code=201)
async def answer_question(
    knowledge_base_id: UUID,
    data: GroundedAnswerRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> GroundedAnswerResponse:
    return await _create_answer(knowledge_base_id, data, current_user, session, request)


@router.post("/{knowledge_base_id}/answers/stream", response_class=StreamingResponse)
async def stream_answer(
    knowledge_base_id: UUID,
    data: GroundedAnswerRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> StreamingResponse:
    answer = await _create_answer(knowledge_base_id, data, current_user, session, request)
    return StreamingResponse(
        _answer_events(answer),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _create_answer(
    knowledge_base_id: UUID,
    data: GroundedAnswerRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> GroundedAnswerResponse:
    settings: Settings = request.app.state.settings
    embedding_provider: EmbeddingProvider = request.app.state.embedding_provider
    rerank_provider: RerankProvider = request.app.state.rerank_provider
    generation_provider: GenerationProvider = request.app.state.generation_provider
    operations_metrics: OperationsMetrics = request.app.state.operations_metrics
    return await create_grounded_answer(
        session,
        current_user,
        knowledge_base_id,
        data.question,
        top_k=data.top_k,
        candidate_limit=settings.retrieval_candidate_limit,
        rank_constant=settings.retrieval_rrf_k,
        evidence_min_score=settings.retrieval_evidence_min_score,
        context_max_characters=settings.answer_context_max_characters,
        embedding_provider=embedding_provider,
        rerank_provider=rerank_provider,
        generation_provider=generation_provider,
        operations_metrics=operations_metrics,
    )


async def _answer_events(answer: GroundedAnswerResponse) -> AsyncIterator[str]:
    for start in range(0, len(answer.answer), 24):
        yield _server_sent_event("answer_delta", {"text": answer.answer[start : start + 24]})
    yield _server_sent_event(
        "citations",
        {"items": [citation.model_dump(mode="json") for citation in answer.citations]},
    )
    yield _server_sent_event(
        "done",
        {
            "answer_id": str(answer.id),
            "model": answer.model,
            "refused": answer.refused,
        },
    )


def _server_sent_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
