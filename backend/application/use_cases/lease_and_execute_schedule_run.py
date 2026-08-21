"""Lease and execute at most one governed schedule-run job."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager
from uuid import UUID

from application.contracts.schedule_version import ScheduleRunStatusV1
from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import (
    IllegalTransitionError,
    RunTransitionConflictError,
    ScheduleRunRepository,
    StaleLeaseError,
)
from application.use_cases.execute_schedule_run import execute_schedule_run


class FatalJobError(ValueError):
    """A leased job that cannot succeed however many times it is replayed.

    Distinct from a bare `ValueError` so the retry classification below is a
    decision the raiser makes explicitly, not one inferred from an exception
    type shared with `StaleLeaseError` and friends.
    """


#: Deterministic causes: replaying the job reproduces them exactly, so the
#: attempt is worth ending permanently rather than re-leasing forever at the
#: head of the queue (`deferred-work.md:291`, the defect terminal `failed` was
#: added for). Everything else -- a dropped connection, a saturated pool, a
#: serialization failure, a blip on commit -- is transient: the job is left
#: `leased`, its lease lapses, and `lease_next_job` recovers and recomputes it,
#: which is AD-6's stated model ("unique effect keys make expired-worker
#: recomputation harmless"). Marking those `failed` would discard a run the
#: system is designed to retry, and Transaction B commits `finalize_run` and
#: `complete_job` together, so a transient failure there rolls back an already
#: successful solve.
_FATAL_EXECUTION_ERRORS = (
    FatalJobError,
    RunTransitionConflictError,
    IllegalTransitionError,
)

_TERMINAL_STATUSES = frozenset(
    (
        "solver_completed",
        "solver_infeasible",
        "solver_timed_out",
        "solver_cancelled",
        "solver_failed",
    )
)


SCOPE_CONTROLS = (
    "COVERS: roles:worker_reuses_shiftmind_runtime; "
    "COVERS: events:literal_schedule_run_transitions; "
    "COVERS: cancellation:cooperative_checkpoints; "
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_first_story_raising_wall_time_limit; "
    "COVERS: contracts:capability_version_persisted_on_job_lease; "
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
    "COVERS: ceilings:lease_seconds_validated_at_process_start"
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
    except StaleLeaseError:
        # Our fence is already lost: another worker re-leased this job under a
        # newer epoch and owns its outcome. Every write we could attempt would
        # be rejected by that same epoch check, so stand down rather than
        # fabricate a terminal state for a run we no longer control.
        raise
    except Exception as exc:
        if not isinstance(exc, _FATAL_EXECUTION_ERRORS):
            # Transient (dropped connection, saturated pool, serialization
            # failure, a blip on commit). Leave the job `leased` so its lease
            # lapses and `lease_next_job` recovers it -- AD-6's stated model.
            # Marking it terminal `failed` would permanently discard work the
            # system is built to retry: Transaction B commits `finalize_run`
            # and `complete_job` together, so a transient failure there rolls
            # back an already successful solve, and `failed` is an absorbing
            # state no worker ever re-selects.
            raise
        assert lease.job_id is not None
        assert lease.schedule_run_id is not None
        assert lease.site_id is not None
        status = _record_fatal_failure(
            runtime_connection_factory, repository, lease=lease, cause=exc
        )
        return _outcome(lease, status)


def _record_fatal_failure(
    runtime_connection_factory: RuntimeConnectionFactory,
    repository: ScheduleRunRepository,
    *,
    lease,
    cause: BaseException,
) -> ScheduleRunStatusV1:
    """End a permanently-failed attempt without ever masking `cause`."""
    try:
        with runtime_connection_factory(lease.site_id) as runtime_connection:
            state = repository.get_run_state(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
            )
            if state is None:
                raise cause
            status: ScheduleRunStatusV1 = state.status
            if state.status not in _TERMINAL_STATUSES:
                if state.status == "cancellation_requested":
                    # An acknowledged cancellation must not be rewritten as a
                    # failure. The run produced no result and the planner asked
                    # for it to stop, so `solver_cancelled` is the honest
                    # terminal. `_FINALIZE_EXPECTED_STATUSES` admits
                    # `cancellation_requested` as a source for both, so the CAS
                    # would succeed either way -- the choice belongs here.
                    status, reason = "solver_cancelled", "cancelled"
                else:
                    status, reason = "solver_failed", "job_execution_failed"
                repository.finalize_run(
                    runtime_connection,
                    run_id=lease.schedule_run_id,
                    site_id=lease.site_id,
                    fencing_epoch=lease.fencing_epoch,
                    status=status,
                    reason=reason,
                    candidate=None,
                    request_id=lease.attempt_id,
                )
            repository.fail_job(
                runtime_connection,
                job_id=lease.job_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
            )
            return status
    except BaseException as recovery_error:
        if recovery_error is cause:
            raise
        # The recovery write lost its own race -- typically the fence moved
        # between the original failure and this attempt. Surfacing that instead
        # of `cause` would hide the failure that actually happened, so re-raise
        # the original with this one attached.
        raise cause from recovery_error


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
            raise FatalJobError("leased job references a missing run snapshot")
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
                raise FatalJobError("leased job references a missing schedule run")
            if state.status == "solver_queued":
                try:
                    repository.mark_running(
                        runtime_connection,
                        run_id=lease.schedule_run_id,
                        site_id=lease.site_id,
                        fencing_epoch=lease.fencing_epoch,
                        request_id=lease.attempt_id,
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
                    request_id=lease.attempt_id,
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
            raise FatalJobError("leased job references a missing schedule run")
        if state.status == "cancellation_requested":
            repository.finalize_run(
                runtime_connection,
                run_id=lease.schedule_run_id,
                site_id=lease.site_id,
                fencing_epoch=lease.fencing_epoch,
                status="solver_cancelled",
                reason="cancelled",
                candidate=None,
                request_id=lease.attempt_id,
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
                request_id=lease.attempt_id,
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
    "FatalJobError",
    "LeaseOutcomeV1",
    "RuntimeConnectionFactory",
    "SCOPE_CONTROLS",
    "lease_and_execute_schedule_run",
]
