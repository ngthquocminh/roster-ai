"""The SSE transport: framing, replay, cursor rejection, and the middleware path.

The repository and the site-context opener are substituted through
`dependency_overrides`, so these tests exercise the transport rather than
PostgreSQL — `test_conversations_postgres.py` owns the governed-storage side and
`test_postgres_integration.py` owns the end-to-end measurement.

Every stream in this module is made finite by having the stub raise
`ClientDisconnect` on a later poll, which is exactly the exception a real
disconnect produces. The one exception is the incremental-delivery test, which
deliberately measures *when* the first frame becomes readable.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_conversation_repository,
    get_identity_store,
    get_settings,
    get_site_context_opener,
)
from api.main import app
from application.contracts.activity import PlannerMessageActivityV1
from application.contracts.persisted_event import PersistedEventV1
from application.contracts.stream_cursor import StreamCursorV1, parse_stream_cursor
from application.ports.conversation import ConversationTimelineV1
from application.ports.session import ResolvedSession
from settings import default_settings

_SESSION_TOKEN = "opaque-session"
_CSRF_TOKEN = "csrf-token-value"
_NOW = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)

#: One body, byte for byte, for all three AC2 rejection causes.
_CURSOR_INVALID_BODY = {
    "type": "https://shiftmind.app/problems/stream_cursor_invalid",
    "title": "Stream cursor invalid",
    "status": 400,
    "detail": "The supplied stream cursor cannot be resumed.",
    "code": "stream_cursor_invalid",
}


def _event(conversation_id: UUID, sequence: int) -> PersistedEventV1:
    return PersistedEventV1(
        stream_id=conversation_id,
        sequence=Decimal(sequence),
        event_type="planner_message_accepted",
        occurred_at=_NOW,
        resource_version=sequence + 1,
        request_id=uuid4(),
        conversation_id=conversation_id,
        agent_run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=PlannerMessageActivityV1(
            activity_id=uuid4(),
            activity_type="planner_message",
            conversation_id=conversation_id,
            conversation_resource_version=sequence + 1,
            scenario_id=uuid4(),
            scenario_version_id=uuid4(),
            occurred_at=_NOW,
            message_id=uuid4(),
            text=f"message {sequence}",
        ),
    )


class _Repository:
    """Serves one known conversation; every other id is absence (AD-3).

    `polls_before_disconnect` bounds the stream: once that many `events_after`
    calls have been made, the next one raises `ClientDisconnect` — the same
    exception `StreamingResponse` raises when a real browser goes away.
    """

    def __init__(self, conversation_id: UUID, events: tuple[PersistedEventV1, ...]) -> None:
        self.conversation_id = conversation_id
        self.events = events
        self.calls: list[str] = []
        self.polls_before_disconnect = 1

    def timeline(self, _connection, *, conversation_id, limit=200):
        self.calls.append("timeline")
        if conversation_id != self.conversation_id:
            return None
        window = self.events[-limit:] if limit else ()
        return ConversationTimelineV1(
            conversation_id, 2, "agent_queued", tuple(window), limit,
            len(self.events) > limit,
        )

    def events_after(self, _connection, *, stream_id, after, limit):
        if self.calls.count("events_after") >= self.polls_before_disconnect:
            self.calls.append("events_after")
            raise ClientDisconnect()
        self.calls.append("events_after")
        if stream_id != self.conversation_id:
            return None
        return tuple(e for e in self.events if e.sequence > after)[:limit]

    def create(self, *_args, **_kwargs):  # pragma: no cover - unused here
        raise AssertionError("the stream must not create")

    def list_for_scenario(self, *_args, **_kwargs):  # pragma: no cover - unused
        raise AssertionError("the stream must not list")

    def accept_turn(self, *_args, **_kwargs):  # pragma: no cover - unused here
        raise AssertionError("the stream must not write")


@contextmanager
def _stub_site_context(_site_id):
    yield object()


@pytest.fixture()
def stream_client(tmp_path):
    conversation_id = uuid4()
    repository = _Repository(
        conversation_id, tuple(_event(conversation_id, n) for n in (1, 2, 3))
    )
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )

    class _IdentityStore:
        def resolve_session(self, _token_hash: str) -> ResolvedSession:
            return resolved

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_conversation_repository] = lambda: repository
    app.dependency_overrides[get_site_context_opener] = lambda: _stub_site_context
    try:
        with TestClient(app) as client:
            yield client, repository
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _headers(**extra: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}", **extra}


def _url(conversation_id: UUID, cursor: str | None = None) -> str:
    base = f"/api/v1/conversations/{conversation_id}/events"
    return base if cursor is None else f"{base}?last_event_id={cursor}"


def _read_stream(client, url: str, headers: dict[str, str]) -> str:
    """Drain a bounded stream to completion and return its raw body."""
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        return "".join(response.iter_text())


def _frames(body: str) -> list[str]:
    return [block for block in body.split("\n\n") if block.strip()]


# --------------------------------------------------------------------------
# Task 4 — framing and replay
# --------------------------------------------------------------------------


def test_the_stream_opens_with_a_heartbeat_then_replays_every_outstanding_event(
    stream_client,
) -> None:
    client, repository = stream_client

    body = _read_stream(client, _url(repository.conversation_id), _headers())

    blocks = _frames(body)
    # The connect heartbeat lands before anything else so a proxy sees bytes
    # ahead of any idle timeout, even on a stream with nothing outstanding.
    assert blocks[0] == ": heartbeat"
    assert len(blocks) == 4
    assert [b.splitlines()[0] for b in blocks[1:]] == [
        f"id: {repository.conversation_id}:{n}" for n in (1, 2, 3)
    ]
    assert all(b.splitlines()[1] == "event: planner_message_accepted" for b in blocks[1:])


def test_a_heartbeat_is_a_comment_and_never_carries_an_id(stream_client) -> None:
    """AD-21: heartbeats carry no ID. One that did would poison a reconnecting
    client's `Last-Event-ID` with a cursor no stream can contain."""
    client, repository = stream_client

    body = _read_stream(client, _url(repository.conversation_id), _headers())

    heartbeats = [line for line in body.splitlines() if line.startswith(":")]
    assert heartbeats
    for line in heartbeats:
        assert line == ": heartbeat"
        assert "id:" not in line
        assert "event:" not in line
        assert "data:" not in line


