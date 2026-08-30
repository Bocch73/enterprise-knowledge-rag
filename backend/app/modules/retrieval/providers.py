"""Provider-neutral reranking and the Alibaba Cloud qwen3-rerank adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.model_usage import ModelUsageLedger
from app.modules.operations.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    run_with_resilience,
)


@dataclass(frozen=True, slots=True)
class RerankItem:
    index: int
    relevance_score: float


@dataclass(frozen=True, slots=True)
class RerankResult:
    items: list[RerankItem]
    model: str
    request_id: str | None = None
    input_tokens: int | None = None
    attempts: int = 1


class RerankProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> RerankResult: ...


class RerankProviderError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class DeterministicTestRerankProvider:
    """Network-free stable ordering used only by automated tests."""

    name = "test-deterministic-rerank-v1"

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> RerankResult:
        del query
        items = [
            RerankItem(index=index, relevance_score=max(0.0, 1.0 - index * 0.01))
            for index, _document in enumerate(documents[:top_n])
        ]
        return RerankResult(items=items, model=self.name, request_id="deterministic-rerank")


class UnavailableRerankProvider:
    name = "unconfigured"

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> RerankResult:
        del query, documents, top_n
        raise RerankProviderError(
            "rerank_provider_unavailable",
            "The rerank provider is not configured",
            retryable=False,
        )


class DashScopeRerankProvider:
    """Call the workspace-scoped OpenAI-compatible qwen3-rerank endpoint."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        timeout_seconds: float,
        instruct: str,
        retry_policy: RetryPolicy,
        circuit_breaker: CircuitBreaker,
        cost_cny_per_million_tokens: float,
        metrics: OperationsMetrics | None = None,
        ledger: ModelUsageLedger | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._instruct = instruct
        self._retry_policy = retry_policy
        self._circuit_breaker = circuit_breaker
        self._cost_cny_per_million_tokens = cost_cny_per_million_tokens
        self._metrics = metrics
        self._ledger = ledger
        self._transport = transport

    @property
    def name(self) -> str:
        return self._model

    async def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> RerankResult:
        copied = list(documents)
        if not copied:
            return RerankResult(items=[], model=self.name)
        requested_top_n = min(top_n, len(copied))
        started = perf_counter()
        try:
            response, attempts = await run_with_resilience(
                lambda: self._request(query, copied, requested_top_n),
                retry_policy=self._retry_policy,
                circuit_breaker=self._circuit_breaker,
                is_retryable=lambda exception: (
                    isinstance(exception, RerankProviderError) and exception.retryable
                ),
                on_retry=self._observe_retry,
            )
            result = self._parse(response, len(copied), attempts)
        except CircuitOpenError as exception:
            self._record_failure(started, "circuit_open")
            raise RerankProviderError(
                "rerank_circuit_open",
                "The rerank provider is temporarily unavailable",
                retryable=True,
            ) from exception
        except Exception:
            self._record_failure(started, "error")
            raise
        self._record_success(result, started)
        return result

    async def _request(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/reranks",
                    headers={
                        "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.name,
                        "query": query,
                        "documents": documents,
                        "top_n": top_n,
                        "instruct": self._instruct,
                    },
                )
        except httpx.TimeoutException as exception:
            raise RerankProviderError(
                "rerank_timeout",
                "The rerank provider timed out",
                retryable=True,
            ) from exception
        except httpx.RequestError as exception:
            raise RerankProviderError(
                "rerank_provider_unavailable",
                "The rerank provider could not be reached",
                retryable=True,
            ) from exception
        if response.status_code >= 400:
            self._raise_provider_error(response.status_code)
        return response

    def _parse(self, response: httpx.Response, document_count: int, attempts: int) -> RerankResult:
        try:
            payload = response.json()
            raw_items = payload["results"]
            if not isinstance(raw_items, list):
                raise TypeError
            items = [
                RerankItem(
                    index=int(item["index"]),
                    relevance_score=float(item["relevance_score"]),
                )
                for item in raw_items
            ]
            usage = payload.get("usage", {})
            input_tokens = usage.get("total_tokens")
            request_id = payload.get("id") or response.headers.get("X-Request-ID")
        except (ValueError, KeyError, TypeError) as exception:
            raise RerankProviderError(
                "rerank_invalid_response",
                "The rerank provider returned an invalid response",
                retryable=False,
            ) from exception
        if (
            len({item.index for item in items}) != len(items)
            or any(item.index < 0 or item.index >= document_count for item in items)
            or any(not 0.0 <= item.relevance_score <= 1.0 for item in items)
        ):
            raise RerankProviderError(
                "rerank_invalid_response",
                "The rerank provider returned invalid ranking values",
                retryable=False,
            )
        return RerankResult(
            items=items,
            model=str(payload.get("model", self.name)),
            request_id=str(request_id) if request_id else None,
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            attempts=attempts,
        )

    @staticmethod
    def _raise_provider_error(status_code: int) -> None:
        if status_code in {401, 403}:
            details = (
                "rerank_authentication_failed",
                "The rerank provider rejected its credentials",
                False,
            )
        elif status_code == 429:
            details = ("rerank_rate_limited", "The rerank provider rate limit was reached", True)
        elif status_code >= 500:
            details = (
                "rerank_provider_unavailable",
                "The rerank provider is temporarily unavailable",
                True,
            )
        else:
            details = ("rerank_request_rejected", "The rerank provider rejected the request", False)
        raise RerankProviderError(details[0], details[1], retryable=details[2])

    def _observe_retry(self) -> None:
        if self._metrics is not None:
            self._metrics.observe_external_retry(
                operation="rerank",
                provider="dashscope",
                model=self.name,
            )

    def _record_success(self, result: RerankResult, started: float) -> None:
        duration = perf_counter() - started
        cost = (
            result.input_tokens * self._cost_cny_per_million_tokens / 1_000_000
            if result.input_tokens is not None
            else None
        )
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation="rerank",
                provider="dashscope",
                model=result.model,
                outcome="success",
                duration_seconds=duration,
                estimated_cost=cost,
                currency="CNY" if cost is not None else None,
            )
        if self._ledger is not None:
            self._ledger.record(
                operation="rerank",
                provider="dashscope",
                model=result.model,
                outcome="success",
                request_id=result.request_id,
                input_tokens=result.input_tokens,
                output_tokens=None,
                attempts=result.attempts,
                latency_ms=duration * 1000,
                estimated_cost=cost,
                currency="CNY" if cost is not None else None,
            )

    def _record_failure(self, started: float, outcome: str) -> None:
        duration = perf_counter() - started
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation="rerank",
                provider="dashscope",
                model=self.name,
                outcome=outcome,
                duration_seconds=duration,
            )


