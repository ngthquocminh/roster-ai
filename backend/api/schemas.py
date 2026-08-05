"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    time_limit_s: float = Field(default=60.0, gt=0)


class ScenarioOut(BaseModel):
    id: str
    name: str
    fixture: str
    time_limit_s: float
    created_at: str


class RunOut(BaseModel):
    id: str
    scenario_id: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    solver_status: Optional[str] = None
    error: Optional[str] = None


class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None    # present when ready=True (INS-01)
    status: Optional[str] = None    # present when ready=False (D-07)
    reason: Optional[str] = None    # present when ready=False (D-07)

    @model_validator(mode="after")
    def check_ready_fields(self) -> "InsightOut":
        if self.ready and self.report is None:
            raise ValueError("report must be set when ready=True")
        if not self.ready and self.status is None:
            raise ValueError("status must be set when ready=False")
        return self


class ConstraintParseRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)


class AppliedConstraint(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str


class RejectedConstraint(BaseModel):
    tool: str
    error: str


class ConstraintParseResponse(BaseModel):
    applied: list[AppliedConstraint]
    rejected: list[RejectedConstraint]
    clarification_needed: str | None
    no_constraint_found: bool


class OverrideOut(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str | None = None  # None for pre-D-02 legacy entries


class ProblemDetailsV1(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str


class AuthSessionOut(BaseModel):
    app_user_id: UUID
    site_id: UUID
    csrf_token: str
    expires_at: datetime


class FixtureCatalogueEntryOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    fixture_id: str
    scenario_name: str
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    imported_at: datetime
    site_id: UUID


class ScenarioContextOut(BaseModel):
    schema_version: str = "v1"
    scenario_name: str
    scenario_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    site_id: UUID
    baseline_schedule_version: str | None


class ScenarioOverviewOut(BaseModel):
    schema_version: str = "v1"
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


class TaskProjectionOut(BaseModel):
    record_id: str
    task_id: str
    name: str
    function: str
    area_id: str
    area_name: str
    unit_type_id: str | None


class QualificationRefOut(BaseModel):
    task_id: str
    rate: float


class AvailabilityWindowOut(BaseModel):
    kind: Literal["roster", "availability"]
    start_minute: int
    end_minute: int


class WorkerProjectionOut(BaseModel):
    record_id: str
    contact_id: str
    name: str
    employment_type: str
    grade: str
    eba: str
    contracted_hours: float
    qualifications: list[QualificationRefOut]
    availability_windows: list[AvailabilityWindowOut]


class DemandIntervalOut(BaseModel):
    record_id: str
    family: Literal["outbound", "inbound", "indirect"]
    task_id: str
    area_id: str | None
    start_minute: int
    end_minute: int
    amount: float
    unit: Literal["volume", "headcount"]


class AssignmentOut(BaseModel):
    record_id: str
    worker_id: str
    task_id: str
    shift_id: str | None
    start_minute: int
    end_minute: int


class LockOut(BaseModel):
    record_id: str
    target_type: str
    target_ref: str
    scope: str
    source: str


class ConstraintProjectionOut(BaseModel):
    record_id: str
    constraint_type: str
    value: str
    value_type: str | None


class TaskPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["work-areas-and-tasks"]
    items: list[TaskProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class WorkerPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["workers"]
    items: list[WorkerProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class DemandIntervalPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["demand"]
    items: list[DemandIntervalOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class AssignmentPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["baseline-assignments"]
    items: list[AssignmentOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class LockPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["locks"]
    items: list[LockOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class ConstraintPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["constraints-and-objectives"]
    items: list[ConstraintProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int
