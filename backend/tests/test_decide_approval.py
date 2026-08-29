from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.schedule_run import ScheduleRunViewV1
from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.decide_approval import (
    BaselinePromotionNotAvailableError, DecideApprovalCommandV1, decide_approval,
)
from application.use_cases.request_approval import RequestApprovalCommandV1, request_approval

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)

class Runs:
    def __init__(self):
        self.run_id = uuid4(); self.candidate = ScheduleVersionV1(schedule_version_id=uuid4(), schedule_run_id=self.run_id, scenario_id=uuid4(), scenario_version_id=uuid4(), feasible_solver_status="FEASIBLE", assignments=())
        self.run = ScheduleRunViewV1(self.run_id, "solver_completed", None, 2, False)
    def get_run(self, *_a, **_k): return self.run
    def get_candidate(self, *_a, **_k): return self.candidate

class Baselines:
    def __init__(self, value=None): self.value = value
    def get(self, *_a): return self.value

class Approvals:
    def __init__(self): self.binding = None; self.terminalized = 0
    def create_pending(self, _c, *, binding, pending_payload): self.binding = binding
    def list_for_schedule_run(self, *_a, **_k): return ()
    def get(self, *_a, **_k): return self.binding
    def terminalize(self, _c, **kw):
        if self.binding.state != "pending" or self.binding.resource_version != kw["expected_resource_version"]: return None
        self.terminalized += 1; self.binding = replace(self.binding, state=kw["state"], decided_by_actor_id=kw["decided_by_actor_id"], decided_at=kw["decided_at"], resource_version=self.binding.resource_version + 1); return self.binding

class Audit:
    def __init__(self): self.items = []
    def append(self, _c, envelope): self.items.append(envelope)

class Conversations:
    def __init__(self): self.items = []
    def append_approval_request_activity(self, _c, **kw): self.items.append(("event", kw)); return None
    def pause_agent_run_for_approval(self, *_a, **_k): return None
    def cancel_agent_run_for_approval(self, _c, **kw): self.items.append(("cancel", kw)); return None

def pending(*, agent_run_id=None, baseline=None):
    runs, approvals, audit, conversations = Runs(), Approvals(), Audit(), Conversations()
    command = RequestApprovalCommandV1(site_id=uuid4(), actor_id=uuid4(), schedule_run_id=runs.run_id, expected_resource_version=2, expected_baseline_schedule_version=str(baseline.schedule_version_id) if baseline else None, request_effect_key="command:test", request_id=uuid4(), conversation_id=uuid4(), agent_run_id=agent_run_id)
    baselines = Baselines(baseline)
    request_approval(None, command=command, schedule_runs=runs, baselines=baselines, approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=True, clock=lambda: NOW)
    audit.items.clear(); conversations.items.clear()
    return runs, approvals, audit, conversations, command

def decide(runs, approvals, audit, conversations, command, *, decision="reject", now=NOW, baseline=None, enabled=True):
    return decide_approval(None, command=DecideApprovalCommandV1(site_id=command.site_id, actor_id=command.actor_id, approval_id=approvals.binding.approval_id, decision=decision, expected_resource_version=approvals.binding.resource_version, request_id=uuid4()), approvals=approvals, schedule_runs=runs, baselines=Baselines(baseline), audit_writer=audit, conversations=conversations, scheduling_baseline_enabled=enabled, clock=lambda: now)

def test_reject_terminalizes_once_and_records_audit_and_event() -> None:
    runs, approvals, audit, conversations, command = pending()
    result = decide(runs, approvals, audit, conversations, command)
    assert result.outcome == "rejected" and approvals.binding.state == "rejected"
    assert [item.outcome for item in audit.items] == ["approval_rejected"]
    assert conversations.items[0][0] == "event"

def test_expiry_outranks_requested_reject_and_clears_pending_slot() -> None:
    runs, approvals, audit, conversations, command = pending()
    result = decide(runs, approvals, audit, conversations, command, now=NOW + timedelta(hours=2))
    assert result.outcome == "expired" and approvals.binding.state == "expired"
    assert audit.items[0].outcome == "approval_expired"

