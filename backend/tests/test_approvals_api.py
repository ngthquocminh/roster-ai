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
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_approval_repository,
    get_audit_reader,
    get_audit_writer,
    get_clock,
    get_conversation_repository,
    get_identity_store,
    get_llm_provider,
    get_membership_reader,
    get_schedule_run_repository,
    get_settings,
    get_site_baseline_reader,
    get_site_baseline_writer,
    get_site_context,
)
from api.main import app
from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.evidence_ref import EvidenceRefV1
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
from application.ports.conversation import AgentRunNotQueuedError
from application.use_cases.decide_approval import (
    ApprovalNotFoundError as DecisionApprovalNotFoundError,
    ApprovalNotGrantedError as DecisionApprovalNotGrantedError,
    ApprovalNotPendingError,
    DecisionResultV1,
    StaleResourceVersionError as DecisionStaleResourceVersionError,
)
from application.use_cases.promote_baseline import BaselineConcurrentlyMovedError
from settings import default_settings
import api.routers.approvals as approvals_router

_SESSION_TOKEN = "approval-session"
_CSRF_TOKEN = "approval-csrf"
# A FIXED instant, injected through `get_clock`. These tests previously pinned
# `NOW` to a literal calendar date while the router read `datetime.now()`
# inline, so the expiry-boundary pair passed or failed purely on what time of
# day the suite ran -- and did go red once real time passed NOW + 1h.
NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def _binding(**overrides):
    defaults = dict(
        approval_id=uuid4(), state="pending", site_id=uuid4(), action="promote_baseline",
        initiated_by_actor_id=uuid4(), decided_by_actor_id=None, conversation_id=uuid4(),
        agent_run_id=None, schedule_run_id=uuid4(), candidate_schedule_version_id=uuid4(),
        scenario_version_id=uuid4(), baseline_schedule_version=None, baseline_resource_version=None, parameter_hash="a" * 64,
        consequence_summary="Candidate schedule version ...", consequence_hash="b" * 64,
        policy_version="one-user-mvp-v1+abc", created_at=NOW, expires_at=NOW + timedelta(hours=1),
        request_effect_key="command:test", resource_version=1,
    )
    defaults.update(overrides)
    return ApprovalBindingV1(**defaults)


class FakeApprovals:
    def __init__(self, binding=None, pending_payload=None):
        self._binding = binding
        self._pending_payload = pending_payload
        self.write_count = 0

    def get(self, _c, *, approval_id, site_id):
        return self._binding if self._binding and self._binding.approval_id == approval_id else None

    def list_for_schedule_run(self, _c, *, schedule_run_id, site_id):
        return (self._binding,) if self._binding and self._binding.schedule_run_id == schedule_run_id else ()

    def create_pending(self, _c, *, binding, pending_payload):
        self.write_count += 1
        self._binding = binding

    def get_pending_for_agent_run(self, _c, *, agent_run_id, site_id):
        return None

    def get_pending_payload(self, _c, *, approval_id, site_id):
        return self._pending_payload

    def terminalize(self, _c, **kwargs):
        if self._binding is None or self._binding.state != "pending" or self._binding.resource_version != kwargs["expected_resource_version"]:
            return None
        self._binding = replace(self._binding, state=kwargs["state"], decided_by_actor_id=kwargs["decided_by_actor_id"], decided_at=kwargs["decided_at"], resource_version=self._binding.resource_version + 1)
        return self._binding


class FakeAudit:
    def __init__(self): self.items = []
    def append(self, _c, envelope): self.items.append(envelope)


class FakeConversations:
    def append_approval_request_activity(self, _c, **kw): return None
    def pause_agent_run_for_approval(self, _c, **kw): return None
    def cancel_agent_run_for_approval(self, _c, **kw): return None


class FakeBaselines:
    def get(self, _c, _site_id): return None


