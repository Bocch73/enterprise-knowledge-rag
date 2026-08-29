"""Tests for the continuous deployment worker boundary."""

import asyncio
from collections import deque
from typing import cast
from uuid import UUID, uuid4

from app.cli.run_ingestion_worker import process_batch
from app.core.config import Settings
from app.db.session import Database


def test_process_batch_stops_when_the_queue_is_empty(settings: Settings) -> None:
    expected_ids = [uuid4(), uuid4()]
    remaining = deque([*expected_ids, None])
    observed: list[object] = []

    async def fake_processor(
        database: Database,
        runtime_settings: Settings,
    ) -> UUID | None:
        observed.append((database, runtime_settings))
        return remaining.popleft()

    database = cast(Database, object())
    processed = asyncio.run(
        process_batch(
            database,
            settings,
            batch_size=10,
            processor=fake_processor,
        )
    )

    assert processed == 2
    assert len(observed) == 3


def test_process_batch_respects_the_batch_size(settings: Settings) -> None:
    calls = 0

    async def fake_processor(
        _database: Database,
        _runtime_settings: Settings,
    ) -> UUID | None:
        nonlocal calls
        calls += 1
        return uuid4()

    processed = asyncio.run(
        process_batch(
            cast(Database, object()),
            settings,
            batch_size=3,
            processor=fake_processor,
        )
    )

    assert processed == 3
    assert calls == 3
