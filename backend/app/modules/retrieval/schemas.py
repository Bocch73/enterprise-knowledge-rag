"""Validated hybrid-search requests and transparent ranked responses."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.retrieval.fusion import FusedCandidate


class HybridSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("query must contain at least two visible characters")
        return cleaned


class HybridSearchResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_version_id: UUID
    version_number: int
    original_filename: str
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int
    fused_score: float
    vector_rank: int | None
    vector_distance: float | None
    keyword_rank: int | None
    keyword_score: float | None
    rerank_rank: int | None
    rerank_score: float | None

    @classmethod
    def from_fused(cls, item: FusedCandidate) -> "HybridSearchResultResponse":
        candidate = item.candidate
        return cls(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            document_title=candidate.document_title,
            document_version_id=candidate.document_version_id,
            version_number=candidate.version_number,
            original_filename=candidate.original_filename,
            chunk_index=candidate.chunk_index,
            content=candidate.content,
            start_offset=candidate.start_offset,
            end_offset=candidate.end_offset,
            fused_score=item.fused_score,
            vector_rank=item.vector_rank,
            vector_distance=item.vector_distance,
            keyword_rank=item.keyword_rank,
            keyword_score=item.keyword_score,
            rerank_rank=item.rerank_rank,
            rerank_score=item.rerank_score,
        )


class HybridSearchResponse(BaseModel):
    knowledge_base_id: UUID
    query: str
    retrieval_method: str = "hybrid_reciprocal_rank_fusion_with_rerank"
    embedding_model: str
    rerank_model: str
    evidence_sufficient: bool
    evidence_threshold: float
    top_rerank_score: float | None
    results: list[HybridSearchResultResponse]
