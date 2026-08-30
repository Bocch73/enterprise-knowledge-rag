"""Small authenticated HTTP client for black-box RAG evaluation."""

from collections.abc import Mapping
from typing import Any

import httpx

from app.modules.evaluation.schemas import AnswerObservation, SearchObservation


class EvaluationApiError(RuntimeError):
    """Expose safe HTTP context without leaking credentials."""


class EvaluationApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def __enter__(self) -> "EvaluationApiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def login(self, email: str, password: str) -> None:
        response = self._client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        payload = self._json(response)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise EvaluationApiError("login response did not contain an access token")
        self._client.headers["Authorization"] = f"Bearer {token}"

    def search(self, knowledge_base_id: str, question: str, top_k: int) -> SearchObservation:
        response = self._client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
            json={"query": question, "top_k": top_k},
        )
        payload = self._json(response)
        results = payload.get("results")
        if not isinstance(results, list):
            raise EvaluationApiError("search response did not contain a result list")
        sources: list[str] = []
        for result in results:
            if not isinstance(result, Mapping):
                raise EvaluationApiError("search result had an invalid shape")
            filename = result.get("original_filename")
            if not isinstance(filename, str):
                raise EvaluationApiError("search result did not contain an original filename")
            sources.append(filename)
        retrieval_method = payload.get("retrieval_method")
        embedding_model = payload.get("embedding_model")
        if not isinstance(retrieval_method, str) or not isinstance(embedding_model, str):
            raise EvaluationApiError("search response did not contain retrieval configuration")
        return SearchObservation(
            sources=sources,
            retrieval_method=retrieval_method,
            embedding_model=embedding_model,
            rerank_model=str(payload.get("rerank_model", "unconfigured")),
            evidence_sufficient=bool(payload.get("evidence_sufficient", bool(results))),
            evidence_threshold=float(payload.get("evidence_threshold", 0.0)),
            top_rerank_score=(
                float(payload["top_rerank_score"])
                if payload.get("top_rerank_score") is not None
                else None
            ),
        )

    def answer(self, knowledge_base_id: str, question: str, top_k: int) -> AnswerObservation:
        response = self._client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/answers",
            json={"question": question, "top_k": top_k},
        )
        payload = self._json(response)
        citations = payload.get("citations")
        if not isinstance(citations, list):
            raise EvaluationApiError("answer response did not contain citations")
        cited_sources: list[str] = []
        for citation in citations:
            if not isinstance(citation, Mapping):
                raise EvaluationApiError("citation had an invalid shape")
            filename = citation.get("original_filename")
            if not isinstance(filename, str):
                raise EvaluationApiError("citation did not contain an original filename")
            cited_sources.append(filename)
        answer = payload.get("answer")
        refused = payload.get("refused")
        model = payload.get("model")
        if (
            not isinstance(answer, str)
            or not isinstance(refused, bool)
            or not isinstance(model, str)
        ):
            raise EvaluationApiError("answer response had an invalid shape")
        return AnswerObservation(
            answer=answer,
            refused=refused,
            cited_sources=cited_sources,
            model=model,
        )

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        if not response.is_success:
            request_id = response.headers.get("X-Request-ID", "missing")
            raise EvaluationApiError(
                f"API request failed with status {response.status_code}; request_id={request_id}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EvaluationApiError("API response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise EvaluationApiError("API response root must be an object")
        return payload
