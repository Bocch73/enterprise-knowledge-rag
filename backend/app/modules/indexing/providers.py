"""Embedding-provider contract, DashScope adapter, and isolated test double."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from functools import partial
from hashlib import sha256
from http import HTTPStatus
from time import perf_counter
from typing import Any, Never, Protocol

import anyio
import dashscope
from dashscope.common.error import DashScopeException
from pydantic import SecretStr
from requests import RequestException

from app.core.config import Settings
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.model_usage import ModelUsageLedger
from app.modules.operations.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    run_with_resilience,
)

EMBEDDING_DIMENSIONS = 1024
TEST_EMBEDDING_MODEL = "test-deterministic-embedding-v1"
WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


class EmbeddingProvider(Protocol):
    """Convert a batch of text into fixed-size floating-point vectors."""

    name: str
    dimensions: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each input text in the original order."""

    async def embed_query(self, text: str) -> list[float]:
        """Return one retrieval-optimized vector for a user's query."""


class EmbeddingProviderError(Exception):
    """Safe provider failure metadata used by the retryable job state machine."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class UnavailableEmbeddingProvider:
    """Keep non-worker processes healthy when embedding credentials are absent."""

    name = "unconfigured"
    dimensions = EMBEDDING_DIMENSIONS

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        self._raise_unavailable()

    async def embed_query(self, text: str) -> list[float]:
        del text
        self._raise_unavailable()

    @staticmethod
    def _raise_unavailable() -> Never:
        raise EmbeddingProviderError(
            "embedding_provider_unavailable",
            "The embedding provider is not configured",
            retryable=False,
        )


class DashScopeEmbeddingProvider:
    """Generate dense document and query vectors with Alibaba Cloud Model Studio."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_http_api_url: str,
        workspace_id: str | None,
        model: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: float,
        query_instruct: str,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        cost_cny_per_million_tokens: float = 0.0,
        metrics: OperationsMetrics | None = None,
        ledger: ModelUsageLedger | None = None,
        call: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._workspace_id = workspace_id
        self.name = model
        self.dimensions = dimensions
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds
        self._query_instruct = query_instruct
        self._retry_policy = retry_policy or RetryPolicy(1, 0.0, 0.0)
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            recovery_seconds=30.0,
        )
        self._cost_cny_per_million_tokens = cost_cny_per_million_tokens
        self._metrics = metrics
        self._ledger = ledger
        self._call = call or dashscope.TextEmbedding.call

        # DashScope exposes its HTTP base address as process-wide SDK configuration.
        # Each API/worker process creates one provider, so it is set once at startup.
        dashscope.base_http_api_url = base_http_api_url.rstrip("/")

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        copied = list(texts)
        if not copied:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(copied), self._batch_size):
            vectors.extend(
                await self._embed_batch(
                    copied[start : start + self._batch_size],
                    text_type="document",
                )
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed_batch(
            [text],
            text_type="query",
            instruct=self._query_instruct,
        )
        if len(vectors) != 1:
            raise EmbeddingProviderError(
                "embedding_count_mismatch",
                "The embedding provider returned a different number of vectors than inputs",
                retryable=False,
            )
        return vectors[0]

    async def _embed_batch(
        self,
        texts: list[str],
        *,
        text_type: str,
        instruct: str | None = None,
    ) -> list[list[float]]:
        request = partial(
            self._call,
            model=self.name,
            input=texts,
            api_key=self._api_key.get_secret_value(),
            workspace=self._workspace_id,
            text_type=text_type,
            dimension=self.dimensions,
            output_type="dense",
            instruct=instruct,
            request_timeout=self._timeout_seconds,
        )

        async def call_once() -> Any:
            try:
                response = await anyio.to_thread.run_sync(request)
            except (DashScopeException, RequestException, TimeoutError) as exception:
                raise EmbeddingProviderError(
                    "embedding_provider_unavailable",
                    "The embedding provider could not be reached",
                    retryable=True,
                ) from exception
            status_code = getattr(response, "status_code", None)
            if status_code != HTTPStatus.OK:
                self._raise_provider_error(status_code)
            return response

        started = perf_counter()
        try:
            response, attempts = await run_with_resilience(
                call_once,
                retry_policy=self._retry_policy,
                circuit_breaker=self._circuit_breaker,
                is_retryable=lambda exception: (
                    isinstance(exception, EmbeddingProviderError) and exception.retryable
                ),
                on_retry=lambda: self._observe_retry(text_type),
            )
        except CircuitOpenError as exception:
            self._record_failure(text_type, started, "circuit_open")
            raise EmbeddingProviderError(
                "embedding_provider_unavailable",
                "The embedding provider circuit is open",
                retryable=True,
            ) from exception
        except Exception:
            self._record_failure(text_type, started, "error")
            raise
        output = getattr(response, "output", None)
        if not isinstance(output, dict) or not isinstance(output.get("embeddings"), list):
            raise EmbeddingProviderError(
                "embedding_invalid_response",
                "The embedding provider returned an invalid response",
                retryable=False,
            )
        items = output["embeddings"]
        try:
            ordered = sorted(items, key=lambda item: item["text_index"])
            vectors = [list(item["embedding"]) for item in ordered]
        except (KeyError, TypeError, ValueError) as exception:
            raise EmbeddingProviderError(
                "embedding_invalid_response",
                "The embedding provider returned an invalid response",
                retryable=False,
            ) from exception
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                "embedding_count_mismatch",
                "The embedding provider returned a different number of vectors than inputs",
                retryable=False,
            )
        self._record_success(response, attempts, text_type, started)
        return vectors

    def _observe_retry(self, text_type: str) -> None:
        if self._metrics is not None:
            self._metrics.observe_external_retry(
                operation=f"embedding_{text_type}",
                provider="dashscope",
                model=self.name,
            )

    def _record_success(
        self,
        response: Any,
        attempts: int,
        text_type: str,
        started: float,
    ) -> None:
        duration = perf_counter() - started
        usage = getattr(response, "usage", None)
        input_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        request_id = getattr(response, "request_id", None)
        cost = (
            input_tokens * self._cost_cny_per_million_tokens / 1_000_000
            if isinstance(input_tokens, int)
            else None
        )
        operation = f"embedding_{text_type}"
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation=operation,
                provider="dashscope",
                model=self.name,
                outcome="success",
                duration_seconds=duration,
                estimated_cost=cost,
                currency="CNY" if cost is not None else None,
            )
        if self._ledger is not None:
            self._ledger.record(
                operation=operation,
                provider="dashscope",
                model=self.name,
                outcome="success",
                request_id=str(request_id) if request_id else None,
                input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                output_tokens=None,
                attempts=attempts,
                latency_ms=duration * 1000,
                estimated_cost=cost,
                currency="CNY" if cost is not None else None,
            )

    def _record_failure(self, text_type: str, started: float, outcome: str) -> None:
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation=f"embedding_{text_type}",
                provider="dashscope",
                model=self.name,
                outcome=outcome,
                duration_seconds=perf_counter() - started,
            )

    @staticmethod
    def _raise_provider_error(status_code: object) -> None:
        if status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            code = "embedding_authentication_failed"
            message = "The embedding provider rejected its credentials"
            retryable = False
        elif status_code == HTTPStatus.TOO_MANY_REQUESTS:
            code = "embedding_rate_limited"
            message = "The embedding provider rate limit was reached"
            retryable = True
        elif isinstance(status_code, int) and status_code >= 500:
            code = "embedding_provider_unavailable"
            message = "The embedding provider is temporarily unavailable"
            retryable = True
        else:
            code = "embedding_request_rejected"
            message = "The embedding provider rejected the request"
            retryable = False
        raise EmbeddingProviderError(code, message, retryable=retryable)