def _retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=settings.external_retry_max_attempts,
        base_delay_seconds=settings.external_retry_base_delay_seconds,
        max_delay_seconds=settings.external_retry_max_delay_seconds,
    )


def _circuit_breaker(settings: Settings) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=settings.external_circuit_failure_threshold,
        recovery_seconds=settings.external_circuit_recovery_seconds,
    )


def create_rerank_provider(
    settings: Settings,
    *,
    metrics: OperationsMetrics | None = None,
    ledger: ModelUsageLedger | None = None,
) -> RerankProvider:
    if settings.environment == "test":
        return DeterministicTestRerankProvider()
    if settings.dashscope_api_key is None:
        return UnavailableRerankProvider()
    return create_dashscope_rerank_provider(settings, metrics=metrics, ledger=ledger)


def create_dashscope_rerank_provider(
    settings: Settings,
    *,
    metrics: OperationsMetrics | None = None,
    ledger: ModelUsageLedger | None = None,
) -> DashScopeRerankProvider:
    if settings.dashscope_api_key is None:
        raise ValueError("DASHSCOPE_API_KEY is required for configured reranking")
    return DashScopeRerankProvider(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_rerank_base_url,
        model=settings.dashscope_rerank_model,
        timeout_seconds=settings.dashscope_rerank_timeout_seconds,
        instruct=settings.dashscope_rerank_instruct,
        retry_policy=_retry_policy(settings),
        circuit_breaker=_circuit_breaker(settings),
        cost_cny_per_million_tokens=(settings.dashscope_rerank_cost_cny_per_million_tokens),
        metrics=metrics,
        ledger=ledger,
    )
