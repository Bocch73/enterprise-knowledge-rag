"""qwen3-rerank adapter, retry, circuit-breaker, and usage-record tests."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.model_usage import ModelUsageLedger
from app.modules.operations.resilience import CircuitBreaker, RetryPolicy
from app.modules.retrieval.providers import DashScopeRerankProvider, RerankProviderError


def provider_for(
    handler: httpx.MockTransport,
    *,
    attempts: int = 1,
    failure_threshold: int = 5,
) -> tuple[DashScopeRerankProvider, OperationsMetrics, ModelUsageLedger]:
    metrics = OperationsMetrics()
    ledger = ModelUsageLedger()
    provider = DashScopeRerankProvider(
        api_key=SecretStr("test-secret"),
        base_url="https://workspace.example/compatible-api/v1",
        model="qwen3-rerank",
        timeout_seconds=1,
        instruct="Retrieve passages that answer the question.",
        retry_policy=RetryPolicy(attempts, 0.0, 0.0),
        circuit_breaker=CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=60,
        ),
        cost_cny_per_million_tokens=0.5,
        metrics=metrics,
        ledger=ledger,
        transport=handler,
    )
    return provider, metrics, ledger


def test_qwen_rerank_normalizes_order_usage_and_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://workspace.example/compatible-api/v1/reranks"
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "id": "rerank-request-1",
                "model": "qwen3-rerank",
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.42},
                ],
                "usage": {"total_tokens": 80},
            },
        )

    provider, metrics, ledger = provider_for(httpx.MockTransport(handler))
    result = asyncio.run(provider.rerank(query="question", documents=["first", "second"], top_n=2))

    assert [item.index for item in result.items] == [1, 0]
    assert result.request_id == "rerank-request-1"
    assert result.input_tokens == 80
    assert ledger.snapshot()[0].estimated_cost == pytest.approx(0.00004)
    rendered = metrics.render().decode()
    assert 'operation="rerank",provider="dashscope"' in rendered


def test_qwen_rerank_retries_temporary_failure_once() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "id": "retry-success",
                "results": [{"index": 0, "relevance_score": 0.9}],
                "usage": {"total_tokens": 10},
            },
        )

    provider, metrics, _ledger = provider_for(httpx.MockTransport(handler), attempts=2)
    result = asyncio.run(provider.rerank(query="q", documents=["d"], top_n=1))

    assert calls == 2
    assert result.attempts == 2
    assert 'rag_external_model_retries_total{model="qwen3-rerank"' in (metrics.render().decode())


def test_qwen_rerank_circuit_opens_after_failure() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    provider, metrics, _ledger = provider_for(
        httpx.MockTransport(handler),
        failure_threshold=1,
    )
    with pytest.raises(RerankProviderError):
        asyncio.run(provider.rerank(query="q", documents=["d"], top_n=1))
    with pytest.raises(RerankProviderError, match="temporarily unavailable") as captured:
        asyncio.run(provider.rerank(query="q", documents=["d"], top_n=1))

    assert captured.value.code == "rerank_circuit_open"
    assert calls == 1
    rendered = metrics.render().decode()
    assert 'outcome="error"' in rendered
    assert 'outcome="circuit_open"' in rendered
