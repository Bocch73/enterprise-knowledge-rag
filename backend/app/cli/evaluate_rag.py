"""Evaluate a running RAG API with a versioned, human-reviewed dataset."""

import argparse
import os
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from app.modules.evaluation.client import EvaluationApiClient, EvaluationApiError
from app.modules.evaluation.runner import run_evaluation
from app.modules.evaluation.schemas import EvaluationDataset

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = BACKEND_ROOT.parent / "evaluation" / "datasets" / "company-policy-v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repeatable retrieval and grounded-answer quality evaluation."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--base-url", default=os.getenv("RAG_EVALUATION_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--knowledge-base-id", default=os.getenv("RAG_EVALUATION_KNOWLEDGE_BASE_ID")
    )
    parser.add_argument("--mode", choices=("retrieval", "full"), default="retrieval")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--allow-threshold-failure", action="store_true")
    return parser.parse_args()


def load_dataset(path: Path) -> EvaluationDataset:
    try:
        return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"evaluation dataset does not exist: {path}") from exc
    except (OSError, ValidationError) as exc:
        raise RuntimeError(f"evaluation dataset is invalid: {exc}") from exc


def main() -> int:
    args = parse_args()
    try:
        dataset = load_dataset(args.dataset)
        if args.validate_only:
            print(
                f"Dataset valid: {dataset.name} v{dataset.version}; "
                f"cases={len(dataset.cases)}; top_k={dataset.top_k}"
            )
            return 0
        if not args.knowledge_base_id:
            raise RuntimeError(
                "knowledge base id is required; set RAG_EVALUATION_KNOWLEDGE_BASE_ID "
                "or pass --knowledge-base-id"
            )

        token = os.getenv("RAG_EVALUATION_TOKEN")
        email = os.getenv("RAG_EVALUATION_EMAIL")
        password = os.getenv("RAG_EVALUATION_PASSWORD")
        if not token and (not email or not password):
            raise RuntimeError(
                "set RAG_EVALUATION_TOKEN, or both RAG_EVALUATION_EMAIL and RAG_EVALUATION_PASSWORD"
            )

        mode = cast(Literal["retrieval", "full"], args.mode)
        with EvaluationApiClient(args.base_url, token=token) as client:
            if not token:
                client.login(cast(str, email), cast(str, password))
            report = run_evaluation(
                dataset,
                client,
                args.knowledge_base_id,
                mode=mode,
            )

        serialized = report.model_dump_json(indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + "\n", encoding="utf-8")
            print(f"Report written to {args.output}")
        print(
            f"Quality gate: {'PASS' if report.quality_gate.passed else 'FAIL'}; "
            f"hit_rate@{dataset.top_k}={report.aggregate.hit_rate_at_k:.3f}; "
            f"MRR={report.aggregate.mean_reciprocal_rank:.3f}; "
            f"NDCG@{dataset.top_k}={report.aggregate.mean_ndcg_at_k:.3f}"
        )
        if not report.quality_gate.passed and not args.allow_threshold_failure:
            return 1
        return 0
    except (RuntimeError, EvaluationApiError) as exc:
        print(f"Evaluation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
