"""Content-free external model call records for cost and evaluation evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

CallOutcome = Literal["success", "error", "circuit_open"]


@dataclass(frozen=True, slots=True)
class ExternalModelCall:
    """Safe metadata only; prompts, questions, documents, and credentials are excluded."""

    occurred_at: datetime
    operation: str
    provider: str
    model: str
    outcome: CallOutcome
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    attempts: int
    latency_ms: float
    estimated_cost: float | None
    currency: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class ModelUsageLedger:
    """Keep bounded per-process call evidence for the current evaluation or runtime."""

    def __init__(self, *, max_records: int = 10_000) -> None:
        if max_records <= 0:
            raise ValueError("model usage ledger bound must be positive")
        self._max_records = max_records
        self._records: list[ExternalModelCall] = []

    def record(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        outcome: CallOutcome,
        request_id: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        attempts: int,
        latency_ms: float,
        estimated_cost: float | None,
        currency: str | None,
    ) -> None:
        self._records.append(
            ExternalModelCall(
                occurred_at=datetime.now(UTC),
                operation=operation,
                provider=provider,
                model=model,
                outcome=outcome,
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                attempts=attempts,
                latency_ms=round(latency_ms, 3),
                estimated_cost=(round(estimated_cost, 10) if estimated_cost is not None else None),
                currency=currency,
            )
        )
        if len(self._records) > self._max_records:
            del self._records[: len(self._records) - self._max_records]

    def snapshot(self) -> list[ExternalModelCall]:
        return list(self._records)
