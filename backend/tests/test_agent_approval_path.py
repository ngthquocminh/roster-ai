"""Wiring proof for the AGENT initiator path of TX1 (Decision 1 + Decision 10).

Why this file exists: nothing exercised `conversations._finish`'s `suspended`
branch. Every other approval proof drives `request_approval` directly with
hand-built commands, so the code that turns a real suspension into a real
command -- unwrapping the tool-argument envelope, coercing the request,
building the effect key, serialising the pending payload, and landing a policy
refusal -- had no coverage at all. That gap is exactly what let a defect ship
where the envelope was never unwrapped and EVERY agent-initiated approval raised
`TypeError`, escaped both handlers, and stranded the run at `agent_running`.

These tests drive the real HTTP route with a scripted suspension.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_agent_runtime_factory,
    get_approval_repository,
    get_audit_writer,
    get_capability_registry,
    get_conversation_repository,
    get_identity_store,
    get_projection_reader,
    get_schedule_run_repository,
    get_settings,
    get_site_baseline_reader,
    get_site_context,
    get_site_context_opener,
)
from api.main import app
from application.contracts.activity import ApprovalRequestActivityV1
from application.contracts.agent_runtime import (
    AgentApprovalPendingV1,
    AgentMessageV1,
    AgentRunOutcomeV1,
    AgentToolCallProposalV1,
    AgentTurnV1,
)
from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.conversation import ClaimedAgentRunV1, ConversationV1, ExecutedAgentRunV1
from application.ports.schedule_run import ScheduleRunViewV1
from application.ports.session import ResolvedSession
from application.contracts.persisted_event import PersistedEventV1
from settings import default_settings

_SESSION_TOKEN = "agent-approval-session"
_CSRF_TOKEN = "agent-approval-csrf"
_NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
_TOOL_CALL_ID = "call-baseline-1"

#: The envelope the adapter ACTUALLY produces. `capability_tools._tool_schema`
#: nests the request under the module's declared `request_argument`, which
#: `scheduling_baseline` leaves at its `"request"` default -- so this, not the
#: request's own fields, is what `tool_args_json` contains.
_RUN_ID = UUID("00000000-0000-0000-0000-000000000009")
_TOOL_ARGS_JSON = (
    '{"request": {"schedule_run_id": "00000000-0000-0000-0000-000000000009", '
    '"expected_baseline_schedule_version": null, "schema_version": "1"}}'
)


def _pending() -> AgentApprovalPendingV1:
    return AgentApprovalPendingV1(
        pending_calls=(
            AgentToolCallProposalV1(
                tool_call_id=_TOOL_CALL_ID,
                tool_name="scheduling_baseline",
                tool_args_json=_TOOL_ARGS_JSON,
            ),
        ),
        turn=AgentTurnV1(messages=(AgentMessageV1(role="user"),)),
    )


class _SuspendingRuntime:
    name = "test-suspend"

    def run_turn(self, _request):
        return AgentRunOutcomeV1(status="suspended", approval=_pending())


class _Conversations:
    def __init__(self, conversation_id, scenario_id, version_id, site_id, actor_id):
        self.conversation_id = conversation_id
        self.scenario_id = scenario_id
        self.version_id = version_id
        self.site_id = site_id
        self.actor_id = actor_id
        self.paused = []
        self.finished_statuses = []
        self.finished_payloads = []

    def claim_queued_run(self, _c, *, conversation_id, agent_run_id):
        if conversation_id != self.conversation_id:
            return None
        return ClaimedAgentRunV1(
            agent_run_id=agent_run_id, conversation_id=conversation_id,
            scenario_id=self.scenario_id, scenario_version_id=self.version_id,
            site_id=self.site_id, actor_id=self.actor_id, membership_id=uuid4(),
            prompt="Promote the reviewed candidate",
        )

    def pause_agent_run_for_approval(self, _c, *, claimed_agent_run_id, binding, request_id):
        self.paused.append({"agent_run_id": claimed_agent_run_id, "binding": binding})
        activity = ApprovalRequestActivityV1(
            activity_id=uuid4(), activity_type="approval_request",
            conversation_id=binding.conversation_id, conversation_resource_version=3,
            scenario_id=self.scenario_id, scenario_version_id=self.version_id,
            occurred_at=_NOW, approval_id=binding.approval_id,
            approval_state=binding.state, agent_run_id=claimed_agent_run_id,
            schedule_run_id=binding.schedule_run_id,
            candidate_schedule_version_id=binding.candidate_schedule_version_id,
            baseline_schedule_version=binding.baseline_schedule_version,
            consequence_summary=binding.consequence_summary,
            parameter_hash=binding.parameter_hash, consequence_hash=binding.consequence_hash,
            policy_version=binding.policy_version, expires_at=binding.expires_at,
        )
        event = PersistedEventV1(
            stream_id=binding.conversation_id, sequence=2, event_type="approval_request",
            occurred_at=_NOW, resource_version=3, request_id=request_id,
            conversation_id=binding.conversation_id, agent_run_id=claimed_agent_run_id,
            site_id=binding.site_id, actor_id=binding.initiated_by_actor_id, payload=activity,
        )
        return ExecutedAgentRunV1(event, 3, "approval_required")

    def finish_agent_run(self, _c, *, claimed, status, payload, request_id):
        self.finished_statuses.append(status)
        self.finished_payloads.append(payload)
        from application.contracts.activity import TerminalOutcomeActivityV1

        activity = TerminalOutcomeActivityV1(
            activity_id=uuid4(), activity_type="terminal_outcome",
            conversation_id=claimed.conversation_id, conversation_resource_version=3,
            scenario_id=claimed.scenario_id, scenario_version_id=claimed.scenario_version_id,
            occurred_at=_NOW, outcome=payload,
        )
        event = PersistedEventV1(
            stream_id=claimed.conversation_id, sequence=2, event_type="terminal_outcome",
            occurred_at=_NOW, resource_version=3, request_id=request_id,
            conversation_id=claimed.conversation_id, agent_run_id=claimed.agent_run_id,
            site_id=claimed.site_id, actor_id=claimed.actor_id, payload=activity,
        )
        return ExecutedAgentRunV1(event, 3, status)


class _Runs:
    def __init__(self, *, status="solver_completed"):
        self.candidate = ScheduleVersionV1(
            schedule_version_id=uuid4(), schedule_run_id=_RUN_ID, scenario_id=uuid4(),
            scenario_version_id=uuid4(), feasible_solver_status="FEASIBLE", assignments=(),
        )
        self.run = ScheduleRunViewV1(_RUN_ID, status, None, 4, False)
        self.seen_run_ids = []

    def get_run(self, _c, *, run_id, site_id):
        self.seen_run_ids.append(run_id)
        return self.run

    def get_candidate(self, _c, *, schedule_run_id, site_id):
        return self.candidate


class _Approvals:
    def __init__(self):
        self.binding = None
        self.pending_payload = None

    def create_pending(self, _c, *, binding, pending_payload):
        self.binding = binding
        self.pending_payload = pending_payload

    def list_for_schedule_run(self, _c, *, schedule_run_id, site_id):
        return ()


class _Audit:
    def __init__(self):
        self.items = []

    def append(self, _c, envelope):
        self.items.append(envelope)


class _Baselines:
    def get(self, _c, _site_id):
        return None


@contextmanager
def _open_context(_site_id):
    yield object()


@pytest.fixture()
def agent_client(tmp_path):
    scenario_id, version_id, conversation_id = uuid4(), uuid4(), uuid4()
    resolved = ResolvedSession(
        app_user_id=uuid4(), site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=_NOW + timedelta(hours=1),
    )
    conversations = _Conversations(
        conversation_id, scenario_id, version_id, resolved.site_id, resolved.app_user_id
    )
    runs, approvals, audit = _Runs(), _Approvals(), _Audit()

    class _IdentityStore:
        def resolve_session(self, token_hash):
            return resolved if token_hash == hash_secret(_SESSION_TOKEN) else None

    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
        scheduling_baseline_enabled=True,
    )
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_site_context_opener] = lambda: _open_context
    app.dependency_overrides[get_conversation_repository] = lambda: conversations
    app.dependency_overrides[get_capability_registry] = lambda: (lambda _c: ())
    app.dependency_overrides[get_projection_reader] = lambda: object()
    app.dependency_overrides[get_schedule_run_repository] = lambda: runs
    app.dependency_overrides[get_approval_repository] = lambda: approvals
    app.dependency_overrides[get_audit_writer] = lambda: audit
    app.dependency_overrides[get_site_baseline_reader] = lambda: _Baselines()
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: _SuspendingRuntime()
    )
    try:
        with TestClient(app) as client:
            yield client, conversations, runs, approvals, audit, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _headers(settings):
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
        "X-CSRF-Token": _CSRF_TOKEN,
    }


def test_a_suspended_agent_turn_creates_the_binding_and_pauses_the_run(agent_client) -> None:
    """The whole agent path, end to end through the real route.

    Fails if the tool-argument envelope is unpacked with `**json.loads(...)`
    instead of being unwrapped -- which raises `TypeError`, escapes both
    handlers, and 500s.
    """
    client, conversations, runs, approvals, audit, settings = agent_client
    agent_run_id = uuid4()

    response = client.post(
        f"/api/v1/conversations/{conversations.conversation_id}/agent-runs/{agent_run_id}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["agent_run_status"] == "approval_required"
    assert response.json()["activity"]["activity_type"] == "approval_request"

    # The request was COERCED, not just unwrapped: a frozen dataclass built with
    # `**kwargs` would have left this a `str` and pushed it into the command.
    # (`get_run` is reached twice: once in `_finish` to pin the resource
    # version, once inside `request_approval`'s own gate.)
    assert set(runs.seen_run_ids) == {_RUN_ID}
    assert all(isinstance(seen, UUID) for seen in runs.seen_run_ids)

    binding = approvals.binding
    assert binding is not None
    # Decision 4 fixes the agent key shape as `tool:{agent_run_id}:{tool_call_id}`.
    assert binding.request_effect_key == f"tool:{agent_run_id}:{_TOOL_CALL_ID}"
    assert binding.agent_run_id == agent_run_id
    assert binding.candidate_schedule_version_id == runs.candidate.schedule_version_id
    # AD-12: the audit envelope keys on the command's real effect identity.
    assert audit.items[0].effect_key == binding.request_effect_key


def test_the_suspension_persists_the_pending_calls_and_owned_turn(agent_client) -> None:
    """EAD-4's persisted pending-call payload, from a REAL suspension.

    Fails if `pending_payload` is dropped, or serialised from anything other
    than the adapter's own `AgentApprovalPendingV1`.
    """
    from pydantic import TypeAdapter

    client, conversations, _runs, approvals, _audit, settings = agent_client

    client.post(
        f"/api/v1/conversations/{conversations.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert approvals.pending_payload is not None
    restored = TypeAdapter(AgentApprovalPendingV1).validate_python(approvals.pending_payload)
    assert restored == _pending()
    assert restored.pending_calls[0].tool_args_json == _TOOL_ARGS_JSON
    assert restored.turn.messages


def test_a_refused_agent_approval_lands_terminal_instead_of_stranding_the_run(
    agent_client,
) -> None:
    """Decision 10's refusal landing.

    `ApprovalRequestError` subclasses `ValueError`, so before this branch existed
    it was caught by neither `except AgentRunNotQueuedError` nor
    `except RuntimeError`: the request 500'd and the run stayed `agent_running`,
    which `claim_queued_run` can never reclaim.

    Fails if the `except ApprovalRequestError` branch is removed.
    """
    client, conversations, runs, approvals, audit, settings = agent_client
    # A non-promotable candidate -- one of AC3's refusal shapes.
    runs.run = ScheduleRunViewV1(_RUN_ID, "solver_infeasible", None, 4, False)

    response = client.post(
        f"/api/v1/conversations/{conversations.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    # AD-7's own "rejected or expired" edge: terminal and truthful.
    assert conversations.finished_statuses == ["agent_cancelled"]
    outcome = conversations.finished_payloads[0]
    assert outcome.reason == "approval_not_grantable"
    # Decision 10: a refused request creates NO binding and NO audit row.
    assert approvals.binding is None
    assert audit.items == []
    assert conversations.paused == []
