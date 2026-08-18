"""Resolve UNTRUSTED draft constraint proposals into TRUSTED solver input.

One resolver, used by both paths that may produce a ``DraftConstraintV1``:

* ``application/capabilities/scheduling_draft.py`` — the model-facing capability
  that creates a draft inside an agent turn;
* ``application/use_cases/manage_proposal.py`` — the HTTP revise command.

Story 3.1's Decision 1 ("the capability validates and resolves") and Decision 2
("the model proposes ``(group, record_id)``, the application resolves") are
properties of the *boundary*, not of the transport that crosses it. A browser
POST is exactly as untrusted as a model tool call, so it runs the same checks
and receives the same application-composed ``description``. Keeping one
implementation is what makes that guarantee checkable rather than aspirational.

This module also owns the single canonicalizer for draft content. Two
pre-canonicalization shapes for one ``canonical_hash`` would let the create and
revise paths disagree about the field AD-20 makes load-bearing.

Framework-free by construction: no adapter, no ORM, no HTTP type. The caller
supplies a read port and a connection through :class:`DraftResolutionContextV1`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence
from uuid import UUID

from application.clarification.resolve import planner_label
from application.contracts.canonical import contract_digest
from application.contracts.evidence_ref import EvidenceGroupV1
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    DraftConstraintV1,
    ResolvedEntityV1,
)
from application.contracts.scenario_projection import LockV1
from application.grounding.resolvers import resolver_name_for_evidence_group
from application.ports.scenario_projection import ScenarioProjectionReader

SCHEMA_VERSION = "1"

#: A flat upper sanity bound on a drafted weekly hours cap.
#:
#: Deliberately NOT an employment-type cap. The solver's own
#: ``config/constants.py:DEFAULT_MAX_HOURS_PER_WEEK`` is a *fallback* consulted
#: only when an employment type has no configured cap
#: (``max_hours_per_week.get(emp_type, DEFAULT)`` in ``engine/cpsat/builder.py``),
#: and no per-worker cap is reachable from the draft path today:
#: ``WorkerV1.contracted_hours`` is a contractual figure, not a ceiling, and
#: ``max_hours_per_week`` lives solver-side. Resolved at review on 2026-08-18:
#: keep a flat bound, do not claim it is type-derived, and record the reduction
#: in the capability's ``SCOPE_CONTROLS``. Story 3.2 supplies the real cap.
HARD_MAX_HOURS_PER_WEEK = 56.0


class DraftConstraintError(ValueError):
    """An untrusted constraint proposal failed validation or resolution.

    Transport-neutral on purpose. The capability re-raises it as its retryable
    ``invalid_query``; the HTTP command re-raises it as a 422. Neither meaning
    belongs in this module.
    """


@dataclass(frozen=True)
class DraftResolutionContextV1:
    """The trusted, server-owned pin every resolution is performed against."""

    projection_reader: ScenarioProjectionReader
    connection: Any
    scenario_id: UUID
    scenario_version_id: UUID
    schema_version: str = SCHEMA_VERSION


def resolve_entity(
    context: DraftResolutionContextV1,
    group: EvidenceGroupV1,
    record_id: str,
) -> tuple[ResolvedEntityV1, object]:
    """Resolve one identifier against the pinned immutable scenario version."""
    resolver_name = resolver_name_for_evidence_group(group)
    resolution = getattr(context.projection_reader, resolver_name)(
        context.connection,
        context.scenario_id,
        context.scenario_version_id,
        record_id,
    )
    if (
        resolution is None
        or resolution.outcome != "resolved"
        or resolution.item is None
        or resolution.current_scenario_version_id != context.scenario_version_id
        or resolution.item.record_id != record_id
    ):
        raise DraftConstraintError(f"{group} entity {record_id!r} is missing or not resolvable")
    return (
        ResolvedEntityV1(
            group=group,
            record_id=record_id,
            label=planner_label(resolution.item),
            scenario_version_id=context.scenario_version_id,
        ),
        resolution.item,
    )


def _require_primary(
    context: DraftResolutionContextV1,
    proposal: DraftConstraintProposalV1,
    expected_group: EvidenceGroupV1,
) -> tuple[ResolvedEntityV1, object]:
    if proposal.group != expected_group:
        raise DraftConstraintError(
            f"{proposal.kind} requires group {expected_group!r}, got {proposal.group!r}"
        )
    return resolve_entity(context, proposal.group, proposal.record_id)


def resolve_constraint(
    context: DraftResolutionContextV1,
    proposal: DraftConstraintProposalV1,
    horizon_minutes: int,
) -> DraftConstraintV1:
    """Validate one untrusted proposal and return trusted solver input.

    Every returned ``description`` is composed here from resolved labels and
    validated arguments, so it can never disagree with the numbers beside it.
    """
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
            raise DraftConstraintError(
                f"{proposal.kind} does not accept arguments {unexpected}"
            )

    if proposal.kind == "set_min_workers_per_task":
        require_only("n")
        task, _ = _require_primary(context, proposal, "work-areas-and-tasks")
        if proposal.n is None or proposal.n <= 0:
            raise DraftConstraintError("n must be greater than 0")
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(task,),
            n=proposal.n,
            description=f"Keep at least {proposal.n} workers on {task.label}.",
        )
    if proposal.kind == "scale_demand":
        require_only("factor")
        task, _ = _require_primary(context, proposal, "work-areas-and-tasks")
        if proposal.factor is None or proposal.factor <= 0:
            raise DraftConstraintError("factor must be greater than 0")
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(task,),
            factor=proposal.factor,
            description=f"Scale demand for {task.label} by {proposal.factor}.",
        )
    if proposal.kind == "lock_worker_shift":
        require_only("start_minute", "end_minute")
        worker, _ = _require_primary(context, proposal, "workers")
        if (
            proposal.start_minute is None
            or proposal.end_minute is None
            or proposal.start_minute < 0
            or proposal.end_minute <= proposal.start_minute
            or proposal.end_minute > horizon_minutes
        ):
            raise DraftConstraintError(
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
        worker, _ = _require_primary(context, proposal, "workers")
        if (
            proposal.related_group != "work-areas-and-tasks"
            or not proposal.related_record_id
        ):
            raise DraftConstraintError(
                "exclude_worker_from_task requires a related work-areas-and-tasks record"
            )
        task, _ = resolve_entity(context, proposal.related_group, proposal.related_record_id)
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(worker, task),
            description=f"Keep {worker.label} off {task.label}.",
        )
    if proposal.kind == "set_max_hours":
        require_only("max_hours")
        worker, _ = _require_primary(context, proposal, "workers")
        if proposal.max_hours is None or proposal.max_hours <= 0:
            raise DraftConstraintError("max_hours must be greater than 0")
        if proposal.max_hours > HARD_MAX_HOURS_PER_WEEK:
            # Names the bound, not an employment type: the ceiling is flat and
            # saying otherwise would describe a rule the repository does not have.
            raise DraftConstraintError(
                f"max_hours must not exceed the flat upper bound of "
                f"{HARD_MAX_HOURS_PER_WEEK:g} hours per week"
            )
        return DraftConstraintV1(
            kind=proposal.kind,
            resolved_entities=(worker,),
            max_hours=proposal.max_hours,
            description=f"Cap {worker.label} at {proposal.max_hours:g} hours per week.",
        )
    raise DraftConstraintError(f"unsupported draft constraint kind {proposal.kind!r}")


def resolve_constraints(
    context: DraftResolutionContextV1,
    proposals: Sequence[DraftConstraintProposalV1],
    horizon_minutes: int,
    *,
    deadline: Any = None,
    clock: Any = None,
    on_timeout: Any = None,
) -> tuple[DraftConstraintV1, ...]:
    """Resolve every proposal, checking the deadline *between* resolutions.

    A budget checked only after all the work has finished bounds nothing; it can
    only discard a completed result. ``on_timeout`` is called with the elapsed
    seconds and must raise.
    """
    resolved: list[DraftConstraintV1] = []
    for proposal in proposals:
        if deadline is not None and clock is not None and clock() > deadline:
            on_timeout()
        resolved.append(resolve_constraint(context, proposal, horizon_minutes))
    return tuple(resolved)


def unique_entities(
    constraints: Sequence[DraftConstraintV1],
) -> tuple[ResolvedEntityV1, ...]:
    """Order-preserving de-duplication by ``(group, record_id)``."""
    entities: list[ResolvedEntityV1] = []
    seen: set[tuple[str, str]] = set()
    for constraint in constraints:
        for entity in constraint.resolved_entities:
            locator = (entity.group, entity.record_id)
            if locator not in seen:
                seen.add(locator)
                entities.append(entity)
    return tuple(entities)


def consequence_summary(
    constraints: Sequence[DraftConstraintV1],
    preserved_locks: Sequence[LockV1],
) -> str:
    """The application-composed summary. Counts only — never a measured metric.

    ``docs/DOMAIN-MODEL.md`` §5: a draft computes no demand, staffing, or
    shortfall quantity; that is ``scheduling_compute``'s, behind grounding.
    """
    return (
        f"{len(constraints)} reversible constraint"
        f"{'s' if len(constraints) != 1 else ''}; preserved "
        f"{len(preserved_locks)} existing lock"
        f"{'s' if len(preserved_locks) != 1 else ''}; no baseline change."
    )


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
    constraints: Sequence[DraftConstraintV1],
    preserved_locks: Sequence[LockV1],
) -> str:
    """Return a stable citation over the immutable version and trusted inputs.

    This is a *citation*, not a row identity. Two identical drafts legitimately
    share one ``draft_id`` — that is what lets a golden case cite it — while
    their durable ``proposal_id`` values stay distinct (see
    ``scheduling_draft.scheduling_draft``).
    """
    return contract_digest(
        {
            "scenario_version_id": str(scenario_version_id),
            "constraints": [_primitive_constraint(value) for value in constraints],
            "preserved_locks": [_primitive_lock(value) for value in preserved_locks],
        }
    )[2]


__all__ = [
    "HARD_MAX_HOURS_PER_WEEK",
    "SCHEMA_VERSION",
    "DraftConstraintError",
    "DraftResolutionContextV1",
    "consequence_summary",
    "derive_draft_id",
    "resolve_constraint",
    "resolve_constraints",
    "resolve_entity",
    "unique_entities",
]
