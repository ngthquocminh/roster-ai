"""The single translation between read-port groups and planner evidence groups."""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from application.contracts.evidence_ref import EvidenceGroupV1
from application.ports.scenario_projection import ScenarioFactGroupV1


EVIDENCE_GROUP_BY_SCENARIO_FACT_GROUP: Mapping[
    ScenarioFactGroupV1, EvidenceGroupV1
] = MappingProxyType(
    {
        "tasks": "work-areas-and-tasks",
        "workers": "workers",
        "demand": "demand",
        "assignments": "baseline-assignments",
        "locks": "locks",
        "constraints": "constraints-and-objectives",
    }
)


def evidence_group_for_scenario_fact_group(
    group: ScenarioFactGroupV1,
) -> EvidenceGroupV1 | None:
    """Return the visible group, or ``None`` for non-evidence overview data."""
    if group == "overview":
        return None
    return EVIDENCE_GROUP_BY_SCENARIO_FACT_GROUP[group]


def scenario_fact_group_for_evidence_group(
    group: EvidenceGroupV1,
) -> ScenarioFactGroupV1:
    """Return the normalized projection group for a visible evidence group."""
    for scenario_group, evidence_group in EVIDENCE_GROUP_BY_SCENARIO_FACT_GROUP.items():
        if evidence_group == group:
            return scenario_group
    raise ValueError(f"unsupported evidence group: {group}")


__all__ = [
    "EVIDENCE_GROUP_BY_SCENARIO_FACT_GROUP",
    "evidence_group_for_scenario_fact_group",
    "scenario_fact_group_for_evidence_group",
]
