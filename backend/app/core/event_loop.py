"""Operating-system-specific asyncio compatibility configuration."""

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """Use the selector loop required by async Psycopg on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_selector_event_loop() -> asyncio.AbstractEventLoop:
    """Return the loop factory required by Uvicorn plus async Psycopg on Windows."""
    return asyncio.SelectorEventLoop()
