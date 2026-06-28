"""Engine-level tests for the set_min_workers_per_task override.

Tests use the REAL CP-SAT engine (no stub) to validate that:
- An override places >= N distinct bodies on the task at each demanded hour
  and strictly more than the no-override baseline (ENG-03, visibly honored).
- A problem solved with overrides=[] is identical to the pre-override baseline
  (ENG-06, no regression).
- An override on a task with no qualified supply still solves feasibly — the
  shortfall degrades to a bounded constant penalty, never infeasible (T-01-E1).

Analog: backend/tests/test_engine_small.py (same hand-built + real-engine idiom).
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
# Helpers
# ---------------------------------------------------------------------------

def _bodies_per_hour(schedule, task_id: str, hour: int) -> int:
    """Count schedule rows for task_id whose span covers the given integer hour."""
    return sum(
        1
        for r in schedule
        if r.task_id == task_id and r.start_h <= hour < r.end_h
    )


def _make_problem(n_members: int = 2, demand_volume: float = 10.0) -> SchedulingProblem:
    """Tiny problem: n members all Pick-qualified (rate 10/h), available 0..8h.

    Uses AVAILABILITY windows (not ROSTER) so the solver is free to assign
    fewer members when cost-optimal — enabling the override to visibly increase
    the body count.  Low demand volume (10 units over 8h) is fully satisfied by
    a single 10/h worker, so the no-override solve chooses exactly 1 member.
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


def _make_problem_no_supply() -> SchedulingProblem:
    """Problem where task 'Pick' has demand but NO qualified members.

    Used to verify a no-supply override stays feasible (safety guarantee).
    Members are qualified for a different task 'Pack'; Pick demand is unmet.
    """
    task_pick = Task("Pick", "Pick", "Pick", "A1")
    task_pack = Task("Pack", "Pack", "Pack", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    members = [
        Member(
            contact_id="M0",
            name="packer",
            emp_type="Casual",
            grade_id="G",
            eba_id="E",
            contracted_hours=38.0,
            wage_per_hour=40.0,
            windows=[Window(id="av0", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
            qualifications=[Qualification("Pack", 10.0)],
        )
    ]
    demand = [
        DemandBand("Pick", DemandFamily.OUTBOUND, 0.0, 8.0, 10.0, "OB0"),
        DemandBand("Pack", DemandFamily.OUTBOUND, 0.0, 8.0, 10.0, "OB1"),
    ]
    return SchedulingProblem(
        horizon_h=8.0,
        members=members,
        tasks=[task_pick, task_pack],
        templates=[tpl],
        demand=demand,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_min_workers_override_honored():
    """Override n=2 forces >= 2 distinct bodies on Pick at every demanded hour.

    The no-override cost-optimal solve uses exactly 1 worker (demand is low);
    the override strictly increases the body count to 2.
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")
    cfg = SolverConfig(time_limit_s=10)

    # Baseline: no override -> cost-optimal assigns 1 member to Pick
    baseline = engine.solve(problem, cfg)
    assert baseline.status in ("OPTIMAL", "FEASIBLE")
    baseline_bodies = {r.contact_id for r in baseline.schedule if r.task_id == "Pick"}
    assert len(baseline_bodies) == 1, (
        f"Expected baseline to use exactly 1 worker, got {len(baseline_bodies)}"
    )

    # With override n=2: shortfall penalty dominates -> 2 members assigned
    args = {"task_id": "Pick", "n": 2}
    ov = OverrideCall(
        id=override_id("set_min_workers_per_task", args),
        tool="set_min_workers_per_task",
        args=args,
    )
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    override_bodies = {r.contact_id for r in result.schedule if r.task_id == "Pick"}
    assert len(override_bodies) >= 2, (
        f"Override n=2 not honored: only {len(override_bodies)} worker(s) on Pick"
    )
    assert len(override_bodies) > len(baseline_bodies), (
        "Override must strictly increase body count over baseline"
    )

    # Per-hour check: >= 2 bodies at each demanded hour (0..7)
    for h in range(8):
        count = _bodies_per_hour(result.schedule, "Pick", h)
        assert count >= 2, f"Only {count} body/bodies on Pick at hour {h}, expected >= 2"


def test_no_regression_empty_overrides():
    """overrides=[] must produce the same result as the default SolverConfig.

    Byte-identical check: status, total_cost, schedule membership (ENG-06).
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[]))

    assert result.status == baseline.status
    assert abs((result.metrics.total_cost or 0.0) - (baseline.metrics.total_cost or 0.0)) < 0.01
    # Same schedule rows (order-independent)
    baseline_rows = sorted((r.contact_id, r.task_id, r.start_h, r.end_h) for r in baseline.schedule)
    result_rows = sorted((r.contact_id, r.task_id, r.start_h, r.end_h) for r in result.schedule)
    assert result_rows == baseline_rows, "overrides=[] must not alter the schedule"


def test_no_supply_override_stays_feasible():
    """Override on a task with no qualified supply must not make the solve infeasible.

    The shortfall slack is bounded (0..n) so it degrades to a constant penalty
    rather than causing infeasibility (safety guarantee T-01-E1, D-03).
    """
    problem = _make_problem_no_supply()
    args = {"task_id": "Pick", "n": 2}
    ov = OverrideCall(
        id=override_id("set_min_workers_per_task", args),
        tool="set_min_workers_per_task",
        args=args,
    )
    result = create_engine("cpsat").solve(
        problem, SolverConfig(time_limit_s=10, overrides=[ov])
    )
    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"No-supply override made solve infeasible: status={result.status}"
    )
