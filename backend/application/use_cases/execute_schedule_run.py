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


class _FencedFinalizationRepository:
    """Inject the lease epoch without widening the frozen finalizer use case."""

    def __init__(self, repository: ScheduleRunRepository, fencing_epoch: int) -> None:
        self._repository = repository
        self._fencing_epoch = fencing_epoch

    def finalize_run(self, connection: Any, **values) -> None:
        self._repository.finalize_run(
            connection, fencing_epoch=self._fencing_epoch, **values
        )


def execute_schedule_run(
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    connection: Any,
    *,
    snapshot: RunSnapshotV1,
    site_id: UUID,
    fencing_epoch: int,
) -> FinalizedScheduleRunV1:
    assert snapshot.schedule_run_id is not None
    repository.mark_running(
        connection,
        run_id=snapshot.schedule_run_id,
        site_id=site_id,
        fencing_epoch=fencing_epoch,
    )
    try:
        outcome = scheduler.solve(snapshot)
    except Exception as exc:
        outcome = SolverOutcomeV1(
            solver_status="UNKNOWN",
            reason=getattr(exc, "code", "solver_adapter_failed"),
        )
    return finalize_schedule_run(
        _FencedFinalizationRepository(repository, fencing_epoch),
        connection,
        snapshot=snapshot,
        outcome=outcome,
        site_id=site_id,
    )


__all__ = ["execute_schedule_run"]
