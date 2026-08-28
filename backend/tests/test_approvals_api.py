"""Router-level proofs for `api/routers/approvals.py` against fake repositories.

Covers what a real database is not needed to prove: problem-code mapping
(AD-13), the feature-policy gate, HTTP idempotency replay/conflict
(Decision 4), the omission-vs-null distinction on
`expected_baseline_schedule_version` (Decision 3), and EAD-7's pure-read
"presented expired" rendering. Real persistence, RLS, and the unique-index
guards are proven against PostgreSQL in `test_approval_governance_postgres.py`.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_approval_repository,
    get_audit_writer,
    get_conversation_repository,
    get_identity_store,
    get_schedule_run_repository,
    get_settings,
    get_site_baseline_reader,
    get_site_context,
)
from api.main import app
from application.contracts.approval_binding import ApprovalBindingV1
from application.ports.schedule_run import IdempotentScheduleRunResultV1
from application.ports.session import ResolvedSession
from application.use_cases.request_approval import (
    ApprovalNotGrantedError,
    CandidateNotFoundError,
    CandidateNotPromotableError,
    RequestApprovalResultV1,
    StaleBaselineVersionError,
    StaleResourceVersionError,
)
from settings import default_settings
import api.routers.approvals as approvals_router

_SESSION_TOKEN = "approval-session"
_CSRF_TOKEN = "approval-csrf"
NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def _binding(**overrides):
    defaults = dict(
        approval_id=uuid4(), state="pending", site_id=uuid4(), action="promote_baseline",
        initiated_by_actor_id=uuid4(), decided_by_actor_id=None, conversation_id=uuid4(),
        agent_run_id=None, schedule_run_id=uuid4(), candidate_schedule_version_id=uuid4(),
        baseline_schedule_version=None, baseline_resource_version=None, parameter_hash="a" * 64,
        consequence_summary="Candidate schedule version ...", consequence_hash="b" * 64,
        policy_version="one-user-mvp-v1+abc", created_at=NOW, expires_at=NOW + timedelta(hours=1),
        request_effect_key="command:test", resource_version=1,
    )
    defaults.update(overrides)
    return ApprovalBindingV1(**defaults)


class FakeApprovals:
    def __init__(self, binding=None):
        self._binding = binding
        self.write_count = 0

    def get(self, _c, *, approval_id):
        return self._binding if self._binding and self._binding.approval_id == approval_id else None

    def list_for_schedule_run(self, _c, *, schedule_run_id):
        return (self._binding,) if self._binding and self._binding.schedule_run_id == schedule_run_id else ()

    def create_pending(self, _c, *, binding, pending_payload):
        self.write_count += 1
        self._binding = binding

    def get_pending_for_agent_run(self, _c, *, agent_run_id):
        return None


class FakeAudit:
    def __init__(self): self.items = []
    def append(self, _c, envelope): self.items.append(envelope)


class FakeConversations:
    def append_approval_request_activity(self, _c, **kw): return None
    def pause_agent_run_for_approval(self, _c, **kw): return None


class FakeBaselines:
    def get(self, _c, _site_id): return None


class FakeSchedulingRuns:
    """Raises the given error from `request_approval`'s policy gate, or
    resolves a conversation for the idempotency/success paths."""

    _UNSET = object()

    def __init__(self, *, conversation_id=_UNSET, raises=None):
        self.conversation_id = uuid4() if conversation_id is self._UNSET else conversation_id
        self.raises = raises
        self.stored: dict[str, IdempotentScheduleRunResultV1] = {}

    def get_conversation_for_run(self, _c, *, run_id, site_id):
        return self.conversation_id

    def get_run(self, *_a, **_k):
        if self.raises:
            raise self.raises
        raise AssertionError("get_run should not be reached in this fixture")

    def get_idempotent_result(self, _c, *, site_id, actor_id, operation, idempotency_key):
        return self.stored.get(idempotency_key)

    def _store_idempotent_result(self, _c, *, site_id, actor_id, operation, idempotency_key, body_hash, response_payload):
        self.stored[idempotency_key] = IdempotentScheduleRunResultV1(body_hash=body_hash, response_payload=response_payload)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    monkeypatch.setenv("ROSTERAI_MAINTENANCE_FLAG", str(tmp_path / "gate-a-maintenance"))
    session = ResolvedSession(
        app_user_id=uuid4(), site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=NOW + timedelta(hours=1),
    )

    class _IdentityStore:
        def resolve_session(self, token_hash):
            return session if token_hash == hash_secret(_SESSION_TOKEN) else None

    settings = replace(default_settings(), scheduling_baseline_enabled=True)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_audit_writer] = lambda: FakeAudit()
    app.dependency_overrides[get_conversation_repository] = lambda: FakeConversations()
    app.dependency_overrides[get_site_baseline_reader] = lambda: FakeBaselines()
    try:
        with TestClient(app) as test_client:
            yield test_client, settings, session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _auth_headers(settings):
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
    }


def _headers(settings, *, key="approve-1"):
    return {
        **_auth_headers(settings),
        "X-CSRF-Token": _CSRF_TOKEN,
        "Idempotency-Key": key,
    }


def _body(*, schedule_run_id=None, expected_resource_version=2, expected_baseline_schedule_version=None):
    return {
        "schedule_run_id": str(schedule_run_id or uuid4()),
        "expected_resource_version": expected_resource_version,
        "expected_baseline_schedule_version": expected_baseline_schedule_version,
    }


def test_rejects_a_request_when_the_feature_is_not_granted(client) -> None:
    test_client, settings, _session = client
    ungranted = replace(settings, scheduling_baseline_enabled=False)
    app.dependency_overrides[get_settings] = lambda: ungranted
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()

    response = test_client.post("/api/v1/approvals", json=_body(), headers=_headers(ungranted))

    assert response.status_code == 403
    assert response.json()["code"] == "approval_not_granted"


def test_rejects_a_request_for_a_candidate_not_visible_in_this_site(client) -> None:
    test_client, settings, _session = client
    runs = FakeSchedulingRuns(conversation_id=None)
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs

    response = test_client.post("/api/v1/approvals", json=_body(), headers=_headers(settings))

    assert response.status_code == 404
    assert response.json()["code"] == "candidate_not_found"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (CandidateNotFoundError("x"), 404, "candidate_not_found"),
        (CandidateNotPromotableError("x"), 409, "candidate_not_promotable"),
        (StaleResourceVersionError("x"), 409, "stale_resource_version"),
        (StaleBaselineVersionError("x"), 409, "stale_baseline_version"),
        (ApprovalNotGrantedError("x"), 422, "approval_not_granted"),
    ],
)
def test_maps_every_policy_refusal_to_a_distinct_stable_problem_code(
    client, error, expected_status, expected_code
) -> None:
    test_client, settings, _session = client
    approvals = FakeApprovals()
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns(raises=error)

    response = test_client.post("/api/v1/approvals", json=_body(), headers=_headers(settings))

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    # AC3: a refused request creates no approvable binding.
    assert approvals.write_count == 0


def test_rejects_an_omitted_baseline_key_distinctly_from_an_explicit_null(client) -> None:
    """Decision 3: omission and an explicit `null` must not be conflated."""
    test_client, settings, _session = client
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns(
        raises=StaleBaselineVersionError("unreachable")
    )
    body = _body()
    del body["expected_baseline_schedule_version"]

    response = test_client.post("/api/v1/approvals", json=body, headers=_headers(settings))

    assert response.status_code == 422


def test_replays_the_original_binding_for_a_repeated_idempotency_key(client) -> None:
    test_client, settings, _session = client
    binding = _binding()
    approvals = FakeApprovals()
    runs = FakeSchedulingRuns()
    calls = {"count": 0}

    def _fake_request_approval(*_a, **_k):
        calls["count"] += 1
        return RequestApprovalResultV1(binding=binding, activity=None)

    body = _body()
    original = approvals_router.request_approval
    approvals_router.request_approval = _fake_request_approval
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    try:
        first = test_client.post("/api/v1/approvals", json=body, headers=_headers(settings, key="replay-1"))
        second = test_client.post("/api/v1/approvals", json=body, headers=_headers(settings, key="replay-1"))
    finally:
        approvals_router.request_approval = original

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls["count"] == 1


def test_conflicts_on_a_changed_body_under_the_same_idempotency_key(client) -> None:
    test_client, settings, _session = client
    binding = _binding()
    runs = FakeSchedulingRuns()
    run_id = uuid4()

    def _fake_request_approval(*_a, **_k):
        return RequestApprovalResultV1(binding=binding, activity=None)

    original = approvals_router.request_approval
    approvals_router.request_approval = _fake_request_approval
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    try:
        first = test_client.post("/api/v1/approvals", json=_body(schedule_run_id=run_id, expected_resource_version=2), headers=_headers(settings, key="conflict-1"))
        second = test_client.post("/api/v1/approvals", json=_body(schedule_run_id=run_id, expected_resource_version=3), headers=_headers(settings, key="conflict-1"))
    finally:
        approvals_router.request_approval = original

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "idempotency_key_conflict"


def test_get_presents_an_overdue_pending_binding_as_expired_and_writes_nothing(client) -> None:
    binding = _binding(state="pending", expires_at=NOW - timedelta(seconds=1))
    test_client, settings, _session = client
    approvals = FakeApprovals(binding)
    app.dependency_overrides[get_approval_repository] = lambda: approvals

    response = test_client.get(f"/api/v1/approvals/{binding.approval_id}", headers=_auth_headers(settings))

    assert response.status_code == 200
    assert response.json()["state"] == "expired"
    # EAD-7: the read path is pure. The fake repository offers no update
    # method at all, so a write is structurally impossible here; this asserts
    # the stored state was never touched underneath the presentation.
    assert approvals._binding.state == "pending"
    assert approvals.write_count == 0


def test_get_presents_a_binding_still_within_its_window_as_pending(client) -> None:
    binding = _binding(state="pending", expires_at=NOW + timedelta(hours=1))
    test_client, settings, _session = client
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)

    response = test_client.get(f"/api/v1/approvals/{binding.approval_id}", headers=_auth_headers(settings))

    assert response.status_code == 200
    assert response.json()["state"] == "pending"


def test_get_returns_404_for_an_approval_not_visible_in_this_site(client) -> None:
    test_client, settings, _session = client
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()

    response = test_client.get(f"/api/v1/approvals/{uuid4()}", headers=_auth_headers(settings))

    assert response.status_code == 404
    assert response.json()["code"] == "approval_not_found"


def test_list_filters_by_schedule_run_id(client) -> None:
    binding = _binding()
    test_client, settings, _session = client
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)

    matching = test_client.get(f"/api/v1/approvals?schedule_run_id={binding.schedule_run_id}", headers=_auth_headers(settings))
    other = test_client.get(f"/api/v1/approvals?schedule_run_id={uuid4()}", headers=_auth_headers(settings))

    assert [item["approval_id"] for item in matching.json()["items"]] == [str(binding.approval_id)]
    assert other.json()["items"] == []
