"""Run a versioned evaluation dataset against any compatible RAG client."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal, Protocol

from app.modules.evaluation.metrics import answer_scores, mean, percentile, retrieval_scores
from app.modules.evaluation.schemas import (
    AggregateScores,
    AnswerObservation,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationReport,
    GateCheck,
    QualityGate,
    SearchObservation,
)


class EvaluationClient(Protocol):
    def search(self, knowledge_base_id: str, question: str, top_k: int) -> SearchObservation: ...

    def answer(self, knowledge_base_id: str, question: str, top_k: int) -> AnswerObservation: ...


def run_evaluation(
    dataset: EvaluationDataset,
    client: EvaluationClient,
    knowledge_base_id: str,
    *,
    mode: Literal["retrieval", "full"] = "retrieval",
) -> EvaluationReport:
    """Execute cases sequentially so latency and provider load stay interpretable."""
    results: list[EvaluationCaseResult] = []
    retrieval_method: str | None = None
    embedding_model: str | None = None
    for case in dataset.cases:
        retrieval_started = perf_counter()
        search = client.search(knowledge_base_id, case.question, dataset.top_k)
        retrieval_latency_ms = (perf_counter() - retrieval_started) * 1000
        if retrieval_method is None:
            retrieval_method = search.retrieval_method
            embedding_model = search.embedding_model
        elif (
            retrieval_method != search.retrieval_method or embedding_model != search.embedding_model
        ):
            raise RuntimeError("retrieval configuration changed during one evaluation run")
        retrieval = (
            retrieval_scores(
                search.sources,
                case.relevant_sources,
                top_k=dataset.top_k,
            )
            if case.answerable
            else None
        )
        result = EvaluationCaseResult(
            id=case.id,
            question=case.question,
            answerable=case.answerable,
            relevant_sources=case.relevant_sources,
            retrieved_sources=search.sources,
            retrieval_latency_ms=round(retrieval_latency_ms, 3),
            retrieval=retrieval,
        )
        if mode == "full":
            answer_started = perf_counter()
            observation = client.answer(knowledge_base_id, case.question, dataset.top_k)
            answer_latency_ms = (perf_counter() - answer_started) * 1000
            result.answer_latency_ms = round(answer_latency_ms, 3)
            result.answer = observation.answer
            result.refused = observation.refused
            result.cited_sources = observation.cited_sources
            result.model = observation.model
            result.answer_scores = answer_scores(
                answer=observation.answer,
                refused=observation.refused,
                cited_sources=observation.cited_sources,
                answerable=case.answerable,
                relevant_sources=case.relevant_sources,
                required_answer_terms=case.required_answer_terms,
            )
        results.append(result)

    aggregate = _aggregate(results, mode=mode)
    quality_gate = _quality_gate(dataset, aggregate, mode=mode)
    return EvaluationReport(
        generated_at=datetime.now(UTC),
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        dataset_sha256=dataset_fingerprint(dataset),
        corpus=dataset.corpus,
        knowledge_base_id=knowledge_base_id,
        mode=mode,
        top_k=dataset.top_k,
        retrieval_method=_required_text(retrieval_method),
        embedding_model=_required_text(embedding_model),
        aggregate=aggregate,
        quality_gate=quality_gate,
        cases=results,
    )


def _aggregate(
    results: Sequence[EvaluationCaseResult],
    *,
    mode: Literal["retrieval", "full"],
) -> AggregateScores:
    retrieval = [result.retrieval for result in results if result.retrieval is not None]
    answer = [result.answer_scores for result in results if result.answer_scores is not None]
    answer_term_scores = [
        score.answer_term_coverage for score in answer if score.answer_term_coverage is not None
    ]
    retrieval_latencies = [result.retrieval_latency_ms for result in results]
    answer_latencies = [
        result.answer_latency_ms for result in results if result.answer_latency_ms is not None
    ]
    include_answers = mode == "full"
    return AggregateScores(
        evaluated_cases=len(results),
        answerable_cases=len(retrieval),
        hit_rate_at_k=mean([score.hit_at_k for score in retrieval]),
        mean_precision_at_k=mean([score.precision_at_k for score in retrieval]),
        mean_recall_at_k=mean([score.recall_at_k for score in retrieval]),
        mean_reciprocal_rank=mean([score.reciprocal_rank for score in retrieval]),
        mean_ndcg_at_k=mean([score.ndcg_at_k for score in retrieval]),
        retrieval_latency_p50_ms=percentile(retrieval_latencies, 0.50),
        retrieval_latency_p95_ms=percentile(retrieval_latencies, 0.95),
        citation_precision=mean([score.citation_precision for score in answer])
        if include_answers
        else None,
        citation_recall=mean([score.citation_recall for score in answer])
        if include_answers
        else None,
        answer_term_coverage=mean(answer_term_scores) if include_answers else None,
        refusal_accuracy=mean([score.refusal_correct for score in answer])
        if include_answers
        else None,
        grounded_answer_rate=mean([score.grounded_answer for score in answer])
        if include_answers
        else None,
        answer_latency_p50_ms=percentile(answer_latencies, 0.50) if include_answers else None,
        answer_latency_p95_ms=percentile(answer_latencies, 0.95) if include_answers else None,
    )


def _quality_gate(
    dataset: EvaluationDataset,
    aggregate: AggregateScores,
    *,
    mode: Literal["retrieval", "full"],
) -> QualityGate:
    thresholds = dataset.thresholds
    metric_pairs = [
        ("hit_rate_at_k", aggregate.hit_rate_at_k, thresholds.hit_rate_at_k),
        (
            "mean_reciprocal_rank",
            aggregate.mean_reciprocal_rank,
            thresholds.mean_reciprocal_rank,
        ),
        ("mean_ndcg_at_k", aggregate.mean_ndcg_at_k, thresholds.mean_ndcg_at_k),
    ]
    if mode == "full":
        metric_pairs.extend(
            [
                (
                    "citation_precision",
                    _required(aggregate.citation_precision),
                    thresholds.citation_precision,
                ),
                (
                    "citation_recall",
                    _required(aggregate.citation_recall),
                    thresholds.citation_recall,
                ),
                (
                    "answer_term_coverage",
                    _required(aggregate.answer_term_coverage),
                    thresholds.answer_term_coverage,
                ),
                (
                    "refusal_accuracy",
                    _required(aggregate.refusal_accuracy),
                    thresholds.refusal_accuracy,
                ),
                (
                    "grounded_answer_rate",
                    _required(aggregate.grounded_answer_rate),
                    thresholds.grounded_answer_rate,
                ),
            ]
        )
    checks = [
        GateCheck(metric=metric, actual=actual, required=required, passed=actual >= required)
        for metric, actual, required in metric_pairs
    ]
    return QualityGate(passed=all(check.passed for check in checks), checks=checks)


def _required(value: float | None) -> float:
    if value is None:
        raise RuntimeError("full evaluation aggregate is incomplete")
    return value


def _required_text(value: str | None) -> str:
    if value is None:
        raise RuntimeError("evaluation did not produce retrieval configuration")
    return value


def dataset_fingerprint(dataset: EvaluationDataset) -> str:
    """Hash canonical validated content so formatting does not change experiment identity."""
    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
