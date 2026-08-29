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
    def __init__(self, existing=()): self.binding = None; self.pending_payload = None; self.existing = tuple(existing)
    def create_pending(self, _c, *, binding, pending_payload): self.binding = binding; self.pending_payload = pending_payload
    def list_for_schedule_run(self, _c, *, schedule_run_id, site_id): return self.existing


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


# --- Decision 9: the Story 2.9 tripwire's own remediation ---------------------
#
# `test_request_path_grants_no_approval_capability_in_this_milestone`
# (test_evaluation_harness.py) asserted that NO granted module declared an
# approval policy, and its message spelled out what had to exist before that
# could change: persist the pending calls, an approval decision endpoint,
# `DeferredToolResults` on the request path, and "restore the
# `approval_required` mapping per AD-7".
#
# Decision 9 requires that test be DELETED and replaced by the guard its own
# message describes -- explicitly NOT relaxed to an allowlist and left standing,
# which "converts a tripwire into decoration". It has been deleted; these three
# guards are the replacement. Each names the mutation that makes it fail.


def test_a_suspended_turn_finalises_as_approval_required_not_agent_cancelled() -> None:
    """Guard 1: the AD-7 mapping the stopgap owed.

    Fails if `"suspended": "agent_cancelled"` is restored in
    `execute_turn.terminal_status`.
    """
    from application.contracts.agent_runtime import AgentRunOutcomeV1
    from application.use_cases.execute_turn import terminal_status

    assert terminal_status(AgentRunOutcomeV1(status="suspended")) == "approval_required"


def test_tx1_persists_the_pending_calls_and_owned_turn_byte_identically() -> None:
    """Guard 2: `outcome.approval.pending_calls` and `.turn` survive the write.

    Asserted against a REAL `AgentApprovalPendingV1` serialization rather than a
    hand-made dict: the claim is that the CONTRACT round-trips, and a dict
    literal would only prove that JSON round-trips.

    Fails if `pending_payload` stops being threaded through
    `RequestApprovalCommandV1` into `create_pending`.
    """
    from pydantic import TypeAdapter

    from application.contracts.agent_runtime import (
        AgentApprovalPendingV1,
        AgentMessageV1,
        AgentToolCallProposalV1,
        AgentTurnV1,
    )

    pending = AgentApprovalPendingV1(
        pending_calls=(
            AgentToolCallProposalV1(
                tool_call_id="call-1",
                tool_name="scheduling_baseline",
                tool_args_json='{"request": {"schedule_run_id": "00000000-0000-0000-0000-000000000009", "expected_baseline_schedule_version": null}}',
            ),
        ),
        turn=AgentTurnV1(messages=(AgentMessageV1(role="user"),)),
    )
    payload = TypeAdapter(AgentApprovalPendingV1).dump_python(pending, mode="json")

    runs = Runs()
    approvals, audit, conversations = Approvals(), Audit(), Conversations()
    command = _command(runs, agent_run_id=uuid4(), pending_payload=payload)
    request_approval(
        None, command=command, schedule_runs=runs, baselines=Baselines(),
        approvals=approvals, audit_writer=audit, conversations=conversations,
        approval_expiry_seconds=3600, scheduling_baseline_enabled=True,
        clock=lambda: NOW,
    )

    assert approvals.pending_payload == payload
    assert TypeAdapter(AgentApprovalPendingV1).validate_python(approvals.pending_payload) == pending


def test_scheduling_baseline_is_the_only_granted_module_declaring_an_approval_policy() -> None:
    """Guard 3: a THIRD consequential capability cannot arrive without persistence.

    The tripwire's real successor. Not an allowlist bolted onto the old
    assertion: it fails on ANY module the request path grants that declares a
    non-`none` approval policy and is not `scheduling_baseline`, so the next
    consequential capability still has to come back through review.

    Fails under `DEMONSTRATION_ENABLED=true`.
    """
    from uuid import UUID

    from api.deps import get_capability_registry
    from application.capabilities.installed import enabled_feature_policy
    from application.capabilities.registry import PLANNER_ROLE, CapabilityGrantContextV1
    from settings import default_settings

    site_id = UUID(int=11)
    granted = get_capability_registry()(
        CapabilityGrantContextV1(
            role=PLANNER_ROLE, site_id=site_id,
            feature_policy=enabled_feature_policy(default_settings()),
            conversation_id=UUID(int=12), conversation_site_id=site_id,
        )
    )
    consequential = sorted(
        module.manifest.capability_name
        for module in granted
        if module.manifest.approval_policy != "none"
    )
    assert consequential == ["scheduling_baseline"], (
        f"{consequential} declare an approval policy on the request path. Every "
        "consequential capability needs its own persisted pending-call payload "
        "and a decision path that can drain it; adding one without that repeats "
        "the Story 2.9 stopgap. See Decision 9 and deferred-work.md."
    )
