"""Execute one queued governed run and preserve every terminal outcome."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import SolverOutcomeV1
from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.finalize_schedule_run import (
    FinalizedScheduleRunV1,
    finalize_schedule_run,
)


def execute_schedule_run(
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    connection: Any,
    *,
    snapshot: RunSnapshotV1,
    site_id: UUID,
) -> FinalizedScheduleRunV1:
    assert snapshot.schedule_run_id is not None
    repository.mark_running(
        connection, run_id=snapshot.schedule_run_id, site_id=site_id
    )
    try:
        outcome = scheduler.solve(snapshot)
    except Exception as exc:
        outcome = SolverOutcomeV1(
            solver_status="UNKNOWN",
            reason=getattr(exc, "code", "solver_adapter_failed"),
        )
    return finalize_schedule_run(
        repository,
        connection,
        snapshot=snapshot,
        outcome=outcome,
        site_id=site_id,
    )


__all__ = ["execute_schedule_run"]