class DeterministicTestEmbeddingProvider:
    """Offline lexical hashing used only for repeatable automated tests.

    Runtime factories never select this provider outside the test environment.
    """

    name = TEST_EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = " ".join(text.casefold().split())
        words = WORD_PATTERN.findall(normalized)
        compact = "".join(character for character in normalized if not character.isspace())
        character_pairs = [compact[index : index + 2] for index in range(len(compact) - 1)]
        return words + character_pairs

    @classmethod
    def _embed_one(cls, text: str) -> list[float]:
        features = cls._features(text)
        if not features:
            raise EmbeddingProviderError(
                "embedding_input_empty",
                "A document chunk did not contain embeddable text",
                retryable=False,
            )

        vector = [0.0] * cls.dimensions
        for feature in features:
            digest = sha256(feature.encode("utf-8")).digest()
            position = int.from_bytes(digest[:4], byteorder="big") % cls.dimensions
            direction = 1.0 if digest[4] & 1 else -1.0
            vector[position] += direction

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            raise EmbeddingProviderError(
                "embedding_normalization_failed",
                "The local embedding vector could not be normalized",
                retryable=False,
            )
        return [value / magnitude for value in vector]

    @classmethod
    def _embed_many(cls, texts: Sequence[str]) -> list[list[float]]:
        return [cls._embed_one(text) for text in texts]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        copied_texts = tuple(texts)
        return await anyio.to_thread.run_sync(self._embed_many, copied_texts)

    async def embed_query(self, text: str) -> list[float]:
        return await anyio.to_thread.run_sync(self._embed_one, text)


def create_embedding_provider(
    settings: Settings,
    *,
    metrics: OperationsMetrics | None = None,
    ledger: ModelUsageLedger | None = None,
) -> EmbeddingProvider:
    """Select the configured runtime provider while keeping tests network-free."""
    if settings.environment == "test":
        return DeterministicTestEmbeddingProvider()
    if settings.dashscope_api_key is not None:
        return create_dashscope_embedding_provider(settings, metrics=metrics, ledger=ledger)
    return UnavailableEmbeddingProvider()


def create_dashscope_embedding_provider(
    settings: Settings,
    *,
    metrics: OperationsMetrics | None = None,
    ledger: ModelUsageLedger | None = None,
) -> DashScopeEmbeddingProvider:
    """Build the explicitly configured external provider for runtime or evaluation."""
    if settings.dashscope_api_key is None:
        raise ValueError("DASHSCOPE_API_KEY is required for configured semantic embeddings")
    return DashScopeEmbeddingProvider(
        api_key=settings.dashscope_api_key,
        base_http_api_url=settings.dashscope_base_http_api_url,
        workspace_id=settings.dashscope_workspace_id,
        model=settings.dashscope_embedding_model,
        dimensions=settings.dashscope_embedding_dimensions,
        batch_size=settings.dashscope_embedding_batch_size,
        timeout_seconds=settings.dashscope_embedding_timeout_seconds,
        query_instruct=settings.dashscope_query_instruct,
        retry_policy=RetryPolicy(
            max_attempts=settings.external_retry_max_attempts,
            base_delay_seconds=settings.external_retry_base_delay_seconds,
            max_delay_seconds=settings.external_retry_max_delay_seconds,
        ),
        circuit_breaker=CircuitBreaker(
            failure_threshold=settings.external_circuit_failure_threshold,
            recovery_seconds=settings.external_circuit_recovery_seconds,
        ),
        cost_cny_per_million_tokens=(settings.dashscope_embedding_cost_cny_per_million_tokens),
        metrics=metrics,
        ledger=ledger,
    )
