"""Transparent deterministic metrics for ranked retrieval and cited answers."""

import math
from collections.abc import Sequence

from app.modules.evaluation.schemas import AnswerScores, RetrievalScores


def retrieval_scores(
    retrieved_sources: Sequence[str],
    relevant_sources: Sequence[str],
    *,
    top_k: int,
) -> RetrievalScores:
    """Score one answerable query using source identifiers and result order."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    relevant = set(relevant_sources)
    if not relevant:
        raise ValueError("retrieval metrics require at least one relevant source")

    # Search returns chunks, while this baseline labels source documents. Keep only the
    # first occurrence of each document so one document cannot receive relevance twice.
    ranked = list(dict.fromkeys(retrieved_sources))[:top_k]
    relevance = [1 if source in relevant else 0 for source in ranked]
    relevant_retrieved = len(set(ranked) & relevant)
    first_relevant_rank = next(
        (rank for rank, is_relevant in enumerate(relevance, start=1) if is_relevant),
        None,
    )
    ideal_relevant_count = min(len(relevant), top_k)
    discounted_gain = sum(
        is_relevant / math.log2(rank + 1) for rank, is_relevant in enumerate(relevance, start=1)
    )
    ideal_gain = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_relevant_count + 1))

    return RetrievalScores(
        precision_at_k=relevant_retrieved / len(ranked) if ranked else 0.0,
        recall_at_k=relevant_retrieved / len(relevant),
        reciprocal_rank=1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0,
        ndcg_at_k=discounted_gain / ideal_gain if ideal_gain else 0.0,
        hit_at_k=1.0 if relevant_retrieved else 0.0,
    )


def answer_scores(
    *,
    answer: str,
    refused: bool,
    cited_sources: Sequence[str],
    answerable: bool,
    relevant_sources: Sequence[str],
    required_answer_terms: Sequence[Sequence[str]],
) -> AnswerScores:
    """Score citations, required facts, and correct refusal behavior."""
    relevant = set(relevant_sources)
    cited = set(cited_sources)
    if answerable:
        citation_precision = len(cited & relevant) / len(cited) if cited else 0.0
        citation_recall = len(cited & relevant) / len(relevant) if relevant else 0.0
        normalized_answer = answer.casefold()
        covered = sum(
            any(term.casefold() in normalized_answer for term in alternatives)
            for alternatives in required_answer_terms
        )
        term_coverage = covered / len(required_answer_terms) if required_answer_terms else 1.0
        grounded = 1.0 if not refused and bool(cited) else 0.0
    else:
        citation_precision = 1.0 if not cited else 0.0
        citation_recall = 1.0 if not cited else 0.0
        term_coverage = None
        grounded = 1.0 if refused and not cited else 0.0

    return AnswerScores(
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        answer_term_coverage=term_coverage,
        refusal_correct=1.0 if refused == (not answerable) else 0.0,
        grounded_answer=grounded,
    )


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """Return a nearest-rank percentile without a numerical dependency."""
    if not values:
        return 0.0
    if not 0.0 <= percentile_value <= 1.0:
        raise ValueError("percentile must be between zero and one")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile_value * len(ordered)))
    return ordered[rank - 1]