class FakeSchedulingRuns:
    """Raises the given error from `request_approval`'s policy gate, or
    resolves a conversation for the idempotency/success paths."""

    _UNSET = object()

    def __init__(self, *, conversation_id=_UNSET, raises=None, candidate=None, candidate_raises=None):
        self.conversation_id = uuid4() if conversation_id is self._UNSET else conversation_id
        self.raises = raises
        self.candidate = candidate
        self.candidate_raises = candidate_raises
        self.candidate_calls = []
        self.stored: dict[str, IdempotentScheduleRunResultV1] = {}

    def get_conversation_for_run(self, _c, *, run_id, site_id):
        return self.conversation_id

    def get_run(self, *_a, **_k):
        if self.raises:
            raise self.raises
        raise AssertionError("get_run should not be reached in this fixture")

    def get_candidate(self, _c, **kwargs):
        self.candidate_calls.append(kwargs)
        if self.candidate_raises is not None:
            raise self.candidate_raises
        return self.candidate

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
    app.dependency_overrides[get_site_baseline_writer] = lambda: object()
    app.dependency_overrides[get_membership_reader] = lambda: object()
    app.dependency_overrides[get_clock] = lambda: NOW
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


def test_decision_stale_response_returns_409_after_the_terminal_write(client, monkeypatch):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    approvals = FakeApprovals(binding)
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    def terminal(*_a, **kwargs):
        updated = approvals.terminalize(None, approval_id=binding.approval_id, site_id=session.site_id, state="stale", decided_by_actor_id=session.app_user_id, decided_at=NOW, expected_resource_version=binding.resource_version)
        return DecisionResultV1("stale", updated, None, {"policy_version": "old"}, {"policy_version": "new"})
    monkeypatch.setattr(approvals_router, "decide_approval", terminal)
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decide-stale"), json={"decision": "approve", "expected_resource_version": 1})
    assert response.status_code == 409 and response.json()["code"] == "approval_stale"
    assert approvals._binding.state == "stale"


def test_valid_approve_returns_the_consumed_binding(client, monkeypatch):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    approvals = FakeApprovals(binding)
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()

    def consumed(*_a, **_kwargs):
        updated = replace(
            binding, state="consumed", decided_by_actor_id=session.app_user_id,
            decided_at=NOW, consumed_at=NOW, resource_version=2,
        )
        approvals._binding = updated
        return DecisionResultV1("consumed", updated, None, {}, {})

    monkeypatch.setattr(approvals_router, "decide_approval", consumed)
    response = test_client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_headers(settings, key="decide-consumed"),
        json={"decision": "approve", "expected_resource_version": 1},
    )
    assert response.status_code == 200 and response.json()["state"] == "consumed"


def test_rollback_conflict_maps_stale_baseline_with_literal_context(client, monkeypatch):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    error = BaselineConcurrentlyMovedError(
        "lost baseline CAS",
        expected={"baseline_schedule_version": "baseline-v12"},
        current={"baseline_schedule_version": "baseline-v13"},
    )
    monkeypatch.setattr(
        approvals_router, "decide_approval",
        lambda *_a, **_k: (_ for _ in ()).throw(error),
    )
    response = test_client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_headers(settings, key="lost-baseline"),
        json={"decision": "approve", "expected_resource_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "stale_baseline_version"
    assert response.json()["expected"] == {"baseline_schedule_version": "baseline-v12"}
    assert response.json()["current"] == {"baseline_schedule_version": "baseline-v13"}


def test_approval_openapi_has_no_temporary_promotion_503_contract(client):
    test_client, _settings, _session = client
    document = test_client.get("/openapi.json").json()
    approval_paths = {
        path: operations for path, operations in document["paths"].items()
        if path.startswith("/api/v1/approvals")
    }
    rendered = str(approval_paths)
    assert "promotion_not_available" not in rendered
    assert all("503" not in operation.get("responses", {}) for operations in approval_paths.values() for operation in operations.values())


def test_decision_replay_returns_its_original_terminal_binding(client, monkeypatch):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    approvals = FakeApprovals(binding)
    runs = FakeSchedulingRuns()
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    def terminal(*_a, **_kwargs):
        updated = approvals.terminalize(None, approval_id=binding.approval_id, site_id=session.site_id, state="rejected", decided_by_actor_id=session.app_user_id, decided_at=NOW, expected_resource_version=1)
        return DecisionResultV1("rejected", updated, None, {}, {})
    monkeypatch.setattr(approvals_router, "decide_approval", terminal)
    body = {"decision": "reject", "expected_resource_version": 1}
    first = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decide-replay"), json=body)
    second = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decide-replay"), json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()["state"] == "rejected"


@pytest.mark.parametrize(
    ("error", "status", "code", "has_context"),
    [
        (DecisionApprovalNotFoundError("x"), 404, "approval_not_found", False),
        (ApprovalNotPendingError("x", expected={"state": "pending"}, current={"state": "rejected"}), 409, "approval_not_pending", True),
        (DecisionStaleResourceVersionError("x", expected={"resource_version": 1}, current={"resource_version": 2}), 409, "stale_resource_version", True),
        (DecisionApprovalNotGrantedError("x"), 403, "approval_not_granted", False),
    ],
)
def test_decision_maps_every_command_refusal_with_literal_context(client, monkeypatch, error, status, code, has_context):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    monkeypatch.setattr(approvals_router, "decide_approval", lambda *_a, **_k: (_ for _ in ()).throw(error))
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key=f"map-{code}"), json={"decision": "approve", "expected_resource_version": 1})
    body = response.json()
    assert response.status_code == status and body["code"] == code
    # AD-13's literal expected/current is carried WHERE THERE IS ANY. The three
    # codes without it describe a condition with no versions to compare, and an
    # always-emitted `{}` is not "no context" to a JSON client -- it is an empty
    # object, truthy in JavaScript, which the decision panel rendered verbatim.
    if has_context:
        assert body["expected"] and body["current"]
    else:
        assert "expected" not in body and "current" not in body


