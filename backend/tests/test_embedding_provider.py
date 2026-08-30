"""DashScope semantic-embedding adapter contract tests without network calls."""

import asyncio
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import pytest
from pydantic import SecretStr

from app.modules.indexing.providers import DashScopeEmbeddingProvider, EmbeddingProviderError
from app.modules.operations.resilience import CircuitBreaker, RetryPolicy


@dataclass
class FakeResponse:
    status_code: int
    output: dict[str, object] | None = None


def test_dashscope_provider_batches_documents_and_distinguishes_queries() -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(**kwargs: Any) -> FakeResponse:
        calls.append(kwargs)
        texts = kwargs["input"]
        return FakeResponse(
            status_code=HTTPStatus.OK,
            output={
                "embeddings": [
                    {"text_index": index, "embedding": [float(index), 1.0, 0.0]}
                    for index, _text in enumerate(texts)
                ]
            },
        )

    provider = DashScopeEmbeddingProvider(
        api_key=SecretStr("test-secret"),
        base_http_api_url="https://workspace.example/api/v1",
        workspace_id="test-workspace",
        model="qwen3.7-text-embedding",
        dimensions=3,
        batch_size=2,
        timeout_seconds=15,
        query_instruct="Retrieve relevant enterprise passages.",
        call=fake_call,
    )

    async def scenario() -> tuple[list[list[float]], list[float]]:
        documents = await provider.embed_documents(["one", "two", "three"])
        query = await provider.embed_query("question")
        return documents, query

    documents, query = asyncio.run(scenario())

    assert len(documents) == 3
    assert query == [0.0, 1.0, 0.0]
    assert [call["text_type"] for call in calls] == ["document", "document", "query"]
    assert [len(call["input"]) for call in calls] == [2, 1, 1]
    assert calls[-1]["instruct"] == "Retrieve relevant enterprise passages."
    assert all(call["dimension"] == 3 for call in calls)
    assert all(call["output_type"] == "dense" for call in calls)


def test_dashscope_rate_limit_is_retryable() -> None:
    provider = DashScopeEmbeddingProvider(
        api_key=SecretStr("test-secret"),
        base_http_api_url="https://workspace.example/api/v1",
        workspace_id=None,
        model="qwen3.7-text-embedding",
        dimensions=3,
        batch_size=2,
        timeout_seconds=15,
        query_instruct="Retrieve relevant enterprise passages.",
        call=lambda **_kwargs: FakeResponse(status_code=HTTPStatus.TOO_MANY_REQUESTS),
    )

    with pytest.raises(EmbeddingProviderError) as captured:
        asyncio.run(provider.embed_query("question"))

    assert captured.value.code == "embedding_rate_limited"
    assert captured.value.retryable is True


def test_dashscope_embedding_retries_temporary_rate_limit() -> None:
    calls = 0

    def fake_call(**kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return FakeResponse(status_code=HTTPStatus.TOO_MANY_REQUESTS)
        return FakeResponse(
            status_code=HTTPStatus.OK,
            output={"embeddings": [{"text_index": 0, "embedding": [0.0, 1.0, 0.0]}]},
        )

    provider = DashScopeEmbeddingProvider(
        api_key=SecretStr("test-secret"),
        base_http_api_url="https://workspace.example/api/v1",
        workspace_id=None,
        model="qwen3.7-text-embedding",
        dimensions=3,
        batch_size=2,
        timeout_seconds=15,
        query_instruct="Retrieve relevant enterprise passages.",
        retry_policy=RetryPolicy(2, 0.0, 0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_seconds=30),
        call=fake_call,
    )

    vector = asyncio.run(provider.embed_query("question"))

    assert calls == 2
    assert vector == [0.0, 1.0, 0.0]
