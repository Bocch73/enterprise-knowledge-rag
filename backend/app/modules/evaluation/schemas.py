"""Strict schemas for versioned evaluation datasets and reports."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Reject misspelled fields instead of silently changing an experiment."""

    model_config = ConfigDict(extra="forbid")


class EvaluationThresholds(StrictModel):
    """Minimum acceptable aggregate scores for the quality gate."""

    hit_rate_at_k: float = Field(default=0.80, ge=0.0, le=1.0)
    mean_reciprocal_rank: float = Field(default=0.70, ge=0.0, le=1.0)
    mean_ndcg_at_k: float = Field(default=0.70, ge=0.0, le=1.0)
    citation_precision: float = Field(default=0.90, ge=0.0, le=1.0)
    citation_recall: float = Field(default=0.80, ge=0.0, le=1.0)
    answer_term_coverage: float = Field(default=0.75, ge=0.0, le=1.0)
    refusal_accuracy: float = Field(default=0.90, ge=0.0, le=1.0)
    grounded_answer_rate: float = Field(default=0.90, ge=0.0, le=1.0)


class EvaluationDocument(StrictModel):
    """One versioned corpus file and its integrity fingerprint."""

    filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationCase(StrictModel):
    """One human-reviewed question and its expected evidence."""

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    question: str = Field(min_length=2, max_length=500)
    answerable: bool
    relevant_sources: list[str] = Field(default_factory=list, max_length=20)
    required_answer_terms: list[list[str]] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("relevant_sources")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        cleaned = [source.strip() for source in value]
        if any(not source for source in cleaned):
            raise ValueError("relevant source names must not be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("relevant source names must be unique")
        return cleaned

    @field_validator("required_answer_terms")
    @classmethod
    def valid_term_groups(cls, value: list[list[str]]) -> list[list[str]]:
        cleaned = [[term.strip() for term in group] for group in value]
        if any(not group or any(not term for term in group) for group in cleaned):
            raise ValueError("every required term group needs at least one non-blank alternative")
        return cleaned

    @model_validator(mode="after")
    def validate_answerability(self) -> Self:
        if self.answerable and not self.relevant_sources:
            raise ValueError("answerable cases require at least one relevant source")
        if not self.answerable and (self.relevant_sources or self.required_answer_terms):
            raise ValueError("unanswerable cases cannot declare evidence or answer terms")
        return self


class EvaluationDataset(StrictModel):
    """A reviewable, versioned collection of evaluation cases."""

    name: str = Field(min_length=2, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    corpus: list[EvaluationDocument] = Field(min_length=1, max_length=1000)
    thresholds: EvaluationThresholds = Field(default_factory=EvaluationThresholds)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_case_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation case ids must be unique")
        filenames = [document.filename for document in self.corpus]
        if len(filenames) != len(set(filenames)):
            raise ValueError("evaluation corpus filenames must be unique")
        corpus_filenames = set(filenames)
        missing = {
            source
            for case in self.cases
            for source in case.relevant_sources
            if source not in corpus_filenames
        }
        if missing:
            raise ValueError(f"relevant sources are missing from corpus: {sorted(missing)}")
        return self


class AnswerObservation(StrictModel):
    """The answer fields needed by deterministic metrics."""

    answer: str
    refused: bool
    cited_sources: list[str]
    model: str


class SearchObservation(StrictModel):
    """Ranked source identifiers plus the configuration that produced them."""

    sources: list[str]
    retrieval_method: str
    embedding_model: str


class RetrievalScores(StrictModel):
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    hit_at_k: float


class AnswerScores(StrictModel):
    citation_precision: float
    citation_recall: float
    answer_term_coverage: float | None
    refusal_correct: float
    grounded_answer: float


class EvaluationCaseResult(StrictModel):
    id: str
    question: str
    answerable: bool
    relevant_sources: list[str]
    retrieved_sources: list[str]
    retrieval_latency_ms: float
    retrieval: RetrievalScores | None
    answer_latency_ms: float | None = None
    answer: str | None = None
    refused: bool | None = None
    cited_sources: list[str] | None = None
    model: str | None = None
    answer_scores: AnswerScores | None = None


class AggregateScores(StrictModel):
    evaluated_cases: int
    answerable_cases: int
    hit_rate_at_k: float
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    retrieval_latency_p50_ms: float
    retrieval_latency_p95_ms: float
    citation_precision: float | None = None
    citation_recall: float | None = None
    answer_term_coverage: float | None = None
    refusal_accuracy: float | None = None
    grounded_answer_rate: float | None = None
    answer_latency_p50_ms: float | None = None
    answer_latency_p95_ms: float | None = None


class GateCheck(StrictModel):
    metric: str
    actual: float
    required: float
    passed: bool


class QualityGate(StrictModel):
    passed: bool
    checks: list[GateCheck]


class EvaluationReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    dataset_name: str
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus: list[EvaluationDocument]
    knowledge_base_id: str
    mode: Literal["retrieval", "full"]
    top_k: int
    retrieval_method: str
    embedding_model: str
    aggregate: AggregateScores
    quality_gate: QualityGate
    cases: list[EvaluationCaseResult]
