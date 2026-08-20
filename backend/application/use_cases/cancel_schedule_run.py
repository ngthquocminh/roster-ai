"""Versioned, idempotent cancellation for one governed schedule run."""
from __future__ import annotations

from dataclasses import dataclass
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
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_story_3_5; "
    "NOT COVERED: job_terminal_state:owned_by_story_3_5; "
    "NOT COVERED: heartbeat:owned_by_story_3_5; "
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
    )


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

    try:
        if state.status == "solver_queued":
            run_repository.cancel_queued_run(
                connection,
                run_id=run_id,
                site_id=site_id,
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
                expected_resource_version=expected_resource_version,
            )
            result = ScheduleRunCancellationV1(
                run_id,
                "cancellation_requested",
                "cancellation_requested",
                state.resource_version + 1,
            )
        elif state.status == "cancellation_requested":
            result = ScheduleRunCancellationV1(
                run_id,
                "cancellation_requested",
                "cancellation_requested",
                state.resource_version,
            )
        else:
            raise RunNotCancellableError(
                f"schedule run in {state.status} is not cancellable"
            )
    except RepositoryRunNotCancellableError as exc:
        raise RunNotCancellableError(str(exc)) from exc

    if state.status in {"solver_queued", "solver_running"}:
        run_repository.set_job_cancellation_requested(
            connection, run_id=run_id, site_id=site_id
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
