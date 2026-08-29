"""Process-local fixed-window request limiting with safe client keys."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic

import anyio
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import build_error_response
from app.modules.operations.metrics import OperationsMetrics


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Bound request frequency in one process; replace with Redis for multiple instances."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = anyio.Lock()

    async def check(
        self,
        *,
        policy: str,
        client_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("rate-limit bounds must be positive")
        now = self._clock()
        key = (policy, client_key)
        async with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= window_seconds:
                window = _Window(started_at=now, count=0)
                self._windows[key] = window
            window.count += 1
            remaining = max(0, limit - window.count)
            retry_after = max(1, math.ceil(window_seconds - (now - window.started_at)))
            allowed = window.count <= limit
            if len(self._windows) > 10_000:
                self._prune(now, window_seconds)
            return RateLimitDecision(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                retry_after_seconds=retry_after,
            )

    def _prune(self, now: float, longest_window_seconds: int) -> None:
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= longest_window_seconds
        ]
        for key in expired:
            del self._windows[key]


class RateLimitMiddleware:
    """Apply stricter policies to authentication and model-cost endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: FixedWindowRateLimiter,
        metrics: OperationsMetrics,
        enabled: bool,
        window_seconds: int,
        default_limit: int,
        auth_limit: int,
        answer_limit: int,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.metrics = metrics
        self.enabled = enabled
        self.window_seconds = window_seconds
        self.default_limit = default_limit
        self.auth_limit = auth_limit
        self.answer_limit = answer_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        policy = self._policy(scope)
        if not self.enabled or policy is None:
            await self.app(scope, receive, send)
            return
        policy_name, limit = policy
        decision = await self.limiter.check(
            policy=policy_name,
            client_key=self._client_key(scope),
            limit=limit,
            window_seconds=self.window_seconds,
        )

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(decision.limit)
                headers["X-RateLimit-Remaining"] = str(decision.remaining)
            await send(message)

        if decision.allowed:
            await self.app(scope, receive, send_with_headers)
            return

        self.metrics.observe_rate_limit_rejection(policy_name)
        response = build_error_response(
            code="rate_limit_exceeded",
            message="Too many requests; retry later",
            status_code=429,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
        await response(scope, receive, send_with_headers)

    def _policy(self, scope: Scope) -> tuple[str, int] | None:
        if scope["type"] != "http":
            return None
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET"))
        if not path.startswith("/api/v1/") or path.startswith("/api/v1/health/"):
            return None
        if method == "POST" and path in {"/api/v1/auth/login", "/api/v1/auth/register"}:
            return "authentication", self.auth_limit
        if method == "POST" and (path.endswith("/answers") or path.endswith("/answers/stream")):
            return "answer_generation", self.answer_limit
        return "default", self.default_limit

    @staticmethod
    def _client_key(scope: Scope) -> str:
        authorization = Headers(scope=scope).get("Authorization")
        if authorization:
            return "token:" + sha256(authorization.encode()).hexdigest()
        client = scope.get("client")
        address = str(client[0]) if client else "unknown"
        return "address:" + sha256(address.encode()).hexdigest()
