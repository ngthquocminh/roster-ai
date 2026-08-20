from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_identity_store,
    get_schedule_run_repository,
    get_settings,
    get_site_context_opener,
)
from api.main import app
from application.contracts.activity import RunProgressActivityV1
from application.contracts.persisted_event import PersistedEventV1
from application.ports.schedule_run import ScheduleRunEventHeadV1
from application.ports.session import ResolvedSession
from settings import default_settings


_SESSION_TOKEN = "schedule-run-stream-session"


def _event(run_id: UUID, sequence: int, status="solver_running") -> PersistedEventV1:
    now = datetime.now(timezone.utc)
    activity = RunProgressActivityV1(
        activity_id=uuid4(),
        activity_type="run_progress",
        schedule_run_id=run_id,
        status=status,
        reason=None,
        resource_version=sequence,
        occurred_at=now,
    )
    return PersistedEventV1(
        stream_id=run_id,
        sequence=Decimal(sequence),
        event_type=f"run.{status.removeprefix('solver_')}.v1",
        occurred_at=now,
        resource_version=sequence,
        request_id=uuid4(),
        conversation_id=None,
        agent_run_id=None,
        schedule_run_id=run_id,
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=activity,
    )


class _Repository:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self.events = (_event(run_id, 1, "solver_queued"), _event(run_id, 2))
        self.calls: list[str] = []
        self.polls = 0

    def event_head(self, _connection, *, run_id, site_id):
        self.calls.append("head")
        if run_id != self.run_id:
            return None
        return ScheduleRunEventHeadV1(max_sequence=Decimal(2))

    def events_after(self, _connection, *, stream_id, after, limit):
        self.calls.append("events_after")
        self.polls += 1
        if self.polls > 1:
            raise ClientDisconnect()
        if stream_id != self.run_id:
            return None
        return tuple(event for event in self.events if event.sequence > after)[:limit]


@contextmanager
def _open(_site_id):
    yield object()


@pytest.fixture()
def stream_client(tmp_path):
    run_id = uuid4()
    repository = _Repository(run_id)
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret("csrf"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "maintenance"),
    )

    class _IdentityStore:
        def resolve_session(self, _token_hash):
            return session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository
    app.dependency_overrides[get_site_context_opener] = lambda: _open
    try:
        with TestClient(app) as client:
            yield client, repository
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _headers(**extra):
    return {"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}", **extra}


def _url(run_id, cursor=None):
    path = f"/api/v1/schedule-runs/{run_id}/events"
    return path if cursor is None else f"{path}?last_event_id={cursor}"


def test_run_stream_replays_only_unseen_literal_progress(stream_client) -> None:
    client, repository = stream_client
    cursor = f"{repository.run_id}:1"

    with client.stream("GET", _url(repository.run_id, cursor), headers=_headers()) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert body.startswith(": heartbeat\n\n")
    assert f"id: {repository.run_id}:2" in body
    assert f"id: {repository.run_id}:1" not in body
    assert '"activity_type":"run_progress"' in body
    assert '"schedule_run_id":"' + str(repository.run_id) + '"' in body


def test_header_cursor_wins_and_foreign_cursor_performs_zero_queries(stream_client) -> None:
    client, repository = stream_client
    response = client.get(
        _url(repository.run_id, f"{repository.run_id}:0"),
        headers=_headers(**{"Last-Event-ID": f"{uuid4()}:1"}),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "stream_cursor_invalid"
    assert repository.calls == []


@pytest.mark.parametrize("cursor", ["bad", "{run}:3", "{run}:1.5"])
def test_run_stream_rejects_every_invalid_cursor_with_one_shape(
    stream_client, cursor
) -> None:
    client, repository = stream_client
    response = client.get(
        _url(repository.run_id, cursor.format(run=repository.run_id)),
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "stream_cursor_invalid"


def test_unknown_run_uses_the_non_disclosing_not_found_shape(stream_client) -> None:
    client, _ = stream_client
    response = client.get(_url(uuid4()), headers=_headers())

    assert response.status_code == 404
    assert response.json()["code"] == "schedule_run_not_found"
