"""Immutable governed solver-output contracts (AD-7, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.scenario_projection import AssignmentV1

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


__all__ = [
    "SCHEMA_VERSION",
    "ConstraintClassV1",
    "ConstraintResultV1",
    "MetricSetV1",
    "ScheduleRunStatusV1",
    "ScheduleVersionV1",
    "SolverOutcomeV1",
    "SolverStatusV1",
]
