"""FastAPI application factory and default process entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.event_loop import configure_event_loop_policy
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.readiness import application_check
from app.db.session import Database
from app.infrastructure.storage import LocalObjectStorage
from app.modules.audit.middleware import AuditMiddleware
from app.modules.generation.providers import (
    DeepSeekGenerationProvider,
    UnavailableGenerationProvider,
)
from app.modules.indexing.providers import create_embedding_provider
from app.modules.operations.cache import CachingEmbeddingProvider, TTLVectorCache
from app.modules.operations.metrics import OperationsMetrics
from app.modules.operations.model_usage import ModelUsageLedger
from app.modules.operations.providers import InstrumentedGenerationProvider
from app.modules.operations.rate_limit import FixedWindowRateLimiter, RateLimitMiddleware
from app.modules.operations.resilience import CircuitBreaker, RetryPolicy
from app.modules.operations.router import router as operations_router
from app.modules.retrieval.providers import create_rerank_provider

configure_event_loop_policy()


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance for runtime or tests."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    database = Database(runtime_settings)
    object_storage = LocalObjectStorage(runtime_settings.object_storage_path)
    operations_metrics = OperationsMetrics()
    model_usage_ledger = ModelUsageLedger()
    base_embedding_provider = create_embedding_provider(
        runtime_settings,
        metrics=operations_metrics,
        ledger=model_usage_ledger,
    )
    embedding_provider = (
        CachingEmbeddingProvider(
            base_embedding_provider,
            TTLVectorCache(
                max_entries=runtime_settings.embedding_cache_max_entries,
                ttl_seconds=runtime_settings.embedding_cache_ttl_seconds,
            ),
            operations_metrics,
        )
        if runtime_settings.embedding_cache_enabled
        else base_embedding_provider
    )
    base_generation_provider = (
        DeepSeekGenerationProvider(
            api_key=runtime_settings.deepseek_api_key,
            base_url=runtime_settings.deepseek_base_url,
            model=runtime_settings.deepseek_model,
            timeout_seconds=runtime_settings.deepseek_timeout_seconds,
            max_output_tokens=runtime_settings.deepseek_max_output_tokens,
            temperature=runtime_settings.deepseek_temperature,
            retry_policy=_retry_policy(runtime_settings),
            circuit_breaker=_circuit_breaker(runtime_settings),
            cache_hit_cost_usd_per_million_tokens=(
                runtime_settings.deepseek_prompt_cache_hit_cost_usd_per_million_tokens
            ),
            cache_miss_cost_usd_per_million_tokens=(
                runtime_settings.deepseek_prompt_cache_miss_cost_usd_per_million_tokens
            ),
            output_cost_usd_per_million_tokens=(
                runtime_settings.deepseek_output_cost_usd_per_million_tokens
            ),
            metrics=operations_metrics,
            ledger=model_usage_ledger,
        )
        if runtime_settings.deepseek_api_key is not None
        else UnavailableGenerationProvider()
    )
    generation_provider = InstrumentedGenerationProvider(
        base_generation_provider,
        operations_metrics,
    )
    rerank_provider = create_rerank_provider(
        runtime_settings,
        metrics=operations_metrics,
        ledger=model_usage_ledger,
    )
    rate_limiter = FixedWindowRateLimiter()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        yield
        await database.dispose()

    docs_url = "/docs" if runtime_settings.docs_enabled else None
    redoc_url = "/redoc" if runtime_settings.docs_enabled else None
    openapi_url = "/openapi.json" if runtime_settings.docs_enabled else None

    application = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        debug=runtime_settings.debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        description="Enterprise document retrieval-augmented generation API",
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.database = database
    application.state.object_storage = object_storage
    application.state.embedding_provider = embedding_provider
    application.state.generation_provider = generation_provider
    application.state.rerank_provider = rerank_provider
    application.state.model_usage_ledger = model_usage_ledger
    application.state.operations_metrics = operations_metrics
    application.state.rate_limiter = rate_limiter
    application.state.readiness_checks = {
        "application": application_check,
        "database": database.ping,
    }

    register_exception_handlers(application)
    application.add_middleware(
        RateLimitMiddleware,
        limiter=rate_limiter,
        metrics=operations_metrics,
        enabled=runtime_settings.rate_limit_enabled,
        window_seconds=runtime_settings.rate_limit_window_seconds,
        default_limit=runtime_settings.rate_limit_default_requests,
        auth_limit=runtime_settings.rate_limit_auth_requests,
        answer_limit=runtime_settings.rate_limit_answer_requests,
    )
    application.add_middleware(AuditMiddleware, database=database)
    application.add_middleware(
        RequestContextMiddleware,
        header_name=runtime_settings.request_id_header,
        metrics=operations_metrics,
    )
    application.include_router(api_router, prefix=runtime_settings.api_v1_prefix)
    application.include_router(operations_router)
    return application


app = create_app()