@pytest.mark.parametrize("candidate_resolves", [True, False])
def test_prewrite_denial_audits_target_candidate_refs_or_honest_absence(
    client, monkeypatch, candidate_resolves,
):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id, state="rejected")
    evidence_ref = EvidenceRefV1(
        binding.scenario_version_id, "sha256", "rfc8785-v1", "c" * 64,
        "run-v1", None, "demand", "demand-1",
    )
    candidate = SimpleNamespace(evidence_refs=(evidence_ref,)) if candidate_resolves else None
    runs = FakeSchedulingRuns(candidate=candidate)
    audit = FakeAudit()
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    app.dependency_overrides[get_audit_writer] = lambda: audit
    monkeypatch.setattr(
        approvals_router,
        "decide_approval",
        lambda *_a, **_k: (_ for _ in ()).throw(
            ApprovalNotPendingError(
                "already terminal", expected={"state": "pending"},
                current={"state": "rejected"},
            )
        ),
    )

    response = test_client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_headers(settings, key=f"denial-refs-{candidate_resolves}"),
        json={"decision": "approve", "expected_resource_version": 1},
    )

    assert response.status_code == 409
    assert runs.candidate_calls == [{
        "schedule_run_id": binding.schedule_run_id,
        "site_id": session.site_id,
    }]
    assert audit.items[0].evidence_refs == ((evidence_ref,) if candidate_resolves else ())


def _validation_error() -> ValidationError:
    """A real pydantic error, built the way the adapter produces one.

    `PostgresScheduleRunRepository.get_candidate` rehydrates the stored payload
    with `TypeAdapter(ScheduleVersionV1).validate_python`, so a `schedule_version`
    row that no longer matches the contract raises exactly this type.
    """
    try:
        TypeAdapter(int).validate_python("not-an-int")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def _denial_setup(monkeypatch, session, runs, audit):
    binding = _binding(site_id=session.site_id, state="rejected")
    runs.binding = binding
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    app.dependency_overrides[get_audit_writer] = lambda: audit
    monkeypatch.setattr(
        approvals_router,
        "decide_approval",
        lambda *_a, **_k: (_ for _ in ()).throw(
            ApprovalNotPendingError(
                "already terminal", expected={"state": "pending"},
                current={"state": "rejected"},
            )
        ),
    )
    return binding


def test_unreadable_candidate_payload_still_commits_the_denial_row_and_the_409(client, monkeypatch):
    """A payload that no longer validates is PERMANENT -- a retry cannot heal it.

    Losing the FR21 denial row to it would be permanent too, so the refusal is
    recorded with honest absence and the mapped 409 still goes out.
    """
    test_client, settings, session = client
    runs = FakeSchedulingRuns(candidate_raises=_validation_error())
    audit = FakeAudit()
    binding = _denial_setup(monkeypatch, session, runs, audit)

    response = test_client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_headers(settings, key="denial-refs-unreadable"),
        json={"decision": "approve", "expected_resource_version": 1},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "approval_not_pending"
    assert len(runs.candidate_calls) == 1
    assert [item.outcome for item in audit.items] == ["approval_denied"]
    assert audit.items[0].evidence_refs == ()


