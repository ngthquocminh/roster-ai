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
    "COVERS: events:literal_schedule_run_transitions; "
    "COVERS: cancellation:cooperative_checkpoints; "
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_first_story_raising_wall_time_limit; "
    "NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6; "
    # `solver_running` now commits before the solve and is observable. The
    # remaining heartbeat debt is only the missing renew_job_lease caller.
    "COVERS: heartbeat:independent_short_transaction_renewal; "
    # A job that fails between lease and completion stays `leased`, expires and
    # is re-leased forever — `JobStatusV1` has no terminal-failure member.
    # Story 3.5 must reopen that closed vocabulary anyway: its AC names
    # `failed` and `timed-out` as required literal states.
    "COVERS: job_failure_state:failed_terminal_and_not_released; "
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
    try:
        return _execute_leased_schedule_run(
            runtime_connection_factory,
            repository,
            scheduler,
            lease=lease,
            lease_seconds=lease_seconds,
        )
    except Exception:
        assert lease.job_id is not None
        assert lease.schedule_run_id is not None
        assert lease.site_id is not None
        with runtime_connection_factory(lease.site_id) as runtime_connection:
            state = repository.get_run_state(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
            )
            if state is None:
                raise
            if state.status not in {
                "solver_completed",
                "solver_infeasible",
                "solver_timed_out",
                "solver_cancelled",
                "solver_failed",
            }:
                repository.finalize_run(
                    runtime_connection,
                    run_id=lease.schedule_run_id,
                    site_id=lease.site_id,
                    fencing_epoch=lease.fencing_epoch,
                    status="solver_failed",
                    reason="job_execution_failed",
                    candidate=None,
                )
            repository.fail_job(
                runtime_connection,
                job_id=lease.job_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
        return _outcome(lease, "solver_failed")


def _execute_leased_schedule_run(
    runtime_connection_factory: RuntimeConnectionFactory,
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    *,
    lease,
    lease_seconds: int,
) -> LeaseOutcomeV1:
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
                job_id=lease.job_id,
                lease_seconds=lease_seconds,
                runtime_connection_factory=runtime_connection_factory,
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
