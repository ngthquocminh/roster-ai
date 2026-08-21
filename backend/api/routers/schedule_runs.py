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
    get_capability_registry,
    get_catalogue_reader,
    get_proposal_repository,
    get_schedule_run_repository,
    get_session,
    get_site_context,
    get_site_context_opener,
    get_settings,
    CapabilityComposer,
    SiteContextOpener,
)
from api.problems import problem_response
from api.schemas import (
    ProblemDetailsV1,
    RunProgressActivityOut,
    ScheduleRunCancellationIn,
    ScheduleRunOut,
    ScheduleRunStartIn,
    ScheduleRunStartOut,
)
from application.capabilities.installed import enabled_feature_policy
from application.capabilities.registry import (
    CapabilityGrantContextV1,
    PLANNER_ROLE,
    resolve_granted_capability,
)
from application.capabilities.scheduling_optimize import (
    CAPABILITY_NAME as OPTIMIZE_CAPABILITY_NAME,
    SchedulingOptimizeDepsV1,
    SchedulingOptimizeRequestV1,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.schedule_version import RUN_EVENT_TYPES
from application.ports.schedule_run import ScheduleRunRepository, ScheduleRunViewV1
from application.ports.proposal import ProposalRepository
from application.ports.scenario_catalogue import ScenarioCatalogueReader
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
from application.use_cases.create_run_snapshot import SnapshotCreationError
from application.use_cases.enqueue_compute import (
    EnqueueComputeError,
    IdempotencyKeyConflictError as EnqueueIdempotencyKeyConflictError,
    SiteConcurrencyExhaustedError,
    StaleProposalResourceVersionError,
    enqueue_compute,
)
from settings import Settings


router = APIRouter(prefix="/schedule-runs", tags=["schedule-runs"])
_PROBLEMS = {
    401: {"model": ProblemDetailsV1},
    403: {"model": ProblemDetailsV1},
    404: {"model": ProblemDetailsV1},
    409: {"model": ProblemDetailsV1},
    422: {"model": ProblemDetailsV1},
}
_START_PROBLEMS = {**_PROBLEMS, 429: {"model": ProblemDetailsV1}}
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


def _start_problem(exc: Exception) -> JSONResponse:
    if isinstance(exc, SiteConcurrencyExhaustedError):
        return problem_response(
            status=429,
            code="site_concurrency_exhausted",
            title="Site run limit reached",
            detail="This site is at its concurrent run limit. Try again shortly.",
        )
    if isinstance(exc, EnqueueIdempotencyKeyConflictError):
        return problem_response(
            status=409,
            code="idempotency_key_conflict",
            title="Idempotency key conflict",
            detail="The idempotency key was already used with a different request body.",
        )
    if isinstance(exc, SnapshotCreationError) and exc.code == "stale_proposal":
        return problem_response(
            status=409,
            code="stale_proposal",
            title="Proposal is stale",
            detail="The proposal's expected scenario or baseline version is no longer current.",
        )
    if isinstance(exc, StaleProposalResourceVersionError):
        return problem_response(
            status=409,
            code="stale_resource_version",
            title="Stale resource version",
            detail=(
                f"Expected resource version {exc.expected}; current resource "
                f"version is {exc.current}."
            ),
        )
    return problem_response(
        status=422,
        code="invalid_run_command",
        title="Invalid run command",
        detail=str(exc) or "The run command could not be validated.",
    )


@router.post(
    "",
    response_model=ScheduleRunStartOut,
    responses=_START_PROBLEMS,
)
def start_schedule_run(
    body: ScheduleRunStartIn,
    idempotency_key: IdempotencyKey,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    compose_capabilities: CapabilityComposer = Depends(get_capability_registry),
    proposal_repository: ProposalRepository = Depends(get_proposal_repository),
    scenario_catalogue: ScenarioCatalogueReader = Depends(get_catalogue_reader),
    run_repository: ScheduleRunRepository = Depends(get_schedule_run_repository),
):
    granted = compose_capabilities(
        CapabilityGrantContextV1(
            role=PLANNER_ROLE,
            site_id=session.site_id,
            feature_policy=enabled_feature_policy(settings),
            conversation_id=None,
            conversation_site_id=session.site_id,
            explicit_run_request=True,
        )
    )
    module = resolve_granted_capability(granted, OPTIMIZE_CAPABILITY_NAME)
    if module is None:
        return problem_response(
            status=403,
            code="compute_not_granted",
            title="Optimization is not available",
            detail="Current policy does not grant optimization for this request.",
        )
    validated = module.handler(
        SchedulingOptimizeDepsV1(
            actor_id=session.app_user_id,
            site_id=session.site_id,
            remaining_budget=AgentBudgetV1(
                tool_calls_limit=settings.agent_runtime_tool_calls_limit
            ),
        ),
        SchedulingOptimizeRequestV1(
            proposal_id=body.proposal_id,
            expected_resource_version=body.expected_resource_version,
            idempotency_key=idempotency_key,
        ),
        module.manifest,
    )
    try:
        result = enqueue_compute(
            proposal_repository,
            scenario_catalogue,
            run_repository,
            connection,
            proposal_id=validated.proposal_id,
            site_id=validated.site_id,
            actor_id=validated.actor_id,
            expected_proposal_resource_version=validated.expected_resource_version,
            idempotency_key=validated.idempotency_key,
            settings=settings,
        )
    except (EnqueueComputeError, SnapshotCreationError) as exc:
        return _start_problem(exc)
    return ScheduleRunStartOut(
        schedule_run_id=result.schedule_run_id,
        status="solver_queued",
        resource_version=1,
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
