from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.schedule_run import ScheduleRunViewV1
from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.request_approval import (
    ApprovalNotGrantedError,
    CandidateNotFoundError,
    CandidateNotPromotableError,
    RequestApprovalCommandV1,
    StaleBaselineVersionError,
    StaleResourceVersionError,
    request_approval,
)

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


class Runs:
    """Fake `ScheduleRunRepository`. Covers every AC3 refusal shape by
    construction: a non-`solver_completed` `status` models infeasible,
    timed-out, cancelled, and failed runs alike -- `request_approval` gates on
    status alone and never branches on which terminal reason produced it."""

    def __init__(self, *, status="solver_completed", no_candidate=False, resource_version=2, run_id=None):
        self.candidate = None if no_candidate else ScheduleVersionV1(schedule_version_id=uuid4(), schedule_run_id=run_id or uuid4(), scenario_id=uuid4(), scenario_version_id=uuid4(), feasible_solver_status="FEASIBLE", assignments=())
        self.run_id = (self.candidate.schedule_run_id if self.candidate else run_id) or uuid4()
        self.run = ScheduleRunViewV1(self.run_id, status, None, resource_version, False)
    def get_run(self, *_a, **_k): return self.run
    def get_candidate(self, *_a, **_k): return self.candidate


class MissingRuns(Runs):
    """No schedule run is visible in this site at all (AC3)."""

    def get_run(self, *_a, **_k): return None


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


def _command(runs: Runs, **overrides):
    defaults = dict(site_id=uuid4(), actor_id=uuid4(), schedule_run_id=runs.run_id, expected_resource_version=2, expected_baseline_schedule_version=None, request_effect_key="command:test", request_id=uuid4(), conversation_id=uuid4())
    defaults.update(overrides)
    return RequestApprovalCommandV1(**defaults)


def _run_approval(runs, *, baselines=None, scheduling_baseline_enabled=True, command=None):
    approvals, audit, conversations = Approvals(), Audit(), Conversations()
    command = command or _command(runs)
    result = request_approval(None, command=command, schedule_runs=runs, baselines=baselines or Baselines(), approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=scheduling_baseline_enabled, clock=lambda: NOW)
    return result, approvals, audit, conversations


def test_tx1_binds_only_the_exact_feasible_candidate_and_writes_success_audit() -> None:
    runs = Runs()
    result, approvals, audit, _ = _run_approval(runs)
    binding = result.binding
    assert binding == approvals.binding
    assert binding.candidate_schedule_version_id == runs.candidate.schedule_version_id
    assert audit.items[0].outcome == "approval_requested"


def test_tx1_persists_the_agent_pending_payload_and_pauses_the_run() -> None:
    runs = Runs()
    agent_run_id = uuid4()
    command = _command(runs, agent_run_id=agent_run_id, pending_payload={"pending_calls": ["tool-1"]})
    result, approvals, _audit, conversations = _run_approval(runs, command=command)
    assert result.binding.agent_run_id == agent_run_id
    assert conversations.items[0]["claimed_agent_run_id"] == agent_run_id
    assert conversations.items[0]["binding"] == result.binding


def test_tx1_refuses_a_missing_schedule_run_before_any_write() -> None:
    runs = MissingRuns()
    with pytest.raises(CandidateNotFoundError):
        _run_approval(runs, command=_command(runs))


def test_tx1_refuses_a_non_completed_run_before_any_write() -> None:
    # Models infeasible / timed-out / cancelled / failed alike -- the use case
    # gates on `status != "solver_completed"`, never on which terminal reason
    # produced that status.
    runs = Runs(status="solver_infeasible")
    _, approvals, audit, conversations = _catch(CandidateNotPromotableError, runs)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_a_completed_run_with_no_candidate_row_before_any_write() -> None:
    runs = Runs(no_candidate=True)
    _, approvals, audit, conversations = _catch(CandidateNotPromotableError, runs)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_a_stale_run_resource_version_before_any_write() -> None:
    runs = Runs(resource_version=5)
    command = _command(runs, expected_resource_version=2)
    _, approvals, audit, conversations = _catch(StaleResourceVersionError, runs, command=command)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_a_changed_baseline_before_any_write() -> None:
    runs = Runs()
    command = _command(runs)
    baselines = Baselines(SiteBaselineV1(command.site_id, uuid4(), 1))
    _, approvals, audit, conversations = _catch(StaleBaselineVersionError, runs, baselines=baselines, command=command)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_an_expected_baseline_that_no_longer_exists_before_any_write() -> None:
    # The other direction of the same check: the planner expected a baseline
    # to still be there (a non-null assertion) and it has since been cleared.
    runs = Runs()
    command = _command(runs, expected_baseline_schedule_version="some-version")
    _, approvals, audit, conversations = _catch(StaleBaselineVersionError, runs, baselines=Baselines(None), command=command)
    assert approvals.binding is None and not audit.items and not conversations.items


def test_tx1_refuses_an_ungranted_capability_before_any_write() -> None:
    runs = Runs()
    _, approvals, audit, conversations = _catch(ApprovalNotGrantedError, runs, scheduling_baseline_enabled=False)
    assert approvals.binding is None and not audit.items and not conversations.items


def _catch(error_type, runs, **kwargs):
    approvals, audit, conversations = Approvals(), Audit(), Conversations()
    command = kwargs.pop("command", None) or _command(runs)
    baselines = kwargs.pop("baselines", None) or Baselines()
    scheduling_baseline_enabled = kwargs.pop("scheduling_baseline_enabled", True)
    with pytest.raises(error_type):
        request_approval(None, command=command, schedule_runs=runs, baselines=baselines, approvals=approvals, audit_writer=audit, conversations=conversations, approval_expiry_seconds=3600, scheduling_baseline_enabled=scheduling_baseline_enabled, clock=lambda: NOW)
    return None, approvals, audit, conversations
