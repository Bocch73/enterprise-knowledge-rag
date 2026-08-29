"""Run a bounded local ingestion worker without Docker or Redis."""

import argparse
import asyncio

from app.core.config import get_settings
from app.core.event_loop import configure_event_loop_policy
from app.db.session import Database
from app.modules.ingestion.worker import process_next_job, recover_stale_jobs


async def run(max_jobs: int) -> int:
    settings = get_settings()
    database = Database(settings)
    processed = 0
    try:
        recovered = await recover_stale_jobs(database, settings)
        if recovered:
            print(f"Recovered {recovered} stale ingestion job(s).")
        for _index in range(max_jobs):
            job_id = await process_next_job(database, settings)
            if job_id is None:
                break
            processed += 1
            print(f"Processed ingestion job {job_id}.")
    finally:
        await database.dispose()
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued document-ingestion jobs")
    parser.add_argument("--max-jobs", type=int, default=1, choices=range(1, 101))
    arguments = parser.parse_args()
    processed = asyncio.run(run(arguments.max_jobs))
    print(f"Worker finished; processed {processed} job(s).")


if __name__ == "__main__":  # pragma: no cover - command-line entry point
    configure_event_loop_policy()
    main()
