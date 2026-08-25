"""Subprocess-only runtime factory for Story 3.11's hard-kill proof."""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

from sqlalchemy import create_engine

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.contracts.schedule_version import SolverOutcomeV1, ValidationFactsV1
from worker.main import WorkerRuntimeV1


DATABASE_URL_ENV = "SHIFTMIND_WORKER_TEST_DATABASE_URL"
SLEEP_SECONDS_ENV = "SHIFTMIND_WORKER_TEST_SLEEP_SECONDS"


def successful_empty_outcome() -> SolverOutcomeV1:
    return SolverOutcomeV1(
        solver_status="OPTIMAL",
        validation_facts=ValidationFactsV1(
            horizon_minutes=1,
            workers=(),
            selected_shifts=(),
            max_hours_per_week=(),
            max_shifts_per_day=(),
            minimum_gap_minutes=0,
        ),
    )


class SlowSuccessfulScheduler:
    def solve(self, _snapshot):
        time.sleep(float(os.environ.get(SLEEP_SECONDS_ENV, "300")))
        return successful_empty_outcome()


def create_runtime() -> WorkerRuntimeV1:
    database_url = os.environ[DATABASE_URL_ENV]
    return WorkerRuntimeV1(
        engine=create_engine(database_url),
        repository=PostgresScheduleRunRepository(),
        scheduler=SlowSuccessfulScheduler(),
        settings=SimpleNamespace(
            lease_seconds=60,
            solver_wall_time_limit_seconds=1,
        ),
    )


__all__ = [
    "DATABASE_URL_ENV",
    "SLEEP_SECONDS_ENV",
    "SlowSuccessfulScheduler",
    "create_runtime",
    "successful_empty_outcome",
]
