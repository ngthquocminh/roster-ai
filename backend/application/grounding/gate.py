"""Fail-closed citation verification for planner-visible grounded answers."""
from __future__ import annotations

from typing import Mapping, Protocol
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import (
    ClaimArgumentsV1,
    ClaimProposalV1,
    GroundedAnswerV1,
    GroundedClaimV1,
    GroundedResponseSegmentV1,
    GroundedResponseV1,
    GroundingFailureV1,
    GroundingUnitV1,
    MetricV1,
)
from application.grounding.evidence_groups import scenario_fact_group_for_evidence_group


SCOPE_CONTROLS: Mapping[str, str] = {
    "citation:turn_results": (
        "COVERS result identity, metric arguments, and immutable scenario-version pinning. "
        "NOT COVERED: model arithmetic, because proposals deliberately carry no value."
    ),
    "locator:exact_resolution": (
        "COVERS exact record resolution without fallback or retargeting. "
        "NOT COVERED: durable EvidenceSnapshot and AuditEnvelope aggregates owned by Epic 4."
    ),
    "version:scenario_only": (
        "COVERS the immutable scenario version and available baseline schedule binding. "
        "NOT COVERED: producing run and schedule-version aggregates, which Epic 3 creates."
    ),
    "prose:no_decimal_digits": (
        "COVERS every Unicode decimal digit so numeric claims cannot bypass claim nodes. "
        "NOT COVERED: spelled-out quantities; the strict model prompt must avoid them."
    ),
}


class UncitedNumericProseError(ValueError):
    failure: GroundingFailureV1 = "uncited_claim"


class TrustedCalculationResultV1(Protocol):
    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID
    result_id: str


_RESOLVER_BY_GROUP = {
    "tasks": "resolve_task",
    "workers": "resolve_worker",
    "demand": "resolve_demand_interval",
    "assignments": "resolve_assignment",
    "locks": "resolve_lock",
    "constraints": "resolve_constraint",
}


def _failed(
    proposal: ClaimProposalV1, failure: GroundingFailureV1
) -> GroundedClaimV1:
    return GroundedClaimV1(
        metric=proposal.metric,
        arguments=proposal.arguments,
        result_id=proposal.result_id,
        verdict="failed",
        failure=failure,
    )


def _locator_failure(
    deps: AgentDepsV1, reference: EvidenceRefV1
) -> GroundingFailureV1 | None:
    if reference.scenario_version_id != deps.scenario_version_id:
        return "version_mismatch"
    group = scenario_fact_group_for_evidence_group(reference.group)
    resolver_name = _RESOLVER_BY_GROUP[group]
    resolution = getattr(deps.projection_reader, resolver_name)(
        deps.connection,
        deps.scenario_id,
        reference.scenario_version_id,
        reference.record_id,
    )
    if resolution is None:
        return "unauthorized_evidence"
    if resolution.outcome == "version_mismatch":
        return "version_mismatch"
    if resolution.outcome != "resolved" or resolution.item is None:
        return "missing_evidence"
    if (
        resolution.current_scenario_version_id != reference.scenario_version_id
        or resolution.item.record_id != reference.record_id
    ):
        return "version_mismatch"
    return None


def _ground_claim(
    proposal: ClaimProposalV1,
    deps: AgentDepsV1,
    results: Mapping[str, TrustedCalculationResultV1],
) -> GroundedClaimV1:
    if not proposal.result_id:
        return _failed(proposal, "uncited_claim")
    result = results.get(proposal.result_id)
    if result is None or result.result_id != proposal.result_id:
        return _failed(proposal, "missing_evidence")
    if result.metric != proposal.metric or result.arguments != proposal.arguments:
        return _failed(proposal, "missing_evidence")
    if result.scenario_version_id != deps.scenario_version_id:
        return _failed(proposal, "version_mismatch")
    if not result.evidence_refs:
        return _failed(proposal, "missing_evidence")
    for reference in result.evidence_refs:
        failure = _locator_failure(deps, reference)
        if failure is not None:
            return _failed(proposal, failure)
    return GroundedClaimV1(
        metric=proposal.metric,
        arguments=proposal.arguments,
        result_id=proposal.result_id,
        value=result.value,
        unit=result.unit,
        evidence_refs=result.evidence_refs,
        verdict="supported",
        failure=None,
    )


def ground_answer(
    answer: GroundedAnswerV1,
    deps: AgentDepsV1,
    results: Mapping[str, TrustedCalculationResultV1],
) -> GroundedResponseV1:
    """Verify citations and exact targets; perform no metric computation."""
    grounded: list[GroundedResponseSegmentV1] = []
    for segment in answer.segments:
        if isinstance(segment, ClaimProposalV1):
            grounded.append(_ground_claim(segment, deps, results))
            continue
        if any(character.isdecimal() for character in segment.text):
            raise UncitedNumericProseError(
                "decimal digits in prose must be represented by a cited claim"
            )
        grounded.append(segment)
    return GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=tuple(grounded),
    )


__all__ = [
    "SCOPE_CONTROLS", "TrustedCalculationResultV1",
    "UncitedNumericProseError", "ground_answer",
]
