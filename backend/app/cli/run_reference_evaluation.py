"""Run a self-contained reference experiment against the disposable test database."""

import argparse
import asyncio
import hashlib
import secrets
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
from app.modules.answers.service import REFUSAL_ANSWER
from app.modules.evaluation.runner import run_evaluation
from app.modules.evaluation.schemas import AnswerObservation, EvaluationDataset, SearchObservation
from app.modules.generation.providers import GenerationResult
from app.modules.ingestion.worker import process_next_job

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "reports" / "reference-retrieval-v1.json"


class ReferenceGenerationProvider:
    """Stable local answers that test the answer pipeline without an external service."""

    name = "reference-deterministic-v1"

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
        question = user_prompt.rsplit("问题：", maxsplit=1)[-1].strip()
        return GenerationResult(
            content=answers.get(question, REFUSAL_ANSWER),
            model=self.name,
            prompt_tokens=0,
            completion_tokens=0,
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
            deepseek_api_key=base_settings.deepseek_api_key,
            deepseek_base_url=base_settings.deepseek_base_url,
            deepseek_model=base_settings.deepseek_model,
        )
        _migrate(test_database_url)
        app = create_app(settings)
        if args.generation_provider == "deterministic":
            app.state.generation_provider = ReferenceGenerationProvider()
        with TestClient(app, raise_server_exceptions=False) as client:
            token, knowledge_base_id = _prepare_corpus(client, settings, dataset)
            adapter = InProcessEvaluationClient(client, token)
            mode = cast(Literal["retrieval", "full"], args.mode)
            report = run_evaluation(dataset, adapter, knowledge_base_id, mode=mode)

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


def _prepare_corpus(
    client: TestClient,
    settings: Settings,
    dataset: EvaluationDataset,
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
    _process_jobs(settings, len(fixtures))
    return token, knowledge_base_id


def _process_jobs(settings: Settings, expected_jobs: int) -> None:
    async def run() -> None:
        database = Database(settings)
        try:
            for index in range(expected_jobs):
                processed = await process_next_job(
                    database,
                    settings,
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


if __name__ == "__main__":
    raise SystemExit(main())
