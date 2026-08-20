from __future__ import annotations

from dataclasses import replace

import pytest

from application.contracts.schedule_version import (
    SelectedShiftFactV1,
    ValidationFactsV1,
    WorkerSchedulingFactV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    DemandIntervalV1,
    LockV1,
    QualificationRefV1,
    TaskV1,
)
from application.scheduling.candidate_metrics import calculate_candidate_metrics
from application.scheduling.hard_constraints import (
    HardConstraintViolation,
    require_hard_constraints,
    validate_hard_constraints,
)


def _facts() -> ValidationFactsV1:
    return ValidationFactsV1(
        horizon_minutes=2880,
        workers=(WorkerSchedulingFactV1(
            worker_id="w1", employment_type="Full Time", contracted_hours=40,
            wage_per_hour=20,
            qualifications=(QualificationRefV1("t1", 10),),
            availability_windows=(
                AvailabilityWindowV1("roster", 0, 480),
                AvailabilityWindowV1("availability", 1440, 1920),
            ),
        ),),
        selected_shifts=(
            SelectedShiftFactV1("s1", "w1", "window-1", "roster", 0, 480, 480),
            SelectedShiftFactV1("s2", "w1", "window-2", "availability", 1440, 1920, 480),
        ),
        max_hours_per_week=(("Full Time", 56.0),),
        max_shifts_per_day=(("Full Time", 2),),
        minimum_gap_minutes=120,
    )


def _assignments() -> tuple[AssignmentV1, ...]:
    q = (QualificationRefV1("t1", 10),)
    return (
        AssignmentV1("a1", "w1", "t1", "s1", 0, 480, q, "solver"),
        AssignmentV1("a2", "w1", "t1", "s2", 1440, 1920, q, "solver"),
    )


def test_all_seven_independent_hard_checks_pass_on_valid_assignments() -> None:
    results = validate_hard_constraints(_assignments(), _facts())
    assert len(results) == 7
    assert all(result.satisfied for result in results)


@pytest.mark.parametrize(
    ("expected", "mutate"),
    (
        ("assignment_inside_selected_shift", lambda a, f: ((replace(a[0], end_minute=500), a[1]), f)),
        ("one_task_per_working_slot", lambda a, f: (a + (replace(a[0], record_id="overlap", start_minute=60),), f)),
        ("selected_shift_nonempty", lambda a, f: ((a[0],), f)),
        ("one_shift_per_window", lambda a, f: (
            a + (AssignmentV1("a3", "w1", "t1", "s3", 700, 760, (QualificationRefV1("t1", 10),), "solver"),),
            replace(f, selected_shifts=f.selected_shifts + (SelectedShiftFactV1("s3", "w1", "window-1", "roster", 700, 760, 60),)),
        )),
        ("max_shifts_per_day", lambda a, f: (a, replace(f, max_shifts_per_day=(("Full Time", 0),)))),
        ("weekly_hours_and_minimum_gap", lambda a, f: (a, replace(f, max_hours_per_week=(("Full Time", 8.0),)))),
        ("worker_qualification", lambda a, f: ((replace(a[0], task_id="t2"), a[1]), f)),
    ),
)
def test_each_corruption_observes_its_own_guard_failing(expected, mutate) -> None:
    assignments, facts = mutate(_assignments(), _facts())
    failed = {result.constraint_type for result in validate_hard_constraints(assignments, facts) if not result.satisfied}
    assert failed == {expected}
    with pytest.raises(HardConstraintViolation):
        require_hard_constraints(assignments, facts)


def test_preserved_lock_is_proved_against_seeded_nonempty_supply() -> None:
    lock = LockV1("lock-1", "worker_shift", "w1:s1", "exact", "seeded-test")
    assert all(validate_hard_constraints(_assignments(), _facts(), preserved_locks=(lock,))[-1].satisfied for _ in range(1))
    with pytest.raises(HardConstraintViolation, match="preserved_lock"):
        require_hard_constraints(_assignments()[1:], _facts(), preserved_locks=(lock,))


def test_candidate_metrics_recompute_volume_minutes_cost_and_overtime() -> None:
    facts = replace(
        _facts(),
        workers=(replace(_facts().workers[0], contracted_hours=0.5),),
        selected_shifts=(_facts().selected_shifts[0],),
    )
    assignment = replace(_assignments()[0], end_minute=60)
    task = TaskV1("t1", "t1", "Pick", "Picking", "a1", "Area", None)
    demand = DemandIntervalV1("d1", "outbound", "t1", "a1", 0, 60, 10, "volume")

    metrics, soft = calculate_candidate_metrics(
        (assignment,), (task,), (demand,), facts, constraints=()
    )

    assert metrics.interval_coverage_required_minutes == (("d1", 60.0),)
    assert metrics.interval_coverage_served_minutes == (("d1", 60.0),)
    assert metrics.function_coverage_required_minutes == (("Picking", 60.0),)
    assert metrics.overtime_minutes == 30.0
    assert metrics.total_cost == 20.0
    assert metrics.assignment_count == 1
    assert metrics.member_count == 1
    assert soft == ()
