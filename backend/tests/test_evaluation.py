"""Dataset validation, quality metrics, runner, and HTTP adapter tests."""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

import httpx
import pytest
from pydantic import ValidationError

from app.cli import evaluate_rag as evaluation_cli
from app.cli.evaluate_rag import DEFAULT_DATASET, load_dataset
from app.cli.run_reference_evaluation import ReferenceGenerationProvider, _require_success
from app.modules.evaluation.client import EvaluationApiClient, EvaluationApiError
from app.modules.evaluation.metrics import answer_scores, percentile, retrieval_scores
from app.modules.evaluation.runner import run_evaluation
from app.modules.evaluation.schemas import (
    AnswerObservation,
    EvaluationCase,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationThresholds,
    SearchObservation,
)


def evaluation_dataset() -> EvaluationDataset:
    return EvaluationDataset(
        name="Test baseline",
        version="1.0.0",
        description="A small deterministic test dataset.",
        top_k=3,
        corpus=[EvaluationDocument(filename="policy-a.md", sha256="a" * 64)],
        thresholds=EvaluationThresholds(
            hit_rate_at_k=1.0,
            mean_reciprocal_rank=1.0,
            mean_ndcg_at_k=1.0,
            citation_precision=1.0,
            citation_recall=1.0,
            answer_term_coverage=1.0,
            refusal_accuracy=1.0,
            grounded_answer_rate=1.0,
        ),
        cases=[
            EvaluationCase(
                id="answerable",
                question="What is policy A?",
                answerable=True,
                relevant_sources=["policy-a.md"],
                required_answer_terms=[["90", "ninety"]],
            ),
            EvaluationCase(
                id="unanswerable",
                question="What is the lunch menu?",
                answerable=False,
            ),
        ],
    )


def test_checked_in_dataset_is_valid_and_versioned() -> None:
    dataset = load_dataset(DEFAULT_DATASET)

    assert dataset.version == "2.0.0"
    assert len(dataset.cases) == 135
    assert sum(case.answerable for case in dataset.cases) == 108
    assert any(not case.answerable for case in dataset.cases)


def test_dataset_rejects_duplicate_ids_and_invalid_unanswerable_labels() -> None:
    case = EvaluationCase(
        id="duplicate",
        question="Valid question?",
        answerable=True,
        relevant_sources=["policy.md"],
    )
    with pytest.raises(ValidationError, match="case ids must be unique"):
        EvaluationDataset(
            name="Invalid dataset",
            version="1",
            description="Duplicate ids are unsafe.",
            corpus=[EvaluationDocument(filename="policy.md", sha256="b" * 64)],
            cases=[case, case],
        )
    with pytest.raises(ValidationError, match="cannot declare evidence"):
        EvaluationCase(
            id="invalid-refusal",
            question="Unknown question?",
            answerable=False,
            relevant_sources=["not-allowed.md"],
        )


def test_retrieval_scores_reward_early_relevant_results_and_deduplicate_sources() -> None:
    scores = retrieval_scores(
        ["noise.md", "policy.md", "policy.md"],
        ["policy.md"],
        top_k=3,
    )

    assert scores.precision_at_k == pytest.approx(0.5)
    assert scores.recall_at_k == 1.0
    assert scores.reciprocal_rank == 0.5
    assert scores.ndcg_at_k == pytest.approx(1 / 1.5849625007)
    assert scores.hit_at_k == 1.0


def test_retrieval_scores_reject_missing_labels_and_invalid_k() -> None:
    with pytest.raises(ValueError, match="relevant source"):
        retrieval_scores(["policy.md"], [], top_k=3)
    with pytest.raises(ValueError, match="positive"):
        retrieval_scores(["policy.md"], ["policy.md"], top_k=0)


