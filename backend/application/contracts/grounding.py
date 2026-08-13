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
    "required_demand_minutes",
    "staffed_minutes",
    "shortfall_minutes",
    "qualified_worker_count",
]
DemandFamilyV1 = Literal["outbound", "inbound", "indirect"]
GroundingFailureV1 = Literal[
    "missing_evidence",
    "unauthorized_evidence",
    "version_mismatch",
    "calculation_failed",
    "uncited_claim",
]
GroundingVerdictV1 = Literal["supported", "failed"]
GroundingUnitV1 = Literal["minutes", "workers"]


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
    metric: MetricV1 = "required_demand_minutes"
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
    metric: MetricV1 = "required_demand_minutes"
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
