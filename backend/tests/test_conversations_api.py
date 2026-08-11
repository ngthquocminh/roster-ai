"""HTTP contracts for the durable-conversation write surface.

The repository is substituted through `dependency_overrides` so these tests
exercise the transport — routing, session, CSRF, status codes, and the RFC 7807
shapes — rather than PostgreSQL. `test_conversations_postgres.py` owns the
governed-storage side.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_conversation_repository,
    get_identity_store,
    get_settings,
    get_site_context,
)
from api.main import app
from application.contracts.activity import ActivityItemV1
from application.contracts.persisted_event import PersistedEventV1
from application.ports.conversation import (
    AcceptedTurnV1,
    ConversationPageV1,
    ConversationTimelineV1,
    ConversationV1,
)
from application.ports.session import ResolvedSession
from settings import default_settings

_CSRF_TOKEN = "csrf-token-value"
_SESSION_TOKEN = "opaque-session"
_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

_NOT_FOUND_BODY = {
    "type": "https://shiftmind.app/problems/resource_not_found",
    "title": "Resource not found",
    "status": 404,
    "detail": "The requested resource was not found.",
    "code": "resource_not_found",
}


class _IdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self.session = session

    def resolve_session(self, _token_hash: str) -> ResolvedSession:
        return self.session


def _event(conversation_id: UUID, scenario_id: UUID, version_id: UUID, sequence: str) -> PersistedEventV1:
    activity_id = uuid4()
    return PersistedEventV1(
        stream_id=conversation_id,
        sequence=Decimal(sequence),
        event_type="planner_message_accepted",
        occurred_at=_NOW,
        resource_version=2,
        request_id=uuid4(),
        conversation_id=conversation_id,
        agent_run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=ActivityItemV1(
            activity_id=activity_id,
            activity_type="planner_message",
            conversation_id=conversation_id,
            conversation_resource_version=2,
            scenario_id=scenario_id,
            scenario_version_id=version_id,
            occurred_at=_NOW,
            message_id=uuid4(),
            text="Check Tuesday night coverage",
        ),
    )


class _Repository:
    """Accepts exactly one known (scenario, version, conversation) triple.

    Everything else returns None, which is how the router is told to produce the
    single non-disclosing 404 — an unknown id and a foreign site are the same
    answer here by construction.
    """

    def __init__(self, scenario_id: UUID, version_id: UUID, conversation_id: UUID) -> None:
        self.scenario_id = scenario_id
        self.version_id = version_id
        self.conversation_id = conversation_id
        self.accepted: list[str] = []
        self.timeline_has_more = False

    def _conversation(self) -> ConversationV1:
        return ConversationV1(self.conversation_id, self.scenario_id, self.version_id, 2)

    def create(self, _connection, *, scenario_id, scenario_version_id, site_id, actor_id):
        if scenario_id != self.scenario_id or scenario_version_id != self.version_id:
            return None
        return self._conversation()

    def list_for_scenario(self, _connection, *, scenario_id, limit=100):
        if scenario_id != self.scenario_id:
            return ConversationPageV1((), limit, False)
        return ConversationPageV1((self._conversation(),), limit, False)

    def timeline(self, _connection, *, conversation_id, limit=200):
        if conversation_id != self.conversation_id:
            return None
        return ConversationTimelineV1(
            conversation_id,
            2,
            "agent_queued",
            (_event(conversation_id, self.scenario_id, self.version_id, "1"),),
            limit,
            self.timeline_has_more,
        )

    def accept_turn(self, _connection, *, conversation_id, site_id, actor_id, text, request_id):
        if conversation_id != self.conversation_id:
            return None
        self.accepted.append(text)
        return AcceptedTurnV1(
            _event(conversation_id, self.scenario_id, self.version_id, "9007199254740993"),
            2,
            "agent_queued",
        )


@pytest.fixture()
def conversation_client(tmp_path):
    scenario_id, version_id, conversation_id = uuid4(), uuid4(), uuid4()
    repository = _Repository(scenario_id, version_id, conversation_id)
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
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(resolved)
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_conversation_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            yield client, repository, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _headers(settings, *, csrf: bool = True) -> dict[str, str]:
    headers = {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
    }
    if csrf:
        headers["X-CSRF-Token"] = _CSRF_TOKEN
    return headers


def test_creating_a_conversation_pins_the_version_the_client_selected(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        "/api/v1/conversations",
        headers=_headers(settings),
        json={
            "scenario_id": str(repository.scenario_id),
            "scenario_version_id": str(repository.version_id),
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(repository.conversation_id),
        "scenario_id": str(repository.scenario_id),
        "scenario_version_id": str(repository.version_id),
        "resource_version": 2,
    }


def test_a_version_that_is_not_the_scenarios_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    """A foreign or unknown version must not be distinguishable from a foreign
    or unknown scenario — the whole point of resolving by identity is that the
    server never silently substitutes a different one."""
    client, repository, settings = conversation_client

    response = client.post(
        "/api/v1/conversations",
        headers=_headers(settings),
        json={
            "scenario_id": str(repository.scenario_id),
            "scenario_version_id": str(uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_post_without_a_csrf_header_is_rejected_before_the_repository(
    conversation_client,
) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings, csrf=False),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_validation_failed"
    assert repository.accepted == []


def test_post_without_a_session_is_rejected_before_the_repository(
    conversation_client,
) -> None:
    client, repository, _ = conversation_client

    response = client.post(
        "/api/v1/conversations",
        json={"scenario_id": str(repository.scenario_id), "scenario_version_id": str(repository.version_id)},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_accepted_turn_serializes_sequence_as_a_lossless_string(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 201
    body = response.json()
    # Beyond float precision: a JSON number here would round-trip wrong in the
    # browser and break AD-21's `<stream_uuid>:<sequence>` SSE id.
    assert '"sequence":"9007199254740993"' in response.text
    assert body["sequence"] == "9007199254740993"
    assert body["activity"]["sequence"] == "9007199254740993"
    assert body["agent_run_status"] == "agent_queued"


@pytest.mark.parametrize("text", ["   ", "\t\n", "　"])
def test_whitespace_only_text_is_a_422_not_a_500(conversation_client, text: str) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": text},
    )

    assert response.status_code == 422
    assert repository.accepted == []


def test_submitted_text_reaches_the_repository_stripped(conversation_client) -> None:
    client, repository, settings = conversation_client

    client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": "  Check Tuesday night coverage  "},
    )

    assert repository.accepted == ["Check Tuesday night coverage"]


def test_message_to_an_unknown_conversation_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    client, _, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{uuid4()}/messages",
        headers=_headers(settings),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_timeline_reports_its_window_and_carries_sequence_on_every_item(
    conversation_client,
) -> None:
    client, repository, settings = conversation_client
    repository.timeline_has_more = True

    response = client.get(
        f"/api/v1/conversations/{repository.conversation_id}/timeline",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is True
    assert body["limit"] == 200
    assert body["latest_agent_run_status"] == "agent_queued"
    # A read that omitted `sequence` would leave a reconnecting client with no
    # resume point, which is the whole reason the window is bounded.
    assert [item["sequence"] for item in body["items"]] == ["1"]


def test_timeline_for_an_unknown_conversation_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    client, _, settings = conversation_client

    response = client.get(
        f"/api/v1/conversations/{uuid4()}/timeline",
        headers=_headers(settings),
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_conversation_list_reports_truncation(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.get(
        f"/api/v1/conversations?scenario_id={repository.scenario_id}",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is False
    assert body["limit"] == 100
    assert [item["id"] for item in body["items"]] == [str(repository.conversation_id)]