def test_answer_scores_cover_citations_terms_grounding_and_refusal() -> None:
    supported = answer_scores(
        answer="Rotate every ninety days.",
        refused=False,
        cited_sources=["security.md", "noise.md"],
        answerable=True,
        relevant_sources=["security.md"],
        required_answer_terms=[["90", "ninety"], ["rotate"]],
    )
    refusal = answer_scores(
        answer="Cannot answer.",
        refused=True,
        cited_sources=[],
        answerable=False,
        relevant_sources=[],
        required_answer_terms=[],
    )

    assert supported.citation_precision == 0.5
    assert supported.citation_recall == 1.0
    assert supported.answer_term_coverage == 1.0
    assert supported.refusal_correct == 1.0
    assert supported.grounded_answer == 1.0
    assert refusal.citation_precision == 1.0
    assert refusal.answer_term_coverage is None
    assert refusal.refusal_correct == 1.0


def test_nearest_rank_percentile_handles_edges() -> None:
    assert percentile([], 0.95) == 0.0
    assert percentile([30.0, 10.0, 20.0], 0.50) == 20.0
    assert percentile([30.0, 10.0, 20.0], 0.95) == 30.0
    with pytest.raises(ValueError, match="between zero and one"):
        percentile([1.0], 1.1)


@dataclass
class FakeEvaluationClient:
    searches: dict[str, list[str]] = field(
        default_factory=lambda: {
            "What is policy A?": ["policy-a.md", "noise.md"],
            "What is the lunch menu?": ["noise.md"],
        }
    )

    def search(self, knowledge_base_id: str, question: str, top_k: int) -> SearchObservation:
        assert knowledge_base_id == "kb-test"
        assert top_k == 3
        return SearchObservation(
            sources=self.searches[question],
            retrieval_method="test-hybrid",
            embedding_model="test-embedding",
            rerank_model="test-rerank",
            evidence_sufficient=question == "What is policy A?",
            evidence_threshold=0.5,
            top_rerank_score=0.95 if question == "What is policy A?" else 0.1,
        )

    def answer(self, knowledge_base_id: str, question: str, top_k: int) -> AnswerObservation:
        if question == "What is policy A?":
            return AnswerObservation(
                answer="The interval is 90 days. [S1]",
                refused=False,
                cited_sources=["policy-a.md"],
                model="fake-v1",
            )
        return AnswerObservation(
            answer="Cannot answer.",
            refused=True,
            cited_sources=[],
            model="fake-v1",
        )


class FakeEvaluationApiContext(FakeEvaluationClient):
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        super().__init__()

    def __enter__(self) -> "FakeEvaluationApiContext":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback

    def login(self, email: str, password: str) -> None:
        del email, password


def test_runner_builds_full_auditable_report_and_passes_gate() -> None:
    report = run_evaluation(
        evaluation_dataset(),
        FakeEvaluationClient(),
        "kb-test",
        mode="full",
    )

    assert report.aggregate.evaluated_cases == 2
    assert report.aggregate.answerable_cases == 1
    assert report.aggregate.hit_rate_at_k == 1.0
    assert report.aggregate.answer_term_coverage == 1.0
    assert report.aggregate.refusal_accuracy == 1.0
    assert report.quality_gate.passed is True
    assert len(report.dataset_sha256) == 64
    assert report.retrieval_method == "test-hybrid"
    assert report.embedding_model == "test-embedding"
    assert len(report.quality_gate.checks) == 10
    assert report.aggregate.evidence_sufficiency_accuracy == 1.0
    assert report.rerank_model == "test-rerank"
    assert report.cases[0].retrieved_sources == ["policy-a.md", "noise.md"]


def test_runner_retrieval_mode_omits_answer_calls_and_answer_gates() -> None:
    report = run_evaluation(
        evaluation_dataset(),
        FakeEvaluationClient(),
        "kb-test",
        mode="retrieval",
    )

    assert report.aggregate.citation_precision is None
    assert report.cases[0].answer is None
    assert [check.metric for check in report.quality_gate.checks] == [
        "hit_rate_at_k",
        "mean_reciprocal_rank",
        "mean_ndcg_at_k",
        "evidence_sufficiency_accuracy",
        "unanswerable_rejection_rate",
    ]