def test_a_transactional_candidate_fault_escapes_so_the_retry_writes_a_real_row(client, monkeypatch):
    """The guard is deliberately narrow.

    An infrastructure fault is transient, and this arm stores no idempotent
    result, so letting it escape means the client's retry re-enters here and
    writes a denial row carrying the real references -- strictly better than
    committing an absence that is indistinguishable from a resolved-to-nothing
    candidate.
    """
    test_client, settings, session = client
    runs = FakeSchedulingRuns(candidate_raises=RuntimeError("connection reset"))
    audit = FakeAudit()
    binding = _denial_setup(monkeypatch, session, runs, audit)

    with pytest.raises(RuntimeError, match="connection reset"):
        test_client.post(
            f"/api/v1/approvals/{binding.approval_id}/decision",
            headers=_headers(settings, key="denial-refs-fault"),
            json={"decision": "approve", "expected_resource_version": 1},
        )

    assert len(runs.candidate_calls) == 1
    assert audit.items == []


def test_decision_conflicts_when_one_idempotency_key_is_reused_with_a_changed_body(client, monkeypatch):
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    approvals = FakeApprovals(binding); runs = FakeSchedulingRuns()
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    def terminal(*_a, **_k):
        updated = approvals.terminalize(None, approval_id=binding.approval_id, site_id=session.site_id, state="rejected", decided_by_actor_id=session.app_user_id, decided_at=NOW, expected_resource_version=1)
        return DecisionResultV1("rejected", updated, None, {}, {})
    monkeypatch.setattr(approvals_router, "decide_approval", terminal)
    first = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decision-conflict"), json={"decision": "reject", "expected_resource_version": 1})
    second = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decision-conflict"), json={"decision": "approve", "expected_resource_version": 1})
    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["code"] == "idempotency_key_conflict"


def test_decision_expiry_returns_409_and_the_committed_terminal_state(client, monkeypatch):
    """`approval_expired` is Decision 9's only OTHER committed-then-refused code.

    It is the code Decision 7's whole dismissal mechanism returns, so it needs
    its own mapping test rather than riding on `approval_stale`'s.
    """
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    approvals = FakeApprovals(binding)
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()

    def terminal(*_a, **_kwargs):
        updated = approvals.terminalize(None, approval_id=binding.approval_id, site_id=session.site_id, state="expired", decided_by_actor_id=session.app_user_id, decided_at=NOW, expected_resource_version=binding.resource_version)
        return DecisionResultV1("expired", updated, None, {"expires_at": "2026-08-29T00:00:00+00:00"}, {"now": "2026-08-29T02:00:00+00:00"})

    monkeypatch.setattr(approvals_router, "decide_approval", terminal)
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="decide-expired"), json={"decision": "reject", "expected_resource_version": 1})
    assert response.status_code == 409 and response.json()["code"] == "approval_expired"
    assert response.json()["expected"] == {"expires_at": "2026-08-29T00:00:00+00:00"}
    assert approvals._binding.state == "expired"


@pytest.mark.parametrize("body", [{"decision": "maybe", "expected_resource_version": 1}, {"decision": "approve", "expected_resource_version": 0}, {"expected_resource_version": 1}])
def test_decision_refuses_a_command_outside_the_closed_body_shape(client, body):
    """Decision 1: `decision` is a required closed literal, never a boolean, and
    `expected_resource_version` is `ge=1`. FastAPI answers all three with 422."""
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="bad-body"), json=body)
    assert response.status_code == 422


def test_an_uncancellable_agent_run_is_a_typed_conflict_not_a_500(client, monkeypatch):
    """`cancel_agent_run_for_approval` raises `AgentRunNotQueuedError` when the
    run left `approval_required`. It is not a `DecideApprovalError`, so before
    this arm the global handler turned it into an untyped 500."""
    test_client, settings, session = client
    binding = _binding(site_id=session.site_id)
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    monkeypatch.setattr(approvals_router, "decide_approval", lambda *_a, **_k: (_ for _ in ()).throw(AgentRunNotQueuedError("agent run is no longer awaiting approval")))
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="run-conflict"), json={"decision": "reject", "expected_resource_version": 1})
    assert response.status_code == 409 and response.json()["code"] == "agent_run_not_cancellable"


