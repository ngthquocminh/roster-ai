"""Owned clarification, refusal, and terminal-outcome contracts (AD-14, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping
from uuid import UUID

from application.contracts.agent_status import AgentRunStatusV1
from application.contracts.evidence_ref import EvidenceGroupV1

SCHEMA_VERSION = "1"

RefusalReasonV1 = Literal[
    "unsupported_request",
    "capability_unavailable",
    "out_of_scope",
]
TerminalReasonV1 = Literal[
    "provider_error",
    "invalid_output",
    "budget_exhausted",
    "deadline_exceeded",
    "cancelled",
    "capability_error",
    "refused",
    "approval_unsupported",
]

# Decision 2 reconciles UX-DR6's refusal label with AD-14's closed eight-item
# activity vocabulary: refusal is a reason-discriminated terminal outcome.
# Gap 1 stays explicit rather than inventing an authorization system for the
# one-user MVP.
SCOPE_CONTROLS: Mapping[str, str] = {
    "activity:closed_vocabulary": (
        "COVERS clarification and reason-discriminated refusal using AD-14's eight "
        "persisted activity discriminants. NOT COVERED: a ninth refusal discriminant; "
        "the distinct planner-visible label is derived from terminal reason instead."
    ),
    "authority:one_user_mvp": (
        "COVERS feature-policy exclusion as capability absence and prohibited manifests "
        "as registration refusal. NOT COVERED: role-based authorization differences or "
        "an installable prohibited capability; neither mechanism exists in the one-user MVP."
    ),
}


@dataclass(frozen=True)
class EntityCandidateProposalV1:
    """UNTRUSTED model proposal. A label is deliberately impossible to provide."""

    group: EvidenceGroupV1 = "workers"
    record_id: str = ""
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class EntityCandidateV1:
    """TRUSTED candidate resolved against the governed scenario projection."""

    group: EvidenceGroupV1 = "workers"
    record_id: str = ""
    label: str = ""
    scenario_version_id: UUID | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ClarificationV1:
    """UNTRUSTED clarification emitted by the model adapter."""

    question: str = ""
    candidates: tuple[EntityCandidateProposalV1, ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ResolvedClarificationV1:
    """Persistable clarification whose candidate labels are application-owned."""

    question: str = ""
    candidates: tuple[EntityCandidateV1, ...] = ()
    scenario_version_id: UUID | None = None
    dropped_candidate_count: int = 0
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class RefusalV1:
    """UNTRUSTED model presentation of an application-bounded refusal."""

    reason: RefusalReasonV1 = "unsupported_request"
    detail: str = ""
    next_step: str | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class TerminalOutcomeV1:
    """Persistable literal terminal state for a completed or failed turn."""

    status: AgentRunStatusV1 = "failed"
    reason: TerminalReasonV1 = "invalid_output"
    detail: str = ""
    next_step: str | None = None
    schema_version: str = SCHEMA_VERSION


__all__ = [
    "SCHEMA_VERSION",
    "SCOPE_CONTROLS",
    "ClarificationV1",
    "EntityCandidateProposalV1",
    "EntityCandidateV1",
    "RefusalReasonV1",
    "RefusalV1",
    "ResolvedClarificationV1",
    "TerminalOutcomeV1",
    "TerminalReasonV1",
]
