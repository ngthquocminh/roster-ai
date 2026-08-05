"""Application port for the normalized scenario projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.scenario_projection import (
    AssignmentV1,
    ConstraintV1,
    DemandIntervalV1,
    LockV1,
    ScenarioOverviewV1,
    TaskV1,
    WorkerV1,
)


@dataclass(frozen=True)
class TaskPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[TaskV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


@dataclass(frozen=True)
class WorkerPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[WorkerV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


@dataclass(frozen=True)
class DemandIntervalPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[DemandIntervalV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


@dataclass(frozen=True)
class AssignmentPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[AssignmentV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


@dataclass(frozen=True)
class LockPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[LockV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


@dataclass(frozen=True)
class ConstraintPageV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    items: tuple[ConstraintV1, ...]
    next_cursor: int | None
    total_count: int
    matching_count: int


class ScenarioProjectionReader(Protocol):
    def get_overview(
        self, connection: Any, scenario_id: UUID
    ) -> ScenarioOverviewV1 | None: ...

    def get_tasks(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> TaskPageV1 | None: ...

    def get_workers(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> WorkerPageV1 | None: ...

    def get_demand(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> DemandIntervalPageV1 | None: ...

    def get_baseline_assignments(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> AssignmentPageV1 | None: ...

    def get_locks(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> LockPageV1 | None: ...

    def get_constraints(
        self, connection: Any, scenario_id: UUID, cursor: int, limit: int
    ) -> ConstraintPageV1 | None: ...
