"""Thin role-scoped adapter for one durable schedule-run job."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
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
            connection.exec_driver_sql("RESET ROLE")


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


def run_once(
    engine: Engine,
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    *,
    lease_owner: str,
    lease_seconds: int,
) -> LeaseOutcomeV1 | None:
    """Lease and advance at most one job; process supervision stays external."""
    with lease_context(engine) as lease_connection:
        return lease_and_execute_schedule_run(
            lease_connection,
            lambda site_id: runtime_context(engine, site_id),
            repository,
            scheduler,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )


__all__ = ["lease_context", "run_once", "runtime_context"]
