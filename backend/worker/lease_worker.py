"""Thin role-scoped adapter for one durable schedule-run job."""
from __future__ import annotations

from contextlib import contextmanager
from math import ceil
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.lease_and_execute_schedule_run import (
    LeaseOutcomeV1,
    lease_and_execute_schedule_run,
)


@contextmanager
def lease_context(engine: Engine) -> Iterator[Connection]:
    """Open the lease-only role with statement-level commit semantics.

    The owner-held function's update must be visible before domain work opens
    its separate transaction. AUTOCOMMIT provides that boundary without
    granting the lease role any table access.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            yield connection
        finally:
            # A failed RESET must not mask the in-flight exception, and a
            # connection still holding the lease role must never go back to the
            # pool. Invalidate instead of hiding either problem.
            try:
                connection.exec_driver_sql("RESET ROLE")
            except Exception:  # noqa: BLE001
                connection.invalidate()


@contextmanager
def runtime_context(engine: Engine, site_id: UUID) -> Iterator[Connection]:
    """Open a new transactional, RLS-scoped domain connection."""
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(site_id)},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        yield connection


#: Multiple of the solver wall-time budget used when no lease duration is given.
#: Story 3.5 renews the lease while a solve is active. This multiple remains a
#: defensive floor and reduces heartbeat churn; Story 3.6 owns the real ceiling
#: (`ceilings:lease_seconds_owned_by_story_3_6`); this is only a floor that keeps
#: the default safe until it does.
LEASE_SECONDS_SOLVER_MULTIPLE = 4
MINIMUM_LEASE_SECONDS = 60


def default_lease_seconds(settings: Any) -> int:
    """Derive a lease duration that cannot be shorter than the solver budget."""
    budget = float(getattr(settings, "solver_wall_time_limit_seconds", 0.0) or 0.0)
    return max(MINIMUM_LEASE_SECONDS, ceil(budget * LEASE_SECONDS_SOLVER_MULTIPLE))


def run_once(
    engine: Engine,
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    *,
    lease_owner: str,
    lease_seconds: int,
) -> LeaseOutcomeV1 | None:
    """Lease and advance at most one job; process supervision stays external.

    `lease_seconds` must exceed the solver wall-time budget — see
    `default_lease_seconds`, which callers without their own ceiling should use.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    with lease_context(engine) as lease_connection:
        return lease_and_execute_schedule_run(
            lease_connection,
            lambda site_id: runtime_context(engine, site_id),
            repository,
            scheduler,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )


__all__ = [
    "LEASE_SECONDS_SOLVER_MULTIPLE",
    "MINIMUM_LEASE_SECONDS",
    "default_lease_seconds",
    "lease_context",
    "run_once",
    "runtime_context",
]
