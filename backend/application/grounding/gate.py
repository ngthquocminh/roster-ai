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
    GroundedFactV1,
    FactFailureV1,
    GroundedProseSegmentV1,
    GroundedResponseSegmentV1,
    GroundedResponseV1,
    GroundingFailureV1,
    GroundingUnitV1,
    MetricV1,
)
from application.grounding.claim_tags import FactTagPart, parse_claim_tags
from application.grounding.evidence_groups import evidence_group_for_scenario_fact_group
from application.grounding.evidence_registry import TrustedRecordV1
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
    "fact:record_content_tier0": (
        "AUTHORITATIVE. A <claim ev field value> fact is verified only when ev is a record "
        "handle issued by a scheduling_inspect call in this turn, field is a field of that "
        "trusted row, and value equals the row's field content (numbers by numeric "
        "equality; lists and nested objects by any element's scalar). The row checked is the "
        "handler's trusted return, never model-visible text, and its locator is resolved "
        "like a calculation's. A failed or malformed fact is shown unverified, never "
        "stripped or blocking. "
        "NOT COVERED: the tag's wording -- the model may name what the record calls by ID -- "
        "which is why the verified marker displays the checked field and value (tier 1, "
        "phase 3, checks wording)."
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


def _matches(recorded: object, claimed: str) -> bool:
    """Tier-0 value equality: text exactly (IDs are case-sensitive), numbers by
    numeric equality, a list or nested object by any element's scalar."""
    if recorded is None:
        return claimed.strip().casefold() in {"", "none", "null"}
    if isinstance(recorded, bool):
        return claimed.strip().casefold() == str(recorded).casefold()
    if isinstance(recorded, (int, float)):
        try:
            return float(claimed) == float(recorded)
        except ValueError:
            return False
    if isinstance(recorded, str):
        return recorded.strip() == claimed.strip()
    if isinstance(recorded, Mapping):
        return any(_matches(item, claimed) for item in recorded.values())
    if isinstance(recorded, (list, tuple)):
        return any(_matches(item, claimed) for item in recorded)
    return False


def _fact(
    tag: FactTagPart, failure: FactFailureV1 | None,
    evidence_refs: tuple[EvidenceRefV1, ...] = (),
) -> GroundedFactV1:
    return GroundedFactV1(
        text=tag.text, field=tag.field, value=tag.value, evidence_refs=evidence_refs,
        verdict="supported" if failure is None else "failed", failure=failure,
    )


def _ground_fact(
    tag: FactTagPart, deps: AgentDepsV1, records: Mapping[str, TrustedRecordV1]
) -> GroundedFactV1:
    trusted = records.get(tag.ev)
    if trusted is None:
        return _fact(tag, "missing_evidence")
    if trusted.scenario_version_id != str(deps.scenario_version_id):
        return _fact(tag, "version_mismatch")
    if tag.field == "ev" or tag.field not in trusted.record:
        return _fact(tag, "unknown_field")
    if not _matches(trusted.record[tag.field], tag.value):
        return _fact(tag, "value_mismatch")
    evidence_group = evidence_group_for_scenario_fact_group(trusted.scenario_group)  # type: ignore[arg-type]
    overview = deps.projection_reader.get_overview(deps.connection, deps.scenario_id)
    record_id = trusted.record.get("record_id")
    if evidence_group is None or overview is None or not isinstance(record_id, str):
        return _fact(tag, "missing_evidence")
    reference = EvidenceRefV1(
        scenario_version_id=overview.scenario_version_id,
        checksum_algorithm=overview.checksum_algorithm,
        checksum_schema_version=overview.checksum_schema_version,
        checksum_digest=overview.checksum_digest,
        producing_run_version=None,
        baseline_schedule_version=overview.baseline_schedule_version,
        group=evidence_group,
        record_id=record_id,
        field=tag.field,
    )
    failure = _locator_failure(deps, reference)
    if failure is not None:
        # The record came from this turn's trusted read, so a locator that no
        # longer resolves means the evidence is gone, not that the model erred.
        return _fact(tag, failure if failure in ("version_mismatch", "unauthorized_evidence")
                     else "missing_evidence")
    return _fact(tag, None, (reference,))


def ground_answer(
    answer: GroundedAnswerV2,
    deps: AgentDepsV1,
    results: Mapping[str, TrustedCalculationResultV1],
    records: Mapping[str, TrustedRecordV1] | None = None,
) -> GroundedResponseV1:
    """Replace each `{{handle}}` with a claim built from its trusted result, and
    check each `<claim>` fact tag against its trusted record.

    Performs no metric computation and never fails the turn: a placeholder that
    cannot be grounded becomes an inspectable failed claim, and every other part
    of the text is kept as prose.
    """
    grounded: list[GroundedResponseSegmentV1] = []
    for tagged in parse_claim_tags(answer.text):
        if isinstance(tagged, FactTagPart):
            grounded.append(_ground_fact(tagged, deps, records or {}))
            continue
        for part in parse_answer_text(tagged.text):
            if isinstance(part, PlaceholderPart):
                grounded.append(_ground_claim(part.handle, deps, results))
            else:
                grounded.append(GroundedProseSegmentV1(text=part.text))
    return GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=tuple(grounded),
    )


__all__ = ["SCOPE_CONTROLS", "TrustedCalculationResultV1", "ground_answer"]
