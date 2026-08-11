"""Read allow-listed facts from the normalized scenario projection."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from application.ports.scenario_projection import GroupQueryV1, ScenarioProjectionReader

ScenarioFactGroupV1 = Literal[
    "overview", "demand", "assignments", "workers", "locks", "constraints"
]


def read_scenario_facts(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    scenario_id: UUID,
    group: ScenarioFactGroupV1,
    query: GroupQueryV1 | None = None,
) -> object | None:
    """Delegate interpretation to the projection adapter; never reinterpret rows."""
    if group == "overview":
        return reader.get_overview(connection, scenario_id)
    page_query = query or GroupQueryV1()
    method_names = {
        "demand": "get_demand",
        "assignments": "get_baseline_assignments",
        "workers": "get_workers",
        "locks": "get_locks",
        "constraints": "get_constraints",
    }
    return getattr(reader, method_names[group])(connection, scenario_id, page_query)


__all__ = ["ScenarioFactGroupV1", "read_scenario_facts"]
