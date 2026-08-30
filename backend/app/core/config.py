"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Validate all runtime configuration before the application starts."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.deepseek"),
        env_file_encoding="utf-8",
        env_prefix="RAG_",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Enterprise Knowledge RAG"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: LogLevel = "INFO"
    docs_enabled: bool = True
    request_id_header: str = "X-Request-ID"
    readiness_timeout_seconds: float = Field(default=2.0, gt=0.0, le=30.0)
    database_url: str
    test_database_url: str | None = None
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=200)
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "enterprise-knowledge-rag"
    jwt_audience: str = "enterprise-knowledge-rag-api"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    object_storage_path: Path = Path("data/objects")
    document_upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    document_max_characters: int = Field(default=5_000_000, ge=1_000)
    document_pdf_max_pages: int = Field(default=500, ge=1, le=10_000)
    document_docx_max_uncompressed_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
    )
    ingestion_max_attempts: int = Field(default=3, ge=1, le=10)
    ingestion_stale_after_seconds: int = Field(default=900, ge=30, le=86_400)
    chunk_size_characters: int = Field(default=800, ge=100, le=8_000)
    chunk_overlap_characters: int = Field(default=120, ge=0, le=2_000)
    retrieval_candidate_limit: int = Field(default=30, ge=20, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1_000)
    retrieval_evidence_min_score: float = Field(default=0.54, ge=0.0, le=1.0)
    dashscope_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "RAG_DASHSCOPE_API_KEY"),
    )
    dashscope_base_http_api_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_workspace_id: str | None = None
    dashscope_embedding_model: str = "qwen3.7-text-embedding"
    dashscope_embedding_dimensions: Literal[1024] = 1024
    dashscope_embedding_batch_size: int = Field(default=20, ge=1, le=20)
    dashscope_embedding_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    dashscope_query_instruct: str = Field(
        default=(
            "Given an enterprise knowledge-base question, retrieve passages that contain "
            "the information needed to answer it."
        ),
        min_length=10,
        max_length=500,
    )
    dashscope_rerank_base_url: str = (
        "https://ws-mr5xamdyyxdwjx02.cn-beijing.maas.aliyuncs.com/compatible-api/v1"
    )
    dashscope_rerank_model: str = "qwen3-rerank"
    dashscope_rerank_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    dashscope_rerank_instruct: str = Field(
        default=(
            "Given an enterprise knowledge-base question, retrieve passages that contain "
            "enough evidence to answer it."
        ),
        min_length=10,
        max_length=500,
    )
    dashscope_embedding_cost_cny_per_million_tokens: float = Field(
        default=0.50,
        ge=0.0,
    )
    dashscope_rerank_cost_cny_per_million_tokens: float = Field(default=0.50, ge=0.0)
    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "RAG_DEEPSEEK_API_KEY"),
    )
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    deepseek_max_output_tokens: int = Field(default=800, ge=16, le=8_000)
    deepseek_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    deepseek_prompt_cache_hit_cost_usd_per_million_tokens: float = Field(
        default=0.014,
        ge=0.0,
    )
    deepseek_prompt_cache_miss_cost_usd_per_million_tokens: float = Field(
        default=0.44,
        ge=0.0,
    )
    deepseek_output_cost_usd_per_million_tokens: float = Field(default=1.32, ge=0.0)
    answer_context_max_characters: int = Field(default=12_000, ge=1_000, le=100_000)
    external_retry_max_attempts: int = Field(default=3, ge=1, le=5)
    external_retry_base_delay_seconds: float = Field(default=0.25, ge=0.0, le=10.0)
    external_retry_max_delay_seconds: float = Field(default=2.0, ge=0.0, le=30.0)
    external_circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    external_circuit_recovery_seconds: float = Field(default=30.0, gt=0.0, le=3_600.0)
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    rate_limit_default_requests: int = Field(default=120, ge=1, le=100_000)
    rate_limit_auth_requests: int = Field(default=10, ge=1, le=10_000)
    rate_limit_answer_requests: int = Field(default=20, ge=1, le=10_000)
    embedding_cache_enabled: bool = True
    embedding_cache_max_entries: int = Field(default=512, ge=1, le=100_000)
    embedding_cache_ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    metrics_enabled: bool = True
    metrics_bearer_token: SecretStr | None = Field(default=None, min_length=32)

    @field_validator("database_url", "test_database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        """Require the SQLAlchemy Psycopg dialect used by this project."""
        if value is not None and not value.startswith("postgresql+psycopg://"):
            raise ValueError("database URL must start with postgresql+psycopg://")
        return value

    @field_validator("dashscope_base_http_api_url", "dashscope_rerank_base_url")
    @classmethod
    def validate_dashscope_base_url(cls, value: str) -> str:
        """Require an encrypted DashScope endpoint without a trailing slash."""
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("DashScope base URL must use HTTPS")
        return normalized

    @model_validator(mode="after")
    def validate_production_safety(self) -> Self:
        """Reject development-only behavior in production."""
        if self.environment == "production" and self.debug:
            raise ValueError("debug must be disabled in production")
        if self.environment == "production" and self.docs_enabled:
            raise ValueError("interactive API documentation must be disabled in production")
        if (
            self.environment == "production"
            and self.metrics_enabled
            and self.metrics_bearer_token is None
        ):
            raise ValueError("metrics must use a bearer token in production")
        if self.chunk_overlap_characters >= self.chunk_size_characters:
            raise ValueError("chunk overlap must be smaller than chunk size")
        if self.external_retry_max_delay_seconds < self.external_retry_base_delay_seconds:
            raise ValueError("external retry maximum delay must not be below the base delay")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    # Values required by the type checker are supplied by the runtime environment.
    return Settings()  # type: ignore[call-arg]
