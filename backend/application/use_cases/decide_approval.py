"""TX3 and the shared EAD-10 approval revalidation fork.

Story 4.3 imports :func:`revalidate_binding`; it must not grow a second
decision/revalidation path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from application.capabilities.registry import PolicyInputsV1, derive_policy_version
from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.canonical import contract_digest
from application.ports.conversation import ExecutedAgentRunV1

SCOPE_CONTROLS = {
    "promotion": "NOT COVERED: promotion:owned_by_story_4_3",
    "audit": "NOT COVERED: audit:denied_attempts_owned_by_story_4_3",
    "resume": "NOT COVERED: resume:deferred_tool_results_owned_by_story_4_3",
}

class DecideApprovalError(ValueError):
    code = "invalid_approval_command"

    def __init__(self, message: str, *, expected: dict | None = None, current: dict | None = None):
        super().__init__(message)
        self.expected = expected or {}
        self.current = current or {}
class ApprovalNotFoundError(DecideApprovalError): code = "approval_not_found"
class ApprovalNotPendingError(DecideApprovalError): code = "approval_not_pending"
class StaleResourceVersionError(DecideApprovalError): code = "stale_resource_version"
class ApprovalNotGrantedError(DecideApprovalError): code = "approval_not_granted"
class BaselinePromotionNotAvailableError(DecideApprovalError): code = "promotion_not_available"

@dataclass(frozen=True)
class RevalidationV1:
    outcome: Literal["expired", "stale"] | None
    expected: dict
    current: dict

@dataclass(frozen=True)
class DecisionResultV1:
    outcome: Literal["rejected", "expired", "stale"]
    binding: ApprovalBindingV1
    activity: ExecutedAgentRunV1 | None
    expected: dict
    current: dict

@dataclass(frozen=True)
class DecideApprovalCommandV1:
    site_id: UUID
    actor_id: UUID
    approval_id: UUID
    decision: Literal["approve", "reject"]
    expected_resource_version: int
    request_id: UUID

def revalidate_binding(connection: Any, *, binding: ApprovalBindingV1, schedule_runs: Any, baselines: Any, now: datetime, scheduling_baseline_enabled: bool) -> RevalidationV1:
    """EAD-10's fixed fork: expiry first, then business mismatch; write faults propagate."""
    if binding.expires_at is not None and now >= binding.expires_at:
        return RevalidationV1("expired", {"expires_at": binding.expires_at.isoformat()}, {"now": now.isoformat()})
    candidate = schedule_runs.get_candidate(connection, schedule_run_id=binding.schedule_run_id, site_id=binding.site_id)
    run = schedule_runs.get_run(connection, run_id=binding.schedule_run_id, site_id=binding.site_id)
    baseline = baselines.get(connection, binding.site_id)
    _, _, consequence_hash = contract_digest({"consequence_summary": binding.consequence_summary})
    parameter = {"action": "promote_baseline", "schedule_run_id": str(binding.schedule_run_id), "candidate_schedule_version_id": str(binding.candidate_schedule_version_id), "expected_baseline_schedule_version": binding.baseline_schedule_version, "expected_resource_version": run.resource_version if run else None}
    _, _, parameter_hash = contract_digest(parameter)
    current_baseline = str(baseline.schedule_version_id) if baseline else None
    current_policy = derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled))
    valid_candidate = candidate is not None and candidate.schedule_version_id == binding.candidate_schedule_version_id and candidate.feasible_solver_status in ("OPTIMAL", "FEASIBLE")
    # The TX1 run version is part of the signed parameter digest; the binding's
    # own resource version is unrelated and must never be used as a proxy.
    valid = valid_candidate and run is not None and current_baseline == binding.baseline_schedule_version and (baseline.resource_version if baseline else None) == binding.baseline_resource_version and parameter_hash == binding.parameter_hash and consequence_hash == binding.consequence_hash and current_policy == binding.policy_version
    if valid:
        return RevalidationV1(None, {}, {})
    return RevalidationV1("stale", {"candidate_schedule_version_id": str(binding.candidate_schedule_version_id), "baseline_schedule_version": binding.baseline_schedule_version, "parameter_hash": binding.parameter_hash, "consequence_hash": binding.consequence_hash, "policy_version": binding.policy_version}, {"candidate_schedule_version_id": str(candidate.schedule_version_id) if candidate else None, "baseline_schedule_version": current_baseline, "parameter_hash": parameter_hash, "consequence_hash": consequence_hash, "policy_version": current_policy})

