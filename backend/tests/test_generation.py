"""DeepSeek adapter success, response validation, and safe failure mapping tests."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import AppError
from app.modules.generation.providers import DeepSeekGenerationProvider, GenerationResult


def provider_for(handler: httpx.MockTransport) -> DeepSeekGenerationProvider:
    return DeepSeekGenerationProvider(
        api_key=SecretStr("test-secret-never-sent-to-a-real-service"),
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=1,
        max_output_tokens=100,
        temperature=0.1,
        transport=handler,
    )


def generate(provider: DeepSeekGenerationProvider) -> GenerationResult:
    return asyncio.run(provider.generate(system_prompt="system", user_prompt="question"))


def test_deepseek_provider_normalizes_success_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"content": "答案 [S1]"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    result = generate(provider_for(httpx.MockTransport(handler)))

    assert result.content == "答案 [S1]"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 4


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, "generation_request_rejected"),
        (401, "generation_authentication_failed"),
        (402, "generation_quota_exhausted"),
        (422, "generation_request_rejected"),
        (429, "generation_rate_limited"),
        (500, "generation_provider_error"),
    ],
)
def test_deepseek_provider_maps_status_without_leaking_response(
    status_code: int,
    expected_code: str,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code, text="sensitive upstream details")
    )

    with pytest.raises(AppError) as captured:
        generate(provider_for(transport))

    assert captured.value.code == expected_code
    assert "sensitive" not in captured.value.message


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{}]}])
def test_deepseek_provider_rejects_invalid_or_empty_payload(payload: dict[str, object]) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))

    with pytest.raises(AppError) as captured:
        generate(provider_for(transport))

    assert captured.value.code == "generation_invalid_response"


@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_deepseek_provider_maps_network_failures(
    exception_type: type[httpx.RequestError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type("simulated network failure", request=request)

    with pytest.raises(AppError) as captured:
        generate(provider_for(httpx.MockTransport(handler)))

    expected = (
        "generation_timeout"
        if issubclass(exception_type, httpx.TimeoutException)
        else "generation_provider_unavailable"
    )
    assert captured.value.code == expected
