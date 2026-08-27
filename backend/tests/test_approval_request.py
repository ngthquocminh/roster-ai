from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.schedule_run import ScheduleRunViewV1
from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.request_approval import ApprovalNotGrantedError, RequestApprovalCommandV1, StaleBaselineVersionError, request_approval

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


class Runs:
    def __init__(self):
        self.candidate = ScheduleVersionV1(schedule_version_id=uuid4(), schedule_run_id=uuid4(), scenario_id=uuid4(), scenario_version_id=uuid4(), feasible_solver_status="FEASIBLE")
        self.run = ScheduleRunViewV1(self.candidate.schedule_run_id, "solver_completed", None, 2, False)
    def get_run(self, *_a, **_k): return self.run
    def get_candidate(self, *_a, **_k): return self.candidate


class Baselines:
    def __init__(self, value=None): self.value = value
    def get(self, *_a): return self.value


class Approvals:
    def __init__(self): self.binding = None
    def create_pending(self, _c, *, binding, pending_payload): self.binding = binding


class Audit:
    def __init__(self): self.items = []
    def append(self, _c, envelope): self.items.append(envelope)


class Conversations:
    def __init__(self): self.items = []
    def append_approval_request_activity(self, _c, **kw): self.items.append(kw)
    def pause_agent_run_for_approval(self, _c, **kw): self.items.append(kw)


def _command(runs: Runs):
    return RequestApprovalCommandV1(site_id=uuid4(), actor_id=uuid4(), schedule_run_id=runs.candidate.schedule_run_id, expected_resource_version=2, expected_baseline_schedule_version=None, request_effect_key="command:test", request_id=uuid4(), conversation_id=uuid4())


def test_tx1_binds_only_the_exact_feasible_candidate_and_writes_success_audit() -> None:
    runs, approvals, audit, conversations = Runs(), Approvals(), Audit(), Conversations()
    result = request_approval(None, command=_command(runs), schedule_runs=runs, baselines=Baselines(), approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=True, clock=lambda: NOW)
    binding = result.binding
    assert binding == approvals.binding
    assert binding.candidate_schedule_version_id == runs.candidate.schedule_version_id
    assert audit.items[0].outcome == "approval_requested"


def test_tx1_refuses_a_changed_baseline_before_any_write() -> None:
    runs, approvals, audit, conversations = Runs(), Approvals(), Audit(), Conversations()
    command = _command(runs)
    with pytest.raises(StaleBaselineVersionError):
        request_approval(None, command=command, schedule_runs=runs, baselines=Baselines(SiteBaselineV1(command.site_id, uuid4(), 1)), approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=True, clock=lambda: NOW)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_an_ungranted_capability_before_any_write() -> None:
    runs, approvals, audit, conversations = Runs(), Approvals(), Audit(), Conversations()
    with pytest.raises(ApprovalNotGrantedError):
        request_approval(None, command=_command(runs), schedule_runs=runs, baselines=Baselines(), approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=False, clock=lambda: NOW)
    assert approvals.binding is None and not audit.items and not conversations.items