def test_decision_does_not_disclose_a_cross_site_binding(client):
    test_client, settings, session = client
    binding = _binding(site_id=uuid4())
    class CrossSiteApprovals(FakeApprovals):
        def get(self, _c, *, approval_id, site_id):
            return self._binding if self._binding.approval_id == approval_id and self._binding.site_id == site_id else None
    app.dependency_overrides[get_approval_repository] = lambda: CrossSiteApprovals(binding)
    app.dependency_overrides[get_schedule_run_repository] = lambda: FakeSchedulingRuns()
    response = test_client.post(f"/api/v1/approvals/{binding.approval_id}/decision", headers=_headers(settings, key="cross-site-decision"), json={"decision": "reject", "expected_resource_version": 1})
    assert response.status_code == 404 and response.json()["code"] == "approval_not_found"


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
        (ApprovalNotGrantedError("x"), 403, "approval_not_granted"),
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


def test_provenance_literal_route_precedes_the_approval_id_route(client) -> None:
    test_client, settings, session = client
    run_id = uuid4()

    class ProvenanceRuns:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed",
                                   reason=None, created_at=NOW)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=uuid4(),
                                   baseline_schedule_version=None, accepted_at=NOW)
        def get_candidate(self, *_args, **_kwargs): return None
        def events_after(self, *_args, **_kwargs): return ()

    app.dependency_overrides[get_schedule_run_repository] = lambda: ProvenanceRuns()
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals()
    app.dependency_overrides[get_audit_reader] = lambda: SimpleNamespace(
        list_for_schedule_run=lambda *_args, **_kwargs: (),
    )

    response = test_client.get(
        "/api/v1/approvals/provenance",
        params={"schedule_run_id": str(run_id)},
        headers=_auth_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["schedule_run_id"] == str(run_id)
    assert response.json()["site_id"] == str(session.site_id)


def test_provenance_route_never_serializes_pending_payload_content(client) -> None:
    test_client, settings, session = client
    run_id, agent_run_id, conversation_id = uuid4(), uuid4(), uuid4()
    marker = "NEVER-LEAK-PENDING-PAYLOAD-4-4"
    binding = _binding(
        site_id=session.site_id, schedule_run_id=run_id, agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    pending_payload = {
        "pending_calls": [{
            "tool_call_id": "call-1", "tool_name": "scheduling_baseline",
            "tool_args_json": f'{{"secret":"{marker}"}}',
        }],
        "turn": {"messages": [{
            "role": "user", "parts": [{"kind": "text", "text": marker}],
        }]},
    }

    class ProvenanceRuns:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed",
                                   reason=None, created_at=NOW)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=binding.scenario_version_id,
                                   baseline_schedule_version=None, accepted_at=NOW)
        def get_candidate(self, *_args, **_kwargs): return None
        def events_after(self, *_args, **_kwargs): return ()

    app.dependency_overrides[get_schedule_run_repository] = lambda: ProvenanceRuns()
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding, pending_payload)
    app.dependency_overrides[get_audit_reader] = lambda: SimpleNamespace(
        list_for_schedule_run=lambda *_args, **_kwargs: (),
    )
    app.dependency_overrides[get_conversation_repository] = lambda: SimpleNamespace(
        timeline=lambda *_args, **_kwargs: SimpleNamespace(events=()),
    )

    response = test_client.get(
        "/api/v1/approvals/provenance", params={"schedule_run_id": str(run_id)},
        headers=_auth_headers(settings),
    )

    assert response.status_code == 200
    assert marker not in response.text
    tool = next(item for item in response.json()["items"] if item["item_type"] == "tool_proposal")
    assert set(tool) >= {"tool_name", "tool_call_id"}


