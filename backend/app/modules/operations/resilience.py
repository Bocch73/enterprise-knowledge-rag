"""Bounded retries and per-provider circuit breakers for external calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import TypeVar

import anyio

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry only known temporary failures with exponential backoff."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def delay_before(self, next_attempt: int) -> float:
        if next_attempt <= 1:
            return 0.0
        return float(
            min(
                self.max_delay_seconds,
                self.base_delay_seconds * (2 ** (next_attempt - 2)),
            )
        )


class CircuitOpenError(RuntimeError):
    """Stop calls temporarily after repeated provider failures."""


class CircuitBreaker:
    """Small in-process closed/open/half-open circuit breaker."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold <= 0 or recovery_seconds <= 0:
            raise ValueError("circuit-breaker bounds must be positive")
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_call_running = False
        self._lock = anyio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            if self._clock() - self._opened_at < self._recovery_seconds:
                raise CircuitOpenError("external provider circuit is open")
            if self._half_open_call_running:
                raise CircuitOpenError("external provider circuit is half-open")
            self._half_open_call_running = True

    async def record_success(self) -> None:
        async with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_call_running = False

    async def record_temporary_failure(self) -> None:
        async with self._lock:
            self._half_open_call_running = False
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._opened_at = self._clock()


async def run_with_resilience(
    operation: Callable[[], Awaitable[T]],
    *,
    retry_policy: RetryPolicy,
    circuit_breaker: CircuitBreaker,
    is_retryable: Callable[[Exception], bool],
    on_retry: Callable[[], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
) -> tuple[T, int]:
    """Return a result and attempt count, or preserve the provider's final error."""
    await circuit_breaker.before_call()
    attempt = 0
    while True:
        attempt += 1
        try:
            result = await operation()
        except Exception as exception:
            retryable = is_retryable(exception)
            if retryable and attempt < retry_policy.max_attempts:
                if on_retry is not None:
                    on_retry()
                await sleep(retry_policy.delay_before(attempt + 1))
                continue
            if retryable:
                await circuit_breaker.record_temporary_failure()
            raise
        await circuit_breaker.record_success()
        return result, attempt
