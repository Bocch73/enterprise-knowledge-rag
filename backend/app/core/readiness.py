"""Readiness checks for dependencies required to serve traffic."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

ReadinessCheck = Callable[[], Awaitable[None]]
CheckState = Literal["up", "down"]

logger = logging.getLogger(__name__)


async def application_check() -> None:
    """A minimal check proving the event loop can execute application code."""


async def run_readiness_checks(
    checks: Mapping[str, ReadinessCheck], *, timeout_seconds: float
) -> dict[str, CheckState]:
    """Run checks independently so one failure does not hide other results."""
    results: dict[str, CheckState] = {}
    for check_name, check in checks.items():
        try:
            await asyncio.wait_for(check(), timeout=timeout_seconds)
            results[check_name] = "up"
        except Exception:
            logger.exception("readiness_check_failed", extra={"check_name": check_name})
            results[check_name] = "down"
    return results
