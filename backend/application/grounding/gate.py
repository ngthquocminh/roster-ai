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
    "attribution:trust_boundary": (
        "AUTHORITATIVE. missing_evidence, uncited_claim and argument mismatch judge the MODEL; "
        "calculation_failed judges the CALCULATOR, whose evidence_refs the model cannot "
        "influence. AC3 requires a failed claim to be inspectable, which one label spanning "
        "both sides would prevent. "
        "NOT COVERED: unauthorized_evidence and version_mismatch, which are two of AR11's three "
        "named EVIDENCE states and stay attributed to the evidence rather than to a party."
    ),
    "empty_set:proven_not_assumed": (
        "COVERS a zero value with no locator, supported only when the calculator reports "
        "consumed_row_count == 0 and len(evidence_refs) == consumed_row_count. "
        "NOT COVERED: an unexplained empty locator set, which fails as calculation_failed -- a "
        "truncating calculator must not be able to render as a supported zero."
    ),
    "locator:exact_resolution": (
        "COVERS exact record resolution without fallback or retargeting. "
        "NOT COVERED: durable EvidenceSnapshot and AuditEnvelope aggregates owned by Epic 4."
    ),
    "version:scenario_only": (
        "COVERS the immutable scenario version and available baseline schedule binding. "
        "NOT COVERED: producing run and schedule-version aggregates, which Epic 3 creates."
    ),
    "prose:no_numeric_characters": (
        "COVERS every Unicode character with a numeric value -- decimal digits plus "
        "superscripts, circled forms, Roman numerals and vulgar fractions -- so a quantity "
        "cannot bypass a claim node. "
        "NOT COVERED: spelled-out quantities; the strict model prompt must avoid them. This "
        "fires rarely by construction: no capability hands the model a quantity, so a numeral "
        "in prose is fabricated rather than echoed."
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
    consumed_row_count: int


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
        # The locator came from the CALCULATOR, not the model, so a target that
        # does not resolve is an application fault. Reporting it as
        # `missing_evidence` -- the state meaning "the model cited something
        # that does not exist" -- puts one label on both sides of the trust
        # boundary and makes the failure uninspectable, which AC3 forbids.
        return "calculation_failed"
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
    # Everything above this line judges the MODEL: it cited nothing, cited an
    # id no call produced, cited a real result against different arguments, or
    # cited across versions. Everything below judges the CALCULATOR, whose
    # output the model cannot influence -- so its faults are `calculation_failed`
    # and never `missing_evidence`.
    if len(result.evidence_refs) != result.consumed_row_count:
        return _failed(proposal, "calculation_failed")
    if not result.evidence_refs:
        # Zero is the one value whose evidence is not a set of records:
        # `EvidenceRefV1` addresses a `record_id`, and absence has none. A
        # proven-empty match set is therefore supported WITHOUT locators, while
        # a result that folded rows in and cited none has already failed above.
        if result.value:
            return _failed(proposal, "calculation_failed")
        return GroundedClaimV1(
            metric=proposal.metric,
            arguments=proposal.arguments,
            result_id=proposal.result_id,
            value=result.value,
            unit=result.unit,
            evidence_refs=(),
            verdict="supported",
            failure=None,
        )
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
        # `isnumeric()` rather than `isdecimal()`: the latter is False for
        # superscripts, circled digits, Roman numerals and vulgar fractions
        # ('2', '(5)', 'IV', '1/2' in their single-codepoint forms), so the
        # declared control below over-claimed its own coverage. isnumeric is a
        # strict superset of isdecimal and isdigit.
        if any(character.isnumeric() for character in segment.text):
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
