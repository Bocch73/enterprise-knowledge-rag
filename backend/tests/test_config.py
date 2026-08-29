"""Configuration validation tests."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENVIRONMENT", "staging")
    monkeypatch.setenv("RAG_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("RAG_DOCS_ENABLED", "false")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.environment == "staging"
    assert settings.log_level == "WARNING"
    assert settings.docs_enabled is False


def test_unprefixed_deepseek_key_is_loaded_as_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-secret")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "test-deepseek-secret"
    assert "test-deepseek-secret" not in repr(settings.deepseek_api_key)


def test_debug_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="debug must be disabled in production"):
        Settings(environment="production", debug=True)  # type: ignore[call-arg]


def test_interactive_documentation_is_rejected_in_production() -> None:
    with pytest.raises(
        ValidationError,
        match="interactive API documentation must be disabled in production",
    ):
        Settings(  # type: ignore[call-arg]
            environment="production",
            debug=False,
            docs_enabled=True,
            metrics_bearer_token=SecretStr("test-metrics-secret-with-more-than-32-characters"),
        )


def test_unprotected_metrics_are_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="metrics must use a bearer token in production"):
        Settings(  # type: ignore[call-arg]
            environment="production",
            debug=False,
            docs_enabled=False,
            metrics_enabled=True,
            metrics_bearer_token=None,
        )


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="chunk overlap must be smaller than chunk size"):
        Settings(  # type: ignore[call-arg]
            chunk_size_characters=200,
            chunk_overlap_characters=200,
        )


@pytest.mark.parametrize("timeout", [0, -1, 31])
def test_readiness_timeout_has_safe_bounds(timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(readiness_timeout_seconds=timeout)  # type: ignore[call-arg]