def decide_approval(connection: Any, *, command: DecideApprovalCommandV1, approvals: Any, schedule_runs: Any, baselines: Any, audit_writer: Any, conversations: Any, scheduling_baseline_enabled: bool, clock: Any, app_version: str = "0.1.0") -> DecisionResultV1:
    if not scheduling_baseline_enabled: raise ApprovalNotGrantedError("baseline approval is not granted by policy")
    binding = approvals.get(connection, approval_id=command.approval_id, site_id=command.site_id)
    if binding is None: raise ApprovalNotFoundError("approval is not visible in this site")
    if binding.state != "pending":
        raise ApprovalNotPendingError("approval is no longer pending", expected={"state": "pending"}, current={"state": binding.state, "resource_version": binding.resource_version})
    if binding.resource_version != command.expected_resource_version:
        raise StaleResourceVersionError("approval resource version changed", expected={"resource_version": command.expected_resource_version}, current={"resource_version": binding.resource_version, "state": binding.state})
    now = clock()
    check = revalidate_binding(connection, binding=binding, schedule_runs=schedule_runs, baselines=baselines, now=now, scheduling_baseline_enabled=scheduling_baseline_enabled)
    if check.outcome is None:
        if command.decision == "approve":
            # Story 4.3 owns TX2; do not write a speculative promotion body.
            raise BaselinePromotionNotAvailableError("Baseline promotion is not available yet.")
        outcome: Literal["rejected", "expired", "stale"] = "rejected"
    else:
        outcome = check.outcome
    terminal = approvals.terminalize(connection, approval_id=binding.approval_id, site_id=command.site_id, state=outcome, decided_by_actor_id=command.actor_id, decided_at=now, expected_resource_version=binding.resource_version)
    if terminal is None:
        raise ApprovalNotPendingError("approval is no longer pending", expected={"state": "pending", "resource_version": binding.resource_version}, current={"state": "terminal_or_changed"})
    reason = f"approval_{outcome}"
    if terminal.agent_run_id is not None:
        conversations.cancel_agent_run_for_approval(connection, agent_run_id=terminal.agent_run_id, binding=terminal, reason=reason)
    audit_writer.append(connection, AuditEnvelopeV1(audit_id=uuid4(), attempt_id=uuid4(), request_id=command.request_id, site_id=command.site_id, initiated_by_actor_id=terminal.initiated_by_actor_id, decided_by_actor_id=command.actor_id, conversation_id=terminal.conversation_id, agent_run_id=terminal.agent_run_id, approval_id=terminal.approval_id, schedule_run_id=terminal.schedule_run_id, action=terminal.action, outcome=f"approval_{outcome}", success=True, effect_key=terminal.request_effect_key, before_version=terminal.baseline_schedule_version, after_version=None, safe_summary=terminal.consequence_summary, parameter_hash=terminal.parameter_hash, consequence_hash=terminal.consequence_hash, policy_version=terminal.policy_version, app_version=app_version, worker_facts=WorkerFactsV1(), evidence_refs=(), occurred_at=now))
    activity = conversations.append_approval_request_activity(connection, binding=terminal, actor_id=command.actor_id, request_id=command.request_id, agent_run_id=terminal.agent_run_id, occurred_at=now)
    return DecisionResultV1(outcome, terminal, activity, check.expected, check.current)

__all__ = ["DecideApprovalCommandV1", "DecisionResultV1", "revalidate_binding", "decide_approval"]
