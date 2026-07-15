"""Engine-level tests for the four new Phase-2 override tools.

Tests use the REAL CP-SAT engine (no stub) to validate that each new tool is
visibly honored against a no-override baseline, and that a solve with
overrides=[] is identical to the pre-override baseline (no regression).

Analog: backend/tests/test_engine_min_workers.py (same hand-built + real-engine idiom).
"""
from __future__ import annotations

from domain.overrides import OverrideCall, override_id
from domain.problem import SchedulingProblem
from domain.types import (
    DemandBand,
    DemandFamily,
    Member,
    Qualification,
    ShiftTemplate,
    Task,
    Window,
    WindowKind,
)
from engine.base import SolverConfig, create_engine


# ---------------------------------------------------------------------------
# Problem helpers
# ---------------------------------------------------------------------------

def _make_problem(n_members: int = 2, demand_volume: float = 10.0) -> SchedulingProblem:
    """Tiny problem: n members all Pick-qualified (rate 10/h), available 0..8h.

    Uses AVAILABILITY windows so the solver is free to assign fewer members
    when cost-optimal — enabling overrides to visibly change the outcome.
    With demand_volume=10.0 over 8h, 1 member (rate=10/h, absenteeism~=9.09/h)
    fully covers demand, so the baseline picks 1 member (cheapest).
    """
    task = Task("Pick", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    members = [
        Member(
            contact_id=f"M{i}",
            name=f"worker{i}",
            emp_type="Casual",
            grade_id="G",
            eba_id="E",
            contracted_hours=38.0,
            wage_per_hour=40.0,
            windows=[Window(id=f"av{i}", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
            qualifications=[Qualification("Pick", 10.0)],
        )
        for i in range(n_members)
    ]
    demand = [DemandBand("Pick", DemandFamily.OUTBOUND, 0.0, 8.0, demand_volume, "OB0")]
    return SchedulingProblem(
        horizon_h=8.0,
        members=members,
        tasks=[task],
        templates=[tpl],
        demand=demand,
    )


def _make_problem_max_hours() -> SchedulingProblem:
    """Two members: M0 cheaper (wage=35), M1 more expensive (wage=45).

    Both qualified for Pick; demand=10 units (1 member handles it).
    Baseline: M0 assigned (cheapest). With set_max_hours(M0, 4.0): M0's 8h
    shift incurs a huge penalty (100_000 * 4h * VOL_SCALE) -> M1 preferred.
    """
    task = Task("Pick", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    members = [
        Member(
            contact_id="M0", name="cheap", emp_type="Casual",
            grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=35.0,
            windows=[Window(id="av0", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
            qualifications=[Qualification("Pick", 10.0)],
        ),
        Member(
            contact_id="M1", name="costly", emp_type="Casual",
            grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=45.0,
            windows=[Window(id="av1", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
            qualifications=[Qualification("Pick", 10.0)],
        ),
    ]
    demand = [DemandBand("Pick", DemandFamily.OUTBOUND, 0.0, 8.0, 10.0, "OB0")]
    return SchedulingProblem(
        horizon_h=8.0,
        members=members,
        tasks=[task],
        templates=[tpl],
        demand=demand,
    )


def _bodies_per_hour(schedule, task_id: str, hour: int) -> int:
    """Count schedule rows for task_id whose span covers the given integer hour."""
    return sum(
        1 for r in schedule if r.task_id == task_id and r.start_h <= hour < r.end_h
    )


# ---------------------------------------------------------------------------
# No-regression: overrides=[] must be identical to baseline
# ---------------------------------------------------------------------------

def test_no_regression_empty_overrides():
    """overrides=[] must produce the same result as the default SolverConfig."""
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[]))

    assert result.status == baseline.status
    assert abs((result.metrics.total_cost or 0.0) - (baseline.metrics.total_cost or 0.0)) < 0.01
    baseline_rows = sorted((r.contact_id, r.task_id, r.start_h, r.end_h) for r in baseline.schedule)
    result_rows = sorted((r.contact_id, r.task_id, r.start_h, r.end_h) for r in result.schedule)
    assert result_rows == baseline_rows, "overrides=[] must not alter the schedule"


# ---------------------------------------------------------------------------
# scale_demand: factor > 1 increases assigned supply on the scaled task
# ---------------------------------------------------------------------------

def test_scale_demand_honored():
    """scale_demand(factor=8.0) increases assigned supply on Pick versus baseline.

    Demand=10 units over 8h -> ~1.25/h. 1 member at rate=10/h provides ~9.09/h
    -> baseline covers demand with 1 member.
    With factor=8.0: demand becomes ~10.0/h, 1 member provides 9.09/h (< 10.0),
    so 2 members needed for full round-1 coverage.
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    baseline_bodies = {r.contact_id for r in baseline.schedule if r.task_id == "Pick"}

    args = {"task_id": "Pick", "factor": 8.0}
    ov = OverrideCall(id=override_id("scale_demand", args), tool="scale_demand", args=args)
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))

    assert result.status in ("OPTIMAL", "FEASIBLE")
    result_bodies = {r.contact_id for r in result.schedule if r.task_id == "Pick"}
    assert len(result_bodies) > len(baseline_bodies), (
        f"scale_demand(factor=8.0) not honored: "
        f"baseline={len(baseline_bodies)} bodies, result={len(result_bodies)} bodies"
    )


# ---------------------------------------------------------------------------
# exclude_worker_from_task: excluded member has fewer (ideally 0) Pick slots
# ---------------------------------------------------------------------------

def test_exclude_worker_from_task_honored():
    """exclude_worker_from_task(M0, Pick) drives M0 off Pick while solve stays feasible.

    Both members equal wage. With exclude M0: M0's task vars incur large penalty
    (EXCLUDE_WORKER_PENALTY=50_000 per slot). Since demand is low and M1 covers it,
    the solver prefers M1 only, leaving M0 unassigned to Pick.
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    args = {"member_id": "M0", "task_id": "Pick"}
    ov = OverrideCall(
        id=override_id("exclude_worker_from_task", args),
        tool="exclude_worker_from_task",
        args=args,
    )
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))

    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"exclude_worker_from_task made solve infeasible: {result.status}"
    )
    # M0 should have zero Pick assignments (the penalty is large enough to
    # push the solver to M1 when M1 can cover demand alone)
    m0_pick = [r for r in result.schedule if r.contact_id == "M0" and r.task_id == "Pick"]
    assert len(m0_pick) == 0, (
        f"M0 still assigned to Pick after exclude override: {len(m0_pick)} rows"
    )


# ---------------------------------------------------------------------------
# set_max_hours: capped member scheduled less than uncapped baseline
# ---------------------------------------------------------------------------

def test_set_max_hours_honored():
    """set_max_hours(M0, 4.0) reduces M0's scheduled hours relative to baseline.

    M0 is cheaper (wage=35) so baseline assigns M0 to meet demand (1 member).
    With max_hours=4.0: M0's 8h shift incurs penalty=(MAX_HOURS_PENALTY / VOL_SCALE) * 4h
    = $4,000, which still dwarfs the ~$80 wage delta of switching to M1 (M1 wage $45/h vs
    M0 wage $35/h = $10/h * 8h shift) -> solver picks M1 instead.
    """
    problem = _make_problem_max_hours()
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    m0_baseline_h = sum(
        (r.end_h - r.start_h) for r in baseline.schedule if r.contact_id == "M0"
    )
    # Baseline should pick M0 (cheaper)
    assert m0_baseline_h > 0.0, (
        "Baseline should assign M0 (cheapest). Check _make_problem_max_hours."
    )

    args = {"member_id": "M0", "max_hours": 4.0}
    ov = OverrideCall(id=override_id("set_max_hours", args), tool="set_max_hours", args=args)
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))
    m0_override_h = sum(
        (r.end_h - r.start_h) for r in result.schedule if r.contact_id == "M0"
    )

    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"set_max_hours made solve infeasible: {result.status}"
    )
    assert m0_override_h < m0_baseline_h, (
        f"set_max_hours not honored: M0 has {m0_override_h}h in override vs "
        f"{m0_baseline_h}h in baseline (expected strictly fewer hours)"
    )


# ---------------------------------------------------------------------------
# lock_worker_shift: feasibility guaranteed even with no shift candidates
# ---------------------------------------------------------------------------

def test_lock_worker_shift_stays_feasible():
    """lock_worker_shift(M0, day=0) must not make the solve infeasible.

    The absent BoolVar (bounded 0..1) absorbs the penalty when M0 has candidates
    on day 0, keeping the model feasible (Pitfall 2 / T-02-07).
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    args = {"member_id": "M0", "day": 0}
    ov = OverrideCall(
        id=override_id("lock_worker_shift", args), tool="lock_worker_shift", args=args
    )
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))

    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"lock_worker_shift made solve infeasible: {result.status}"
    )
