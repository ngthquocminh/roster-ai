"""Lease and execute at most one governed schedule-run job."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager
from uuid import UUID

from application.contracts.schedule_version import ScheduleRunStatusV1
from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.execute_schedule_run import execute_schedule_run


SCOPE_CONTROLS = (
    "COVERS: roles:worker_reuses_shiftmind_runtime; "
    "NOT COVERED: events:owned_by_story_3_5; "
    "NOT COVERED: cancellation:owned_by_story_3_4; "
    "NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6"
)


@dataclass(frozen=True)
class LeaseOutcomeV1:
    job_id: UUID
    attempt_id: UUID
    schedule_run_id: UUID
    status: ScheduleRunStatusV1


RuntimeConnectionFactory = Callable[[UUID], ContextManager[Any]]


def lease_and_execute_schedule_run(
    lease_connection: Any,
    runtime_connection_factory: RuntimeConnectionFactory,
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    *,
    lease_owner: str,
    lease_seconds: int,
) -> LeaseOutcomeV1 | None:
    lease = repository.lease_next_job(
        lease_connection,
        lease_owner=lease_owner,
        lease_seconds=lease_seconds,
    )
    if lease is None:
        return None
    assert lease.job_id is not None
    assert lease.attempt_id is not None
    assert lease.schedule_run_id is not None
    assert lease.site_id is not None

    with runtime_connection_factory(lease.site_id) as runtime_connection:
        snapshot = repository.load_snapshot(
            runtime_connection,
            run_id=lease.schedule_run_id,
            site_id=lease.site_id,
        )
        if snapshot is None:
            raise ValueError("leased job references a missing run snapshot")
        if lease.cancellation_requested:
            repository.mark_running(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
            repository.finalize_run(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
                status="solver_cancelled",
                reason="cancellation_requested_before_execution",
                candidate=None,
            )
            status: ScheduleRunStatusV1 = "solver_cancelled"
        else:
            finalized = execute_schedule_run(
                repository,
                scheduler,
                runtime_connection,
                snapshot=snapshot,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
            status = finalized.status
        repository.complete_job(
            runtime_connection,
            job_id=lease.job_id,
            site_id=lease.site_id,
            fencing_epoch=lease.fencing_epoch,
        )
    return LeaseOutcomeV1(
        job_id=lease.job_id,
        attempt_id=lease.attempt_id,
        schedule_run_id=lease.schedule_run_id,
        status=status,
    )


__all__ = [
    "LeaseOutcomeV1",
    "RuntimeConnectionFactory",
    "SCOPE_CONTROLS",
    "lease_and_execute_schedule_run",
]
