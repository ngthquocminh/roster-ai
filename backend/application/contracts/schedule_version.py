"""Immutable governed solver-output contracts (AD-7, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    DemandIntervalV1,
    QualificationRefV1,
    TaskV1,
)

SCHEMA_VERSION = "1"

ScheduleRunStatusV1 = Literal[
    "solver_queued",
    "solver_running",
    "cancellation_requested",
    "solver_completed",
    "solver_infeasible",
    "solver_timed_out",
    "solver_cancelled",
    "solver_failed",
]
ConstraintClassV1 = Literal["hard", "soft"]
SolverStatusV1 = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "MODEL_INVALID", "UNKNOWN"]


@dataclass(frozen=True)
class WorkerSchedulingFactV1:
    worker_id: str
    employment_type: str
    contracted_hours: float
    wage_per_hour: float
    qualifications: tuple[QualificationRefV1, ...]
    availability_windows: tuple[AvailabilityWindowV1, ...]
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SelectedShiftFactV1:
    shift_id: str
    worker_id: str
    window_id: str
    window_kind: Literal["roster", "availability"]
    start_minute: int
    end_minute: int
    effective_minutes: int
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationFactsV1:
    horizon_minutes: int
    workers: tuple[WorkerSchedulingFactV1, ...]
    selected_shifts: tuple[SelectedShiftFactV1, ...]
    max_hours_per_week: tuple[tuple[str, float], ...]
    max_shifts_per_day: tuple[tuple[str, int], ...]
    minimum_gap_minutes: int
    tasks: tuple[TaskV1, ...] = ()
    demand_intervals: tuple[DemandIntervalV1, ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class MetricSetV1:
    """Minute-, currency-, and count-valued candidate metrics."""

    interval_coverage_required_minutes: tuple[tuple[str, float], ...] = ()
    interval_coverage_served_minutes: tuple[tuple[str, float], ...] = ()
    function_coverage_required_minutes: tuple[tuple[str, float], ...] = ()
    function_coverage_served_minutes: tuple[tuple[str, float], ...] = ()
    overtime_minutes: float = 0.0
    total_cost: float = 0.0
    objective_components: tuple[tuple[str, float], ...] = ()
    assignment_count: int = 0
    member_count: int = 0
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ConstraintResultV1:
    constraint_id: str = ""
    constraint_type: str = ""
    constraint_class: ConstraintClassV1 = "hard"
    satisfied: bool = False
    measured_value: float | None = None
    limit: float | None = None
    unit: str = ""
    contributing_assignment_ids: tuple[str, ...] = ()
    contributing_evidence_refs: tuple[EvidenceRefV1, ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SolverOutcomeV1:
    solver_status: SolverStatusV1 = "UNKNOWN"
    assignments: tuple[AssignmentV1, ...] = ()
    metrics: MetricSetV1 | None = None
    constraint_results: tuple[ConstraintResultV1, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRefV1, ...] = ()
    round1_value: float | None = None
    round2_value: float | None = None
    wall_time_seconds: float = 0.0
    validation_facts: ValidationFactsV1 | None = None
    reason: str | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ScheduleVersionV1:
    schedule_version_id: UUID | None = None
    schedule_run_id: UUID | None = None
    scenario_id: UUID | None = None
    scenario_version_id: UUID | None = None
    proposal_id: UUID | None = None
    proposal_version_id: UUID | None = None
    feasible_solver_status: Literal["OPTIMAL", "FEASIBLE"] | None = None
    assignments: tuple[AssignmentV1, ...] = ()
    metrics: MetricSetV1 | None = None
    constraint_results: tuple[ConstraintResultV1, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRefV1, ...] = ()
    created_at: datetime | None = None
    schema_version: str = SCHEMA_VERSION



#: `event_type` is client-facing SSE contract under AD-20/AD-21, so it is a
#: closed mapping rather than `status.removeprefix("solver_")`: string surgery
#: would let a rename of an internal status literal silently rename a published
#: event, and it hides that `cancellation_requested` carries no `solver_`
#: prefix and so breaks the pattern the other seven follow. Values here are
#: byte-identical to what the derivation produced -- rows already persisted
#: must keep resolving.
RUN_EVENT_TYPES: dict[str, str] = {
    "solver_queued": "run.queued.v1",
    "solver_running": "run.running.v1",
    "cancellation_requested": "run.cancellation_requested.v1",
    "solver_completed": "run.completed.v1",
    "solver_infeasible": "run.infeasible.v1",
    "solver_timed_out": "run.timed_out.v1",
    "solver_cancelled": "run.cancelled.v1",
    "solver_failed": "run.failed.v1",
}

__all__ = [
    "RUN_EVENT_TYPES",
    "SCHEMA_VERSION",
    "ConstraintClassV1",
    "ConstraintResultV1",
    "MetricSetV1",
    "ScheduleRunStatusV1",
    "ScheduleVersionV1",
    "SelectedShiftFactV1",
    "SolverOutcomeV1",
    "SolverStatusV1",
    "ValidationFactsV1",
    "WorkerSchedulingFactV1",
]
