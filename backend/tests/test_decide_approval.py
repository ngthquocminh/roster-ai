from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.schedule_run import ScheduleRunViewV1
from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval
from application.use_cases.request_approval import RequestApprovalCommandV1, request_approval

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)

class Runs:
    def __init__(self):
        self.run_id = uuid4()
        evidence_ref = EvidenceRefV1(
            scenario_version_id=uuid4(),
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            producing_run_version="run-v1",
            baseline_schedule_version=None,
            group="demand",
            record_id="demand-1",
        )
        self.candidate = ScheduleVersionV1(schedule_version_id=uuid4(), schedule_run_id=self.run_id, scenario_id=uuid4(), scenario_version_id=evidence_ref.scenario_version_id, feasible_solver_status="FEASIBLE", assignments=(), evidence_refs=(evidence_ref,))
        self.run = ScheduleRunViewV1(self.run_id, "solver_completed", None, 2, False)
    def get_run(self, *_a, **_k): return self.run
    def get_candidate(self, *_a, **_k): return self.candidate

class Baselines:
    def __init__(self, value=None): self.value = value
    def get(self, *_a): return self.value

class Memberships:
    def __init__(self, active=True): self.active = active; self.calls = []
    def has_active_membership(self, _c, **kw): self.calls.append(kw); return self.active

class Approvals:
    def __init__(self): self.binding = None; self.terminalized = 0
    def create_pending(self, _c, *, binding, pending_payload): self.binding = binding
    def list_for_schedule_run(self, *_a, **_k): return ()
    def get(self, *_a, **_k): return self.binding
    def terminalize(self, _c, **kw):
        if self.binding.state != "pending" or self.binding.resource_version != kw["expected_resource_version"]: return None
        self.terminalized += 1; self.binding = replace(self.binding, state=kw["state"], decided_by_actor_id=kw["decided_by_actor_id"], decided_at=kw["decided_at"], resource_version=self.binding.resource_version + 1); return self.binding
    def consume(self, _c, **kw):
        if self.binding.state != "pending" or self.binding.resource_version != kw["expected_resource_version"]: return None
        self.binding = replace(self.binding, state="consumed", decided_by_actor_id=kw["decided_by_actor_id"], decided_at=kw["decided_at"], consumed_at=kw["decided_at"], resource_version=self.binding.resource_version + 1); return self.binding
    def get_pending_payload(self, *_a, **_k): return {"pending_calls": [{"tool_call_id": "call-1"}], "turn": {}}

class BaselineWriter:
    def promote(self, _c, **kw): return SiteBaselineV1(kw["site_id"], kw["schedule_version_id"], 1)

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

def decide(runs, approvals, audit, conversations, command, *, decision="reject", now=NOW, baseline=None, enabled=True, memberships=None, telemetry=None):
    return decide_approval(None, command=DecideApprovalCommandV1(site_id=command.site_id, actor_id=command.actor_id, approval_id=approvals.binding.approval_id, decision=decision, expected_resource_version=approvals.binding.resource_version, request_id=uuid4()), approvals=approvals, schedule_runs=runs, baselines=Baselines(baseline), baseline_writer=BaselineWriter(), memberships=memberships or Memberships(), audit_writer=audit, conversations=conversations, scheduling_baseline_enabled=enabled, clock=lambda: now, telemetry=telemetry)


@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("active", [False, None])
def test_inactive_or_absent_initiator_membership_terminalizes_stale(decision, active) -> None:
    runs, approvals, audit, conversations, command = pending()
    memberships = Memberships(active)
    result = decide(
        runs, approvals, audit, conversations, command,
        decision=decision, memberships=memberships,
    )
    assert result.outcome == "stale"
    assert result.expected["initiating_actor_membership"] == "active"
    assert result.current["initiating_actor_membership"] == "revoked_or_absent"
    assert memberships.calls == [{
        "app_user_id": approvals.binding.initiated_by_actor_id,
        "site_id": command.site_id,
    }]

def test_reject_terminalizes_once_and_records_audit_and_event() -> None:
    runs, approvals, audit, conversations, command = pending()
    result = decide(runs, approvals, audit, conversations, command)
    assert result.outcome == "rejected" and approvals.binding.state == "rejected"
    assert [item.outcome for item in audit.items] == ["approval_rejected"]
    assert conversations.items[0][0] == "event"


