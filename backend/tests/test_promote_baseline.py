from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.decide_approval import ApprovalNotPendingError
from application.use_cases.promote_baseline import (
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
        None, binding=approvals.binding, actor_id=command.actor_id, request_id=uuid4(),
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