def test_every_frame_id_round_trips_through_the_cursor_parser(stream_client) -> None:
    """A frame whose id the parser rejects is a stream that cannot be resumed."""
    client, repository = stream_client

    body = _read_stream(client, _url(repository.conversation_id), _headers())

    ids = [
        line[len("id: "):]
        for line in body.splitlines()
        if line.startswith("id: ")
    ]
    assert len(ids) == 3
    for index, raw in enumerate(ids, start=1):
        parsed = parse_stream_cursor(raw)
        assert isinstance(parsed, StreamCursorV1)
        assert parsed.stream_id == repository.conversation_id
        assert parsed.sequence == Decimal(index)


def test_the_data_payload_is_the_same_activity_shape_the_timeline_returns(
    stream_client,
) -> None:
    """One shape, so a client can merge a replayed event and a fetched timeline
    item without a second mapper — including `sequence` as a JSON string."""
    client, repository = stream_client

    body = _read_stream(client, _url(repository.conversation_id), _headers())

    payloads = [
        line[len("data: "):]
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert len(payloads) == 3
    first = payloads[0]
    assert '"sequence":"1"' in first
    assert '"activity_type":"planner_message"' in first
    assert '"activity_id":' in first
    assert f'"conversation_id":"{repository.conversation_id}"' in first


def test_a_cursor_replays_only_strictly_greater_sequences(stream_client) -> None:
    client, repository = stream_client

    body = _read_stream(
        client,
        _url(repository.conversation_id, f"{repository.conversation_id}:2"),
        _headers(),
    )

    ids = [line for line in body.splitlines() if line.startswith("id: ")]
    assert ids == [f"id: {repository.conversation_id}:3"]


def test_a_cursor_equal_to_the_maximum_is_legal_and_replays_nothing(
    stream_client,
) -> None:
    """"Nothing outstanding" is a common, correct state — not an error."""
    client, repository = stream_client

    body = _read_stream(
        client,
        _url(repository.conversation_id, f"{repository.conversation_id}:3"),
        _headers(),
    )

    assert _frames(body) == [": heartbeat"]


def test_the_last_event_id_header_wins_over_the_query_parameter(stream_client) -> None:
    """One resolution rule, so the two paths cannot disagree. The header is what
    the browser sets on its own auto-reconnect; the query parameter is what the
    client supplies when it constructs a fresh `EventSource`."""
    client, repository = stream_client

    body = _read_stream(
        client,
        _url(repository.conversation_id, f"{repository.conversation_id}:0"),
        _headers(**{"Last-Event-ID": f"{repository.conversation_id}:2"}),
    )

    ids = [line for line in body.splitlines() if line.startswith("id: ")]
    assert ids == [f"id: {repository.conversation_id}:3"]


def test_an_unknown_conversation_keeps_the_existing_non_disclosing_404(
    stream_client,
) -> None:
    client, _ = stream_client

    response = client.get(_url(uuid4()), headers=_headers())

    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


# --------------------------------------------------------------------------
# Task 5 — one code, one body, zero queries
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cause",
    ["malformed", "foreign_stream", "beyond_maximum", "non_integral"],
)
def test_every_rejection_cause_returns_a_byte_identical_problem_response(
    stream_client, cause: str
) -> None:
    client, repository = stream_client
    conversation_id = repository.conversation_id
    cursor = {
        "malformed": "not-a-cursor",
        "foreign_stream": f"{uuid4()}:1",
        # The stream's maximum is 3; 4 is a sequence it cannot contain.
        "beyond_maximum": f"{conversation_id}:4",
        "non_integral": f"{conversation_id}:1.5",
    }[cause]

    response = client.get(_url(conversation_id, cursor), headers=_headers())

    assert response.status_code == 400
    assert response.json() == _CURSOR_INVALID_BODY
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_rejected_cursor_is_not_an_event_stream(stream_client) -> None:
    """Decision 4's mechanism. A 200 carrying an error frame would make the
    browser auto-retry forever with the same poisoned `Last-Event-ID`; a non-200
    that is not `text/event-stream` fails the source permanently, which is what
    lets the client re-establish from its own cursor."""
    client, repository = stream_client

    response = client.get(
        _url(repository.conversation_id, "not-a-cursor"), headers=_headers()
    )

    assert response.status_code != 200
    assert "text/event-stream" not in response.headers["content-type"]


