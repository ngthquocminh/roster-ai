from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.decide_approval import ApprovalNotPendingError
from application.use_cases.promote_baseline import (
    ApprovalPayloadUnreadableError,
    BaselineConcurrentlyMovedError,
    promote_baseline,
)
from tests.test_decide_approval import NOW, pending


class Writer:
    def __init__(self, result=True): self.result = result; self.calls = []
    def promote(self, _c, **kw):
        self.calls.append(kw)
        if not self.result: return None
        return SiteBaselineV1(kw["site_id"], kw["schedule_version_id"], 1)


def _tx(*, agent_run_id=None, consume=True, promote=True, fail_at=None):
    runs, approvals, audit, conversations, command = pending(agent_run_id=agent_run_id)
    approvals.consume = lambda _c, **kw: (
        None if not consume else replace(
            approvals.binding, state="consumed", decided_by_actor_id=kw["decided_by_actor_id"],
            decided_at=kw["decided_at"], consumed_at=kw["decided_at"],
            resource_version=approvals.binding.resource_version + 1,
        )
    )
    approvals.get_pending_payload = lambda *_a, **_k: {
        "pending_calls": [{"tool_call_id": "call-1", "tool_name": "scheduling_baseline", "tool_args_json": "{}"}],
        "turn": {"messages": []},
    }
    writer = Writer(promote)
    conversations.resume_agent_run_for_approval = lambda _c, **kw: conversations.items.append(("resume", kw)) or None
    if fail_at == "audit":
        audit.append = lambda *_a, **_k: (_ for _ in ()).throw(DBAPIError("INSERT", {}, RuntimeError("down")))
    elif fail_at == "event":
        conversations.append_approval_request_activity = lambda *_a, **_k: (_ for _ in ()).throw(DBAPIError("INSERT", {}, RuntimeError("down")))
    return runs, approvals, audit, conversations, command, writer


def _promote(values):
    runs, approvals, audit, conversations, command, writer = values
    return promote_baseline(
        None, binding=approvals.binding, candidate=runs.candidate,
        actor_id=command.actor_id, request_id=uuid4(),
        approvals=approvals, baseline_writer=writer, audit_writer=audit,
        conversations=conversations, occurred_at=NOW,
    )


def test_first_promotion_consumes_moves_pointer_and_records_one_audit_and_event() -> None:
    values = _tx()
    result = _promote(values)
    _, approvals, audit, conversations, command, writer = values
    assert result.binding.state == "consumed" and result.baseline.resource_version == 1
    assert writer.calls[0]["expected_resource_version"] is None
    assert audit.items[0].outcome == "approval_consumed"
    assert audit.items[0].evidence_refs == values[0].candidate.evidence_refs
    assert audit.items[0].effect_key == approvals.binding.request_effect_key
    assert [kind for kind, _ in conversations.items] == ["event"]


def test_lost_consume_cas_never_writes_the_pointer() -> None:
    values = _tx(consume=False)
    with pytest.raises(ApprovalNotPendingError): _promote(values)
    assert values[-1].calls == []


def test_lost_pointer_cas_is_typed_and_writes_no_audit_or_event() -> None:
    values = _tx(promote=False)
    with pytest.raises(BaselineConcurrentlyMovedError): _promote(values)
    assert values[2].items == [] and values[3].items == []


@pytest.mark.parametrize("fault_at", ["audit", "event"])
def test_late_database_fault_propagates_for_caller_transaction_rollback(fault_at) -> None:
    values = _tx(fail_at=fault_at)
    with pytest.raises(DBAPIError): _promote(values)


def test_agent_path_resumes_while_planner_path_never_writes_an_agent_run() -> None:
    agent_values = _tx(agent_run_id=uuid4())
    _promote(agent_values)
    assert [kind for kind, _ in agent_values[3].items] == ["resume"]
    planner_values = _tx()
    _promote(planner_values)
    assert [kind for kind, _ in planner_values[3].items] == ["event"]


def test_agent_path_resumes_the_consumed_binding_and_returns_a_usable_resume_request() -> None:
    """The default suite must prove the resume CONTRACT, not just the call.

    The `agent_run_status="agent_running"` and cleared `status_reason` live in the
    PostgreSQL adapter and are asserted in the `@pytest.mark.postgres` suite,
    which is deselected by default -- so the deselected run proved nothing about
    what TX2 hands the resume, which is this use case's own responsibility.
    """
    agent_run_id = uuid4()
    values = _tx(agent_run_id=agent_run_id)
    result = _promote(values)
    _, approvals, _, conversations, _, _ = values
    (kind, kwargs), = conversations.items
    assert kind == "resume"
    assert kwargs["agent_run_id"] == agent_run_id
    # The CONSUMED binding, never the pre-consume one: the activity this writes
    # reports the state the same transaction just produced.
    assert kwargs["binding"].state == "consumed"
    assert kwargs["binding"].consumed_at is not None
    # EAD-5 drives the run to terminal through the existing seam, so TX2 must
    # hand the route the exact call to approve and the owned history to replay.
    assert result.resume is not None
    assert result.resume.agent_run_id == agent_run_id
    assert result.resume.tool_call_id == "call-1"
    assert result.resume.history is not None


def test_planner_path_produces_no_resume_request_at_all() -> None:
    # Trap 7: the guard is `agent_run_id is not None`, never "a payload exists".
    result = _promote(_tx())
    assert result.resume is None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (None, "absent"),
        ({"pending_calls": [], "turn": {"messages": []}}, "zero calls"),
        ({"turn": {"messages": []}, "pending_calls": [
            {"tool_call_id": "a", "tool_name": "scheduling_baseline", "tool_args_json": "{}"},
            {"tool_call_id": "b", "tool_name": "scheduling_baseline", "tool_args_json": "{}"},
        ]}, "two calls"),
        ({"not": "a payload"}, "malformed"),
    ],
)
def test_an_unusable_agent_payload_is_typed_and_rolls_the_bundle_back(payload, reason) -> None:
    """`agent_run_id IS NOT NULL` does not imply a usable `pending_payload`.

    The column is nullable and no CHECK ties the two together, so this is a
    reachable data state. It must raise a TYPED, documented error rather than a
    bare `RuntimeError`/`ValidationError` surfacing as an undeclared 500 -- and
    like every post-write failure it must escape so TX2 rolls back whole.
    """
    values = _tx(agent_run_id=uuid4())
    values[1].get_pending_payload = lambda *_a, **_k: payload
    with pytest.raises(ApprovalPayloadUnreadableError) as raised:
        _promote(values)
    assert raised.value.code == "approval_payload_unreadable", reason
