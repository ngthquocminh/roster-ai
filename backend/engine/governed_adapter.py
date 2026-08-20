"""The sole governed translation boundary between V1 contracts and CP-SAT.

Application contracts remain integer-minute and solver-free. Raw fixture
hours, legacy engine results, and override calls exist only inside this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from time import perf_counter
from typing import Iterable

from ortools.sat.python import cp_model

from application.contracts.canonical import contract_digest
from application.contracts.proposal import DraftConstraintV1, ResolvedEntityV1
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import (
    SelectedShiftFactV1,
    SolverOutcomeV1,
    ValidationFactsV1,
    WorkerSchedulingFactV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    DemandIntervalV1,
    QualificationRefV1,
    TaskV1,
)
from application.ports.scheduler import SolverInputSource
from domain.overrides import OverrideCall, override_id
from config import constants as C
from engine.cpsat.builder import CpSatBuilder
from ingest.input_adapter import build_problem


SCOPE_CONTROLS = (
    "COVERS: inputs:solver_reads_raw_fixture — the adapter alone translates the re-verified checksummed fixture into SchedulingProblem.",
    "COVERS: solver:reproducibility — sample_tiny_input, seed 42: single-worker "
    "max_deterministic_time=1.0 produced identical 70-assignment/10-member sets "
    "in 3/3 runs (round1=247.44352 hours, round2=1118241; wall "
    "6.22/7.24/6.71s; terminal UNKNOWN because round 2 consumed the ceiling).",
    "COVERS: solver:multi_worker_trade — 8-worker wall-time=3.0s produced "
    "211.85190-211.85271 unmet hours, round2=1173123-1201002, 76-78 "
    "assignments, 10 members, and two distinct assignment sets across 3 runs.",
    "COVERS: solver:wall_total — both lexicographic rounds share one decreasing "
    "wall-time budget; a 0.25s fixture solve returns UNKNOWN within 0.40s.",
    "NOT COVERED: solution-quality parity at longer ceilings — deterministic "
    "reproducibility is the governed default; performance ceilings remain settings-owned.",
    "NOT COVERED: events:owned_by_story_3_5 — persisted run progress/event replay is not emitted here.",
    "NOT COVERED: cancellation:owned_by_story_3_4 — solver_cancelled is persistable but no cancellation request is observed here.",
    "NOT COVERED: baseline:pointer_owned_by_epic_4 — candidates are created without moving the site baseline pointer.",
    "NOT COVERED: locks:seeded_supply_only — production projection still supplies zero locks; independent validation is tested with a seeded lock.",
    "NOT COVERED: constraints:min_gap_not_wired — governed validation retains the legacy 2-hour minimum; source fixture 10-hour policy needs its own change.",
)


def _minutes_to_hours(minutes: int) -> float:
    return minutes / 60.0


def _hours_to_minutes(hours: float) -> int:
    if not math.isfinite(hours):
        raise ValueError("solver hours must be finite")
    return int(round(hours * 60.0))


def _record_id(
    entities: tuple[ResolvedEntityV1, ...], group: str
) -> str:
    matches = [entity.record_id for entity in entities if entity.group == group]
    if len(matches) != 1:
        raise ValueError(f"constraint requires exactly one {group} entity")
    return matches[0]


def _constraint_args(constraint: DraftConstraintV1) -> dict:
    entities = constraint.resolved_entities
    if constraint.kind == "set_min_workers_per_task":
        return {"task_id": _record_id(entities, "work-areas-and-tasks"), "n": constraint.n}
    if constraint.kind == "scale_demand":
        return {"task_id": _record_id(entities, "work-areas-and-tasks"), "factor": constraint.factor}
    if constraint.kind == "lock_worker_shift":
        if constraint.start_minute is None:
            raise ValueError("lock_worker_shift requires start_minute")
        return {"member_id": _record_id(entities, "workers"), "day": constraint.start_minute // 1440}
    if constraint.kind == "exclude_worker_from_task":
        return {
            "member_id": _record_id(entities, "workers"),
            "task_id": _record_id(entities, "work-areas-and-tasks"),
        }
    if constraint.kind == "set_max_hours":
        return {"member_id": _record_id(entities, "workers"), "max_hours": constraint.max_hours}
    raise ValueError(f"unsupported governed constraint kind: {constraint.kind}")


def _constraints_to_overrides(
    constraints: Iterable[DraftConstraintV1],
) -> list[OverrideCall]:
    values = []
    for constraint in constraints:
        args = _constraint_args(constraint)
        values.append(
            OverrideCall(
                id=override_id(constraint.kind, args),
                tool=constraint.kind,
                args=args,
            )
        )
    return values


def _wire_employment_caps(problem, payload: dict) -> None:
    for row in payload.get("Shift Constraint", ()):
        if row.get("ConstraintType") != "Maximum Hours a Week":
            continue
        employment_type = str(row.get("ValueType") or "").strip()
        try:
            limit = float(row.get("Value"))
        except (TypeError, ValueError):
            continue
        if employment_type and limit > 0:
            problem.max_hours_per_week[employment_type] = limit


def _assignment(row, members_by_id) -> AssignmentV1:
    member = members_by_id[row.contact_id]
    rate = member.rate_for(row.task_id)
    qualification_refs = (
        ()
        if rate is None
        else (QualificationRefV1(task_id=row.task_id, rate=rate),)
    )
    start_minute = _hours_to_minutes(row.start_h)
    end_minute = _hours_to_minutes(row.end_h)
    record_id = "asg_" + contract_digest(
        {
            "worker_id": row.contact_id,
            "task_id": row.task_id,
            "shift_id": row.shift_id,
            "start_minute": start_minute,
            "end_minute": end_minute,
        }
    )[2][:24]
    return AssignmentV1(
        record_id=record_id,
        worker_id=row.contact_id,
        task_id=row.task_id,
        shift_id=row.shift_id,
        start_minute=start_minute,
        end_minute=end_minute,
        qualification_refs=qualification_refs,
        source="solver",
    )


_STATUS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


@dataclass
class _GovernedLexResult:
    status: str
    solver: cp_model.CpSolver
    round1_value: float
    round2_value: float
    wall_time_seconds: float
    snapshot: list[int] | None = None
    reason: str | None = None

    def value(self, variable) -> int:
        if self.snapshot is not None:
            return self.snapshot[variable.Index()]
        return self.solver.Value(variable)


def _solve_lexicographic_governed(
    builder: CpSatBuilder,
    *,
    wall_time_limit_seconds: float,
    max_deterministic_time: float | None,
    num_search_workers: int,
    seed: int,
) -> _GovernedLexResult:
    """Bound both lexicographic rounds by one wall and deterministic budget."""
    started = perf_counter()
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = num_search_workers
    solver.parameters.random_seed = seed

    def apply_remaining_budget(deterministic_used: float = 0.0) -> str | None:
        """Configure the solver's remaining budget for the next round.

        Returns None once a budget is applied, or which ceiling is already
        exhausted ("wall" or "deterministic") — AD-7 requires wall-time
        exhaustion (`solver_timed_out`) to stay distinguishable from any other
        ceiling exhausting first (`solver_failed`/`budget_exhausted`).
        """
        wall_remaining = wall_time_limit_seconds - (perf_counter() - started)
        if wall_remaining <= 0:
            return "wall"
        solver.parameters.max_time_in_seconds = wall_remaining
        if max_deterministic_time is not None:
            deterministic_remaining = max_deterministic_time - deterministic_used
            if deterministic_remaining <= 0:
                return "deterministic"
            solver.parameters.max_deterministic_time = deterministic_remaining
        else:
            solver.parameters.ClearField("max_deterministic_time")
        return None

    model = builder.m
    model.Minimize(builder.round1_unmet)
    exhausted = apply_remaining_budget()
    if exhausted is not None:
        return _GovernedLexResult(
            "UNKNOWN", solver, float("nan"), float("nan"), perf_counter() - started,
            reason="deterministic_budget_exhausted" if exhausted == "deterministic" else None,
        )
    first_status = solver.Solve(model)
    if first_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _GovernedLexResult(
            _STATUS.get(first_status, "UNKNOWN"), solver,
            float("nan"), float("nan"), perf_counter() - started,
        )
    round1_value = solver.ObjectiveValue()
    snapshot = list(solver.ResponseProto().solution)
    round1_cost = solver.Value(builder.round2_cost)
    deterministic_used = solver.ResponseProto().deterministic_time

    model.Add(builder.round1_unmet <= int(round(round1_value)))
    model.Minimize(builder.round2_cost)
    exhausted = apply_remaining_budget(deterministic_used)
    if exhausted is not None:
        return _GovernedLexResult(
            "UNKNOWN", solver, round1_value, float(round1_cost),
            perf_counter() - started, snapshot,
            reason="deterministic_budget_exhausted" if exhausted == "deterministic" else None,
        )
    second_status = solver.Solve(model)
    if second_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _GovernedLexResult(
            _STATUS.get(second_status, "UNKNOWN"), solver,
            round1_value, float(round1_cost), perf_counter() - started, snapshot,
        )
    return _GovernedLexResult(
        _STATUS.get(second_status, "UNKNOWN"), solver, round1_value,
        solver.ObjectiveValue(), perf_counter() - started,
    )


class GovernedSchedulerAdapter:
    def __init__(
        self,
        input_source: SolverInputSource,
        *,
        use_deterministic_time: bool = True,
    ):
        self._input_source = input_source
        self._use_deterministic_time = use_deterministic_time

    def solve(self, snapshot: RunSnapshotV1) -> SolverOutcomeV1:
        assert snapshot.scenario_version_id is not None
        assert snapshot.solver_config is not None
        payload = self._input_source.load(
            snapshot.scenario_version_id, snapshot.checksum_digest
        )
        problem = build_problem(payload)
        _wire_employment_caps(problem, payload)
        config = snapshot.solver_config
        if config.engine_name != "cpsat":
            raise ValueError(f"unsupported governed solver engine: {config.engine_name}")
        builder = CpSatBuilder(
            problem, overrides=_constraints_to_overrides(snapshot.constraints)
        ).build()
        result = _solve_lexicographic_governed(
            builder,
            wall_time_limit_seconds=config.wall_time_limit_seconds,
            max_deterministic_time=(
                config.max_deterministic_time if self._use_deterministic_time else None
            ),
            num_search_workers=config.num_search_workers,
            seed=config.seed,
        )
        members_by_id = {member.contact_id: member for member in problem.members}
        function_by_task = {task.task_id: task.function for task in problem.tasks}
        rows = []
        if not math.isnan(result.round1_value):
            from domain.result import ScheduleRow

            for task_variable in builder.task_vars:
                if result.value(task_variable.var) != 1:
                    continue
                shift = task_variable.shift
                rows.append(ScheduleRow(
                    contact_id=shift.member.contact_id,
                    member_name=shift.member.name,
                    task_id=task_variable.task_id,
                    function=function_by_task.get(task_variable.task_id, "Unknown"),
                    shift_id=shift.var.Name(),
                    start_h=task_variable.start_h,
                    end_h=task_variable.end_h,
                ))
        rows.sort(key=lambda row: (row.contact_id, row.start_h, row.task_id))
        assignments = tuple(_assignment(row, members_by_id) for row in rows)
        worker_facts = tuple(
            WorkerSchedulingFactV1(
                worker_id=member.contact_id,
                employment_type=member.emp_type,
                contracted_hours=member.contracted_hours,
                wage_per_hour=member.wage_per_hour,
                qualifications=tuple(
                    QualificationRefV1(task_id=q.task_id, rate=q.rate)
                    for q in member.qualifications
                ),
                availability_windows=tuple(
                    AvailabilityWindowV1(
                        kind=window.kind.value,
                        start_minute=_hours_to_minutes(window.start_h),
                        end_minute=_hours_to_minutes(window.end_h),
                    )
                    for window in member.windows
                ),
            )
            for member in problem.members
        )
        selected_shifts = tuple(
            SelectedShiftFactV1(
                shift_id=shift.var.Name(),
                worker_id=shift.member.contact_id,
                window_id=shift.window.id,
                window_kind=shift.window.kind.value,
                start_minute=_hours_to_minutes(shift.start_h),
                end_minute=_hours_to_minutes(shift.end_h),
                effective_minutes=_hours_to_minutes(shift.eff_h),
            )
            for shift in builder.shift_vars
            if not math.isnan(result.round1_value) and result.value(shift.var) == 1
        )
        employment_types = sorted({member.emp_type for member in problem.members})
        validation_facts = ValidationFactsV1(
            horizon_minutes=_hours_to_minutes(problem.horizon_h),
            workers=worker_facts,
            selected_shifts=selected_shifts,
            max_hours_per_week=tuple(
                (employment_type, problem.max_hours_per_week.get(
                    employment_type, C.DEFAULT_MAX_HOURS_PER_WEEK
                ))
                for employment_type in employment_types
            ),
            max_shifts_per_day=tuple(
                (employment_type, problem.max_shifts_per_day.get(
                    employment_type, C.DEFAULT_MAX_SHIFTS_PER_DAY
                ))
                for employment_type in employment_types
            ),
            minimum_gap_minutes=_hours_to_minutes(C.DEFAULT_MIN_GAP_HOURS),
            tasks=tuple(
                TaskV1(
                    record_id=task.task_id,
                    task_id=task.task_id,
                    name=task.name,
                    function=task.function,
                    area_id=task.area_id,
                    area_name=task.area_id,
                    unit_type_id=task.unit_id,
                )
                for task in problem.tasks
            ),
            demand_intervals=tuple(
                DemandIntervalV1(
                    record_id="dem_" + contract_digest({
                        "task_id": demand.task_id,
                        "family": demand.family.value,
                        "start": demand.start_h,
                        "end": demand.end_h,
                        "amount": demand.amount,
                        "order_id": demand.order_id,
                    })[2][:24],
                    family=demand.family.value,
                    task_id=demand.task_id,
                    area_id=None,
                    start_minute=_hours_to_minutes(demand.start_h),
                    end_minute=_hours_to_minutes(demand.end_h),
                    amount=demand.amount,
                    unit=("headcount" if demand.family.value == "indirect" else "volume"),
                )
                for demand in problem.demand
            ),
        )
        return SolverOutcomeV1(
            solver_status=result.status,
            assignments=assignments,
            round1_value=result.round1_value,
            round2_value=result.round2_value,
            wall_time_seconds=result.wall_time_seconds,
            validation_facts=validation_facts,
            reason=result.reason,
        )


__all__ = [
    "GovernedSchedulerAdapter",
    "SCOPE_CONTROLS",
    "_constraints_to_overrides",
    "_hours_to_minutes",
    "_minutes_to_hours",
    "_solve_lexicographic_governed",
    "_wire_employment_caps",
]
