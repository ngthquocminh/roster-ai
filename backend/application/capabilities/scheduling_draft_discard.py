"""Explicit discard of the conversation's working draft (Story 5.11, spec 2.3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_draft_discard"
SCHEDULING_DRAFT_DISCARD_POLICY = "scheduling_draft_discard_enabled"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_draft_discard/valid.json",
    "evals/golden/scheduling_draft_discard/no-working-draft.json",
    "evals/golden/scheduling_draft_discard/after-draft-same-turn.json",
    "evals/golden/scheduling_draft_discard/start-over-is-not-discard.json",
)

SCOPE_CONTROLS: Mapping[str, str] = {
    "site:trusted_dependencies": (
        "AUTHORITATIVE. The conversation and site come from the server-owned deps. "
        "NOT COVERED: construction of the site-scoped database connection."
    ),
    "lifecycle:explicit_request_only": (
        "COVERS ending the working draft as `rejected` with ended_by='assistant', and only "
        "when the planner explicitly asks to discard, delete or throw the draft away. NOT "
        "COVERED: whether a real model routes 'start over with just X' to scheduling_draft "
        "instead — that is instruction and routing quality, measured live (Story 5.12), not "
        "enforced here."
    ),
    "lifecycle:observed_state_only": (
        "COVERS discarding exactly the draft this turn observed, at the resource version it "
        "observed; the finalize guard applies the discard only if the conversation still "
        "matches. NOT COVERED: a change after observation — the guard ends the turn with a "
        "capability_error and writes nothing."
    ),
    "lifecycle:tool_ordering": (
        "COVERS discard-then-draft in one turn (the draft becomes a fresh v1) and refuses "
        "draft-then-discard (`draft_changed_this_turn`). NOT COVERED: any other ordering "
        "between the two tools; the finalize table is the authority."
    ),
    "authz:site_scoped_shared_drafting": (
        "COVERS site scoping through RLS. NOT COVERED: per-actor ownership of a draft; "
        "any planner in a site may discard any draft in that site (Story 3.1)."
    ),
    "metrics:none": (
        "AUTHORITATIVE. The capability computes no demand, staffing or shortfall metric."
    ),
}


class SchedulingDraftDiscardError(CapabilityError):
    code = "draft_discard_failed"


class NoWorkingDraftError(SchedulingDraftDiscardError):
    code = "no_working_draft"


class DraftChangedThisTurnError(SchedulingDraftDiscardError):
    code = "draft_changed_this_turn"


class BudgetExhaustedError(SchedulingDraftDiscardError):
    code = "budget_exhausted"


# `draft_discard_failed` is the base class code; the conformance suite requires the
# declared vocabulary to equal every code the module can raise.
ERROR_CODES = (
    "no_working_draft", "draft_changed_this_turn", "budget_exhausted", "draft_discard_failed",
)


@dataclass(frozen=True)
class SchedulingDraftDiscardRequestV1:
    """No arguments: the working draft is resolved server-side (spec 2.3)."""

    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingDraftDiscardResultV1:
    """TRUSTED result captured by the sink before model projection."""

    result_id: str
    proposal_id: UUID
    observed_resource_version: int
    version_ordinal: int
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingDraftDiscardModelViewV1:
    """The model never sees the proposal id."""

    outcome: str
    version_ordinal: int
    schema_version: str = SCHEMA_VERSION


def _model_view(result: SchedulingDraftDiscardResultV1) -> SchedulingDraftDiscardModelViewV1:
    return SchedulingDraftDiscardModelViewV1(
        outcome="discarded", version_ordinal=result.version_ordinal
    )


def scheduling_draft_discard_manifest() -> CapabilityManifestV1:
    from settings import default_settings

    settings = default_settings()
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref=(
            "application.capabilities.scheduling_draft_discard.SchedulingDraftDiscardRequestV1"
        ),
        output_schema_ref=(
            "application.capabilities.scheduling_draft_discard.SchedulingDraftDiscardResultV1"
        ),
        risk_class="draft",
        permission="scenario:draft",
        scope="current_site/current_conversation",
        version_semantics="discards the working draft as observed at the start of the turn",
        idempotency_semantics="at most one discard per turn; applied once at finalize",
        budget_limit=1,
        timeout_seconds=settings.scheduling_draft_timeout_seconds,
        approval_policy="none",
        audit_mapping="agent run + trusted discard result + proposal ended_by assistant",
        evidence_mapping="the observed working draft's proposal id and resource version",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
        citable_result_id=False,
    )


def scheduling_draft_discard(
    deps: AgentDepsV1,
    request: SchedulingDraftDiscardRequestV1,
    manifest: CapabilityManifestV1 | None = None,
) -> SchedulingDraftDiscardResultV1:
    del request, manifest
    if deps.remaining_budget.tool_calls_limit is not None and deps.remaining_budget.tool_calls_limit <= 0:
        raise BudgetExhaustedError("no tool-call budget remains for this run")
    if deps.draft_turn.drafted:
        raise DraftChangedThisTurnError("this turn already changed the draft")
    if deps.draft_turn.discarded is not None:
        raise NoWorkingDraftError("this turn already discarded the draft")
    observed = deps.draft_turn.observe()
    if observed is None:
        raise NoWorkingDraftError("this conversation has no working draft to discard")
    deps.draft_turn.record_discard(observed)
    return SchedulingDraftDiscardResultV1(
        result_id=f"discard-{observed.proposal_id}-{observed.resource_version}",
        proposal_id=observed.proposal_id,
        observed_resource_version=observed.resource_version,
        version_ordinal=observed.version_ordinal,
    )


def scheduling_draft_discard_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_draft_discard_manifest(),
        handler=scheduling_draft_discard,
        request_type=SchedulingDraftDiscardRequestV1,
        error_type=SchedulingDraftDiscardError,
        retryable_error_codes=frozenset({"no_working_draft", "draft_changed_this_turn"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_DRAFT_DISCARD_POLICY,
        model_facing_view=_model_view,
        model_description=(
            "scheduling_draft_discard discards the conversation's working draft. Call it only "
            "when the planner explicitly asks to discard, delete, or throw away the draft. "
            "'Start over with just X' or any other request to change what the draft contains is "
            "scheduling_draft with only X, never discard. It takes no arguments and never "
            "touches a run or the baseline. If it reports no_working_draft there is nothing to "
            "discard; say so plainly."
        ),
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "EVALUATION_FIXTURES",
    "SCHEDULING_DRAFT_DISCARD_POLICY", "SCOPE_CONTROLS", "BudgetExhaustedError",
    "DraftChangedThisTurnError", "NoWorkingDraftError", "SchedulingDraftDiscardError",
    "SchedulingDraftDiscardModelViewV1", "SchedulingDraftDiscardRequestV1",
    "SchedulingDraftDiscardResultV1", "scheduling_draft_discard",
    "scheduling_draft_discard_manifest", "scheduling_draft_discard_module",
]
