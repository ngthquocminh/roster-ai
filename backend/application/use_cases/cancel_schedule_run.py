"""Versioned, idempotent cancellation for one governed schedule run."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from application.contracts.canonical import contract_digest
from application.contracts.job_lease import MAX_IDEMPOTENCY_KEY_LENGTH
from application.contracts.schedule_version import ScheduleRunStatusV1
from application.ports.schedule_run import (
    RunNotCancellableError as RepositoryRunNotCancellableError,
    ScheduleRunRepository,
)


SCOPE_CONTROLS = (
    "COVERS: cancellation:queued_and_running; "
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_first_story_raising_wall_time_limit; "
    "COVERED AT: job_terminal_state:lease_and_execute_schedule_run; "
    "COVERED AT: heartbeat:execute_schedule_run; "
    "NOT COVERED: audit:owned_by_epic_4"
)


class CancelScheduleRunError(ValueError):
    pass


class IdempotencyKeyConflictError(CancelScheduleRunError):
    pass


class StaleResourceVersionError(CancelScheduleRunError):
    def __init__(self, expected: int, current: int) -> None:
        self.expected = expected
        self.current = current
        super().__init__(
            f"expected schedule run resource version {expected}; current is {current}"
        )


class RunNotCancellableError(CancelScheduleRunError):
    pass


@dataclass(frozen=True)
class ScheduleRunCancellationV1:
    schedule_run_id: UUID
    status: ScheduleRunStatusV1
    reason: str
    resource_version: int
    # Read back from `workflow.job_queue`, never asserted: Decision 4 permits a
    # run with no job row, where the flag genuinely does not exist. Story 3.7
    # renders this as a distinct literal state, so it has to be true.
    cancellation_requested: bool = False


def _operation(run_id: UUID) -> str:
    return f"cancel_schedule_run:{run_id}"


def _body_hash(run_id: UUID, expected_resource_version: int) -> str:
    return contract_digest(
        {
            "run_id": str(run_id),
            "expected_resource_version": expected_resource_version,
        }
    )[2]


def _from_payload(payload: dict) -> ScheduleRunCancellationV1:
    return ScheduleRunCancellationV1(
        schedule_run_id=UUID(payload["schedule_run_id"]),
        status=payload["status"],
        reason=payload["reason"],
        resource_version=payload["resource_version"],
        cancellation_requested=payload.get("cancellation_requested", True),
    )


def _resolve_lost_race(
    run_repository: ScheduleRunRepository,
    connection: Any,
    *,
    run_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    operation: str,
    idempotency_key: str,
    body_hash: str,
    expected_resource_version: int,
    exc: Exception,
) -> ScheduleRunCancellationV1 | None:
    """Decide what a zero-row compare-and-set actually means.

    The predicate combines status AND resource_version, so a lost CAS usually
    means another session moved the row -- not "this run is not cancellable".
    Under READ COMMITTED a zero-row result rather than a block proves the
    winner already COMMITTED, so both re-reads below observe it.
    """
    replayed = run_repository.get_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        # A concurrent request carrying the SAME key won. AD-8 requires the
        # replay to return the original semantic result, not this loser's 409.
        if replayed.body_hash != body_hash:
            raise IdempotencyKeyConflictError(
                "idempotency key was already used with another body"
            ) from exc
        return _from_payload(replayed.response_payload)
    current = run_repository.get_run_state(
        connection, run_id=run_id, site_id=site_id
    )
    if current is None:
        return None
    if current.resource_version != expected_resource_version:
        # Decision 9: the version moved, so the planner must re-read and retry.
        # `run_not_cancellable` is terminal for Story 3.7 and would be a lie.
        raise StaleResourceVersionError(
            expected_resource_version, current.resource_version
        ) from exc
    raise RunNotCancellableError(str(exc)) from exc


def cancel_schedule_run(
    run_repository: ScheduleRunRepository,
    connection: Any,
    *,
    run_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    expected_resource_version: int,
    idempotency_key: str,
) -> ScheduleRunCancellationV1 | None:
    if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise CancelScheduleRunError(
            f"idempotency_key must be 1..{MAX_IDEMPOTENCY_KEY_LENGTH} characters"
        )

    state = run_repository.get_run_state(
        connection, run_id=run_id, site_id=site_id
    )
    if state is None:
        return None

    operation = _operation(run_id)
    body_hash = _body_hash(run_id, expected_resource_version)
    stored = run_repository.get_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    if stored is not None:
        if stored.body_hash != body_hash:
            raise IdempotencyKeyConflictError(
                "idempotency key was already used with another body"
            )
        return _from_payload(stored.response_payload)

    if state.resource_version != expected_resource_version:
        raise StaleResourceVersionError(
            expected_resource_version, state.resource_version
        )

    if state.status not in {"solver_queued", "solver_running", "cancellation_requested"}:
        raise RunNotCancellableError(
            f"schedule run in {state.status} is not cancellable"
        )

    if state.status in {"solver_queued", "solver_running"}:
        # LOCK ORDER: job_queue BEFORE schedule_run. `finalize_run` claims the
        # job row (`_claim_epoch`) before writing the run row, and its window
        # between the two spans one INSERT per assignment. Taking the two locks
        # in the opposite order here deadlocks (40P01) against a worker
        # finalizing the same run -- discarding a completed solve, or turning
        # this command's 409 into a bare 500. Both writes live in this one
        # transaction, so a compare-and-set that loses below still rolls the
        # flag back.
        run_repository.set_job_cancellation_requested(
            connection, run_id=run_id, site_id=site_id
        )

    try:
        if state.status == "solver_queued":
            run_repository.cancel_queued_run(
                connection,
                run_id=run_id,
                site_id=site_id,
                actor_id=actor_id,
                expected_resource_version=expected_resource_version,
            )
            result = ScheduleRunCancellationV1(
                run_id, "solver_cancelled", "cancelled", state.resource_version + 1
            )
        elif state.status == "solver_running":
            run_repository.request_cancellation(
                connection,
                run_id=run_id,
                site_id=site_id,
                actor_id=actor_id,
                expected_resource_version=expected_resource_version,
            )
            result = ScheduleRunCancellationV1(
                run_id,
                "cancellation_requested",
                "cancellation_requested",
                state.resource_version + 1,
            )
        else:
            result = ScheduleRunCancellationV1(
                run_id,
                "cancellation_requested",
                "cancellation_requested",
                state.resource_version,
            )
    except RepositoryRunNotCancellableError as exc:
        return _resolve_lost_race(
            run_repository,
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=actor_id,
            operation=operation,
            idempotency_key=idempotency_key,
            body_hash=body_hash,
            expected_resource_version=expected_resource_version,
            exc=exc,
        )

    result = replace(
        result,
        cancellation_requested=run_repository.get_job_cancellation_requested(
            connection, run_id=run_id, site_id=site_id
        ),
    )

    run_repository._store_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
        body_hash=body_hash,
        response_payload={
            "schedule_run_id": str(result.schedule_run_id),
            "status": result.status,
            "reason": result.reason,
            "resource_version": result.resource_version,
            "cancellation_requested": result.cancellation_requested,
        },
    )
    return result


__all__ = [
    "CancelScheduleRunError",
    "IdempotencyKeyConflictError",
    "RunNotCancellableError",
    "SCOPE_CONTROLS",
    "ScheduleRunCancellationV1",
    "StaleResourceVersionError",
    "cancel_schedule_run",
]
