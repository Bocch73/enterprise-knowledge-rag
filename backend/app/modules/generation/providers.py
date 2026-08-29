"""Provider-neutral text generation and the DeepSeek HTTP adapter."""

from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Normalized model output independent of one external supplier."""

    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class GenerationProvider(Protocol):
    """Small contract that lets business code swap model suppliers."""

    @property
    def name(self) -> str:
        """Return the configured public model name."""
        ...

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        """Generate one complete answer from system and user messages."""
        ...


class UnavailableGenerationProvider:
    """Keep startup healthy while reporting missing model configuration on use."""

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
    """Call DeepSeek's OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        temperature: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._transport = transport

    @property
    def name(self) -> str:
        return self._model

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
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
        return GenerationResult(
            content=content.strip(),
            model=response_model if isinstance(response_model, str) else self._model,
            prompt_tokens=_optional_int(usage, "prompt_tokens"),
            completion_tokens=_optional_int(usage, "completion_tokens"),
        )

    @staticmethod
    def _raise_provider_error(status_code: int) -> None:
        if status_code == 401:
            code = "generation_authentication_failed"
            message = "The answer-generation provider rejected its credentials"
            public_status = 503
        elif status_code == 402:
            code = "generation_quota_exhausted"
            message = "The answer-generation provider has insufficient quota"
            public_status = 503
        elif status_code == 429:
            code = "generation_rate_limited"
            message = "The answer-generation provider rate limit was reached"
            public_status = 503
        elif status_code in {400, 422}:
            code = "generation_request_rejected"
            message = "The answer-generation provider rejected the request"
            public_status = 502
        else:
            code = "generation_provider_error"
            message = "The answer-generation provider failed"
            public_status = 502 if status_code < 500 else 503
        raise AppError(code=code, message=message, status_code=public_status)


def _optional_int(value: object, key: str) -> int | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, int) else None
