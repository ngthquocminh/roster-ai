"""Append-only consequential-workflow audit contract (AD-12, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1

SCHEMA_VERSION = "1"
AuditOutcomeV1 = Literal[
    "approval_requested", "approval_consumed", "approval_rejected", "approval_expired", "approval_stale",
    "approval_denied",
]


@dataclass(frozen=True)
class WorkerFactsV1:
    lease_owner: str | None = None
    attempt_id: UUID | None = None
    fencing_epoch: int | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AuditEnvelopeV1:
    audit_id: UUID
    attempt_id: UUID
    request_id: UUID
    site_id: UUID
    initiated_by_actor_id: UUID
    decided_by_actor_id: UUID | None
    conversation_id: UUID | None
    agent_run_id: UUID | None
    approval_id: UUID | None
    schedule_run_id: UUID | None
    action: str
    outcome: AuditOutcomeV1
    success: bool
    effect_key: str
    before_version: str | None
    after_version: str | None
    safe_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    app_version: str
    worker_facts: WorkerFactsV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    occurred_at: datetime
    schema_version: str = SCHEMA_VERSION


__all__ = ["AuditEnvelopeV1", "AuditOutcomeV1", "SCHEMA_VERSION", "WorkerFactsV1"]
