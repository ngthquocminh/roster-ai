"""Independent minute-based re-checks over solver assignments (AD-11).

No solver model or OR-Tools object is accepted here. Candidate creation calls
``require_hard_constraints`` and therefore cannot trust CP-SAT's own claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from application.contracts.schedule_version import ConstraintResultV1, ValidationFactsV1
from application.contracts.scenario_projection import AssignmentV1, LockV1


class HardConstraintViolation(ValueError):
    code = "hard_constraint_violated"


def _result(name: str, satisfied: bool, measured: float, limit: float, unit: str, ids=()) -> ConstraintResultV1:
    return ConstraintResultV1(
        constraint_id=f"hard:{name}", constraint_type=name,
        constraint_class="hard", satisfied=satisfied,
        measured_value=measured, limit=limit, unit=unit,
        contributing_assignment_ids=tuple(ids),
    )


def validate_hard_constraints(
    assignments: tuple[AssignmentV1, ...],
    facts: ValidationFactsV1,
    *,
    preserved_locks: tuple[LockV1, ...] = (),
) -> tuple[ConstraintResultV1, ...]:
    workers = {worker.worker_id: worker for worker in facts.workers}
    shifts = {shift.shift_id: shift for shift in facts.selected_shifts}
    by_shift: dict[str, list[AssignmentV1]] = defaultdict(list)
    by_worker: dict[str, list[AssignmentV1]] = defaultdict(list)
    for assignment in assignments:
        if assignment.shift_id is not None:
            by_shift[assignment.shift_id].append(assignment)
        by_worker[assignment.worker_id].append(assignment)

    outside = [a.record_id for a in assignments if (
        a.shift_id not in shifts
        or shifts[a.shift_id].worker_id != a.worker_id  # type: ignore[index]
        or a.start_minute < shifts[a.shift_id].start_minute  # type: ignore[index]
        or a.end_minute > shifts[a.shift_id].end_minute  # type: ignore[index]
    )]
    results = [_result("assignment_inside_selected_shift", not outside, len(outside), 0, "assignments", outside)]

    overlaps = []
    for values in by_worker.values():
        ordered = sorted(values, key=lambda value: (value.start_minute, value.end_minute))
        for left, right in zip(ordered, ordered[1:]):
            if right.start_minute < left.end_minute:
                overlaps.extend((left.record_id, right.record_id))
    results.append(_result("one_task_per_working_slot", not overlaps, len(set(overlaps)), 0, "assignments", overlaps))

    empty = [shift.shift_id for shift in facts.selected_shifts if not by_shift[shift.shift_id]]
    results.append(_result("selected_shift_nonempty", not empty, len(empty), 0, "shifts"))

    window_counts = Counter((shift.worker_id, shift.window_id) for shift in facts.selected_shifts)
    extra_windows = sum(max(0, count - 1) for count in window_counts.values())
    results.append(_result("one_shift_per_window", extra_windows == 0, extra_windows, 0, "shifts"))

    day_counts = Counter((shift.worker_id, shift.start_minute // 1440) for shift in facts.selected_shifts)
    shift_caps = dict(facts.max_shifts_per_day)
    day_excess = 0
    for (worker_id, _day), count in day_counts.items():
        worker = workers.get(worker_id)
        cap = 0 if worker is None else shift_caps.get(worker.employment_type, 0)
        day_excess += max(0, count - cap)
    results.append(_result("max_shifts_per_day", day_excess == 0, day_excess, 0, "shifts"))

    hour_caps = dict(facts.max_hours_per_week)
    excess_minutes = 0.0
    gap_violations = 0
    shifts_by_worker: dict[str, list] = defaultdict(list)
    for shift in facts.selected_shifts:
        shifts_by_worker[shift.worker_id].append(shift)
    for worker_id, values in shifts_by_worker.items():
        worker = workers.get(worker_id)
        cap_minutes = 0.0 if worker is None else hour_caps.get(worker.employment_type, 0.0) * 60
        excess_minutes += max(0.0, sum(value.effective_minutes for value in values) - cap_minutes)
        ordered = sorted(values, key=lambda value: value.start_minute)
        gap_violations += sum(
            1 for left, right in zip(ordered, ordered[1:])
            if right.start_minute - left.end_minute < facts.minimum_gap_minutes
        )
    combined = excess_minutes + gap_violations
    results.append(_result("weekly_hours_and_minimum_gap", combined == 0, combined, 0, "minutes_or_gaps"))

    unqualified = []
    for assignment in assignments:
        worker = workers.get(assignment.worker_id)
        qualified = set() if worker is None else {q.task_id for q in worker.qualifications}
        if assignment.task_id not in qualified:
            unqualified.append(assignment.record_id)
    results.append(_result("worker_qualification", not unqualified, len(unqualified), 0, "assignments", unqualified))

    if preserved_locks:
        missing = []
        assignment_keys = {(a.worker_id, a.shift_id) for a in assignments}
        for lock in preserved_locks:
            if lock.target_type == "worker_shift":
                worker_id, _, shift_id = lock.target_ref.partition(":")
                satisfied = (worker_id, shift_id) in assignment_keys
            else:
                satisfied = any(a.lock_ref == lock.record_id for a in assignments)
            if not satisfied:
                missing.append(lock.record_id)
        results.append(_result("preserved_lock", not missing, len(missing), 0, "locks", missing))
    return tuple(results)


def require_hard_constraints(
    assignments: tuple[AssignmentV1, ...],
    facts: ValidationFactsV1,
    *,
    preserved_locks: tuple[LockV1, ...] = (),
) -> tuple[ConstraintResultV1, ...]:
    results = validate_hard_constraints(assignments, facts, preserved_locks=preserved_locks)
    failed = [result.constraint_type for result in results if not result.satisfied]
    if failed:
        raise HardConstraintViolation("hard_constraint_violated: " + ", ".join(failed))
    return results


__all__ = ["HardConstraintViolation", "require_hard_constraints", "validate_hard_constraints"]
