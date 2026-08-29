"""Run the database-backed ingestion worker continuously."""

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.event_loop import configure_event_loop_policy
from app.core.logging import configure_logging
from app.db.session import Database
from app.modules.ingestion.worker import process_next_job, recover_stale_jobs

logger = logging.getLogger(__name__)
JobProcessor = Callable[[Database, Settings], Awaitable[UUID | None]]


async def process_batch(
    database: Database,
    settings: Settings,
    *,
    batch_size: int,
    processor: JobProcessor = process_next_job,
) -> int:
    """Process at most one bounded batch and return the completed claim count."""
    processed = 0
    for _index in range(batch_size):
        job_id = await processor(database, settings)
        if job_id is None:
            break
        processed += 1
        logger.info("ingestion_job_processed", extra={"job_id": str(job_id)})
    return processed


async def run_forever(settings: Settings, *, poll_interval_seconds: float, batch_size: int) -> None:
    """Poll for work until the container runtime requests shutdown."""
    database = Database(settings)
    try:
        recovered = await recover_stale_jobs(database, settings)
        if recovered:
            logger.warning("stale_ingestion_jobs_recovered", extra={"count": recovered})
        while True:
            processed = await process_batch(database, settings, batch_size=batch_size)
            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)
    finally:
        await database.dispose()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the continuous ingestion worker")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=10)
    arguments = parser.parse_args()
    if not 0.1 <= arguments.poll_interval_seconds <= 60:
        parser.error("--poll-interval-seconds must be between 0.1 and 60")
    if not 1 <= arguments.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")
    return arguments


def main() -> None:
    configure_event_loop_policy()
    settings = get_settings()
    configure_logging(settings.log_level)
    arguments = parse_arguments()
    try:
        asyncio.run(
            run_forever(
                settings,
                poll_interval_seconds=arguments.poll_interval_seconds,
                batch_size=arguments.batch_size,
            )
        )
    except KeyboardInterrupt:
        logger.info("ingestion_worker_stopped")


if __name__ == "__main__":  # pragma: no cover - command-line entry point
    main()
