"""TX1: atomically bind one feasible candidate for a consequential decision."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from application.app_version import APP_VERSION

from application.capabilities.registry import PolicyInputsV1, derive_policy_version
from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.canonical import contract_digest
from application.ports.conversation import ExecutedAgentRunV1

SCOPE_CONTROLS = {
    "decision": "NOT COVERED: decision:owned_by_story_4_2",
    "promotion": "NOT COVERED: promotion:owned_by_story_4_3",
    "audit": "NOT COVERED: audit:non_success_outcomes_owned_by_story_4_3",
}


class ApprovalRequestError(ValueError):
    code = "invalid_approval_command"


class CandidateNotFoundError(ApprovalRequestError):
    code = "candidate_not_found"


class CandidateNotPromotableError(ApprovalRequestError):
    code = "candidate_not_promotable"


class StaleResourceVersionError(ApprovalRequestError):
    code = "stale_resource_version"


class StaleBaselineVersionError(ApprovalRequestError):
    code = "stale_baseline_version"


class ApprovalNotGrantedError(ApprovalRequestError):
    code = "approval_not_granted"


class ApprovalAlreadyPendingError(ApprovalRequestError):
    """A pending binding already exists for this candidate.

    AD-14 forbids the browser being authority for a decision, so this cannot be
    left to the client's `pendingApproval` prop -- which fails open while the
    approvals query is loading or errored. The application check below is the
    friendly 409; the partial unique index
    `uq_approval_request_pending_run` is what makes duplication actually
    impossible under concurrency, since this check is read-then-write.
    """

    code = "approval_already_pending"


@dataclass(frozen=True)
class RequestApprovalCommandV1:
    site_id: UUID
    actor_id: UUID
    schedule_run_id: UUID
    expected_resource_version: int
    expected_baseline_schedule_version: str | None
    request_effect_key: str
    request_id: UUID
    conversation_id: UUID
    agent_run_id: UUID | None = None
    pending_payload: dict | None = None


@dataclass(frozen=True)
class RequestApprovalResultV1:
    binding: ApprovalBindingV1
    activity: ExecutedAgentRunV1 | None


def request_approval(
    connection: Any,
    *,
    command: RequestApprovalCommandV1,
    schedule_runs: Any,
    baselines: Any,
    approvals: Any,
    audit_writer: Any,
    conversations: Any,
    approval_expiry_seconds: int,
    scheduling_baseline_enabled: bool,
    clock: Any,
    app_version: str = APP_VERSION,
) -> RequestApprovalResultV1:
    """Build TX1. The caller owns the transaction; no repository may commit."""
    if not scheduling_baseline_enabled:
        raise ApprovalNotGrantedError("baseline approval is not granted by policy")
    run = schedule_runs.get_run(connection, run_id=command.schedule_run_id, site_id=command.site_id)
    if run is None:
        raise CandidateNotFoundError("the requested schedule run is not available")
    if run.status != "solver_completed":
        raise CandidateNotPromotableError("the requested schedule run is not promotable")
    if run.resource_version != command.expected_resource_version:
        raise StaleResourceVersionError("the schedule run has changed")
    candidate = schedule_runs.get_candidate(connection, schedule_run_id=command.schedule_run_id, site_id=command.site_id)
    if candidate is None or candidate.feasible_solver_status not in ("OPTIMAL", "FEASIBLE") or candidate.schedule_version_id is None:
        raise CandidateNotPromotableError("the requested schedule run has no feasible candidate")
    existing = approvals.list_for_schedule_run(connection, schedule_run_id=command.schedule_run_id, site_id=command.site_id)
    if any(item.state == "pending" for item in existing):
        raise ApprovalAlreadyPendingError("a decision is already pending for this candidate")
    baseline = baselines.get(connection, command.site_id)
    current_baseline = str(baseline.schedule_version_id) if baseline else None
    if current_baseline != command.expected_baseline_schedule_version:
        raise StaleBaselineVersionError("the current baseline has changed")
    now = clock()
    approval_id = uuid4()
    summary = (
        f"Candidate schedule version {candidate.schedule_version_id}; baseline "
        f"{current_baseline or 'no current baseline'}; scenario version "
        f"{candidate.scenario_version_id}; {len(candidate.assignments)} candidate assignments."
    )
    parameter = {
        "action": "promote_baseline", "schedule_run_id": str(command.schedule_run_id),
        "candidate_schedule_version_id": str(candidate.schedule_version_id),
        "expected_baseline_schedule_version": current_baseline,
        "expected_resource_version": command.expected_resource_version,
    }
    algorithm, schema, parameter_hash = contract_digest(parameter)
    _, _, consequence_hash = contract_digest({"consequence_summary": summary})
    binding = ApprovalBindingV1(
        approval_id=approval_id, state="pending", site_id=command.site_id, action="promote_baseline",
        initiated_by_actor_id=command.actor_id, decided_by_actor_id=None, conversation_id=command.conversation_id,
        agent_run_id=command.agent_run_id, schedule_run_id=command.schedule_run_id,
        candidate_schedule_version_id=candidate.schedule_version_id, scenario_version_id=candidate.scenario_version_id,
        baseline_schedule_version=current_baseline,
        baseline_resource_version=baseline.resource_version if baseline else None, parameter_hash=parameter_hash,
        consequence_summary=summary, consequence_hash=consequence_hash, checksum_algorithm=algorithm,
        checksum_schema_version=schema, policy_version=derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled)),
        created_at=now, expires_at=now + timedelta(seconds=approval_expiry_seconds), request_effect_key=command.request_effect_key,
    )
    approvals.create_pending(connection, binding=binding, pending_payload=command.pending_payload)
    audit_writer.append(connection, AuditEnvelopeV1(
        audit_id=uuid4(), attempt_id=uuid4(), request_id=command.request_id, site_id=command.site_id,
        initiated_by_actor_id=command.actor_id, decided_by_actor_id=None, conversation_id=command.conversation_id,
        agent_run_id=command.agent_run_id, approval_id=approval_id, schedule_run_id=command.schedule_run_id,
        # AD-12 keys successful mutation audit on (site_id, effect_key, outcome).
        # `str(approval_id)` is a UUID minted moments ago, so it can never
        # collide and `uq_audit_event_success_effect` would guarantee nothing
        # about the effect it names. The command's `request_effect_key` IS the
        # effect identity -- the same value the binding is unique on.
        action="promote_baseline", outcome="approval_requested", success=True, effect_key=command.request_effect_key,
        before_version=current_baseline, after_version=None, safe_summary=summary, parameter_hash=parameter_hash,
        consequence_hash=consequence_hash, policy_version=binding.policy_version, app_version=app_version,
        worker_facts=WorkerFactsV1(), evidence_refs=candidate.evidence_refs, occurred_at=now,
    ))
    if command.agent_run_id is not None:
        activity = conversations.pause_agent_run_for_approval(connection, claimed_agent_run_id=command.agent_run_id, binding=binding, request_id=command.request_id)
    else:
        activity = conversations.append_approval_request_activity(connection, binding=binding, actor_id=command.actor_id, request_id=command.request_id)
    return RequestApprovalResultV1(binding=binding, activity=activity)


__all__ = ["RequestApprovalCommandV1", "RequestApprovalResultV1", "request_approval"]
