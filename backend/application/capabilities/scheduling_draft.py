"""Governed validation and resolution of reversible scheduling drafts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping
from uuid import UUID, uuid4

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    DraftConstraintV1,
    ProposalV1,
)
from application.contracts.scenario_projection import LockV1
from application.drafting.resolve import (
    HARD_MAX_HOURS_PER_WEEK,
    DraftConstraintError,
    DraftResolutionContextV1,
    consequence_summary,
    derive_draft_id,
    resolve_constraints,
    unique_entities,
)
from application.ports.scenario_projection import GroupQueryV1

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_draft"
SCHEDULING_DRAFT_POLICY = "scheduling_draft_enabled"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_draft/valid.json",
    "evals/golden/scheduling_draft/unresolvable-entity.json",
    "evals/golden/scheduling_draft/out-of-range-argument.json",
    "evals/golden/scheduling_draft/stale-version.json",
)
MAX_PRESERVED_LOCKS = 200

SCOPE_CONTROLS: Mapping[str, str] = {
    "site:trusted_dependencies": (
        "AUTHORITATIVE. Overview, resolutions, and locks must match the server-owned site pin. "
        "NOT COVERED: construction of the site-scoped database connection."
    ),
    "version:immutable_scenario_pin": (
        "AUTHORITATIVE. Every entity and lock is resolved against the selected immutable "
        "scenario version. NOT COVERED: a baseline schedule version; its projection value is "
        "truthfully None until a later Epic 3 story supplies that aggregate."
    ),
    "locks:real_projection_supply": (
        "COVERS preserving every lock returned by the projection under a bounded drain. "
        "NOT COVERED: the production reader currently supplies no locks; the mechanism is "
        "proved with a seeded reader carrying real lock records."
    ),
    "validation:before_solver": (
        "COVERS exact entity resolution, closed kinds, combinations, and numeric bounds at "
        "draft time, applied identically to model tool calls and to the HTTP revise command "
        "through application/drafting/resolve.py. NOT COVERED: execution ordering relative to "
        "a governed solver, which does not exist until Story 3.2 and inherits this refusal "
        "contract."
    ),
    "hours:flat_upper_bound": (
        "COVERS a flat upper sanity bound of 56 weekly hours on set_max_hours. NOT COVERED: "
        "per-employment-type caps. config/constants.py:DEFAULT_MAX_HOURS_PER_WEEK is a solver "
        "FALLBACK consulted only when a type has no configured cap, and no per-worker ceiling "
        "is reachable from the draft path — WorkerV1.contracted_hours is contractual, not a "
        "cap. Recorded at review 2026-08-18 per docs/DOMAIN-MODEL.md section 5 item 7; the "
        "real per-type cap arrives with the solver at Story 3.2."
    ),
    "identity:content_addressed_citation_only": (
        "AUTHORITATIVE. draft_id is content-addressed so a golden case can cite it, and two "
        "identical drafts legitimately share one. NOT COVERED: durable row identity — "
        "proposal_id and proposal_version_id are freshly minted per draft, because a "
        "content-addressed primary key turns a repeated request into a write conflict."
    ),
    "authz:site_scoped_shared_drafting": (
        "COVERS site scoping through RLS and the server-owned site pin. NOT COVERED: per-actor "
        "ownership of a proposal. Any planner in a site may revise or reject any draft in that "
        "site; created_by_actor_id is an audit trail, not an authorization check. Accepted as "
        "the MVP posture at review 2026-08-18."
    ),
    "metrics:none": (
        "AUTHORITATIVE. The capability composes descriptions and a consequence summary but "
        "computes no demand, staffing, or shortfall metric. NOT COVERED: solver outcomes."
    ),
}


class SchedulingDraftError(CapabilityError):
    code = "draft_failed"


class ScenarioNotFoundError(SchedulingDraftError):
    code = "scenario_not_found"


class VersionMismatchError(SchedulingDraftError):
    code = "version_mismatch"


class SiteMismatchError(SchedulingDraftError):
    code = "site_mismatch"


class InvalidQueryError(SchedulingDraftError):
    code = "invalid_query"


class DraftFailedError(SchedulingDraftError):
    code = "draft_failed"


class DraftTimeoutError(SchedulingDraftError):
    """Retryable: the budget was exceeded, not the request malformed."""

    code = "invalid_query"


class BudgetExhaustedError(SchedulingDraftError):
    code = "budget_exhausted"


ERROR_CODES = (
    "scenario_not_found",
    "version_mismatch",
    "site_mismatch",
    "invalid_query",
    "draft_failed",
    "budget_exhausted",
)


@dataclass(frozen=True)
class SchedulingDraftRequestV1:
    expected_scenario_version_id: UUID | None = None
    constraints: tuple[DraftConstraintProposalV1, ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingDraftResultV1:
    """TRUSTED result captured by the sink before model projection."""

    result_id: str
    proposal: ProposalV1
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingDraftModelViewV1:
    """The model receives only the content-addressed citation handle."""

    draft_id: str
    schema_version: str = SCHEMA_VERSION


def _model_view(result: SchedulingDraftResultV1) -> SchedulingDraftModelViewV1:
    return SchedulingDraftModelViewV1(draft_id=result.result_id)


def _context(deps: AgentDepsV1) -> DraftResolutionContextV1:
    return DraftResolutionContextV1(
        projection_reader=deps.projection_reader,
        connection=deps.connection,
        scenario_id=deps.scenario_id,
        scenario_version_id=deps.scenario_version_id,
    )


def _preserved_locks(deps: AgentDepsV1, deadline, on_timeout) -> tuple[LockV1, ...]:
    """Drain the lock supply under a bound, checking the deadline each page."""
    locks: list[LockV1] = []
    cursor = 0
    while True:
        if deps.clock() > deadline:
            on_timeout()
        remaining = MAX_PRESERVED_LOCKS - len(locks)
        if remaining <= 0:
            raise DraftFailedError(
                f"locks exceed the bounded preservation limit of {MAX_PRESERVED_LOCKS}"
            )
        limit = min(50, remaining)
        page = deps.projection_reader.get_locks(
            deps.connection,
            deps.scenario_id,
            GroupQueryV1(cursor=cursor, limit=limit),
        )
        if page is None:
            raise ScenarioNotFoundError("scenario is unavailable while reading locks")
        if page.site_id != deps.site_id:
            raise SiteMismatchError("lock page does not belong to the trusted site")
        if page.scenario_version_id != deps.scenario_version_id:
            raise VersionMismatchError("lock page does not match the selected scenario version")
        if len(page.items) > limit:
            # An over-long page would drive `remaining` negative on the next
            # iteration and land on the ceiling error for the wrong reason.
            raise DraftFailedError(
                f"lock page returned {len(page.items)} records for a limit of {limit}"
            )
        locks.extend(page.items)
        if page.next_cursor is None:
            return tuple(locks)
        if page.next_cursor <= cursor:
            raise DraftFailedError("lock paging cursor did not advance")
        cursor = page.next_cursor


def scheduling_draft_manifest() -> CapabilityManifestV1:
    from settings import default_settings

    settings = default_settings()
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref="application.capabilities.scheduling_draft.SchedulingDraftRequestV1",
        output_schema_ref="application.capabilities.scheduling_draft.SchedulingDraftResultV1",
        risk_class="draft",
        permission="scenario:draft",
        scope="current_site/current_scenario_version",
        version_semantics="resolved inputs are pinned to one immutable scenario version",
        idempotency_semantics="content-addressed by canonical constraints and preserved locks",
        budget_limit=settings.scheduling_draft_max_constraints,
        timeout_seconds=settings.scheduling_draft_timeout_seconds,
        approval_policy="none",
        audit_mapping="agent run + trusted draft result + immutable proposal version",
        evidence_mapping="resolved governed projection identities and preserved lock records",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def scheduling_draft(
    deps: AgentDepsV1,
    request: SchedulingDraftRequestV1,
    manifest: CapabilityManifestV1 | None = None,
) -> SchedulingDraftResultV1:
    resolved_manifest = manifest or scheduling_draft_manifest()
    if deps.remaining_budget.tool_calls_limit is not None and deps.remaining_budget.tool_calls_limit <= 0:
        raise BudgetExhaustedError("no tool-call budget remains for this run")
    if not request.constraints:
        raise InvalidQueryError("at least one draft constraint is required")
    if len(request.constraints) > resolved_manifest.budget_limit:
        raise InvalidQueryError(
            f"at most {resolved_manifest.budget_limit} draft constraints are allowed"
        )
    if request.expected_scenario_version_id != deps.scenario_version_id:
        raise InvalidQueryError(
            "expected scenario version is stale; refresh before creating a draft"
        )

    started_at = deps.clock()
    deadline = started_at + timedelta(seconds=resolved_manifest.timeout_seconds)

    def _timed_out() -> None:
        raise DraftTimeoutError(
            f"draft validation exceeded the {resolved_manifest.timeout_seconds}s budget"
        )

    overview = deps.projection_reader.get_overview(deps.connection, deps.scenario_id)
    if overview is None:
        raise ScenarioNotFoundError("scenario is unavailable")
    if overview.site_id != deps.site_id:
        raise SiteMismatchError("scenario does not belong to the trusted site")
    if overview.scenario_version_id != deps.scenario_version_id:
        raise VersionMismatchError("scenario version changed before draft validation")

    try:
        constraints = resolve_constraints(
            _context(deps),
            request.constraints,
            overview.horizon_minutes,
            deadline=deadline,
            clock=deps.clock,
            on_timeout=_timed_out,
        )
    except DraftConstraintError as exc:
        # Retryable by design: the model can correct itself inside the run.
        raise InvalidQueryError(str(exc)) from exc
    locks = _preserved_locks(deps, deadline, _timed_out)
    if deps.clock() > deadline:
        _timed_out()

    result_id = derive_draft_id(deps.scenario_version_id, constraints, locks)
    # Durable identity is NOT the citation. A content-addressed primary key
    # makes a legitimately repeated draft a write conflict that aborts the
    # finalisation transaction and strands the agent run.
    proposal = ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=deps.scenario_id,
        scenario_version_id=deps.scenario_version_id,
        expected_baseline_schedule_version=overview.baseline_schedule_version,
        resolved_entities=unique_entities(constraints),
        constraints=constraints,
        preserved_locks=locks,
        consequence_summary=consequence_summary(constraints, locks),
        canonical_hash=result_id,
    )
    return SchedulingDraftResultV1(result_id=result_id, proposal=proposal)


def scheduling_draft_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_draft_manifest(),
        handler=scheduling_draft,
        request_type=SchedulingDraftRequestV1,
        error_type=SchedulingDraftError,
        retryable_error_codes=frozenset({"invalid_query"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_DRAFT_POLICY,
        model_facing_view=_model_view,
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "EVALUATION_FIXTURES", "HARD_MAX_HOURS_PER_WEEK",
    "MAX_PRESERVED_LOCKS", "SCHEDULING_DRAFT_POLICY", "SCOPE_CONTROLS",
    "BudgetExhaustedError", "DraftFailedError", "DraftTimeoutError", "InvalidQueryError",
    "ScenarioNotFoundError", "SchedulingDraftError", "SchedulingDraftModelViewV1",
    "SchedulingDraftRequestV1", "SchedulingDraftResultV1", "SiteMismatchError",
    "VersionMismatchError", "derive_draft_id", "scheduling_draft",
    "scheduling_draft_manifest", "scheduling_draft_module",
]
