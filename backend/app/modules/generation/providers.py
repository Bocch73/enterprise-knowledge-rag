"""Provider-neutral generation and a resilient DeepSeek HTTP adapter."""

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.core.errors import AppError
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.model_usage import ModelUsageLedger
from app.modules.operations.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    run_with_resilience,
)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Normalized model output and safe call metadata."""

    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None
    request_id: str | None = None
    attempts: int = 1
    estimated_cost_usd: float | None = None


class GenerationProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult: ...


class UnavailableGenerationProvider:
    @property
    def name(self) -> str:
        return "unconfigured"

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        del system_prompt, user_prompt
        raise AppError(
            code="generation_provider_unavailable",
            message="The answer-generation provider is not configured",
            status_code=503,
        )


class DeepSeekGenerationProvider:
    """Call DeepSeek with bounded retries, a circuit breaker, usage, and cost evidence."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        temperature: float,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        cache_hit_cost_usd_per_million_tokens: float = 0.0,
        cache_miss_cost_usd_per_million_tokens: float = 0.0,
        output_cost_usd_per_million_tokens: float = 0.0,
        metrics: OperationsMetrics | None = None,
        ledger: ModelUsageLedger | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._retry_policy = retry_policy or RetryPolicy(1, 0.0, 0.0)
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            recovery_seconds=30.0,
        )
        self._cache_hit_cost = cache_hit_cost_usd_per_million_tokens
        self._cache_miss_cost = cache_miss_cost_usd_per_million_tokens
        self._output_cost = output_cost_usd_per_million_tokens
        self._metrics = metrics
        self._ledger = ledger
        self._transport = transport

    @property
    def name(self) -> str:
        return self._model

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        started = perf_counter()
        try:
            response, attempts = await run_with_resilience(
                lambda: self._request(system_prompt, user_prompt),
                retry_policy=self._retry_policy,
                circuit_breaker=self._circuit_breaker,
                is_retryable=self._is_retryable,
                on_retry=self._observe_retry,
            )
            result = self._parse(response, attempts)
        except CircuitOpenError as exception:
            self._record_failure(started, "circuit_open")
            raise AppError(
                code="generation_circuit_open",
                message="The answer-generation provider is temporarily unavailable",
                status_code=503,
            ) from exception
        except Exception:
            self._record_failure(started, "error")
            raise
        self._record_success(result, started)
        return result

    async def _request(self, system_prompt: str, user_prompt: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": self._max_output_tokens,
                        "temperature": self._temperature,
                        "stream": False,
                    },
                )
        except httpx.TimeoutException as exception:
            raise AppError(
                code="generation_timeout",
                message="The answer-generation provider timed out",
                status_code=504,
            ) from exception
        except httpx.RequestError as exception:
            raise AppError(
                code="generation_provider_unavailable",
                message="The answer-generation provider is temporarily unavailable",
                status_code=503,
            ) from exception
        if response.status_code >= 400:
            self._raise_provider_error(response.status_code)
        return response

    def _parse(self, response: httpx.Response, attempts: int) -> GenerationResult:
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            response_model = payload.get("model", self._model)
            usage = payload.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as exception:
            raise AppError(
                code="generation_invalid_response",
                message="The answer-generation provider returned an invalid response",
                status_code=502,
            ) from exception
        if not isinstance(content, str) or not content.strip():
            raise AppError(
                code="generation_invalid_response",
                message="The answer-generation provider returned an empty response",
                status_code=502,
            )
        prompt_tokens = _optional_int(usage, "prompt_tokens")
        completion_tokens = _optional_int(usage, "completion_tokens")
        cache_hit_tokens = _optional_int(usage, "prompt_cache_hit_tokens")
        cache_miss_tokens = _optional_int(usage, "prompt_cache_miss_tokens")
        if prompt_tokens is not None and cache_hit_tokens is None and cache_miss_tokens is None:
            cache_hit_tokens = 0
            cache_miss_tokens = prompt_tokens
        cost = self._estimated_cost(cache_hit_tokens, cache_miss_tokens, completion_tokens)
        request_id = payload.get("id") or response.headers.get("X-Request-ID")
        return GenerationResult(
            content=content.strip(),
            model=response_model if isinstance(response_model, str) else self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_cache_hit_tokens=cache_hit_tokens,
            prompt_cache_miss_tokens=cache_miss_tokens,
            request_id=str(request_id) if request_id else None,
            attempts=attempts,
            estimated_cost_usd=cost,
        )

    def _estimated_cost(
        self,
        cache_hit_tokens: int | None,
        cache_miss_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        if cache_hit_tokens is None and cache_miss_tokens is None and output_tokens is None:
            return None
        return (
            (cache_hit_tokens or 0) * self._cache_hit_cost
            + (cache_miss_tokens or 0) * self._cache_miss_cost
            + (output_tokens or 0) * self._output_cost
        ) / 1_000_000

    @staticmethod
    def _is_retryable(exception: Exception) -> bool:
        return isinstance(exception, AppError) and exception.code in {
            "generation_timeout",
            "generation_provider_unavailable",
            "generation_rate_limited",
            "generation_provider_error",
        }

    @staticmethod
    def _raise_provider_error(status_code: int) -> None:
        if status_code == 401:
            details = (
                "generation_authentication_failed",
                "The answer-generation provider rejected its credentials",
                503,
            )
        elif status_code == 402:
            details = (
                "generation_quota_exhausted",
                "The answer-generation provider has insufficient quota",
                503,
            )
        elif status_code == 429:
            details = (
                "generation_rate_limited",
                "The answer-generation provider rate limit was reached",
                503,
            )
        elif status_code in {400, 422}:
            details = (
                "generation_request_rejected",
                "The answer-generation provider rejected the request",
                502,
            )
        else:
            details = (
                "generation_provider_error",
                "The answer-generation provider failed",
                502 if status_code < 500 else 503,
            )
        raise AppError(code=details[0], message=details[1], status_code=details[2])

    def _observe_retry(self) -> None:
        if self._metrics is not None:
            self._metrics.observe_external_retry(
                operation="generation",
                provider="deepseek",
                model=self.name,
            )

    def _record_success(self, result: GenerationResult, started: float) -> None:
        duration = perf_counter() - started
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation="generation",
                provider="deepseek",
                model=result.model,
                outcome="success",
                duration_seconds=duration,
                estimated_cost=result.estimated_cost_usd,
                currency="USD" if result.estimated_cost_usd is not None else None,
            )
        if self._ledger is not None:
            self._ledger.record(
                operation="generation",
                provider="deepseek",
                model=result.model,
                outcome="success",
                request_id=result.request_id,
                input_tokens=result.prompt_tokens,
                output_tokens=result.completion_tokens,
                attempts=result.attempts,
                latency_ms=duration * 1000,
                estimated_cost=result.estimated_cost_usd,
                currency="USD" if result.estimated_cost_usd is not None else None,
            )

    def _record_failure(self, started: float, outcome: str) -> None:
        if self._metrics is not None:
            self._metrics.observe_external_model(
                operation="generation",
                provider="deepseek",
                model=self.name,
                outcome=outcome,
                duration_seconds=perf_counter() - started,
            )


def _optional_int(value: object, key: str) -> int | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, int) else None
