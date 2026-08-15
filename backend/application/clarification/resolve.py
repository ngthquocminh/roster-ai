"""Resolve model-proposed candidates against the trusted exact-target reader."""
from __future__ import annotations

from application.capabilities.deps import AgentDepsV1
from application.contracts.dialogue import (
    ClarificationV1,
    EntityCandidateV1,
    ResolvedClarificationV1,
)
from application.contracts.scenario_projection import TaskV1, WorkerV1
from application.grounding.resolvers import resolver_name_for_evidence_group


def _planner_label(item: object) -> str:
    """Use the same primary identifier rendered by the Scenario Data grid."""
    if isinstance(item, TaskV1):
        return item.task_id
    if isinstance(item, WorkerV1):
        return item.contact_id
    return str(getattr(item, "record_id"))


def resolve_clarification(
    clarification: ClarificationV1,
    deps: AgentDepsV1,
) -> ResolvedClarificationV1:
    """Resolve exact cited records once; drop every miss without retargeting."""
    candidates: list[EntityCandidateV1] = []
    dropped = 0
    for proposal in clarification.candidates:
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
                label=_planner_label(resolution.item),
                scenario_version_id=deps.scenario_version_id,
            )
        )
    return ResolvedClarificationV1(
        question=clarification.question,
        candidates=tuple(candidates),
        scenario_version_id=deps.scenario_version_id,
        dropped_candidate_count=dropped,
    )


__all__ = ["resolve_clarification"]
