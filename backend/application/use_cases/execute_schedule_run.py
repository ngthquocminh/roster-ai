"""Execute one already-running governed run and preserve every terminal outcome."""
from __future__ import annotations

import threading
from typing import Any, Callable, ContextManager
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
    job_id: UUID | None = None,
    lease_seconds: int | None = None,
    runtime_connection_factory: Callable[[UUID], ContextManager[Any]] | None = None,
) -> FinalizedScheduleRunV1:
    assert snapshot.schedule_run_id is not None
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    if (
        job_id is not None
        and lease_seconds is not None
        and runtime_connection_factory is not None
    ):
        interval_seconds = max(1, lease_seconds // 3)

        def _heartbeat() -> None:
            while not heartbeat_stop.wait(interval_seconds):
                with runtime_connection_factory(site_id) as heartbeat_connection:
                    renewal = repository.renew_job_lease(
                        heartbeat_connection,
                        job_id=job_id,
                        fencing_epoch=fencing_epoch,
                        extension_seconds=lease_seconds,
                    )
                if not renewal.renewed:
                    return

        heartbeat_thread = threading.Thread(
            target=_heartbeat,
            name=f"schedule-run-heartbeat-{snapshot.schedule_run_id}",
            daemon=True,
        )
        heartbeat_thread.start()
    try:
        outcome = scheduler.solve(snapshot)
    except Exception as exc:
        outcome = SolverOutcomeV1(
            solver_status="UNKNOWN",
            reason=getattr(exc, "code", "solver_adapter_failed"),
        )
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()
    return finalize_schedule_run(
        _FencedFinalizationRepository(repository, fencing_epoch),
        connection,
        snapshot=snapshot,
        outcome=outcome,
        site_id=site_id,
    )


__all__ = ["execute_schedule_run"]