def test_provenance_survives_provider_failure_with_audit_and_evidence(client) -> None:
    test_client, settings, session = client
    run_id, candidate_id, scenario_version_id = uuid4(), uuid4(), uuid4()
    approval_id, actor_id = uuid4(), session.app_user_id
    evidence = EvidenceRefV1(
        scenario_version_id, "sha256", "v1", "e" * 64, "run-v1", None,
        "demand", "row-1",
    )
    binding = _binding(
        approval_id=approval_id, state="consumed", site_id=session.site_id,
        schedule_run_id=run_id, candidate_schedule_version_id=candidate_id,
        scenario_version_id=scenario_version_id, decided_by_actor_id=actor_id,
        decided_at=NOW, consumed_at=NOW,
    )
    audit = AuditEnvelopeV1(
        uuid4(), uuid4(), uuid4(), session.site_id, actor_id, actor_id,
        binding.conversation_id, None, approval_id, run_id, "promote_baseline",
        "approval_consumed", True, "effect", None, str(candidate_id), "safe",
        "a" * 64, "b" * 64, "policy", "app", WorkerFactsV1(), (), NOW,
    )

    class ProvenanceRuns:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed",
                                   reason=None, created_at=NOW)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=scenario_version_id,
                                   baseline_schedule_version=None, accepted_at=NOW)
        def get_candidate(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_version_id=candidate_id,
                                   evidence_refs=(evidence,), metrics=None)
        def events_after(self, *_args, **_kwargs): return ()

    app.dependency_overrides[get_schedule_run_repository] = lambda: ProvenanceRuns()
    app.dependency_overrides[get_approval_repository] = lambda: FakeApprovals(binding)
    app.dependency_overrides[get_audit_reader] = lambda: SimpleNamespace(
        list_for_schedule_run=lambda *_args, **_kwargs: (audit,),
    )
    app.dependency_overrides[get_conversation_repository] = lambda: SimpleNamespace(
        timeline=lambda *_args, **_kwargs: SimpleNamespace(events=()),
    )
    app.dependency_overrides[get_llm_provider] = lambda: (_ for _ in ()).throw(
        RuntimeError("provider unavailable")
    )

    response = test_client.get(
        "/api/v1/approvals/provenance", params={"schedule_run_id": str(run_id)},
        headers=_auth_headers(settings),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["item_type"] for item in items} >= {
        "solver_run", "approval_request", "approval_decision", "audit_record",
        "baseline_promotion",
    }
    assert next(item for item in items if item["item_type"] == "solver_run")["evidence_refs"][0]["record_id"] == "row-1"


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


# --------------------------------------------------------------------------
# `_drive_resumed_turn`: the post-commit resume drive (Decision 8).
#
# This ran with ZERO coverage: every route-level approve test produces
# `resume is None` (planner path), and the end-to-end promotion test calls
# `decide_approval` directly, bypassing the router and the dependency teardown.
# It is also the one place in the app that executes AFTER the response has been
# sent, where a raised exception cannot become a response and instead tears down
# the connection mid-body while abandoning the run.
# --------------------------------------------------------------------------


class _Row:
    def __init__(self, scenario_id, membership_id):
        self.scenario_id = scenario_id
        self.membership_id = membership_id


class _Connection:
    def __init__(self, row=None, error=None):
        self._row = row
        self._error = error

    def execute(self, *_args, **_kwargs):
        if self._error is not None:
            raise self._error
        return self

    def one(self):
        return self._row


class _SiteContext:
    """Stands in for `get_site_context_opener`'s context manager."""

    def __init__(self, connection):
        self._connection = connection

    def __call__(self, _site_id):
        return self

    def __enter__(self):
        return self._connection

    def __exit__(self, *_exc):
        return False


def _resume_fixtures(*, row=None, query_error=None):
    from application.use_cases.promote_baseline import ResumeRequestV1

    binding = _binding(state="consumed")
    binding = replace(binding, agent_run_id=uuid4(), conversation_id=uuid4())
    resume = ResumeRequestV1(
        agent_run_id=binding.agent_run_id, tool_call_id="call-1", history=None
    )
    connection = _Connection(
        row=row if row is not None else _Row(uuid4(), uuid4()), error=query_error
    )
    return binding, resume, _SiteContext(connection)


