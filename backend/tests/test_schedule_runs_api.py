from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_identity_store,
    get_schedule_run_repository,
    get_settings,
    get_site_context,
)
from api.main import app
from application.ports.session import ResolvedSession
from application.use_cases.cancel_schedule_run import (
    CancelScheduleRunError,
    IdempotencyKeyConflictError,
    RunNotCancellableError,
    ScheduleRunCancellationV1,
    StaleResourceVersionError,
)
from settings import default_settings


_SESSION_TOKEN = "schedule-run-session"
_CSRF_TOKEN = "schedule-run-csrf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    monkeypatch.setenv(
        "ROSTERAI_MAINTENANCE_FLAG", str(tmp_path / "gate-a-maintenance")
    )
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class _IdentityStore:
        def resolve_session(self, token_hash):
            return session if token_hash == hash_secret(_SESSION_TOKEN) else None

    settings = replace(default_settings())
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_schedule_run_repository] = lambda: object()
    try:
        with TestClient(app) as test_client:
            yield test_client, settings, session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _headers(settings, *, key="cancel-1"):
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
        "X-CSRF-Token": _CSRF_TOKEN,
        "Idempotency-Key": key,
    }


def test_cancellation_route_returns_the_replayed_semantic_result(
    client, monkeypatch
) -> None:
    test_client, settings, _ = client
    run_id = uuid4()
    result = ScheduleRunCancellationV1(
        run_id, "cancellation_requested", "cancellation_requested", 4
    )
    monkeypatch.setattr(
        "api.routers.schedule_runs.cancel_schedule_run", lambda *_a, **_k: result
    )

    response = test_client.post(
        f"/api/v1/schedule-runs/{run_id}/cancellation",
        json={"expected_resource_version": 3},
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["schedule_run_id"] == str(run_id)
    assert response.json()["status"] == "cancellation_requested"
    assert response.json()["resource_version"] == 4
    assert response.json()["cancellation_requested"] is True


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    (
        (IdempotencyKeyConflictError("conflict"), 409, "idempotency_key_conflict"),
        (StaleResourceVersionError(2, 3), 409, "stale_resource_version"),
        (RunNotCancellableError("terminal"), 409, "run_not_cancellable"),
        (CancelScheduleRunError("bad"), 422, "invalid_cancellation_command"),
    ),
)
def test_cancellation_route_maps_command_problems(
    client, monkeypatch, exception, status, code
) -> None:
    test_client, settings, _ = client

    def _raise(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr("api.routers.schedule_runs.cancel_schedule_run", _raise)
    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=_headers(settings),
    )

    assert response.status_code == status
    assert response.json()["code"] == code


def test_cancellation_route_does_not_disclose_unknown_or_other_site_run(
    client, monkeypatch
) -> None:
    test_client, settings, _ = client
    monkeypatch.setattr(
        "api.routers.schedule_runs.cancel_schedule_run", lambda *_a, **_k: None
    )

    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=_headers(settings),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "schedule_run_not_found"


@pytest.mark.parametrize("key", (None, "x" * 41))
def test_cancellation_route_enforces_idempotency_header_bounds(client, key) -> None:
    test_client, settings, _ = client
    headers = _headers(settings)
    if key is None:
        headers.pop("Idempotency-Key")
    else:
        headers["Idempotency-Key"] = key

    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
