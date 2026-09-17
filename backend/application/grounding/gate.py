"""Fail-closed citation verification for planner-visible grounded answers."""
from __future__ import annotations

import re
from typing import Iterable, Mapping, Protocol
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
from application.grounding.resolvers import resolver_name_for_evidence_group


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
    "prose:no_untraceable_numerals": (
        "COVERS every Unicode character with a numeric value -- decimal digits plus "
        "superscripts, circled forms, Roman numerals and vulgar fractions. A prose word "
        "carrying one is allowed ONLY when that exact word appears in trusted text for "
        "the turn: the planner's own messages, persisted gate-passed conversation text, "
        "the application workflow snapshot, and this turn's tool results. So an entity "
        "name such as 'Grid P 8GR' or a planner-given '40' hours can be copied, while a "
        "quantity the model counted or summed cannot -- that still needs a cited claim. "
        "UUIDs and long hex strings are removed from trusted text first, because their "
        "digit runs would otherwise vouch for almost any short number. Enforced TWICE: as "
        "an in-loop output validator giving the model a corrective retry, and here as the "
        "fail-closed backstop over a superset of that trusted text. "
        "Narrowed 2026-09-17 from 'no numeric characters at all' (Story 5.7), which made "
        "real task names with digits and planner-given values impossible to state. "
        "NOT COVERED: a wrong number that coincidentally matches a word in trusted text "
        "(the per-turn fact checks, not this rule, catch that); spelled-out quantities."
    ),
}


class UncitedNumericProseError(ValueError):
    failure: GroundingFailureV1 = "uncited_claim"


_IDENTIFIER_NOISE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\b[0-9a-fA-F]{16,}\b"
)
_WORD = re.compile(r"[^\W_]+(?:[.,:][^\W_]+)*")


def _numeric_words(text: str) -> list[str]:
    return [word for word in _WORD.findall(text) if any(c.isnumeric() for c in word)]


def trusted_numeric_words(trusted_texts: Iterable[str]) -> frozenset[str]:
    """Every numeral-bearing word a reply may copy from trusted text."""
    words: set[str] = set()
    for text in trusted_texts:
        for word in _numeric_words(_IDENTIFIER_NOISE.sub(" ", text)):
            words.add(word)
            # A trusted `40.0` (e.g. JSON-serialized max_hours) vouches for `40`.
            if re.fullmatch(r"\d+\.0+", word):
                words.add(word.split(".")[0])
    return frozenset(words)


def numeric_prose_violation(
    text: str, trusted_words: frozenset[str] = frozenset()
) -> str | None:
    """The prose rule, as a pure predicate. Returns the offending words or None.

    Single-sourced deliberately. `backend/agent/` registers this as a pydantic-ai
    output validator so a violation becomes a `ModelRetry` the model can act on,
    while `ground_answer` below keeps it as the fail-closed backstop. Two call
    sites, one rule -- a second implementation in the adapter is exactly the
    drift this function exists to prevent, and `application/**` must stay free of
    framework imports (AD-19), so the predicate lives here and the framework
    wiring lives there.

    `isnumeric()` rather than `isdecimal()`: the latter is False for
    superscripts, circled digits, Roman numerals and vulgar fractions.
    With no `trusted_words` every numeral is offending (the original rule).
    """
    offending = [word for word in _numeric_words(text) if word not in trusted_words]
    return ", ".join(offending) or None


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
    trusted_words: frozenset[str] = frozenset(),
) -> GroundedResponseV1:
    """Verify citations and exact targets; perform no metric computation."""
    grounded: list[GroundedResponseSegmentV1] = []
    for segment in answer.segments:
        if isinstance(segment, ClaimProposalV1):
            grounded.append(_ground_claim(segment, deps, results))
            continue
        # Backstop. The output validator in `backend/agent/runtime.py` has
        # already given the model one chance to correct this, so reaching here
        # means it did not -- which is the rare, meaningful signal the design
        # wants, rather than the routine event it used to be.
        if numeric_prose_violation(segment.text, trusted_words) is not None:
            raise UncitedNumericProseError(
                "numerals in prose must be represented by a cited claim"
            )
        grounded.append(segment)
    return GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=tuple(grounded),
    )


__all__ = [
    "SCOPE_CONTROLS", "TrustedCalculationResultV1",
    "UncitedNumericProseError", "ground_answer", "numeric_prose_violation",
    "trusted_numeric_words",
]
