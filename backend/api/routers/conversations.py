"""Durable conversation commands, bounded timeline reads, and the live SSE stream."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from time import monotonic
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Connection
from starlette.requests import ClientDisconnect
from starlette.responses import Response, StreamingResponse

from adapters.postgres.conversation import UnsupportedActivityPayloadError
from api.deps import (
    SiteContextOpener,
    get_conversation_repository,
    get_session,
    get_site_context,
    get_site_context_opener,
)
from api.problems import problem_response
from api.schemas import (
    AcceptedTurnOut,
    ActivityItemOut,
    ConversationCreateIn,
    ConversationListOut,
    ConversationOut,
    MessageCreateIn,
    ProblemDetailsV1,
    TimelineOut,
)
from application.contracts.persisted_event import PersistedEventV1
from application.contracts.stream_cursor import (
    StreamCursorV1,
    format_event_id,
    parse_stream_cursor,
)
from application.ports.conversation import ConversationRepository, ConversationV1
from application.ports.session import ResolvedSession
from application.use_cases.accept_turn import accept_turn

router = APIRouter(prefix="/conversations", tags=["conversations"])
_PROBLEM_RESPONSES = {401: {"model": ProblemDetailsV1}, 403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}
_STREAM_RESPONSES = {
    200: {
        "description": (
            "An SSE stream of persisted conversation activity. Each frame is "
            "`id: <stream_uuid>:<sequence>`, `event: <event_type>`, `data: "
            "<ActivityItemOut as compact JSON>`; comment-only heartbeats carry "
            "no id and are never persisted (AD-21)."
        ),
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    },
    400: {"model": ProblemDetailsV1},
    **_PROBLEM_RESPONSES,
    500: {"model": ProblemDetailsV1},
}

# Polling rather than LISTEN/NOTIFY. `LISTEN` needs a dedicated connection held
# open for the life of the subscription — the exact resource profile
# `site_context`'s docstring exists to avoid, one layer down. A short bounded
# poll against the indexed `(stream_id, sequence)` unique constraint is the
# right shape at this scale and the shape Story 3.5 reuses.
_POLL_INTERVAL_S = 1.0
# AD-21 fixes the heartbeat at 15 seconds. Deliberately not configurable: no
# requirement asks for it, and a per-deployment value would make the CloudFront/
# ALB idle-timeout proof in Story 6.3 untestable.
_HEARTBEAT_INTERVAL_S = 15.0
# One replay batch. Matched to the timeline read cap below, which is the largest
# number of activities the product renders at once.
_REPLAY_BATCH = 200
# A comment frame: no id, no event, no data, never persisted.
_HEARTBEAT = ": heartbeat\n\n"


class EventStreamResponse(StreamingResponse):
    """`StreamingResponse` that declares its media type on the class.

    FastAPI derives a route's default 200 content type from `response_class`,
    and plain `StreamingResponse` leaves `media_type` at `None` — which makes
    the published contract advertise `application/json` for a body that is
    never JSON. Setting it here is what keeps the generated schema honest.
    """

    media_type = "text/event-stream"


def _conversation(value: ConversationV1) -> ConversationOut:
    return ConversationOut(id=value.id, scenario_id=value.scenario_id, scenario_version_id=value.scenario_version_id, resource_version=value.resource_version)


def _activity(event: PersistedEventV1) -> ActivityItemOut:
    """Project one persisted envelope into its planner-visible activity item.

    `sequence` is carried down from the envelope and rendered as a string; see
    ActivityItemOut.
    """
    return ActivityItemOut(**event.payload.__dict__, sequence=str(event.sequence))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationOut, responses=_PROBLEM_RESPONSES)
def create_conversation(body: ConversationCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> ConversationOut:
    value = repository.create(connection, scenario_id=body.scenario_id, scenario_version_id=body.scenario_version_id, site_id=session.site_id, actor_id=session.app_user_id)
    # An unknown scenario, an unknown version, a version belonging to another
    # scenario, and anything owned by another site all land here with one
    # indistinguishable shape (AD-3 non-disclosure).
    if value is None:
        raise HTTPException(status_code=404)
    return _conversation(value)


@router.get("", response_model=ConversationListOut, responses=_PROBLEM_RESPONSES)
def list_conversations(scenario_id: UUID, limit: int = Query(100, ge=1, le=100), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> ConversationListOut:
    page = repository.list_for_scenario(connection, scenario_id=scenario_id, limit=limit)
    return ConversationListOut(items=[_conversation(v) for v in page.items], limit=page.limit, has_more=page.has_more)


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, response_model=AcceptedTurnOut, responses=_PROBLEM_RESPONSES)
def send_message(conversation_id: UUID, body: MessageCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> AcceptedTurnOut:
    value = accept_turn(repository, connection, conversation_id=conversation_id, site_id=session.site_id, actor_id=session.app_user_id, text=body.text)
    if value is None:
        raise HTTPException(status_code=404)
    return AcceptedTurnOut(activity=_activity(value.event), resource_version=value.resource_version, agent_run_status=value.agent_run_status, sequence=str(value.event.sequence))


@router.get("/{conversation_id}/timeline", response_model=TimelineOut, responses=_PROBLEM_RESPONSES)
def timeline(conversation_id: UUID, limit: int = Query(200, ge=1, le=200), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> TimelineOut:
    value = repository.timeline(connection, conversation_id=conversation_id, limit=limit)
    if value is None:
        raise HTTPException(status_code=404)
    return TimelineOut(conversation_id=value.conversation_id, resource_version=value.resource_version, latest_agent_run_status=value.latest_agent_run_status, items=[_activity(e) for e in value.events], limit=value.limit, has_more=value.has_more)


def _cursor_invalid() -> Response:
    """The single response for all three AC2 rejection causes.

    Malformed, foreign-stream and impossible-sequence are the same event to the
    planner and must be indistinguishable to a prober, so they share one status,
    one code and one body — byte for byte.
    """
    return problem_response(
        status=400,
        code="stream_cursor_invalid",
        title="Stream cursor invalid",
        detail="The supplied stream cursor cannot be resumed.",
    )


def _frame(event: PersistedEventV1) -> str:
    """One AD-21 SSE frame.

    The payload is built with `_activity` — the *same* projection the timeline
    returns — rather than a second one. A frame and a timeline item that drift
    apart break the client's merge silently, with no error anywhere.
    """
    return (
        f"id: {format_event_id(event.stream_id, event.sequence)}\n"
        f"event: {event.event_type}\n"
        f"data: {_activity(event).model_dump_json()}\n\n"
    )


async def _event_frames(
    *,
    repository: ConversationRepository,
    open_site_context: SiteContextOpener,
    site_id: UUID,
    stream_id: UUID,
    cursor: Decimal,
) -> AsyncIterator[str]:
    """Replay from `cursor`, then poll forward, heartbeating through idleness."""
    # Emit immediately, before any database work, so a proxy sees bytes on this
    # connection ahead of its idle timeout even when nothing is outstanding.
    yield _HEARTBEAT
    last_emitted = monotonic()

    def _poll(after: Decimal):
        # One SHORT transaction per poll, opened and closed here — never a
        # request-lifetime one. `run_in_threadpool` is what keeps this
        # synchronous SQLAlchemy call off the event loop; awaited directly it
        # would freeze every other client on every poll.
        with open_site_context(site_id) as connection:
            return repository.events_after(
                connection, stream_id=stream_id, after=after, limit=_REPLAY_BATCH
            )

    try:
        while True:
            batch = await run_in_threadpool(_poll, cursor)
            if batch is None:
                # The conversation stopped being visible to this site. End the
                # connection without saying anything about why.
                return
            for event in batch:
                # The same cursor drives the next poll and the heartbeat timer,
                # so the two cannot disagree about what has been delivered.
                cursor = event.sequence
                yield _frame(event)
                last_emitted = monotonic()
            if len(batch) == _REPLAY_BATCH:
                # A full batch means more backlog is outstanding; drain it
                # without waiting out a poll interval.
                continue
            if monotonic() - last_emitted >= _HEARTBEAT_INTERVAL_S:
                yield _HEARTBEAT
                last_emitted = monotonic()
            await asyncio.sleep(_POLL_INTERVAL_S)
    except ClientDisconnect:
        # `StreamingResponse` raises this when the client goes away. Letting the
        # generator exit is the supported pattern; a second disconnect watchdog
        # would only race it.
        return
    except UnsupportedActivityPayloadError:
        # A later story wrote an event this reader predates. Terminate this one
        # connection cleanly — never a partial frame, never a 500 mid-body.
        return
    except Exception:
        # Anything else — a lost DB connection, pool exhaustion, a malformed
        # stored payload `_frame`/`_activity` cannot render — must still end
        # the generator cleanly rather than propagate out of an async
        # generator whose response has already sent a 200. The client's
        # `EventSource` sees the connection close and reconnects from its own
        # cursor; nothing here can safely change the already-sent status.
        return


@router.get(
    "/{conversation_id}/events",
    responses=_STREAM_RESPONSES,
    response_class=EventStreamResponse,
)
async def conversation_events(
    conversation_id: UUID,
    request: Request,
    last_event_id: str | None = Query(default=None),
    session: ResolvedSession = Depends(get_session),
    repository: ConversationRepository = Depends(get_conversation_repository),
    open_site_context: SiteContextOpener = Depends(get_site_context_opener),
) -> Response:
    """Replay and follow one conversation's persisted event stream (AD-21).

    Note what this route does **not** depend on: `get_site_context`. That
    dependency holds one pooled connection inside an open transaction for the
    whole request, which is correct for a 40 ms read and an outage for a stream
    that lives for hours. The stream opens a short transaction per poll instead.
    """
    # Cursor precedence, fixed in exactly one place so the two paths cannot
    # disagree: `Last-Event-ID` wins when present. The browser sets that header
    # itself on an automatic reconnect; `?last_event_id=` is how a client passes
    # its own persisted cursor when it constructs a fresh `EventSource`, which
    # cannot set request headers at all. Absent means replay from 0.
    # An empty-but-present header (e.g. `Last-Event-ID: `) is treated the same
    # as absent, not as "present" — otherwise it would silently shadow a valid
    # query parameter and reject a connection that should have resumed.
    raw = request.headers.get("last-event-id")
    if not raw:
        raw = last_event_id

    cursor = Decimal(0)
    if raw is not None:
        parsed = parse_stream_cursor(raw)
        if not isinstance(parsed, StreamCursorV1):
            return _cursor_invalid()
        # Reject a foreign stream on the string comparison ALONE — no query is
        # issued, so no timing signal, error shape or row count can disclose
        # whether that stream exists.
        if parsed.stream_id != conversation_id:
            return _cursor_invalid()
        cursor = parsed.sequence

    def _head():
        # Reads only the URL's own authorized stream, and therefore discloses
        # nothing. `limit=1` on the tail-anchored timeline window IS the stream's
        # current maximum sequence, so one pre-flight answers both "does this
        # conversation exist for this site" and "can it contain that sequence".
        with open_site_context(session.site_id) as connection:
            return repository.timeline(
                connection, conversation_id=conversation_id, limit=1
            )

    try:
        head = await run_in_threadpool(_head)
    except UnsupportedActivityPayloadError:
        return problem_response(
            status=500,
            code="internal_error",
            title="Internal server error",
            detail="The request could not be completed.",
        )
    if head is None:
        # An unknown or cross-site conversation keeps the conversation's own
        # non-disclosure shape, unchanged from Story 2.3.
        raise HTTPException(status_code=404)

    maximum = head.events[-1].sequence if head.events else Decimal(0)
    # A cursor EQUAL to the maximum is legal and common — it means "nothing
    # outstanding". Only a cursor beyond it names a sequence this stream cannot
    # contain, which is AC2's third rejection cause.
    if cursor > maximum:
        return _cursor_invalid()

    return EventStreamResponse(
        _event_frames(
            repository=repository,
            open_site_context=open_site_context,
            site_id=session.site_id,
            stream_id=conversation_id,
            cursor=cursor,
        ),
        headers={
            # AD-21 assumes no generic CloudFront buffering toggle, so the
            # origin states its own requirements. Story 6.3 proves the edge.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
