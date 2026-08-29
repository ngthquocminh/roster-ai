"""Immutable approval binding persisted by the Epic 4 consequential workflow."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from application.contracts.canonical import CHECKSUM_ALGORITHM, CHECKSUM_SCHEMA_VERSION

SCHEMA_VERSION = "1"
ApprovalStateV1 = Literal["pending", "consumed", "rejected", "expired", "stale"]
ApprovalActionV1 = Literal["promote_baseline"]


@dataclass(frozen=True)
class ApprovalBindingV1:
    """One-time exact-action approval state; it never grants a broad authority."""

    approval_id: UUID
    state: ApprovalStateV1
    site_id: UUID
    action: ApprovalActionV1
    initiated_by_actor_id: UUID
    decided_by_actor_id: UUID | None
    conversation_id: UUID
    agent_run_id: UUID | None
    schedule_run_id: UUID
    candidate_schedule_version_id: UUID
    # Pinned at TX1 alongside the candidate. Decision 5 already quotes it in the
    # consequence summary; carrying it structurally is what lets the Results
    # surface render the scenario version Task 10 requires without re-reading
    # the run.
    scenario_version_id: UUID
    baseline_schedule_version: str | None
    baseline_resource_version: int | None
    parameter_hash: str
    consequence_summary: str
    consequence_hash: str
    checksum_algorithm: str = CHECKSUM_ALGORITHM
    checksum_schema_version: str = CHECKSUM_SCHEMA_VERSION
    # This is the derived consequential-policy version, not AgentDepsV1's
    # capability-grant generation string.
    policy_version: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    consumed_at: datetime | None = None
    request_effect_key: str = ""
    resource_version: int = 1
    schema_version: str = SCHEMA_VERSION


__all__ = ["ApprovalActionV1", "ApprovalBindingV1", "ApprovalStateV1", "SCHEMA_VERSION"]
