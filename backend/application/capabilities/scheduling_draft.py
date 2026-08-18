"""Governed validation and resolution of reversible scheduling drafts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.clarification.resolve import planner_label
from application.contracts.canonical import contract_digest
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1
from application.contracts.evidence_ref import EvidenceGroupV1
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    DraftConstraintV1,
    ProposalV1,
    ResolvedEntityV1,
)
from application.contracts.scenario_projection import LockV1, WorkerV1
from application.grounding.resolvers import resolver_name_for_evidence_group
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
HARD_MAX_HOURS_PER_WEEK = 56.0

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
        "draft time. NOT COVERED: execution ordering relative to a governed solver, which does "
        "not exist until Story 3.2 and inherits this refusal contract."
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


def _primitive_constraint(value: DraftConstraintV1) -> dict[str, object]:
    payload = asdict(value)
    for entity in payload["resolved_entities"]:
        entity["scenario_version_id"] = str(entity["scenario_version_id"])
    payload["resolved_entities"] = list(payload["resolved_entities"])
    return payload


def _primitive_lock(value: LockV1) -> dict[str, object]:
    return asdict(value)


def derive_draft_id(
    scenario_version_id: UUID,
    constraints: tuple[DraftConstraintV1, ...],
    preserved_locks: tuple[LockV1, ...],
) -> str:
    """Return a stable citation over the immutable version and trusted inputs."""
    return contract_digest(
        {
            "scenario_version_id": str(scenario_version_id),
            "constraints": [_primitive_constraint(value) for value in constraints],
            "preserved_locks": [_primitive_lock(value) for value in preserved_locks],
        }
    )[2]


def _resolve_entity(
    deps: AgentDepsV1,
    group: EvidenceGroupV1,
    record_id: str,
) -> tuple[ResolvedEntityV1, object]:
    resolver_name = resolver_name_for_evidence_group(group)
    resolution = getattr(deps.projection_reader, resolver_name)(
        deps.connection,
        deps.scenario_id,
        deps.scenario_version_id,
        record_id,
    )
    if (
        resolution is None
        or resolution.outcome != "resolved"
        or resolution.item is None
        or resolution.current_scenario_version_id != deps.scenario_version_id
        or resolution.item.record_id != record_id
    ):
        raise InvalidQueryError(f"{group} entity {record_id!r} is missing or not resolvable")
    return (
        ResolvedEntityV1(
            group=group,
            record_id=record_id,
            label=planner_label(resolution.item),
            scenario_version_id=deps.scenario_version_id,
        ),
        resolution.item,
    )


def _require_primary(
    deps: AgentDepsV1,
    proposal: DraftConstraintProposalV1,
    expected_group: EvidenceGroupV1,
) -> tuple[ResolvedEntityV1, object]:
    if proposal.group != expected_group:
        raise InvalidQueryError(
            f"{proposal.kind} requires group {expected_group!r}, got {proposal.group!r}"
        )
    return _resolve_entity(deps, proposal.group, proposal.record_id)


def _resolve_constraint(
    deps: AgentDepsV1,
    proposal: DraftConstraintProposalV1,
    horizon_minutes: int,
) -> DraftConstraintV1:
    numeric = {
        "n": proposal.n,
        "factor": proposal.factor,
        "max_hours": proposal.max_hours,
        "start_minute": proposal.start_minute,
        "end_minute": proposal.end_minute,
    }

    def require_only(*allowed: str) -> None:
        unexpected = sorted(
            name for name, value in numeric.items()
            if value is not None and name not in allowed
        )
        if unexpected:
            raise InvalidQueryError(
                f"{proposal.kind} does not accept arguments {unexpected}"
            )

    if proposal.kind == "set_min_workers_per_task":
        require_only("n")
        task, _ = _require_primary(deps, proposal, "work-areas-and-tasks")
        if proposal.n is None or proposal.n <= 0:
            raise InvalidQueryError("n must be greater than 0")
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(task,),
            n=proposal.n,
            description=f"Keep at least {proposal.n} workers on {task.label}.",
        )
    if proposal.kind == "scale_demand":
        require_only("factor")
        task, _ = _require_primary(deps, proposal, "work-areas-and-tasks")
        if proposal.factor is None or proposal.factor <= 0:
            raise InvalidQueryError("factor must be greater than 0")
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(task,),
            factor=proposal.factor,
            description=f"Scale demand for {task.label} by {proposal.factor}.",
        )
    if proposal.kind == "lock_worker_shift":
        require_only("start_minute", "end_minute")
        worker, _ = _require_primary(deps, proposal, "workers")
        if (
            proposal.start_minute is None
            or proposal.end_minute is None
            or proposal.start_minute < 0
            or proposal.end_minute <= proposal.start_minute
            or proposal.end_minute > horizon_minutes
        ):
            raise InvalidQueryError(
                "start_minute must be non-negative and end_minute must be greater than start_minute"
                f" and no greater than the horizon bound {horizon_minutes}"
            )
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(worker,),
            start_minute=proposal.start_minute,
            end_minute=proposal.end_minute,
            description=(
                f"Keep {worker.label} on the half-open window "
                f"[{proposal.start_minute}, {proposal.end_minute})."
            ),
        )
    if proposal.kind == "exclude_worker_from_task":
        require_only()
        worker, _ = _require_primary(deps, proposal, "workers")
        if (
            proposal.related_group != "work-areas-and-tasks"
            or not proposal.related_record_id
        ):
            raise InvalidQueryError(
                "exclude_worker_from_task requires a related work-areas-and-tasks record"
            )
        task, _ = _resolve_entity(
            deps, proposal.related_group, proposal.related_record_id
        )
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(worker, task),
            description=f"Keep {worker.label} off {task.label}.",
        )
    if proposal.kind == "set_max_hours":
        require_only("max_hours")
        worker, raw_worker = _require_primary(deps, proposal, "workers")
        if proposal.max_hours is None or proposal.max_hours <= 0:
            raise InvalidQueryError("max_hours must be greater than 0")
        if proposal.max_hours > HARD_MAX_HOURS_PER_WEEK:
            employment_type = (
                raw_worker.employment_type if isinstance(raw_worker, WorkerV1) else "worker"
            )
            raise InvalidQueryError(
                f"max_hours for {employment_type} must not exceed the hard cap "
                f"of {HARD_MAX_HOURS_PER_WEEK:g}"
            )
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(worker,),
            max_hours=proposal.max_hours,
            description=f"Cap {worker.label} at {proposal.max_hours:g} hours per week.",
        )
    raise InvalidQueryError(f"unsupported draft constraint kind {proposal.kind!r}")


def _preserved_locks(deps: AgentDepsV1) -> tuple[LockV1, ...]:
    locks: list[LockV1] = []
    cursor = 0
    while True:
        remaining = MAX_PRESERVED_LOCKS - len(locks)
        if remaining <= 0:
            raise DraftFailedError(
                f"locks exceed the bounded preservation limit of {MAX_PRESERVED_LOCKS}"
            )
        page = deps.projection_reader.get_locks(
            deps.connection,
            deps.scenario_id,
            GroupQueryV1(cursor=cursor, limit=min(50, remaining)),
        )
        if page is None:
            raise ScenarioNotFoundError("scenario is unavailable while reading locks")
        if page.site_id != deps.site_id:
            raise SiteMismatchError("lock page does not belong to the trusted site")
        if page.scenario_version_id != deps.scenario_version_id:
            raise VersionMismatchError("lock page does not match the selected scenario version")
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
    overview = deps.projection_reader.get_overview(deps.connection, deps.scenario_id)
    if overview is None:
        raise ScenarioNotFoundError("scenario is unavailable")
    if overview.site_id != deps.site_id:
        raise SiteMismatchError("scenario does not belong to the trusted site")
    if overview.scenario_version_id != deps.scenario_version_id:
        raise VersionMismatchError("scenario version changed before draft validation")

    constraints = tuple(
        _resolve_constraint(deps, value, overview.horizon_minutes)
        for value in request.constraints
    )
    locks = _preserved_locks(deps)
    elapsed = (deps.clock() - started_at).total_seconds()
    if elapsed > resolved_manifest.timeout_seconds:
        raise DraftFailedError(
            f"draft validation exceeded the {resolved_manifest.timeout_seconds}s budget"
        )

    result_id = derive_draft_id(deps.scenario_version_id, constraints, locks)
    entities: list[ResolvedEntityV1] = []
    seen: set[tuple[EvidenceGroupV1, str]] = set()
    for constraint in constraints:
        for entity in constraint.resolved_entities:
            locator = (entity.group, entity.record_id)
            if locator not in seen:
                seen.add(locator)
                entities.append(entity)
    proposal_id = uuid5(NAMESPACE_URL, f"shiftmind:proposal:{result_id}")
    proposal_version_id = uuid5(
        NAMESPACE_URL, f"shiftmind:proposal-version:{result_id}:1"
    )
    proposal = ProposalV1(
        proposal_id=proposal_id,
        proposal_version_id=proposal_version_id,
        scenario_id=deps.scenario_id,
        scenario_version_id=deps.scenario_version_id,
        expected_baseline_schedule_version=overview.baseline_schedule_version,
        resolved_entities=tuple(entities),
        constraints=constraints,
        preserved_locks=locks,
        consequence_summary=(
            f"{len(constraints)} reversible constraint"
            f"{'s' if len(constraints) != 1 else ''}; preserved {len(locks)} existing "
            f"lock{'s' if len(locks) != 1 else ''}; no baseline change."
        ),
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
    "CAPABILITY_NAME", "ERROR_CODES", "EVALUATION_FIXTURES", "SCHEDULING_DRAFT_POLICY",
    "SCOPE_CONTROLS", "BudgetExhaustedError", "DraftFailedError", "InvalidQueryError",
    "ScenarioNotFoundError", "SchedulingDraftError", "SchedulingDraftModelViewV1",
    "SchedulingDraftRequestV1", "SchedulingDraftResultV1", "SiteMismatchError",
    "VersionMismatchError", "derive_draft_id", "scheduling_draft",
    "scheduling_draft_manifest", "scheduling_draft_module",
]
