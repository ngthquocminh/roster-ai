"""Version-bound evidence locators and exact-target resolution outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from application.contracts.scenario_projection import (
    AssignmentV1,
    ConstraintV1,
    DemandIntervalV1,
    LockV1,
    TaskV1,
    WorkerV1,
)


EvidenceGroupV1 = Literal[
    "work-areas-and-tasks",
    "workers",
    "demand",
    "baseline-assignments",
    "locks",
    "constraints-and-objectives",
]
ResolutionOutcomeV1 = Literal["resolved", "not_found", "version_mismatch"]


@dataclass(frozen=True)
class EvidenceRefV1:
    scenario_version_id: UUID
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    producing_run_version: str | None
    baseline_schedule_version: str | None
    group: EvidenceGroupV1
    record_id: str
    field: str | None = None
    start_minute: int | None = None
    end_minute: int | None = None


@dataclass(frozen=True)
class TaskResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: TaskV1 | None


@dataclass(frozen=True)
class WorkerResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: WorkerV1 | None


@dataclass(frozen=True)
class DemandIntervalResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: DemandIntervalV1 | None


@dataclass(frozen=True)
class AssignmentResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: AssignmentV1 | None


@dataclass(frozen=True)
class LockResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: LockV1 | None


@dataclass(frozen=True)
class ConstraintResolutionV1:
    outcome: ResolutionOutcomeV1
    scenario_id: UUID
    current_scenario_version_id: UUID
    item: ConstraintV1 | None
