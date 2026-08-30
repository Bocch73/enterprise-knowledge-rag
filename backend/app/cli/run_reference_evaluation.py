"""Run a self-contained reference experiment against the disposable test database."""

import argparse
import asyncio
import hashlib
import secrets
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, cast
from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from alembic import command
from app.cli.evaluate_rag import DEFAULT_DATASET, load_dataset
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app
from app.modules.answers.service import ANSWER_PROMPT_VERSION, REFUSAL_ANSWER
from app.modules.evaluation.runner import run_evaluation
from app.modules.evaluation.schemas import (
    AnswerObservation,
    EvaluationDataset,
    ExperimentConfiguration,
    ExternalModelCallRecord,
    SearchObservation,
)
from app.modules.generation.providers import GenerationResult
from app.modules.indexing.providers import (
    EmbeddingProvider,
    create_dashscope_embedding_provider,
)
from app.modules.ingestion.worker import process_next_job
from app.modules.retrieval.providers import (
    RerankItem,
    RerankProvider,
    RerankResult,
    create_dashscope_rerank_provider,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "reports" / "reference-retrieval-v1.json"


class ReferenceGenerationProvider:
    """Stable local answers that test the answer pipeline without an external service."""

    name = "reference-deterministic-v1"

    def __init__(self, dataset: EvaluationDataset | None = None) -> None:
        self._answers = {
            case.question: (
                "；".join(group[0] for group in case.required_answer_terms) + "。[S1]"
                if case.answerable
                else REFUSAL_ANSWER
            )
            for case in (dataset.cases if dataset is not None else [])
        }

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        del system_prompt
        answers = {
            "SEC-104 对员工密码轮换有什么要求？": "SEC-104 要求员工每 90 天轮换一次密码。[S1]",
            "员工远程访问公司系统需要满足什么认证要求？": "员工远程访问必须使用多因素认证。[S1]",
            "超过 200 元的差旅报销需要提供什么？": (
                "超过 200 元的差旅报销需要明细收据和经理批准。[S1]"
            ),
            "全职员工每年有多少天带薪年假？": "全职员工每年享有 15 天带薪年假。[S1]",
            "公司周五下午茶的预算是多少？": REFUSAL_ANSWER,
        }
        answers.update(self._answers)
        question = user_prompt.rsplit("问题：", maxsplit=1)[-1].strip()
        return GenerationResult(
            content=answers.get(question, REFUSAL_ANSWER),
            model=self.name,
            prompt_tokens=0,
            completion_tokens=0,
        )


class ReferenceRerankProvider:
    """Dataset-aware stable reranker used only by the isolated reference experiment."""

    name = "reference-deterministic-rerank-v1"

    def __init__(self, dataset: EvaluationDataset) -> None:
        fixture_root = PROJECT_ROOT / "evaluation" / "fixtures"
        self._target_by_question = {
            case.question: (fixture_root / case.relevant_sources[0]).read_text(encoding="utf-8")
            for case in dataset.cases
            if case.answerable
        }

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> RerankResult:
        target = self._target_by_question.get(query)
        if target is None:
            items = [
                RerankItem(index=index, relevance_score=0.1)
                for index, _document in enumerate(documents[:top_n])
            ]
        else:
            ranked = sorted(
                range(len(documents)),
                key=lambda index: SequenceMatcher(None, target, documents[index]).ratio(),
                reverse=True,
            )[:top_n]
            items = [
                RerankItem(
                    index=index,
                    relevance_score=0.99 if rank == 1 else 0.2,
                )
                for rank, index in enumerate(ranked, start=1)
            ]
        return RerankResult(
            items=items,
            model=self.name,
            request_id="reference-deterministic-rerank",
        )


class InProcessEvaluationClient:
    """Call the real FastAPI routes without opening a network port."""

    def __init__(self, client: TestClient, token: str) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"}

    def search(self, knowledge_base_id: str, question: str, top_k: int) -> SearchObservation:
        response = self._client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
            headers=self._headers,
            json={"query": question, "top_k": top_k},
        )
        _require_success(response.status_code, response.text)
        payload = cast(dict[str, Any], response.json())
        return SearchObservation(
            sources=[str(item["original_filename"]) for item in payload["results"]],
            retrieval_method=str(payload["retrieval_method"]),
            embedding_model=str(payload["embedding_model"]),
            rerank_model=str(payload["rerank_model"]),
            evidence_sufficient=bool(payload["evidence_sufficient"]),
            evidence_threshold=float(payload["evidence_threshold"]),
            top_rerank_score=(
                float(payload["top_rerank_score"])
                if payload["top_rerank_score"] is not None
                else None
            ),
        )

    def answer(self, knowledge_base_id: str, question: str, top_k: int) -> AnswerObservation:
        response = self._client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/answers",
            headers=self._headers,
            json={"question": question, "top_k": top_k},
        )
        _require_success(response.status_code, response.text)
        payload = cast(dict[str, Any], response.json())
        return AnswerObservation(
            answer=str(payload["answer"]),
            refused=bool(payload["refused"]),
            cited_sources=[str(citation["original_filename"]) for citation in payload["citations"]],
            model=str(payload["model"]),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the checked-in corpus in the disposable test database and run an experiment."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mode", choices=("retrieval", "full"), default="retrieval")
    parser.add_argument(
        "--embedding-provider",
        choices=("deterministic", "configured"),
        default="deterministic",
        help="Use the network-free test provider or configured DashScope embeddings.",
    )
    parser.add_argument(
        "--rerank-provider",
        choices=("deterministic", "configured"),
        default="deterministic",
        help="Use the network-free test reranker or configured qwen3-rerank.",
    )
    parser.add_argument(
        "--generation-provider",
        choices=("deterministic", "configured"),
        default="deterministic",
        help="Use local stable answers or the configured external model for full mode.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-threshold-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = load_dataset(args.dataset)
    base_settings = Settings()  # type: ignore[call-arg]
    test_database_url = base_settings.test_database_url
    if test_database_url is None or not (make_url(test_database_url).database or "").endswith(
        "_test"
    ):
        raise RuntimeError("reference evaluation refuses to use a database not ending in _test")

    with TemporaryDirectory(prefix="rag1-evaluation-") as storage_directory:
        settings = Settings(
            environment="test",
            debug=False,
            log_level="CRITICAL",
            database_url=test_database_url,
            test_database_url=test_database_url,
            jwt_secret_key=SecretStr(secrets.token_urlsafe(48)),
            object_storage_path=Path(storage_directory),
            rate_limit_enabled=False,
            deepseek_api_key=base_settings.deepseek_api_key,
            deepseek_base_url=base_settings.deepseek_base_url,
            deepseek_model=base_settings.deepseek_model,
            dashscope_api_key=base_settings.dashscope_api_key,
            dashscope_base_http_api_url=base_settings.dashscope_base_http_api_url,
            dashscope_workspace_id=base_settings.dashscope_workspace_id,
            dashscope_embedding_model=base_settings.dashscope_embedding_model,
            dashscope_embedding_dimensions=base_settings.dashscope_embedding_dimensions,
            dashscope_embedding_batch_size=base_settings.dashscope_embedding_batch_size,
            dashscope_embedding_timeout_seconds=(base_settings.dashscope_embedding_timeout_seconds),
            dashscope_query_instruct=base_settings.dashscope_query_instruct,
        )
        _migrate(test_database_url)
        _clear_test_data(settings)
        app = create_app(settings)
        embedding_provider: EmbeddingProvider = app.state.embedding_provider
        if args.embedding_provider == "configured":
            embedding_provider = create_dashscope_embedding_provider(
                settings,
                metrics=app.state.operations_metrics,
                ledger=app.state.model_usage_ledger,
            )
            app.state.embedding_provider = embedding_provider
        rerank_provider: RerankProvider = app.state.rerank_provider
        if args.rerank_provider == "configured":
            rerank_provider = create_dashscope_rerank_provider(
                settings,
                metrics=app.state.operations_metrics,
                ledger=app.state.model_usage_ledger,
            )
            app.state.rerank_provider = rerank_provider
        else:
            rerank_provider = ReferenceRerankProvider(dataset)
            app.state.rerank_provider = rerank_provider
        if args.generation_provider == "deterministic":
            app.state.generation_provider = ReferenceGenerationProvider(dataset)
        with TestClient(app, raise_server_exceptions=False) as client:
            token, knowledge_base_id = _prepare_corpus(
                client,
                settings,
                dataset,
                embedding_provider,
            )
            adapter = InProcessEvaluationClient(client, token)
            mode = cast(Literal["retrieval", "full"], args.mode)
            report = run_evaluation(
                dataset,
                adapter,
                knowledge_base_id,
                mode=mode,
                experiment_configuration=_experiment_configuration(
                    settings,
                    dataset,
                    mode,
                    embedding_model=embedding_provider.name,
                    rerank_model=rerank_provider.name,
                    generation_model=app.state.generation_provider.name,
                ),
            )
            records = app.state.model_usage_ledger.snapshot()
            report.external_calls = [
                ExternalModelCallRecord.model_validate(record.as_dict()) for record in records
            ]
            report.estimated_costs = _estimated_costs(report.external_calls)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Reference report written to {args.output}")
    print(
        f"Quality gate: {'PASS' if report.quality_gate.passed else 'FAIL'}; "
        f"hit_rate@{dataset.top_k}={report.aggregate.hit_rate_at_k:.3f}; "
        f"MRR={report.aggregate.mean_reciprocal_rank:.3f}; "
        f"NDCG@{dataset.top_k}={report.aggregate.mean_ndcg_at_k:.3f}"
    )
    return 0 if report.quality_gate.passed or args.allow_threshold_failure else 1


def _migrate(database_url: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _clear_test_data(settings: Settings) -> None:
    """Remove prior experiment rows after the database-name safety check."""

    async def clear() -> None:
        database = Database(settings)
        try:
            async with database.engine.begin() as connection:
                await connection.exec_driver_sql("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
        finally:
            await database.dispose()

    asyncio.run(clear())


def _prepare_corpus(
    client: TestClient,
    settings: Settings,
    dataset: EvaluationDataset,
    embedding_provider: EmbeddingProvider,
) -> tuple[str, str]:
    email = f"rag-evaluation-{uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "RAG Evaluation Runner",
            "password": password,
        },
    )
    _require_success(registration.status_code, registration.text)
    login = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    _require_success(login.status_code, login.text)
    token = str(login.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    knowledge_base = client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={
            "name": f"Step 11 reference {uuid4().hex[:8]}",
            "description": "Disposable quality evaluation corpus.",
        },
    )
    _require_success(knowledge_base.status_code, knowledge_base.text)
    knowledge_base_id = str(knowledge_base.json()["id"])

    fixture_root = PROJECT_ROOT / "evaluation" / "fixtures"
    fixtures: list[Path] = []
    for document in dataset.corpus:
        fixture = fixture_root / document.filename
        try:
            content = fixture.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"evaluation fixture is unavailable: {fixture}") from exc
        if hashlib.sha256(content).hexdigest() != document.sha256:
            raise RuntimeError(f"evaluation fixture hash does not match dataset: {fixture.name}")
        fixtures.append(fixture)
    for fixture in fixtures:
        upload = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
            headers=headers,
            files={"file": (fixture.name, fixture.read_bytes(), "text/markdown")},
        )
        _require_success(upload.status_code, upload.text)
    _process_jobs(settings, len(fixtures), embedding_provider)
    return token, knowledge_base_id