def test_a_foreign_stream_cursor_is_rejected_without_touching_the_database(
    stream_client,
) -> None:
    """Decision 5, asserted as a mechanism rather than as copywriting.

    If no query is issued then no timing signal, error shape, or row count can
    disclose whether the named stream exists. The string comparison alone is
    what guarantees it.
    """
    client, repository = stream_client

    response = client.get(
        _url(repository.conversation_id, f"{uuid4()}:1"), headers=_headers()
    )

    assert response.status_code == 400
    assert repository.calls == []


def test_the_rejection_body_is_identical_across_all_four_causes(stream_client) -> None:
    client, repository = stream_client
    conversation_id = repository.conversation_id

    bodies = {
        client.get(_url(conversation_id, cursor), headers=_headers()).text
        for cursor in (
            "not-a-cursor",
            f"{uuid4()}:1",
            f"{conversation_id}:4",
            f"{conversation_id}:1.5",
        )
    }

    # A prober must not be able to tell the three AC2 causes apart.
    assert len(bodies) == 1


# --------------------------------------------------------------------------
# Task 8 — the transport, not just the handler
# --------------------------------------------------------------------------


def test_frames_arrive_incrementally_through_both_http_middleware_layers(
    stream_client,
) -> None:
    """Decision 2 rests on `BaseHTTPMiddleware.body_stream()` yielding each
    chunk as it arrives rather than accumulating the body. This asserts the
    behaviour instead of trusting it: if either `@app.middleware("http")` layer
    ever buffers, the whole feature is dead and the cause would be invisible.

    Driven at the ASGI boundary rather than through `TestClient`, deliberately.
    `TestClient`'s own transport writes every `http.response.body` message into
    one `io.BytesIO` and blocks on `response_complete` before it returns a
    response at all (`starlette/testclient.py`), so a `TestClient` read cannot
    distinguish a streamed body from a buffered one — it would report every
    frame arriving at the end even when the middleware is behaving. Observing
    the ASGI `send` messages puts the assertion exactly where the buffering
    would occur, with the real `app` object and both middleware layers active.
    """
    _, repository = stream_client
    repository.polls_before_disconnect = 4
    path = f"/api/v1/conversations/{repository.conversation_id}/events"
    chunks: list[tuple[float, bytes]] = []

    async def _drive() -> None:
        started = perf_counter()

        async def receive():
            # The client never speaks and never disconnects; the stub ends the
            # stream, so this must simply never resolve.
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")  # pragma: no cover

        async def send(message) -> None:
            if message["type"] == "http.response.body":
                chunks.append((perf_counter() - started, message.get("body", b"")))

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [
                    (b"host", b"testserver"),
                    (b"cookie", f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}".encode()),
                ],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )

    asyncio.run(_drive())

    body = b"".join(chunk for _, chunk in chunks)
    assert b"id: " in body
    # More than one body message: a buffered stack would emit exactly one.
    assert len(chunks) > 1
    first_frame_at = next(at for at, chunk in chunks if b"id: " in chunk)
    total = chunks[-1][0]
    # The generator ran for at least three poll intervals...
    assert total >= 2.0
    # ...and the first frame had already crossed the boundary long before it
    # finished, which is the property the whole feature depends on.
    assert first_frame_at < 1.0


def test_an_unauthenticated_stream_request_is_refused_before_the_body_opens(
    stream_client,
) -> None:
    """The existing middleware answers first. A client that got an empty
    `text/event-stream` here would see a silently dead stream instead of an
    authentication failure it can act on."""
    client, repository = stream_client

    response = client.get(_url(repository.conversation_id))

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert repository.calls == []


def test_the_stream_is_a_get_and_therefore_needs_no_csrf_token(stream_client) -> None:
    """`EventSource` cannot send `X-CSRF-Token`, which is precisely why this
    endpoint has to be a GET — and GET is not in `_UNSAFE_METHODS`."""
    client, repository = stream_client

    body = _read_stream(client, _url(repository.conversation_id), _headers())

    assert ": heartbeat" in body


def test_the_stream_advertises_the_origin_side_no_buffering_hints(
    stream_client,
) -> None:
    """AD-21 assumes no generic CloudFront buffering toggle, so the origin says
    what it needs. Story 6.3 proves the edge; omitting these would make that
    story's job harder for no reason."""
    client, repository = stream_client

    with client.stream(
        "GET", _url(repository.conversation_id), headers=_headers()
    ) as response:
        assert response.headers["cache-control"] == "no-cache, no-transform"
        assert response.headers["x-accel-buffering"] == "no"
        response.read()