def test_runner_reports_a_failed_quality_gate() -> None:
    client = FakeEvaluationClient()
    client.searches["What is policy A?"] = ["noise.md"]

    report = run_evaluation(evaluation_dataset(), client, "kb-test")

    assert report.quality_gate.passed is False
    checks = {check.metric: check for check in report.quality_gate.checks}
    assert checks["hit_rate_at_k"].passed is False
    assert checks["mean_reciprocal_rank"].passed is False
    assert checks["mean_ndcg_at_k"].passed is False
    assert checks["evidence_sufficiency_accuracy"].passed is True


def test_cli_runs_full_evaluation_and_writes_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "report.json"
    dataset_path.write_text(evaluation_dataset().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(evaluation_cli, "EvaluationApiClient", FakeEvaluationApiContext)
    monkeypatch.setenv("RAG_EVALUATION_TOKEN", "opaque-test-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate-rag",
            "--dataset",
            str(dataset_path),
            "--knowledge-base-id",
            "kb-test",
            "--mode",
            "full",
            "--output",
            str(output_path),
        ],
    )

    exit_code = evaluation_cli.main()

    assert exit_code == 0
    assert '"quality_gate"' in output_path.read_text(encoding="utf-8")


def test_cli_validate_only_and_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(evaluation_dataset().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate-rag", "--dataset", str(dataset_path), "--validate-only"],
    )
    assert evaluation_cli.main() == 0

    for variable in (
        "RAG_EVALUATION_TOKEN",
        "RAG_EVALUATION_EMAIL",
        "RAG_EVALUATION_PASSWORD",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate-rag",
            "--dataset",
            str(dataset_path),
            "--knowledge-base-id",
            "kb-test",
        ],
    )
    assert evaluation_cli.main() == 2


def test_reference_provider_and_status_guard_are_deterministic() -> None:
    provider = ReferenceGenerationProvider()

    known = asyncio.run(
        provider.generate(
            system_prompt="ignored",
            user_prompt="<sources>fixture</sources>\n问题：全职员工每年有多少天带薪年假？",  # noqa: RUF001
        )
    )
    unknown = asyncio.run(
        provider.generate(
            system_prompt="ignored",
            user_prompt="<sources>fixture</sources>\n问题：没有标注的问题？",  # noqa: RUF001
        )
    )

    assert known.model == "reference-deterministic-v1"
    assert "15" in known.content
    assert unknown.content == "根据当前知识库内容，我无法回答这个问题。"  # noqa: RUF001
    _require_success(204, "")
    with pytest.raises(RuntimeError, match="status 500"):
        _require_success(500, "safe error")


def test_http_client_logs_in_and_normalizes_source_filenames() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"access_token": "opaque-test-token"})
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "retrieval_method": "hybrid-test",
                    "embedding_model": "embedding-test",
                    "results": [
                        {"original_filename": "policy.md"},
                        {"original_filename": "policy.md"},
                    ],
                },
            )
        return httpx.Response(
            201,
            json={
                "answer": "Supported. [S1]",
                "refused": False,
                "model": "model-v1",
                "citations": [{"original_filename": "policy.md"}],
            },
        )

    with EvaluationApiClient("http://testserver", transport=httpx.MockTransport(handler)) as client:
        client.login("evaluator@example.com", "not-logged")
        sources = client.search("kb", "question", 3)
        answer = client.answer("kb", "question", 3)

    assert sources.sources == ["policy.md", "policy.md"]
    assert sources.retrieval_method == "hybrid-test"
    assert answer.cited_sources == ["policy.md"]
    assert requests[1].headers["Authorization"] == "Bearer opaque-test-token"


def test_http_client_maps_errors_without_echoing_response_or_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"X-Request-ID": "request-123"},
            json={"secret": "must-not-appear"},
        )

    with EvaluationApiClient(
        "http://testserver",
        token="must-not-appear",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(EvaluationApiError) as error:
            client.search("kb", "question", 3)

    message = str(error.value)
    assert "503" in message
    assert "request-123" in message
    assert "must-not-appear" not in message