def _drive(monkeypatch, *, binding, resume, opener, outcome=None, turn_error=None,
           finalize_error=None, settings=None):
    """Call the real `_drive_resumed_turn` with the collaborators faked out."""
    from api.routers import approvals as module

    recorded: dict = {}

    def _execute_turn(*_args, **kwargs):
        recorded["approvals"] = kwargs.get("approvals")
        if turn_error is not None:
            raise turn_error
        return outcome

    def _finalize(*_args, **kwargs):
        recorded["status"] = kwargs.get("status")
        if finalize_error is not None:
            raise finalize_error

    monkeypatch.setattr(module, "execute_turn", _execute_turn)
    monkeypatch.setattr(module, "finalize_agent_run", _finalize)
    # `terminal_status` is deliberately NOT mocked: its `"suspended" ->
    # "approval_required"` mapping IS the hazard under test, and stubbing it
    # would make the assertion below pass no matter what the code does.
    monkeypatch.setattr(module, "activity_payload", lambda *_a, **_k: {})
    monkeypatch.setattr(module, "failed_outcome_for_exception",
                        lambda _exc: SimpleNamespace(status="failed"))

    module._drive_resumed_turn(
        resume=resume, binding=binding,
        settings=settings if settings is not None else _settings_stub(),
        runtime_factory=lambda **_k: object(),
        compose_capabilities=lambda _ctx: (),
        projection_reader=object(), conversations=object(), proposals=object(),
        open_site_context=opener,
    )
    return recorded


def _settings_stub():
    from settings import default_settings

    return replace(default_settings(), scheduling_baseline_enabled=True)


def test_the_resumed_turn_forwards_the_server_owned_approval_for_the_exact_call(monkeypatch) -> None:
    binding, resume, opener = _resume_fixtures()
    recorded = _drive(monkeypatch, binding=binding, resume=resume, opener=opener,
                      outcome=SimpleNamespace(status="timed_out"))

    decision, = recorded["approvals"]
    assert decision.tool_call_id == "call-1"
    # The decision is SERVER-owned and derived from the persisted binding, never
    # from a client boolean (AC1).
    assert decision.approved is True
    assert recorded["status"] == "agent_timed_out"


def test_a_resumed_turn_that_defers_again_is_refused_instead_of_parked(monkeypatch) -> None:
    """Decision 8 covers ONE resumed turn; a second deferral must not strand it.

    Mutation that must turn this red: delete the `ResumedTurnSuspendedError`
    raise. `terminal_status` then maps `suspended` to `approval_required` -- a
    status meaning "a binding is pending" -- while the resume path creates no
    binding, so `get_pending_for_agent_run` reports none and `claim_queued_run`
    never reclaims it. The run waits forever for an approval that cannot exist.
    """
    binding, resume, opener = _resume_fixtures()
    recorded = _drive(monkeypatch, binding=binding, resume=resume, opener=opener,
                      outcome=SimpleNamespace(status="suspended"))

    assert recorded["status"] == "agent_failed"
    assert recorded["status"] != "approval_required"


def test_a_failing_resumed_turn_still_finalizes_the_run(monkeypatch) -> None:
    binding, resume, opener = _resume_fixtures()
    recorded = _drive(monkeypatch, binding=binding, resume=resume, opener=opener,
                      turn_error=RuntimeError("provider down"))

    assert recorded["status"] == "agent_failed"


def test_setup_failure_after_commit_is_contained_and_never_escapes(monkeypatch) -> None:
    """The promotion is already durable; this runs after the response was sent.

    An escape here cannot be rendered (Starlette: "response already started") and
    would tear down the connection mid-body. Containment is the contract.
    """
    from sqlalchemy.exc import NoResultFound

    binding, resume, opener = _resume_fixtures(query_error=NoResultFound("membership revoked"))
    recorded = _drive(monkeypatch, binding=binding, resume=resume, opener=opener,
                      outcome=SimpleNamespace(status="timed_out"))

    # Nothing was finalized because the claim could not be built -- but nothing
    # raised either. The run is left for Epic 3's recovery sweep.
    assert "status" not in recorded


def test_a_failing_finalize_after_commit_is_contained_and_never_escapes(monkeypatch) -> None:
    binding, resume, opener = _resume_fixtures()

    _drive(monkeypatch, binding=binding, resume=resume, opener=opener,
           outcome=SimpleNamespace(status="timed_out"),
           finalize_error=AgentRunNotQueuedError("run left agent_running"))
