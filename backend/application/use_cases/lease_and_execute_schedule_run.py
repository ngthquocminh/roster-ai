"""Lease and execute at most one governed schedule-run job."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager
from uuid import UUID

from application.contracts.schedule_version import ScheduleRunStatusV1
from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import (
    RunTransitionConflictError,
    ScheduleRunRepository,
)
from application.use_cases.execute_schedule_run import execute_schedule_run


SCOPE_CONTROLS = (
    "COVERS: roles:worker_reuses_shiftmind_runtime; "
    "NOT COVERED: events:owned_by_story_3_5; "
    "COVERS: cancellation:cooperative_checkpoints; "
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_story_3_5; "
    "NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6; "
    # `solver_running` now commits before the solve and is observable. The
    # remaining heartbeat debt is only the missing renew_job_lease caller.
    "NOT COVERED: heartbeat:owned_by_story_3_5 — renewal caller only; "
    # A job that fails between lease and completion stays `leased`, expires and
    # is re-leased forever — `JobStatusV1` has no terminal-failure member.
    # Story 3.5 must reopen that closed vocabulary anyway: its AC names
    # `failed` and `timed-out` as required literal states.
    "NOT COVERED: job_failure_state:owned_by_story_3_5; "
    # `lease_seconds` must exceed the solver budget or every long solve fences
    # itself out. `DEFAULT_LEASE_SECONDS` is a floor, not the ceiling AD-8
    # wants: Story 3.6's AC requires application-owned ceilings for solver time
    # and total elapsed time (epics.md:1000-1003).
    "NOT COVERED: ceilings:lease_seconds_owned_by_story_3_6"
)


@dataclass(frozen=True)
class LeaseOutcomeV1:
    job_id: UUID
    attempt_id: UUID
    schedule_run_id: UUID
    status: ScheduleRunStatusV1


RuntimeConnectionFactory = Callable[[UUID], ContextManager[Any]]


def _outcome(lease, status: ScheduleRunStatusV1) -> LeaseOutcomeV1:
    return LeaseOutcomeV1(
        job_id=lease.job_id,
        attempt_id=lease.attempt_id,
        schedule_run_id=lease.schedule_run_id,
        status=status,
    )


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

    # Transaction A is deliberately short: committing `solver_running` here
    # makes it visible to the cancellation command and releases the row lock
    # before the solve starts.
    with runtime_connection_factory(lease.site_id) as runtime_connection:
        snapshot = repository.load_snapshot(
            runtime_connection,
            run_id=lease.schedule_run_id,
            site_id=lease.site_id,
        )
        if snapshot is None:
            raise ValueError("leased job references a missing run snapshot")
        # The state read is unlocked, so a cancellation can commit between it
        # and `mark_running`'s compare-and-set. Losing that CAS is recoverable:
        # re-read once and route through the same branches. Raising instead
        # would leave the job `leased` with no terminal status for a full lease
        # period -- `JobStatusV1` has no failure member (deferred-work).
        for attempt in (1, 2):
            state = repository.get_run_state(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
            )
            if state is None:
                raise ValueError("leased job references a missing schedule run")
            if state.status == "solver_queued":
                try:
                    repository.mark_running(
                        runtime_connection,
                        run_id=lease.schedule_run_id,
                        site_id=lease.site_id,
                        fencing_epoch=lease.fencing_epoch,
                    )
                except RunTransitionConflictError:
                    if attempt == 1:
                        continue
                    raise
                break
            if state.status == "solver_running":
                # A recovered attempt under the current fencing epoch resumes
                # the already-visible run without replaying the queued->running
                # edge.
                break
            if state.status == "cancellation_requested":
                repository.finalize_run(
                    runtime_connection,
                    run_id=lease.schedule_run_id,
                    site_id=lease.site_id,
                    fencing_epoch=lease.fencing_epoch,
                    status="solver_cancelled",
                    reason="cancelled",
                    candidate=None,
                )
                repository.complete_job(
                    runtime_connection,
                    job_id=lease.job_id,
                    site_id=lease.site_id,
                    fencing_epoch=lease.fencing_epoch,
                )
                return _outcome(lease, "solver_cancelled")
            repository.complete_job(
                runtime_connection,
                job_id=lease.job_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
            return _outcome(lease, state.status)

    # Transaction B gets a fresh READ COMMITTED snapshot. A cancellation that
    # landed after A committed is therefore observed before scheduler.solve.
    with runtime_connection_factory(lease.site_id) as runtime_connection:
        state = repository.get_run_state(
            runtime_connection,
            run_id=lease.schedule_run_id,
            site_id=lease.site_id,
        )
        if state is None:
            raise ValueError("leased job references a missing schedule run")
        if state.status == "cancellation_requested":
            repository.finalize_run(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
                status="solver_cancelled",
                reason="cancelled",
                candidate=None,
            )
            status: ScheduleRunStatusV1 = "solver_cancelled"
        elif state.status == "solver_running":
            finalized = execute_schedule_run(
                repository,
                scheduler,
                runtime_connection,
                snapshot=snapshot,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
            status = finalized.status
        else:
            # Already terminal: another worker finalized this run under a newer
            # fencing epoch while our lease lapsed. Never re-solve -- FR16
            # forbids duplicate work, and a full CP-SAT solve would burn before
            # `_claim_epoch` rejected it. `complete_job` below fences us out.
            # Checkpoint 1 carries the same branch.
            status = state.status
        repository.complete_job(
            runtime_connection,
            job_id=lease.job_id,
            site_id=lease.site_id,
            fencing_epoch=lease.fencing_epoch,
        )
    return _outcome(lease, status)


__all__ = [
    "LeaseOutcomeV1",
    "RuntimeConnectionFactory",
    "SCOPE_CONTROLS",
    "lease_and_execute_schedule_run",
]
