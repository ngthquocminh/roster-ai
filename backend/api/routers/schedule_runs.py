"""Versioned idempotent commands for governed schedule runs."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from api.deps import (
    get_schedule_run_repository,
    get_session,
    get_site_context,
)
from api.problems import problem_response
from api.schemas import ProblemDetailsV1, ScheduleRunCancellationIn, ScheduleRunOut
from application.ports.schedule_run import ScheduleRunRepository
from application.ports.session import ResolvedSession
from application.use_cases.cancel_schedule_run import (
    CancelScheduleRunError,
    IdempotencyKeyConflictError,
    RunNotCancellableError,
    ScheduleRunCancellationV1,
    StaleResourceVersionError,
    cancel_schedule_run,
)


router = APIRouter(prefix="/schedule-runs", tags=["schedule-runs"])
_PROBLEMS = {
    401: {"model": ProblemDetailsV1},
    403: {"model": ProblemDetailsV1},
    404: {"model": ProblemDetailsV1},
    409: {"model": ProblemDetailsV1},
    422: {"model": ProblemDetailsV1},
}
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=40)
]


def _out(value: ScheduleRunCancellationV1) -> ScheduleRunOut:
    return ScheduleRunOut(
        schedule_run_id=value.schedule_run_id,
        status=value.status,
        reason=value.reason,
        resource_version=value.resource_version,
        cancellation_requested=True,
    )


def _not_found() -> JSONResponse:
    return problem_response(
        status=404,
        code="schedule_run_not_found",
        title="Schedule run not found",
        detail="No schedule run with that identifier is visible in this site.",
    )


def _command_problem(exc: CancelScheduleRunError) -> JSONResponse:
    if isinstance(exc, IdempotencyKeyConflictError):
        return problem_response(
            status=409,
            code="idempotency_key_conflict",
            title="Idempotency key conflict",
            detail="The idempotency key was already used with a different request body.",
        )
    if isinstance(exc, StaleResourceVersionError):
        return problem_response(
            status=409,
            code="stale_resource_version",
            title="Stale resource version",
            detail=(
                f"Expected resource version {exc.expected}; current resource "
                f"version is {exc.current}."
            ),
        )
    if isinstance(exc, RunNotCancellableError):
        return problem_response(
            status=409,
            code="run_not_cancellable",
            title="Schedule run is not cancellable",
            detail="Only queued or running work can be cancelled.",
        )
    return problem_response(
        status=422,
        code="invalid_cancellation_command",
        title="Invalid cancellation command",
        detail=str(exc) or "The cancellation command could not be validated.",
    )


# The return annotation is omitted because the handler returns either the
# response model or an RFC 7807 JSONResponse problem.
@router.post(
    "/{run_id}/cancellation",
    response_model=ScheduleRunOut,
    responses=_PROBLEMS,
)
def cancel(
    run_id: UUID,
    body: ScheduleRunCancellationIn,
    idempotency_key: IdempotencyKey,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    repository: ScheduleRunRepository = Depends(get_schedule_run_repository),
):
    try:
        value = cancel_schedule_run(
            repository,
            connection,
            run_id=run_id,
            site_id=session.site_id,
            actor_id=session.app_user_id,
            expected_resource_version=body.expected_resource_version,
            idempotency_key=idempotency_key,
        )
    except CancelScheduleRunError as exc:
        return _command_problem(exc)
    if value is None:
        return _not_found()
    return _out(value)
