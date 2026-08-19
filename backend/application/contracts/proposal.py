"""Owned reversible scheduling-proposal contracts (AD-9, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from application.contracts.evidence_ref import EvidenceGroupV1
from application.contracts.scenario_projection import LockV1

SCHEMA_VERSION = "1"

# Closed vocabulary persisted in both ``persisted_event.payload`` and
# ``proposal_version.payload``. Adding, renaming, or removing a member is a
# contract migration, not a refactor. The names intentionally match the five
# operations already consumed by the CP-SAT builder; no legacy fuzzy resolver
# is imported into this boundary.
DraftConstraintKindV1 = Literal[
    "set_min_workers_per_task",
    "scale_demand",
    "lock_worker_shift",
    "exclude_worker_from_task",
    "set_max_hours",
]
ProposalStateV1 = Literal["active", "rejected"]


@dataclass(frozen=True)
class DraftConstraintProposalV1:
    """UNTRUSTED model input containing identifiers and typed arguments only."""

    kind: DraftConstraintKindV1 = "set_min_workers_per_task"
    group: EvidenceGroupV1 = "work-areas-and-tasks"
    record_id: str = ""
    related_group: EvidenceGroupV1 | None = None
    related_record_id: str | None = None
    n: int | None = None
    factor: float | None = None
    max_hours: float | None = None
    start_minute: int | None = None
    end_minute: int | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ResolvedEntityV1:
    """TRUSTED projection identity with an application-composed label."""

    group: EvidenceGroupV1 = "work-areas-and-tasks"
    record_id: str = ""
    label: str = ""
    scenario_version_id: UUID | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DraftConstraintV1:
    """TRUSTED, resolved and validated reversible solver input."""

    kind: DraftConstraintKindV1 = "set_min_workers_per_task"
    resolved_entities: tuple[ResolvedEntityV1, ...] = ()
    n: int | None = None
    factor: float | None = None
    max_hours: float | None = None
    start_minute: int | None = None
    end_minute: int | None = None
    description: str = ""
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ProposalV1:
    """Immutable proposal version and its mutable aggregate-state projection.

    Staleness is deliberately absent: it is derived at read time by comparing
    ``scenario_version_id`` with the current governed projection version.
    """

    proposal_id: UUID | None = None
    proposal_version_id: UUID | None = None
    scenario_id: UUID | None = None
    scenario_version_id: UUID | None = None
    expected_baseline_schedule_version: str | None = None
    resolved_entities: tuple[ResolvedEntityV1, ...] = ()
    constraints: tuple[DraftConstraintV1, ...] = ()
    preserved_locks: tuple[LockV1, ...] = ()
    consequence_summary: str = ""
    canonical_hash: str = ""
    canonical_hash_algorithm: str = "sha256"
    canonical_hash_schema_version: str = "rfc8785-v1"
    state: ProposalStateV1 = "active"
    resource_version: int = 1
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DraftProposalV1:
    """UNTRUSTED model output: a citation to one trusted draft result."""

    draft_id: str = ""
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ProposalViewV1:
    """Current proposal plus derived version-drift state for planner reads."""

    proposal: ProposalV1
    current_scenario_version_id: UUID
    stale: bool
    schema_version: str = SCHEMA_VERSION


__all__ = [
    "SCHEMA_VERSION",
    "DraftConstraintKindV1",
    "DraftConstraintProposalV1",
    "DraftConstraintV1",
    "DraftProposalV1",
    "ProposalStateV1",
    "ProposalV1",
    "ProposalViewV1",
    "ResolvedEntityV1",
]
