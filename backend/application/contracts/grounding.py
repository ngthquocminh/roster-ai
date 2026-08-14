"""Owned contracts for computed claims and exact evidence (AD-11, AD-20).

Model-produced proposals are deliberately value-free: they cite a trusted
application calculation by ``result_id``.  The grounding gate turns those
untrusted citations into persisted claims whose values and evidence locators
come only from the governed calculator result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1

SCHEMA_VERSION = "1"

MetricV1 = Literal[
    # Demand splits by the dimension it is measured in, because
    # `DemandIntervalV1.unit` is `volume | headcount` and the two are not
    # interconvertible here: the only rate in the projection is
    # `QualificationRefV1.rate`, which is per WORKER per task. Converting volume
    # to minutes therefore depends on who performs the work, which is an
    # assignment -- a solver question owned by Epic 3, not a read-model one.
    # This is a fifth member for dimensional honesty, NOT padding toward a
    # rounder catalogue; `epics.md:1527` forbids the latter and this is not it.
    "required_headcount_minutes",
    "required_demand_volume",
    "staffed_minutes",
    "shortfall_minutes",
    "qualified_worker_count",
]
DemandFamilyV1 = Literal["outbound", "inbound", "indirect"]

# `family` is a property of a demand row alone and is NOT a function of
# `task_id` -- one task carries rows in several families (measured on
# `sample_tiny_input`: task 1E5596F1 has 197 inbound, 53 outbound, 6 indirect).
# `AssignmentV1` does not carry it and it cannot be derived, so any metric that
# reads assignments is per-task and family-agnostic.
FAMILY_AWARE_METRICS: frozenset[str] = frozenset(
    {"required_headcount_minutes", "required_demand_volume"}
)
GroundingFailureV1 = Literal[
    "missing_evidence",
    "unauthorized_evidence",
    "version_mismatch",
    "calculation_failed",
    "uncited_claim",
]
GroundingVerdictV1 = Literal["supported", "failed"]
# "units" is demand volume as the source states it (cartons, pieces, ...). It is
# deliberately NOT convertible to "minutes" here -- see MetricV1's note.
GroundingUnitV1 = Literal["minutes", "workers", "units"]


@dataclass(frozen=True)
class ClaimArgumentsV1:
    """Canonical metric arguments shared by a call and the claim citing it."""

    schema_version: str = SCHEMA_VERSION
    task_id: str | None = None
    family: DemandFamilyV1 | None = None
    start_minute: int | None = None
    end_minute: int | None = None


@dataclass(frozen=True)
class GroundedProseSegmentV1:
    """Non-numeric prose in its original answer position."""

    schema_version: str = SCHEMA_VERSION
    kind: Literal["prose"] = "prose"
    text: str = ""


@dataclass(frozen=True)
class ClaimProposalV1:
    """UNTRUSTED model output: a citation claim, never evidence or authority.

    ``result_id`` is model-supplied provenance only. The gate must match it to
    this turn's trusted results and verify these arguments before display.
    """

    schema_version: str = SCHEMA_VERSION
    kind: Literal["claim"] = "claim"
    metric: MetricV1 = "required_headcount_minutes"
    arguments: ClaimArgumentsV1 = ClaimArgumentsV1()
    result_id: str = ""


GroundedAnswerSegmentV1 = GroundedProseSegmentV1 | ClaimProposalV1


@dataclass(frozen=True)
class GroundedAnswerV1:
    """Strict ordered answer emitted by the model adapter."""

    schema_version: str = SCHEMA_VERSION
    segments: tuple[GroundedAnswerSegmentV1, ...] = ()


@dataclass(frozen=True)
class GroundedClaimV1:
    """A supported computed value or one inspectable per-claim failure."""

    schema_version: str = SCHEMA_VERSION
    kind: Literal["claim"] = "claim"
    metric: MetricV1 = "required_headcount_minutes"
    arguments: ClaimArgumentsV1 = ClaimArgumentsV1()
    result_id: str = ""
    value: int | float | None = None
    unit: GroundingUnitV1 | None = None
    evidence_refs: tuple[EvidenceRefV1, ...] = ()
    verdict: GroundingVerdictV1 = "failed"
    failure: GroundingFailureV1 | None = None


GroundedResponseSegmentV1 = GroundedProseSegmentV1 | GroundedClaimV1


@dataclass(frozen=True)
class GroundedResponseV1:
    """Persistable planner-visible response pinned to one immutable version."""

    schema_version: str = SCHEMA_VERSION
    scenario_version_id: UUID | None = None
    segments: tuple[GroundedResponseSegmentV1, ...] = ()

    @property
    def claims(self) -> tuple[GroundedClaimV1, ...]:
        return tuple(
            segment for segment in self.segments if isinstance(segment, GroundedClaimV1)
        )


__all__ = [
    "FAMILY_AWARE_METRICS",
    "SCHEMA_VERSION",
    "ClaimArgumentsV1",
    "ClaimProposalV1",
    "DemandFamilyV1",
    "GroundedAnswerSegmentV1",
    "GroundedAnswerV1",
    "GroundedClaimV1",
    "GroundedProseSegmentV1",
    "GroundedResponseSegmentV1",
    "GroundedResponseV1",
    "GroundingFailureV1",
    "GroundingUnitV1",
    "GroundingVerdictV1",
    "MetricV1",
]