def _process_jobs(
    settings: Settings,
    expected_jobs: int,
    embedding_provider: EmbeddingProvider,
) -> None:
    async def run() -> None:
        database = Database(settings)
        try:
            for index in range(expected_jobs):
                processed = await process_next_job(
                    database,
                    settings,
                    embedding_provider=embedding_provider,
                    worker_id=f"reference-evaluation-{index}",
                )
                if processed is None:
                    raise RuntimeError("an uploaded evaluation document was not processed")
        finally:
            await database.dispose()

    asyncio.run(run())


def _require_success(status_code: int, response_text: str) -> None:
    if not 200 <= status_code < 300:
        raise RuntimeError(f"reference API call failed with status {status_code}: {response_text}")


def _experiment_configuration(
    settings: Settings,
    dataset: EvaluationDataset,
    mode: str,
    *,
    embedding_model: str,
    rerank_model: str,
    generation_model: str,
) -> ExperimentConfiguration:
    return ExperimentConfiguration(
        chunk_size_characters=settings.chunk_size_characters,
        chunk_overlap_characters=settings.chunk_overlap_characters,
        retrieval_candidate_limit=settings.retrieval_candidate_limit,
        retrieval_rrf_k=settings.retrieval_rrf_k,
        retrieval_evidence_min_score=settings.retrieval_evidence_min_score,
        answer_context_max_characters=settings.answer_context_max_characters,
        top_k=dataset.top_k,
        embedding_model=embedding_model,
        embedding_dimensions=settings.dashscope_embedding_dimensions,
        rerank_model=rerank_model,
        generation_model=generation_model if mode == "full" else None,
        generation_temperature=settings.deepseek_temperature if mode == "full" else None,
        generation_max_output_tokens=(
            settings.deepseek_max_output_tokens if mode == "full" else None
        ),
        answer_prompt_version=ANSWER_PROMPT_VERSION,
        pricing_basis={
            "dashscope_embedding_cny_per_million_tokens": (
                settings.dashscope_embedding_cost_cny_per_million_tokens
            ),
            "dashscope_rerank_cny_per_million_tokens": (
                settings.dashscope_rerank_cost_cny_per_million_tokens
            ),
            "deepseek_cache_hit_usd_per_million_tokens": (
                settings.deepseek_prompt_cache_hit_cost_usd_per_million_tokens
            ),
            "deepseek_cache_miss_usd_per_million_tokens": (
                settings.deepseek_prompt_cache_miss_cost_usd_per_million_tokens
            ),
            "deepseek_output_usd_per_million_tokens": (
                settings.deepseek_output_cost_usd_per_million_tokens
            ),
        },
    )


def _estimated_costs(calls: list[ExternalModelCallRecord]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for call in calls:
        if call.estimated_cost is None or call.currency is None:
            continue
        totals[call.currency] = round(
            totals.get(call.currency, 0.0) + call.estimated_cost,
            10,
        )
    return totals


if __name__ == "__main__":
    raise SystemExit(main())
