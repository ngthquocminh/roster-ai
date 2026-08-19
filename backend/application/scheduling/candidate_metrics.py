"""Recompute candidate numbers from immutable assignments and source facts.

Per ``docs/DOMAIN-MODEL.md`` sections 1 and 4, outbound/inbound rows are
volume and convert to labour-minutes only through the rates on the workers who
were actually assigned. Indirect rows are headcount rates and need no such
conversion. No solver objective or variable is accepted by this calculator.
"""
from __future__ import annotations

from collections import defaultdict

from application.contracts.proposal import DraftConstraintV1
from application.contracts.schedule_version import (
    ConstraintResultV1,
    MetricSetV1,
    ValidationFactsV1,
)
from application.contracts.scenario_projection import AssignmentV1, DemandIntervalV1, TaskV1


SCOPE_CONTROLS = (
    "COVERS: metrics:overtime_is_above_contracted_hours — assigned effective minutes above WorkerV1.contracted_hours, floored at zero.",
    "NOT COVERED: overtime penalty rates — the engine prices all hours at base rate.",
)


def _overlap(start: int, end: int, other_start: int, other_end: int) -> int:
    return max(0, min(end, other_end) - max(start, other_start))


def calculate_candidate_metrics(
    assignments: tuple[AssignmentV1, ...],
    tasks: tuple[TaskV1, ...],
    demand: tuple[DemandIntervalV1, ...],
    facts: ValidationFactsV1,
    *,
    constraints: tuple[DraftConstraintV1, ...],
) -> tuple[MetricSetV1, tuple[ConstraintResultV1, ...]]:
    workers = {worker.worker_id: worker for worker in facts.workers}
    functions = {task.task_id: task.function for task in tasks}
    required_by_function: dict[str, float] = defaultdict(float)
    served_by_function: dict[str, float] = defaultdict(float)
    interval_required = []
    interval_served = []

    for row in demand:
        matching = [a for a in assignments if a.task_id == row.task_id and _overlap(a.start_minute, a.end_minute, row.start_minute, row.end_minute)]
        if row.unit == "headcount":
            required = (row.end_minute - row.start_minute) * row.amount
        else:
            rates = [
                q.rate for assignment in matching
                for q in assignment.qualification_refs if q.task_id == row.task_id
            ]
            if not rates:
                raise ValueError(f"volume demand {row.record_id} has no assigned-worker qualification rate")
            required = row.amount / (sum(rates) / len(rates)) * 60.0
        served = float(sum(_overlap(a.start_minute, a.end_minute, row.start_minute, row.end_minute) for a in matching))
        interval_required.append((row.record_id, required))
        interval_served.append((row.record_id, served))
        function = functions.get(row.task_id, "Unknown")
        required_by_function[function] += required
        served_by_function[function] += served

    assigned_by_worker: dict[str, int] = defaultdict(int)
    total_cost = 0.0
    for assignment in assignments:
        minutes = assignment.end_minute - assignment.start_minute
        assigned_by_worker[assignment.worker_id] += minutes
        worker = workers[assignment.worker_id]
        total_cost += minutes / 60.0 * worker.wage_per_hour
    overtime = sum(
        max(0.0, minutes - workers[worker_id].contracted_hours * 60.0)
        for worker_id, minutes in assigned_by_worker.items()
    )
    total_required = sum(value for _, value in interval_required)
    total_served = sum(value for _, value in interval_served)
    metrics = MetricSetV1(
        interval_coverage_required_minutes=tuple(sorted(interval_required)),
        interval_coverage_served_minutes=tuple(sorted(interval_served)),
        function_coverage_required_minutes=tuple(sorted(required_by_function.items())),
        function_coverage_served_minutes=tuple(sorted(served_by_function.items())),
        overtime_minutes=overtime,
        total_cost=round(total_cost, 2),
        objective_components=(
            ("unmet_minutes", max(0.0, total_required - total_served)),
            ("overtime_minutes", overtime),
        ),
        assignment_count=len(assignments),
        member_count=len(assigned_by_worker),
    )
    soft_results = tuple(
        _soft_constraint_result(constraint, assignments, assigned_by_worker)
        for constraint in constraints
    )
    return metrics, soft_results


def _soft_constraint_result(constraint, assignments, assigned_by_worker) -> ConstraintResultV1:
    entities = {entity.group: entity.record_id for entity in constraint.resolved_entities}
    task_id = entities.get("work-areas-and-tasks")
    worker_id = entities.get("workers")
    if constraint.kind == "set_min_workers_per_task":
        measured = len({a.worker_id for a in assignments if a.task_id == task_id})
        limit, unit = float(constraint.n or 0), "workers"
        satisfied = measured >= limit
    elif constraint.kind == "exclude_worker_from_task":
        measured, limit, unit = sum(1 for a in assignments if a.worker_id == worker_id and a.task_id == task_id), 0.0, "assignments"
        satisfied = measured == 0
    elif constraint.kind == "set_max_hours":
        measured, limit, unit = assigned_by_worker.get(worker_id or "", 0) / 60.0, float(constraint.max_hours or 0), "hours"
        satisfied = measured <= limit
    elif constraint.kind == "lock_worker_shift":
        start, end = constraint.start_minute or 0, constraint.end_minute or 0
        measured, limit, unit = sum(1 for a in assignments if a.worker_id == worker_id and a.start_minute < end and a.end_minute > start), 1.0, "assignments"
        satisfied = measured >= 1
    else:
        measured, limit, unit, satisfied = 1.0, float(constraint.factor or 1), "factor", True
    return ConstraintResultV1(
        constraint_id=f"soft:{constraint.kind}:{task_id or worker_id or ''}",
        constraint_type=constraint.kind,
        constraint_class="soft", satisfied=satisfied,
        measured_value=float(measured), limit=float(limit), unit=unit,
    )


__all__ = ["SCOPE_CONTROLS", "calculate_candidate_metrics"]
