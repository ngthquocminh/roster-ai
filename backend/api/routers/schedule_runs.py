"""Versioned idempotent commands for governed schedule runs."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Connection

from api.deps import (
    get_schedule_run_repository,
    get_session,
    get_site_context,
    get_site_context_opener,
    SiteContextOpener,
)
from api.problems import problem_response
from api.schemas import (
    ProblemDetailsV1,
    RunProgressActivityOut,
    ScheduleRunCancellationIn,
    ScheduleRunOut,
)
from application.contracts.schedule_version import RUN_EVENT_TYPES
from application.ports.schedule_run import ScheduleRunRepository, ScheduleRunViewV1
from application.contracts.stream_cursor import StreamCursorV1, parse_stream_cursor
from api.routers.conversations import EventStreamResponse, _cursor_invalid, _event_frames
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
_STREAM_RESPONSES = {
    200: {
        # The body is an SSE byte stream, but each frame's `data:` line is one
        # `RunProgressActivityOut`. Naming the model here is what puts it in
        # the published components: it is otherwise referenced by no route, so
        # the payload this story exists to deliver reached neither
        # `frontend/openapi.json` nor the generated TypeScript, leaving Story
        # 3.7 to hand-author a type the project's conventions forbid.
        "description": (
            "Persisted schedule-run progress as resumable SSE frames. Each frame is "
            "`id: <run_uuid>:<sequence>`, `event: <event_type>`, `data: "
            "<RunProgressActivityOut as compact JSON>`; comment-only heartbeats carry "
            "no id and are not persisted."
        ),
        "model": RunProgressActivityOut,
        # Declared explicitly so the frame payload is the only schema on this
        # media type. Left to the model alone, FastAPI merges its `$ref` with
        # the response class's `type: string`, which reads as "a string that is
        # also this object".
        "content": {
            "text/event-stream": {
                "schema": {"$ref": "#/components/schemas/RunProgressActivityOut"}
            }
        },
    },
    400: {"model": ProblemDetailsV1},
    **_PROBLEMS,
    500: {"model": ProblemDetailsV1},
}


def _out(value: ScheduleRunCancellationV1) -> ScheduleRunOut:
    return ScheduleRunOut(
        schedule_run_id=value.schedule_run_id,
        status=value.status,
        reason=value.reason,
        resource_version=value.resource_version,
        cancellation_requested=value.cancellation_requested,
    )


def _view_out(value: ScheduleRunViewV1) -> ScheduleRunOut:
    return ScheduleRunOut(
        schedule_run_id=value.schedule_run_id,
        status=value.status,
        reason=value.reason,
        resource_version=value.resource_version,
        cancellation_requested=value.cancellation_requested,
        created_at=value.created_at,
        finished_at=value.finished_at,
    )


#: AD-7's five terminal statuses. A run that reaches one can emit nothing
#: further, so the stream closes rather than polling a finished aggregate
#: forever.
_TERMINAL_RUN_EVENT_TYPES = frozenset(
    (
        RUN_EVENT_TYPES["solver_completed"],
        RUN_EVENT_TYPES["solver_infeasible"],
        RUN_EVENT_TYPES["solver_timed_out"],
        RUN_EVENT_TYPES["solver_cancelled"],
        RUN_EVENT_TYPES["solver_failed"],
    )
)


def _is_terminal_run_event(event) -> bool:
    return event.event_type in _TERMINAL_RUN_EVENT_TYPES


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


@router.get(
    "/{run_id}/events",
    responses=_STREAM_RESPONSES,
    response_class=EventStreamResponse,
)
async def schedule_run_events(
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Query(default=None),
    session: ResolvedSession = Depends(get_session),
    repository: ScheduleRunRepository = Depends(get_schedule_run_repository),
    open_site_context: SiteContextOpener = Depends(get_site_context_opener),
) -> Response:
    raw = request.headers.get("last-event-id")
    if not raw:
        raw = last_event_id

    cursor = Decimal(0)
    if raw is not None:
        parsed = parse_stream_cursor(raw)
        if not isinstance(parsed, StreamCursorV1):
            return _cursor_invalid()
        if parsed.stream_id != run_id:
            return _cursor_invalid()
        cursor = parsed.sequence

    def _head():
        with open_site_context(session.site_id) as connection:
            return repository.event_head(
                connection, run_id=run_id, site_id=session.site_id
            )

    head = await run_in_threadpool(_head)
    if head is None:
        return _not_found()
    if cursor > head.max_sequence:
        return _cursor_invalid()

    return EventStreamResponse(
        _event_frames(
            repository=repository,
            open_site_context=open_site_context,
            site_id=session.site_id,
            stream_id=run_id,
            cursor=cursor,
            is_final=_is_terminal_run_event,
        ),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{run_id}",
    response_model=ScheduleRunOut,
    responses=_PROBLEMS,
)
def get_schedule_run(
    run_id: UUID,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    repository: ScheduleRunRepository = Depends(get_schedule_run_repository),
):
    value = repository.get_run(
        connection, run_id=run_id, site_id=session.site_id
    )
    if value is None:
        return _not_found()
    return _view_out(value)


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
