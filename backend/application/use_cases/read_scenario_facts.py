"""Read allow-listed facts from the normalized scenario projection."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.contracts.scenario_projection import ScenarioOverviewV1
from application.ports.scenario_projection import (
    AssignmentPageV1,
    ConstraintPageV1,
    DemandIntervalPageV1,
    GroupQueryV1,
    LockPageV1,
    ScenarioFactGroupV1,
    ScenarioProjectionReader,
    TaskPageV1,
    WorkerPageV1,
)

ScenarioFactPageV1 = (
    TaskPageV1
    | WorkerPageV1
    | DemandIntervalPageV1
    | AssignmentPageV1
    | LockPageV1
    | ConstraintPageV1
)

# Every group the port declares. Kept exhaustive against `ScenarioFactGroupV1`
# by `test_scheduling_inspect.test_every_declared_group_is_routable`, so adding
# a group to the vocabulary without routing it here fails rather than raising
# KeyError at call time.
_GROUP_READERS: dict[str, str] = {
    "tasks": "get_tasks",
    "demand": "get_demand",
    "assignments": "get_baseline_assignments",
    "workers": "get_workers",
    "locks": "get_locks",
    "constraints": "get_constraints",
}


def read_scenario_facts(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    scenario_id: UUID,
    group: ScenarioFactGroupV1,
    query: GroupQueryV1 | None = None,
) -> ScenarioOverviewV1 | ScenarioFactPageV1 | None:
    """Delegate interpretation to the projection adapter; never reinterpret rows.

    Raises `ValueError` for a group outside `ScenarioFactGroupV1` so a widened
    vocabulary surfaces as a typed error rather than a `KeyError` from the
    dispatch table.
    """
    if group == "overview":
        return reader.get_overview(connection, scenario_id)
    method_name = _GROUP_READERS.get(group)
    if method_name is None:
        raise ValueError(f"unknown scenario fact group: {group!r}")
    return getattr(reader, method_name)(connection, scenario_id, query or GroupQueryV1())


__all__ = ["ScenarioFactGroupV1", "ScenarioFactPageV1", "read_scenario_facts"]
