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
ProposalStateV1 = Literal["active", "rejected", "applied"]
# Who ended a draft (Story 5.11). `system` covers both the migration's duplicate
# collapse and a promotion (`applied`); the planner and the assistant each end a
# draft on an explicit request.
ProposalEndedByV1 = Literal["planner", "assistant", "system"]
# What an agent draft turn did to the conversation's one working draft.
DraftOutcomeV1 = Literal["created", "updated"]


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
    """Current proposal plus derived version-drift state for planner reads.

    The three lifecycle fields default only so ``command_idempotency`` rows
    written before Story 5.11 still decode on replay; every fresh read fills
    ``version_ordinal``. State is read from the ``proposal`` row, never from a
    stored version payload (``ProposalV1.state`` there is whatever it held at
    write time).
    """

    proposal: ProposalV1
    current_scenario_version_id: UUID
    stale: bool
    version_ordinal: int | None = None
    ended_by: ProposalEndedByV1 | None = None
    applied_version_ordinal: int | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class WorkingDraftObservationV1:
    """TRUSTED: the conversation's working draft as one agent turn first saw it."""

    proposal_id: UUID
    resource_version: int
    version_ordinal: int
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AgentDraftWriteV1:
    """TRUSTED: what finalize applies for an agent draft (spec 2.1, 2.7).

    ``observed_*`` are the working draft this turn resolved against, or ``None``
    when there was none; finalize applies the write only if the conversation
    still looks exactly like that.
    """

    proposal: ProposalV1
    outcome: DraftOutcomeV1
    version_ordinal: int
    observed_working_id: UUID | None = None
    observed_resource_version: int | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AgentDraftDiscardV1:
    """TRUSTED: an explicit agent discard, bound to the state it observed."""

    proposal_id: UUID
    observed_resource_version: int
    version_ordinal: int
    schema_version: str = SCHEMA_VERSION


__all__ = [
    "SCHEMA_VERSION",
    "AgentDraftDiscardV1",
    "AgentDraftWriteV1",
    "DraftConstraintKindV1",
    "DraftConstraintProposalV1",
    "DraftConstraintV1",
    "DraftOutcomeV1",
    "DraftProposalV1",
    "ProposalEndedByV1",
    "ProposalStateV1",
    "ProposalV1",
    "ProposalViewV1",
    "ResolvedEntityV1",
    "WorkingDraftObservationV1",
]
