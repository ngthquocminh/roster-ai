"""Pure read contracts for reconstructing one persisted scheduling decision."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from application.contracts.audit_envelope import AuditOutcomeV1, WorkerFactsV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import MetricSetV1, ScheduleRunStatusV1

SCHEMA_VERSION = "1"

SCOPE_CONTROLS = (
    "membership:agent_run_bound_conversation_events",
    "tool_proposals:approval_triggering_call_only",
    "comparison:linked_by_reference_never_recomputed",
    "payload:identity_only_never_turn",
)


@dataclass(frozen=True)
class ProvenanceCommonV1:
    occurred_at: datetime
    item_type: str
    site_id: UUID
    actor_id: UUID | None
    initiated_by_actor_id: UUID | None
    decided_by_actor_id: UUID | None
    request_id: UUID | None
    attempt_id: UUID | None
    conversation_id: UUID | None
    agent_run_id: UUID | None
    tool_call_id: str | None
    approval_id: UUID | None
    job_attempt_id: UUID | None
    schedule_run_id: UUID | None
    audit_id: UUID | None
    schedule_version_id: UUID | None
    scenario_version_id: UUID | None
    evidence_refs: tuple[EvidenceRefV1, ...]
    schema_version: str


@dataclass(frozen=True)
class SolverRunProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["solver_run"]
    status: ScheduleRunStatusV1
    reason: str | None
    baseline_schedule_version: str | None
    candidate_schedule_version_id: UUID | None
    comparison_status: Literal["available", "unavailable"]
    comparison_reason: str | None
    metrics: MetricSetV1 | None


@dataclass(frozen=True)
class RunProgressProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["run_progress"]
    status: ScheduleRunStatusV1
    reason: str | None
    resource_version: int


@dataclass(frozen=True)
class DraftProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["draft"]
    proposal_id: UUID
    proposal_version_id: UUID
    consequence_summary: str


@dataclass(frozen=True)
class EvidenceClaimProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["evidence_claim"]
    claim: str
    value: float | int | str | None
    unit: str | None


@dataclass(frozen=True)
class ToolProposalProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["tool_proposal"]
    tool_name: str


@dataclass(frozen=True)
class ApprovalRequestProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["approval_request"]
    state: Literal["pending", "consumed", "rejected", "expired", "stale"]
    consequence_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    expires_at: datetime


@dataclass(frozen=True)
class ApprovalDecisionProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["approval_decision"]
    outcome: AuditOutcomeV1
    state: Literal["consumed", "rejected", "expired", "stale"]


@dataclass(frozen=True)
class AuditRecordProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["audit_record"]
    action: str
    outcome: AuditOutcomeV1
    success: bool
    safe_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    app_version: str
    worker_facts: WorkerFactsV1


@dataclass(frozen=True)
class BaselinePromotionProvenanceV1(ProvenanceCommonV1):
    item_type: Literal["baseline_promotion"]
    before_version: str | None
    after_version: str


DecisionProvenanceItemV1 = (
    SolverRunProvenanceV1 | RunProgressProvenanceV1 | DraftProvenanceV1
    | EvidenceClaimProvenanceV1 | ToolProposalProvenanceV1
    | ApprovalRequestProvenanceV1 | ApprovalDecisionProvenanceV1
    | AuditRecordProvenanceV1 | BaselinePromotionProvenanceV1
)


@dataclass(frozen=True)
class DecisionProvenanceV1:
    schedule_run_id: UUID
    site_id: UUID
    items: tuple[DecisionProvenanceItemV1, ...]
    schema_version: str = SCHEMA_VERSION


__all__ = [name for name in globals() if name.endswith("V1") or name == "SCOPE_CONTROLS"]