def test_valid_approve_is_explicitly_unavailable_without_a_write() -> None:
    runs, approvals, audit, conversations, command = pending()
    with pytest.raises(BaselinePromotionNotAvailableError): decide(runs, approvals, audit, conversations, command, decision="approve")
    assert approvals.binding.state == "pending" and not audit.items and not conversations.items

def test_changed_candidate_terminalizes_stale() -> None:
    runs, approvals, audit, conversations, command = pending()
    runs.candidate = None
    assert decide(runs, approvals, audit, conversations, command, decision="approve").outcome == "stale"
    assert approvals.binding.state == "stale" and audit.items[0].outcome == "approval_stale"

def test_agent_path_cancels_with_the_literal_reason() -> None:
    runs, approvals, audit, conversations, command = pending(agent_run_id=uuid4())
    decide(runs, approvals, audit, conversations, command)
    assert conversations.items[0][0] == "cancel"
    assert conversations.items[0][1]["reason"] == "approval_rejected"


@pytest.mark.parametrize("mutation", ["candidate_infeasible", "run_version", "parameter_hash", "consequence_hash", "policy_version"])
def test_every_non_baseline_business_mismatch_terminalizes_stale(mutation) -> None:
    runs, approvals, audit, conversations, command = pending()
    if mutation == "candidate_infeasible":
        runs.candidate = replace(runs.candidate, feasible_solver_status="INFEASIBLE")
    elif mutation == "run_version":
        runs.run = replace(runs.run, resource_version=3)
    elif mutation == "parameter_hash":
        approvals.binding = replace(approvals.binding, parameter_hash="0" * 64)
    elif mutation == "consequence_hash":
        approvals.binding = replace(approvals.binding, consequence_hash="0" * 64)
    else:
        approvals.binding = replace(approvals.binding, policy_version="old-policy")
    result = decide(runs, approvals, audit, conversations, command, decision="approve")
    assert result.outcome == "stale"
    assert approvals.binding.state == "stale"


def test_baseline_appearing_after_an_absent_snapshot_terminalizes_stale() -> None:
    runs, approvals, audit, conversations, command = pending()
    baseline = SiteBaselineV1(command.site_id, uuid4(), 1)
    assert decide(runs, approvals, audit, conversations, command, baseline=baseline).outcome == "stale"


def test_baseline_disappearing_or_moving_or_changing_version_terminalizes_stale() -> None:
    original = SiteBaselineV1(uuid4(), uuid4(), 4)
    for current in (None, SiteBaselineV1(original.site_id, uuid4(), 4), SiteBaselineV1(original.site_id, original.schedule_version_id, 5)):
        runs, approvals, audit, conversations, command = pending(baseline=original)
        assert decide(runs, approvals, audit, conversations, command, baseline=current).outcome == "stale"


def test_non_agent_path_never_writes_an_agent_run() -> None:
    runs, approvals, audit, conversations, command = pending()
    decide(runs, approvals, audit, conversations, command)
    assert [kind for kind, _ in conversations.items] == ["event"]


def test_lost_terminal_compare_and_set_writes_no_audit_event_or_agent_cancellation() -> None:
    runs, approvals, audit, conversations, command = pending(agent_run_id=uuid4())
    approvals.terminalize = lambda *_a, **_k: None
    from application.use_cases.decide_approval import ApprovalNotPendingError
    with pytest.raises(ApprovalNotPendingError):
        decide(runs, approvals, audit, conversations, command)
    assert not audit.items and not conversations.items


def test_database_fault_before_terminal_write_leaves_binding_pending() -> None:
    runs, approvals, audit, conversations, command = pending()
    def fail(*_a, **_k):
        raise DBAPIError("UPDATE", {}, RuntimeError("database unavailable"))
    approvals.terminalize = fail
    with pytest.raises(DBAPIError):
        decide(runs, approvals, audit, conversations, command)
    assert approvals.binding.state == "pending" and not audit.items and not conversations.items