def test_decision_emits_approval_age_and_outcome() -> None:
    runs, approvals, audit, conversations, command = pending()
    records = []

    class Sink:
        def emit(self, record) -> None:
            records.append(record)

    result = decide(
        runs, approvals, audit, conversations, command, telemetry=Sink()
    )
    assert result.outcome == "rejected"
    assert len(records) == 1
    assert records[0].event == "approval.decided"
    assert records[0].approval_age_s == 0.0
    assert records[0].labels == {"approval_outcome": "rejected"}
    assert records[0].correlation.approval_id == approvals.binding.approval_id

def test_expiry_outranks_requested_reject_and_clears_pending_slot() -> None:
    runs, approvals, audit, conversations, command = pending()
    result = decide(runs, approvals, audit, conversations, command, now=NOW + timedelta(hours=2))
    assert result.outcome == "expired" and approvals.binding.state == "expired"
    assert audit.items[0].outcome == "approval_expired"


def test_expired_attempt_audits_the_candidate_that_resolves_in_the_transaction() -> None:
    runs, approvals, audit, conversations, command = pending()

    result = decide(
        runs, approvals, audit, conversations, command,
        now=NOW + timedelta(hours=2),
    )

    assert result.outcome == "expired"
    assert runs.candidate.evidence_refs != ()
    assert audit.items[0].evidence_refs == runs.candidate.evidence_refs

def test_valid_approve_consumes_and_promotes() -> None:
    runs, approvals, audit, conversations, command = pending()
    result = decide(runs, approvals, audit, conversations, command, decision="approve")
    assert result.outcome == "consumed" and approvals.binding.state == "consumed"
    assert audit.items[0].outcome == "approval_consumed"

def test_changed_candidate_terminalizes_stale() -> None:
    runs, approvals, audit, conversations, command = pending()
    runs.candidate = None
    assert decide(runs, approvals, audit, conversations, command, decision="approve").outcome == "stale"
    assert approvals.binding.state == "stale" and audit.items[0].outcome == "approval_stale"
    # AC1's other half: a candidate that does not resolve writes an ASSERTED empty
    # set, not an unlooked-at one. Reverting the write site to an unguarded
    # `candidate.evidence_refs` raises here instead of silently passing.
    assert audit.items[0].evidence_refs == ()

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


@pytest.mark.parametrize("fault_at", ["cancel", "audit", "event"])
def test_a_write_fault_inside_the_bundle_propagates_and_is_never_converted_to_stale(fault_at) -> None:
    """EAD-10's SECOND fork arm, proven where a mis-implementation would live.

    Faulting `terminalize` -- the bundle's first statement -- proves only that a
    failure before any write leaves nothing behind. The arm that actually
    matters is a fault AFTER the terminal row is written: the rule is that it
    propagates so the transaction rolls the whole bundle back, and that it is
    NEVER caught and re-reported as a business `stale`. Each of the three
    remaining bundle members is faulted in turn.
    """
    runs, approvals, audit, conversations, command = pending(agent_run_id=uuid4())

    def fail(*_a, **_k):
        raise DBAPIError("INSERT", {}, RuntimeError("database unavailable"))

    if fault_at == "cancel":
        conversations.cancel_agent_run_for_approval = fail
    elif fault_at == "audit":
        audit.append = fail
    else:
        conversations.append_approval_request_activity = fail

    # Propagates as DBAPIError -- not swallowed, not returned as a
    # `DecisionResultV1(outcome="stale")`.
    with pytest.raises(DBAPIError):
        decide(runs, approvals, audit, conversations, command)


def test_agent_path_reports_the_status_it_actually_wrote() -> None:
    """The activity must not claim `approval_required` for a cancelled run.

    `DecisionResultV1.activity` is part of the surface Story 4.3 imports.
    """
    runs, approvals, audit, conversations, command = pending(agent_run_id=uuid4())
    decide(runs, approvals, audit, conversations, command)
    event = next(kw for kind, kw in conversations.items if kind == "event")
    assert event["agent_run_status"] == "agent_cancelled"


def test_planner_path_states_no_agent_run_status() -> None:
    runs, approvals, audit, conversations, command = pending()
    decide(runs, approvals, audit, conversations, command)
    event = next(kw for kind, kw in conversations.items if kind == "event")
    assert event["agent_run_status"] is None
