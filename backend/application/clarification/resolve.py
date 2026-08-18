"""Resolve model-proposed candidates against the trusted exact-target reader."""
from __future__ import annotations

from application.capabilities.deps import AgentDepsV1
from application.contracts.dialogue import (
    ClarificationV1,
    EntityCandidateV1,
    ResolvedClarificationV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    ConstraintV1,
    DemandIntervalV1,
    LockV1,
    TaskV1,
    WorkerV1,
)
from application.grounding.resolvers import resolver_name_for_evidence_group

# Upper bound on model-proposed candidates resolved per turn. Bounds request-path
# database work by an application constant rather than by model output.
MAX_CANDIDATES = 10


# A candidate list of identifiers alone cannot falsify a fabricated name: the
# clarification QUESTION is free model prose and may say "Taylor Smith", while
# the list said only "w1 · workers · w1". The planner had no way to check one
# against the other without leaving Chat. Every group therefore renders the
# columns `scenario-data/columns.ts` marks `essential: true`, so the two
# surfaces agree and the model's wording is comparable against real rows.
def planner_label(item: object) -> str:
    """Render the identifying essential columns the Scenario Data grid shows."""
    if isinstance(item, TaskV1):
        return f"{item.name} ({item.task_id})"
    if isinstance(item, WorkerV1):
        return f"{item.name} ({item.contact_id})"
    if isinstance(item, DemandIntervalV1):
        return f"{item.family} {item.task_id} ({item.record_id})"
    if isinstance(item, AssignmentV1):
        return f"{item.worker_id} → {item.task_id} ({item.record_id})"
    if isinstance(item, LockV1):
        return f"{item.target_type} {item.target_ref} ({item.record_id})"
    if isinstance(item, ConstraintV1):
        return f"{item.constraint_type} ({item.record_id})"
    # Unreachable while `EvidenceGroupV1` has six members, all handled above.
    # Fails loud rather than rendering an opaque id as if it were a label.
    raise TypeError(f"no planner label defined for {type(item).__name__}")


def resolve_clarification(
    clarification: ClarificationV1,
    deps: AgentDepsV1,
) -> ResolvedClarificationV1:
    """Resolve exact cited records once; drop every miss without retargeting."""
    candidates: list[EntityCandidateV1] = []
    dropped = 0
    # The proposal tuple is MODEL-CONTROLLED and was unbounded, so model output
    # decided how many exact-target projection reads the request path performed
    # -- each one its own short site transaction. A clarification asking the
    # planner to choose between more than a handful of records is not usable
    # anyway, so the surplus is dropped and counted like any other miss.
    seen: set[tuple[str, str]] = set()
    for proposal in clarification.candidates[:MAX_CANDIDATES]:
        # Duplicates would collide on the frontend list key and show the planner
        # the same record twice.
        locator = (proposal.group, proposal.record_id)
        if locator in seen:
            dropped += 1
            continue
        seen.add(locator)
        resolver_name = resolver_name_for_evidence_group(proposal.group)
        resolution = getattr(deps.projection_reader, resolver_name)(
            deps.connection,
            deps.scenario_id,
            deps.scenario_version_id,
            proposal.record_id,
        )
        if (
            resolution is None
            or resolution.outcome != "resolved"
            or resolution.item is None
            or resolution.current_scenario_version_id != deps.scenario_version_id
            or resolution.item.record_id != proposal.record_id
        ):
            dropped += 1
            continue
        candidates.append(
            EntityCandidateV1(
                group=proposal.group,
                record_id=proposal.record_id,
                label=planner_label(resolution.item),
                scenario_version_id=deps.scenario_version_id,
            )
        )
    dropped += max(0, len(clarification.candidates) - MAX_CANDIDATES)
    return ResolvedClarificationV1(
        question=clarification.question,
        candidates=tuple(candidates),
        scenario_version_id=deps.scenario_version_id,
        dropped_candidate_count=dropped,
    )


__all__ = ["planner_label", "resolve_clarification"]
