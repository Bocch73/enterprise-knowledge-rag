"""Score-independent reciprocal rank fusion for retrieval candidates."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """Stable citation metadata shared by both retrieval routes."""

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


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One route's already ordered candidate and route-specific raw score."""

    candidate: RetrievalCandidate
    raw_score: float


@dataclass(frozen=True, slots=True)
class FusedCandidate:
    """One merged result with transparent route ranks and scores."""

    candidate: RetrievalCandidate
    fused_score: float
    vector_rank: int | None
    vector_distance: float | None
    keyword_rank: int | None
    keyword_score: float | None


@dataclass(slots=True)
class _Accumulator:
    candidate: RetrievalCandidate
    fused_score: float = 0.0
    vector_rank: int | None = None
    vector_distance: float | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None


def reciprocal_rank_fusion(
    vector_candidates: list[RankedCandidate],
    keyword_candidates: list[RankedCandidate],
    *,
    rank_constant: int,
    limit: int,
) -> list[FusedCandidate]:
    """Merge ordered lists without assuming their raw scores share a scale."""
    if rank_constant <= 0:
        raise ValueError("rank constant must be positive")
    if limit <= 0:
        raise ValueError("result limit must be positive")

    accumulators: dict[UUID, _Accumulator] = {}
    for rank, item in enumerate(vector_candidates, start=1):
        accumulator = accumulators.setdefault(
            item.candidate.chunk_id,
            _Accumulator(candidate=item.candidate),
        )
        accumulator.fused_score += 1.0 / (rank_constant + rank)
        accumulator.vector_rank = rank
        accumulator.vector_distance = item.raw_score

    for rank, item in enumerate(keyword_candidates, start=1):
        accumulator = accumulators.setdefault(
            item.candidate.chunk_id,
            _Accumulator(candidate=item.candidate),
        )
        accumulator.fused_score += 1.0 / (rank_constant + rank)
        accumulator.keyword_rank = rank
        accumulator.keyword_score = item.raw_score

    ordered = sorted(
        accumulators.values(),
        key=lambda item: (
            -item.fused_score,
            min(item.vector_rank or 1_000_000, item.keyword_rank or 1_000_000),
            str(item.candidate.chunk_id),
        ),
    )
    return [
        FusedCandidate(
            candidate=item.candidate,
            fused_score=item.fused_score,
            vector_rank=item.vector_rank,
            vector_distance=item.vector_distance,
            keyword_rank=item.keyword_rank,
            keyword_score=item.keyword_score,
        )
        for item in ordered[:limit]
    ]
