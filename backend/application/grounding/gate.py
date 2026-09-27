"""Fail-closed citation verification for planner-visible grounded answers."""
from __future__ import annotations

from typing import Mapping, Protocol
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import (
    ClaimArgumentsV1,
    GroundedAnswerV2,
    GroundedClaimV1,
    GroundedProseSegmentV1,
    GroundedResponseSegmentV1,
    GroundedResponseV1,
    GroundingFailureV1,
    GroundingUnitV1,
    MetricV1,
)
from application.grounding.placeholders import PlaceholderPart, parse_answer_text
from application.grounding.resolvers import resolver_name_for_evidence_group


SCOPE_CONTROLS: Mapping[str, str] = {
    "citation:turn_results": (
        "COVERS result identity and immutable scenario-version pinning. "
        "NOT COVERED: model arithmetic, because answers deliberately carry no value, and "
        "whether the prose around a placeholder describes the result it names."
    ),
    "attribution:trust_boundary": (
        "AUTHORITATIVE. missing_evidence judges the MODEL; "
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
    "placeholder:value_from_trusted_result": (
        "AUTHORITATIVE. A number is rendered only where the answer text carries a "
        "{{handle}} placeholder resolved through this turn's evidence registry; its value, "
        "unit, metric and arguments are the trusted result's, never the model's. An "
        "unresolved placeholder renders as a failed missing_evidence claim and the answer is "
        "still delivered. "
        "NOT COVERED: text outside placeholders, which is plain unverified prose (D2) -- a "
        "numeral typed there is not checked (the lexical numeral rule was removed)."
    ),
}


class TrustedCalculationResultV1(Protocol):
    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID
    result_id: str
    consumed_row_count: int


def _failed(
    handle: str,
    failure: GroundingFailureV1,
    result: TrustedCalculationResultV1 | None = None,
) -> GroundedClaimV1:
    """A failed claim. With no resolved result the claim's metric/arguments are
    the contract defaults: the model named only a handle, and nothing trusted
    says what it meant."""
    if result is None:
        return GroundedClaimV1(result_id=handle, verdict="failed", failure=failure)
    return GroundedClaimV1(
        metric=result.metric,
        arguments=result.arguments,
        result_id=result.result_id,
        verdict="failed",
        failure=failure,
    )


def _locator_failure(
    deps: AgentDepsV1, reference: EvidenceRefV1
) -> GroundingFailureV1 | None:
    if reference.scenario_version_id != deps.scenario_version_id:
        return "version_mismatch"
    resolver_name = resolver_name_for_evidence_group(reference.group)
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
    handle: str,
    deps: AgentDepsV1,
    results: Mapping[str, TrustedCalculationResultV1],
) -> GroundedClaimV1:
    # Keyed by canonical id and by this turn's short handle (see
    # `evidence_registry.trusted_results_by_citation`).
    result = results.get(handle)
    if result is None:
        return _failed(handle, "missing_evidence")
    if result.scenario_version_id != deps.scenario_version_id:
        return _failed(handle, "version_mismatch", result)
    # Everything above this line judges the MODEL: it cited an id no call
    # produced, or cited across versions. Everything below judges the CALCULATOR, whose
    # output the model cannot influence -- so its faults are `calculation_failed`
    # and never `missing_evidence`.
    if len(result.evidence_refs) != result.consumed_row_count:
        return _failed(handle, "calculation_failed", result)
    if not result.evidence_refs:
        # Zero is the one value whose evidence is not a set of records:
        # `EvidenceRefV1` addresses a `record_id`, and absence has none. A
        # proven-empty match set is therefore supported WITHOUT locators, while
        # a result that folded rows in and cited none has already failed above.
        if result.value:
            return _failed(handle, "calculation_failed", result)
        return GroundedClaimV1(
            metric=result.metric,
            arguments=result.arguments,
            result_id=result.result_id,
            value=result.value,
            unit=result.unit,
            evidence_refs=(),
            verdict="supported",
            failure=None,
        )
    for reference in result.evidence_refs:
        failure = _locator_failure(deps, reference)
        if failure is not None:
            return _failed(handle, failure, result)
    return GroundedClaimV1(
        metric=result.metric,
        arguments=result.arguments,
        result_id=result.result_id,
        value=result.value,
        unit=result.unit,
        evidence_refs=result.evidence_refs,
        verdict="supported",
        failure=None,
    )


def ground_answer(
    answer: GroundedAnswerV2,
    deps: AgentDepsV1,
    results: Mapping[str, TrustedCalculationResultV1],
) -> GroundedResponseV1:
    """Replace each `{{handle}}` with a claim built from its trusted result.

    Performs no metric computation and never fails the turn: a placeholder that
    cannot be grounded becomes an inspectable failed claim, and every other part
    of the text is kept as prose.
    """
    grounded: list[GroundedResponseSegmentV1] = []
    for part in parse_answer_text(answer.text):
        if isinstance(part, PlaceholderPart):
            grounded.append(_ground_claim(part.handle, deps, results))
        else:
            grounded.append(GroundedProseSegmentV1(text=part.text))
    return GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=tuple(grounded),
    )


__all__ = ["SCOPE_CONTROLS", "TrustedCalculationResultV1", "ground_answer"]
