"""Observability decorators for external model providers."""

from time import perf_counter

from app.modules.generation.providers import GenerationProvider, GenerationResult
from app.modules.operations.metrics import OperationsMetrics


class InstrumentedGenerationProvider:
    """Measure model calls without adding question or document content to labels."""

    def __init__(self, delegate: GenerationProvider, metrics: OperationsMetrics) -> None:
        self._delegate = delegate
        self._metrics = metrics

    @property
    def name(self) -> str:
        return self._delegate.name

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        started = perf_counter()
        outcome = "success"
        try:
            return await self._delegate.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception:
            outcome = "error"
            raise
        finally:
            self._metrics.observe_model(
                self.name,
                outcome,
                perf_counter() - started,
            )
