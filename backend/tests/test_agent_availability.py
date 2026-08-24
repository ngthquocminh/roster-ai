"""Agent availability is config + durable evidence, never a provider probe."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_agent_runtime_factory,
    get_conversation_repository,
    get_identity_store,
    get_session,
    get_settings,
    get_site_context,
)
from api.main import app
from api.auth_security import SESSION_COOKIE_NAME
from application.contracts.activity import TerminalOutcomeActivityV1
from application.contracts.dialogue import TerminalOutcomeV1
from application.contracts.persisted_event import PersistedEventV1
from application.ports.session import ResolvedSession
from application.use_cases.agent_availability import get_agent_availability
from settings import InvalidFlagError, default_settings

_NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def _terminal_event(*, site_id: UUID, reason: str, occurred_at: datetime) -> PersistedEventV1:
    conversation_id = uuid4()
    activity = TerminalOutcomeActivityV1(
        activity_id=uuid4(),
        activity_type="terminal_outcome",
        conversation_id=conversation_id,
        conversation_resource_version=2,
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        occurred_at=occurred_at,
        outcome=TerminalOutcomeV1(status="failed", reason=reason, detail="Bounded copy."),
    )
    return PersistedEventV1(
        stream_id=conversation_id,
        sequence=Decimal(2),
        event_type="terminal_outcome",
        occurred_at=occurred_at,
        resource_version=2,
        request_id=uuid4(),
        conversation_id=conversation_id,
        agent_run_id=uuid4(),
        site_id=site_id,
        actor_id=uuid4(),
        payload=activity,
    )


class _AvailabilityRepository:
    def __init__(self, event: PersistedEventV1 | None = None) -> None:
        self.event = event
        self.site_ids: list[UUID] = []

    def latest_terminal_outcome_for_site(self, _connection, *, site_id: UUID):
        self.site_ids.append(site_id)
        if self.event is None or self.event.site_id != site_id:
            return None
        return self.event


class _IdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self.session = session

    def resolve_session(self, _token_hash: str) -> ResolvedSession:
        return self.session


def test_not_configured_is_resolved_without_a_provider_call() -> None:
    site_id = uuid4()
    repository = _AvailabilityRepository()

    def broken_factory():
        raise ValueError("model setting is invalid")

    result = get_agent_availability(
        broken_factory,
        repository,
        object(),
        site_id=site_id,
        recency_seconds=120.0,
        clock=lambda: _NOW,
    )

    assert result.available is False
    assert result.reason == "not_configured"
    assert result.observed_at == _NOW
    assert repository.site_ids == []


def test_recent_typed_provider_failure_is_site_scoped() -> None:
    site_id = uuid4()
    event = _terminal_event(
        site_id=site_id,
        reason="provider_error",
        occurred_at=_NOW - timedelta(seconds=30),
    )
    repository = _AvailabilityRepository(event)

    result = get_agent_availability(
        lambda: object(),
        repository,
        object(),
        site_id=site_id,
        recency_seconds=120.0,
        clock=lambda: _NOW,
    )

    assert result.available is False
    assert result.reason == "provider_error"
    assert result.observed_at == event.occurred_at
    assert repository.site_ids == [site_id]


def test_provider_failure_older_than_the_recency_window_does_not_latch() -> None:
    site_id = uuid4()
    repository = _AvailabilityRepository(
        _terminal_event(
            site_id=site_id,
            reason="provider_error",
            occurred_at=_NOW - timedelta(seconds=121),
        )
    )

    result = get_agent_availability(
        lambda: object(), repository, object(), site_id=site_id,
        recency_seconds=120.0, clock=lambda: _NOW,
    )

    assert result.available is True
    assert result.reason is None
    assert result.observed_at is None


def test_provider_failure_exactly_at_the_cutoff_is_not_newer_than_the_window() -> None:
    site_id = uuid4()
    repository = _AvailabilityRepository(
        _terminal_event(
            site_id=site_id,
            reason="provider_error",
            occurred_at=_NOW - timedelta(seconds=120),
        )
    )

    result = get_agent_availability(
        lambda: object(), repository, object(), site_id=site_id,
        recency_seconds=120.0, clock=lambda: _NOW,
    )

    assert result.available is True


@pytest.mark.parametrize("reason", ["invalid_output", "budget_exhausted"])
def test_non_provider_terminal_reasons_do_not_disable_agent_actions(reason: str) -> None:
    site_id = uuid4()
    repository = _AvailabilityRepository(
        _terminal_event(
            site_id=site_id,
            reason=reason,
            occurred_at=_NOW - timedelta(seconds=30),
        )
    )

    result = get_agent_availability(
        lambda: object(), repository, object(), site_id=site_id,
        recency_seconds=120.0, clock=lambda: _NOW,
    )

    assert result.available is True


def test_provider_failure_at_another_site_is_isolated() -> None:
    current_site_id = uuid4()
    repository = _AvailabilityRepository(
        _terminal_event(
            site_id=uuid4(),
            reason="provider_error",
            occurred_at=_NOW - timedelta(seconds=30),
        )
    )

    result = get_agent_availability(
        lambda: object(), repository, object(), site_id=current_site_id,
        recency_seconds=120.0, clock=lambda: _NOW,
    )

    assert result.available is True
    assert repository.site_ids == [current_site_id]


def test_agent_availability_recency_is_positive_validated(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AVAILABILITY_RECENCY_SECONDS", "0")
    with pytest.raises(InvalidFlagError, match="AGENT_AVAILABILITY_RECENCY_SECONDS"):
        default_settings()


def test_route_constructs_the_runtime_but_never_calls_run_turn() -> None:
    site_id = uuid4()
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=site_id,
        csrf_token_hash="unused",
        expires_at=_NOW + timedelta(hours=1),
    )
    repository = _AvailabilityRepository()
    constructed: list[bool] = []

    class _RuntimeThatMustNotRun:
        def run_turn(self, _request):
            raise AssertionError("availability must never call run_turn")

    def factory(**_kwargs):
        constructed.append(True)
        return _RuntimeThatMustNotRun()

    settings = replace(default_settings(), agent_availability_recency_seconds=120.0)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(session)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_conversation_repository] = lambda: repository
    app.dependency_overrides[get_agent_runtime_factory] = lambda: factory
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/agent-availability",
                params={"scenario_id": str(uuid4())},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}=opaque-session"},
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "reason": None,
        "observed_at": None,
    }
    assert constructed == [True]


def test_story_3_9_scope_declares_unimplemented_authority_and_diagnosis() -> None:
    from application.use_cases.agent_availability import SCOPE_CONTROLS

    assert "NOT COVERED: audit:owned_by_epic_4" in SCOPE_CONTROLS
    assert "NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6" in SCOPE_CONTROLS
