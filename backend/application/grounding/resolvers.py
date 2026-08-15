"""Single exhaustive map from evidence groups to exact projection resolvers."""
from __future__ import annotations

from typing import Final

from application.contracts.evidence_ref import EvidenceGroupV1
from application.grounding.evidence_groups import scenario_fact_group_for_evidence_group

RESOLVER_BY_SCENARIO_FACT_GROUP: Final[dict[str, str]] = {
    "tasks": "resolve_task",
    "workers": "resolve_worker",
    "demand": "resolve_demand_interval",
    "assignments": "resolve_assignment",
    "locks": "resolve_lock",
    "constraints": "resolve_constraint",
}


def resolver_name_for_evidence_group(group: EvidenceGroupV1) -> str:
    return RESOLVER_BY_SCENARIO_FACT_GROUP[
        scenario_fact_group_for_evidence_group(group)
    ]


__all__ = ["RESOLVER_BY_SCENARIO_FACT_GROUP", "resolver_name_for_evidence_group"]
