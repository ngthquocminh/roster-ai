"""Normalized, versioned scenario projection contracts.

These immutable application records are the authoritative normalized shape.
HTTP and persistence layers map to and from them explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")


@dataclass(frozen=True)
class ScenarioOverviewV1:
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    fixture_id: str
    scenario_name: str
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    horizon_start: datetime
    site_timezone: str
    horizon_minutes: int
    baseline_schedule_version: str | None
    projection_generated_at: datetime
    work_area_count: int
    task_count: int
    worker_count: int
    demand_interval_count: int
    baseline_assignment_count: int
    lock_count: int
    constraint_count: int

    def __post_init__(self) -> None:
        _require_utc(self.horizon_start, "horizon_start")
        _require_utc(self.projection_generated_at, "projection_generated_at")


@dataclass(frozen=True)
class TaskV1:
    record_id: str
    task_id: str
    name: str
    function: str
    area_id: str
    area_name: str
    unit_type_id: str | None


@dataclass(frozen=True)
class QualificationRefV1:
    task_id: str
    rate: float


@dataclass(frozen=True)
class AvailabilityWindowV1:
    kind: Literal["roster", "availability"]
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class WorkerV1:
    record_id: str
    contact_id: str
    name: str
    employment_type: str
    grade: str
    eba: str
    contracted_hours: float
    qualifications: tuple[QualificationRefV1, ...]
    availability_windows: tuple[AvailabilityWindowV1, ...]


@dataclass(frozen=True)
class DemandIntervalV1:
    record_id: str
    family: Literal["outbound", "inbound", "indirect"]
    task_id: str
    area_id: str | None
    start_minute: int
    end_minute: int
    amount: float
    unit: Literal["volume", "headcount"]


@dataclass(frozen=True)
class AssignmentV1:
    record_id: str
    worker_id: str
    task_id: str
    shift_id: str | None
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class LockV1:
    record_id: str
    target_type: str
    target_ref: str
    scope: str
    source: str


@dataclass(frozen=True)
class ConstraintV1:
    record_id: str
    constraint_type: str
    value: str
    value_type: str | None
