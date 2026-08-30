"""Cache, rate limiting, metrics, provider instrumentation, and audit tests."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.cli.create_admin import create_or_promote_admin
from app.core.config import Settings
from app.main import create_app
from app.modules.audit.middleware import _match_audited_route
from app.modules.generation.providers import GenerationResult
from app.modules.operations.cache import CachingEmbeddingProvider, TTLVectorCache
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.providers import InstrumentedGenerationProvider
from app.modules.operations.rate_limit import FixedWindowRateLimiter
from tests.test_authentication import (
    authorization_header,
    login_user,
    register_user,
)
from tests.test_document_ingestion import create_knowledge_base, upload_markdown


@dataclass
class CountingEmbeddingProvider:
    name: str = "counting-v1"
    dimensions: int = 2
    calls: int = 0

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(text)), 1.0] for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return [float(len(text)), 2.0]


def test_embedding_cache_hits_expires_and_evicts_without_aliasing() -> None:
    now = [100.0]

    async def scenario() -> tuple[int, list[float], list[float], list[float]]:
        delegate = CountingEmbeddingProvider()
        metrics = OperationsMetrics()
        cache = TTLVectorCache(max_entries=1, ttl_seconds=10, clock=lambda: now[0])
        provider = CachingEmbeddingProvider(delegate, cache, metrics)

        first = (await provider.embed_documents(["alpha"]))[0]
        first[0] = 999.0
        cached = (await provider.embed_documents(["alpha"]))[0]
        await provider.embed_documents(["beta"])
        evicted = (await provider.embed_documents(["alpha"]))[0]
        now[0] += 11
        expired = (await provider.embed_documents(["alpha"]))[0]
        rendered = metrics.render().decode()
        assert 'rag_embedding_cache_requests_total{outcome="hit"} 1.0' in rendered
        assert 'rag_embedding_cache_requests_total{outcome="miss"} 4.0' in rendered
        return delegate.calls, cached, evicted, expired

    calls, cached, evicted, expired = asyncio.run(scenario())

    assert calls == 4
    assert cached == [5.0, 1.0]
    assert evicted == [5.0, 1.0]
    assert expired == [5.0, 1.0]


def test_embedding_cache_validates_bounds_and_provider_batches() -> None:
    with pytest.raises(ValueError, match="positive"):
        TTLVectorCache(max_entries=0, ttl_seconds=1)

    class BrokenProvider(CountingEmbeddingProvider):
        async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
            del texts
            return []

    async def scenario() -> None:
        provider = CachingEmbeddingProvider(
            BrokenProvider(),
            TTLVectorCache(max_entries=2, ttl_seconds=10),
            OperationsMetrics(),
        )
        with pytest.raises(RuntimeError, match="cache-fill batch"):
            await provider.embed_documents(["alpha"])

    asyncio.run(scenario())


def test_embedding_cache_separates_query_and_document_vectors() -> None:
    async def scenario() -> tuple[list[float], list[float], int]:
        delegate = CountingEmbeddingProvider()
        provider = CachingEmbeddingProvider(
            delegate,
            TTLVectorCache(max_entries=4, ttl_seconds=10),
            OperationsMetrics(),
        )
        document = (await provider.embed_documents(["alpha"]))[0]
        query = await provider.embed_query("alpha")
        await provider.embed_query("alpha")
        return document, query, delegate.calls

    document, query, calls = asyncio.run(scenario())

    assert document == [5.0, 1.0]
    assert query == [5.0, 2.0]
    assert calls == 2


def test_fixed_window_rate_limiter_resets_after_window() -> None:
    now = [50.0]

    async def scenario() -> tuple[bool, bool, int, bool]:
        limiter = FixedWindowRateLimiter(clock=lambda: now[0])
        first = await limiter.check(policy="auth", client_key="client", limit=2, window_seconds=10)
        second = await limiter.check(policy="auth", client_key="client", limit=2, window_seconds=10)
        rejected = await limiter.check(
            policy="auth", client_key="client", limit=2, window_seconds=10
        )
        now[0] += 10
        reset = await limiter.check(policy="auth", client_key="client", limit=2, window_seconds=10)
        return first.allowed, second.allowed, rejected.retry_after_seconds, reset.allowed

    first, second, retry_after, reset = asyncio.run(scenario())

    assert first is True
    assert second is True
    assert retry_after == 10
    assert reset is True


def test_retry_route_is_classified_for_audit() -> None:
    matched = _match_audited_route(
        "POST",
        "/api/v1/ingestion-jobs/123e4567-e89b-12d3-a456-426614174000/retry",
    )

    assert matched is not None
    descriptor, template, resource_id = matched
    assert descriptor.action == "ingestion.retry"
    assert template == "/api/v1/ingestion-jobs/{job_id}/retry"
    assert resource_id == "123e4567-e89b-12d3-a456-426614174000"


def test_authentication_rate_limit_returns_safe_standard_error(settings: Settings) -> None:
    limited_settings = settings.model_copy(
        update={"rate_limit_auth_requests": 2, "rate_limit_window_seconds": 60}
    )
    app = create_app(limited_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        register_user(client)
        login_user(client)
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "learner@example.com", "password": "WrongPassword123!"},
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.headers["Retry-After"] == "60"
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-Request-ID"]


def test_metrics_endpoint_exposes_bounded_labels_and_optional_token(
    client: TestClient,
    settings: Settings,
) -> None:
    client.get("/api/v1/health/live")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'rag_http_requests_total{method="GET",route="/api/v1/health/live",status="200"}' in (
        response.text
    )
    assert 'rag_ingestion_jobs{status="queued"} 0.0' in response.text

    protected_settings = settings.model_copy(update={"metrics_bearer_token": SecretStr("m" * 32)})
    protected_app = create_app(protected_settings)
    with TestClient(protected_app, raise_server_exceptions=False) as protected_client:
        denied = protected_client.get("/metrics")
        allowed = protected_client.get("/metrics", headers={"Authorization": f"Bearer {'m' * 32}"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert "mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm" not in allowed.text


def test_metrics_can_be_disabled(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"metrics_enabled": False}))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/metrics")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "metrics_disabled"


@dataclass
class FakeGenerationProvider:
    fail: bool = False
    name: str = "instrumented-fake-v1"

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        del system_prompt, user_prompt
        if self.fail:
            raise RuntimeError("provider failed")
        return GenerationResult(content="answer", model=self.name)


def test_generation_instrumentation_records_success_and_error() -> None:
    async def scenario() -> str:
        metrics = OperationsMetrics()
        success = InstrumentedGenerationProvider(FakeGenerationProvider(), metrics)
        failure = InstrumentedGenerationProvider(FakeGenerationProvider(fail=True), metrics)
        assert (await success.generate(system_prompt="s", user_prompt="u")).content == "answer"
        with pytest.raises(RuntimeError, match="provider failed"):
            await failure.generate(system_prompt="s", user_prompt="u")
        return metrics.render().decode()

    rendered = asyncio.run(scenario())

    assert (
        'rag_model_calls_total{outcome="success",provider="instrumented-fake-v1"} 1.0' in rendered
    )
    assert 'rag_model_calls_total{outcome="error",provider="instrumented-fake-v1"} 1.0' in rendered


def test_audit_events_are_persistent_filtered_and_admin_only(
    client: TestClient,
    settings: Settings,
) -> None:
    registered = register_user(client)
    wrong = client.post(
        "/api/v1/auth/login",
        data={"username": "learner@example.com", "password": "WrongPassword123!"},
    )
    assert wrong.status_code == 401
    member_token = login_user(client)
    knowledge_base_id = create_knowledge_base(client, member_token, name="Audited Base")
    uploaded = upload_markdown(
        client,
        member_token,
        knowledge_base_id,
        content=b"Audited queue document.",
        filename="audited.md",
    )

    denied = client.get(
        "/api/v1/admin/audit-events",
        headers=authorization_header(member_token),
    )
    assert denied.status_code == 403
    denied_jobs = client.get(
        "/api/v1/admin/ingestion-jobs",
        headers=authorization_header(member_token),
    )
    assert denied_jobs.status_code == 403

    asyncio.run(
        create_or_promote_admin(
            "admin@example.com",
            "Audit Admin",
            "CorrectHorseBattery1!",
            settings,
        )
    )
    admin_token = login_user(client, email="admin@example.com")
    response = client.get(
        "/api/v1/admin/audit-events",
        headers=authorization_header(admin_token),
        params={"actor_user_id": registered["id"], "limit": 20},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 4
    actions = {item["action"] for item in payload["items"]}
    assert {"auth.register", "auth.login", "knowledge_base.create", "document.upload"} <= actions
    knowledge_events = [
        item for item in payload["items"] if item["action"] == "knowledge_base.create"
    ]
    assert knowledge_events[0]["resource_id"] == knowledge_base_id
    document_data = cast(dict[str, object], uploaded["document"])
    document_id = str(document_data["id"])
    document_events = [item for item in payload["items"] if item["action"] == "document.upload"]
    assert document_events[0]["resource_id"] == document_id
    assert all("password" not in str(item).lower() for item in payload["items"])
    assert all("token" not in str(item).lower() for item in payload["items"])

    failed_logins = client.get(
        "/api/v1/admin/audit-events",
        headers=authorization_header(admin_token),
        params={"action": "auth.login"},
    ).json()["items"]
    assert any(
        item["outcome"] == "denied" and item["actor_user_id"] is None for item in failed_logins
    )

    jobs = client.get(
        "/api/v1/admin/ingestion-jobs",
        headers=authorization_header(admin_token),
        params={"status": "queued"},
    )
    assert jobs.status_code == 200
    assert jobs.json()["total"] == 1
    assert jobs.json()["items"][0]["status"] == "queued"


def test_audit_query_has_bounded_pagination(client: TestClient, settings: Settings) -> None:
    asyncio.run(
        create_or_promote_admin(
            "admin@example.com",
            "Audit Admin",
            "CorrectHorseBattery1!",
            settings,
        )
    )
    token = login_user(client, email="admin@example.com")

    response = client.get(
        "/api/v1/admin/audit-events?limit=201",
        headers=authorization_header(token),
    )

    assert response.status_code == 422
