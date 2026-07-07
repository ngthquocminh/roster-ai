"""Real-engine regression tests locking ENG-04 penalty calibration + folded WR-05.

These are small, hand-built, deterministic-real-engine regressions that lock
the *behavior* of the calibrated constants in config/constants.py in place —
they mirror the existing passing idiom in test_engine_overrides.py (tiny
problems, real CpSatEngine, short bounded time_limit_s) rather than the
committed full-week fixture.

Why not the full-week fixture (data/sample_tiny_input.json): it was tried
first and found unsuitable for the default (non-live) suite. CP-SAT's
parallel portfolio search is not wall-clock-deterministic even with a fixed
seed, so a round-2 (cost) solve on that fixture (11 members, 6 tasks, 168h
horizon, 1547 demand bands) sometimes lands on a non-convergent UNKNOWN status
within any bounded wall-clock limit, making an assertion on the resulting
status/cost inherently flaky — and a limit generous enough to avoid that
flakiness (empirically ~300s) makes the whole file take ~15 minutes, violating
the phase's fast, stub-only default-CI principle. Small hand-built problems
(same idiom as test_engine_overrides.py) reach OPTIMAL/FEASIBLE deterministically
in seconds, so this file uses those instead for anything that runs in the
default (`not live`) suite.

The *empirical magnitude* calibration of the four `*_PENALTY` constants against
real wage-cost scale is still done by `backend/scripts/calibrate_penalties.py`,
which targets the full-week fixture intentionally — it is a run-on-demand
derivation script (`python scripts/calibrate_penalties.py`), not a CI test, and
is left unchanged by this fix.
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

    Same idiom as test_engine_overrides._make_problem: AVAILABILITY windows so
    the solver is free to assign fewer members when cost-optimal, letting
    overrides visibly change the outcome. With demand_volume=10.0 over 8h,
    1 member (rate=10/h, absenteeism~=9.09/h) fully covers demand, so the
    baseline picks 1 member (cheapest).
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


def _make_single_member_problem(demand_volume: float = 10.0) -> SchedulingProblem:
    """One member qualified for Pick — no idle qualified replacement exists.

    Hand-built analog of the full-week fixture's "exclude a worker with no
    idle qualified replacement" scenario: since M0 is the *only* qualified
    member, round 1's minimal-unmet-hours lock requires M0 to stay assigned to
    Pick regardless of any round-2-only override, so excluding M0 can only be
    "respected" via the bounded round-2 penalty (Pitfall 4), never by
    reassignment — exactly the degrade-gracefully scenario this test locks in.
    """
    task = Task("Pick", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    member = Member(
        contact_id="M0", name="only", emp_type="Casual",
        grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=40.0,
        windows=[Window(id="av0", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
        qualifications=[Qualification("Pick", 10.0)],
    )
    demand = [DemandBand("Pick", DemandFamily.OUTBOUND, 0.0, 8.0, demand_volume, "OB0")]
    return SchedulingProblem(
        horizon_h=8.0,
        members=[member],
        tasks=[task],
        templates=[tpl],
        demand=demand,
    )


def _make_starved_problem() -> SchedulingProblem:
    """A demanded task (Pick) with zero qualified members (WR-05 degeneracy).

    M0 exists but carries no qualification for Pick, so served_h stays 0 for
    that function in round 1 AND round 2 regardless of solve time —
    structurally impossible to serve, exactly the folded-WR-05 scenario.
    """
    task = Task("Pick", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    member = Member(
        contact_id="M0", name="unqualified", emp_type="Casual",
        grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=40.0,
        windows=[Window(id="av0", start_h=0.0, end_h=8.0, kind=WindowKind.AVAILABILITY)],
        qualifications=[],  # not qualified for Pick -- zero supply
    )
    demand = [DemandBand("Pick", DemandFamily.OUTBOUND, 0.0, 8.0, 10.0, "OB0")]
    return SchedulingProblem(
        horizon_h=8.0,
        members=[member],
        tasks=[task],
        templates=[tpl],
        demand=demand,
    )


# ---------------------------------------------------------------------------
# 1. Satisfiable override honored (ENG-04)
# ---------------------------------------------------------------------------

def test_satisfiable_override_honored():
    """scale_demand(factor=8.0) pulls in a second body vs the wage-only baseline.

    Same idiom (and same demand/factor combination) as the already-passing
    test_engine_overrides.test_scale_demand_honored -- small, hand-built,
    deterministic, no full-week fixture.
    """
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    assert baseline.status in ("OPTIMAL", "FEASIBLE"), (
        f"Baseline solve did not converge to a usable solution: {baseline.status}"
    )
    baseline_bodies = {r.contact_id for r in baseline.schedule if r.task_id == "Pick"}

    args = {"task_id": "Pick", "factor": 8.0}
    ov = OverrideCall(id=override_id("scale_demand", args), tool="scale_demand", args=args)
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))

    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"scale_demand made solve infeasible/non-convergent: {result.status}"
    )
    result_bodies = {r.contact_id for r in result.schedule if r.task_id == "Pick"}
    assert len(result_bodies) > len(baseline_bodies), (
        f"scale_demand(factor=8.0) not honored: baseline={len(baseline_bodies)} bodies, "
        f"result={len(result_bodies)} bodies on task Pick"
    )


# ---------------------------------------------------------------------------
# 2. Unsatisfiable override degrades gracefully (ENG-04 / Pitfall 4)
# ---------------------------------------------------------------------------

def test_unsatisfiable_override_degrades_gracefully():
    """Excluding the sole qualified member (no idle replacement) keeps the
    solve OPTIMAL/FEASIBLE and bounds the round-2 cost increase to a small
    multiple of baseline (respected via the bounded penalty, never dominating).
    """
    problem = _make_single_member_problem(demand_volume=10.0)
    engine = create_engine("cpsat")

    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    assert baseline.status in ("OPTIMAL", "FEASIBLE"), (
        f"Baseline solve did not converge to a usable solution: {baseline.status}"
    )
    baseline_cost = baseline.metrics.total_cost or 0.0

    args = {"member_id": "M0", "task_id": "Pick"}
    ov = OverrideCall(
        id=override_id("exclude_worker_from_task", args),
        tool="exclude_worker_from_task",
        args=args,
    )
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[ov]))

    assert result.status in ("OPTIMAL", "FEASIBLE"), (
        f"exclude_worker_from_task made solve infeasible/non-convergent: {result.status}"
    )
    result_cost = result.metrics.total_cost or 0.0
    delta = result_cost - baseline_cost
    assert delta >= 0.0, "Excluding the sole qualified worker should never reduce total cost"
    # Bounded, not dominating: the penalty must never inflate round-2 cost by
    # more than a small multiple of the baseline (Pitfall 4). Conservative
    # bound so it holds regardless of the exact calibrated constant.
    bound = max(baseline_cost, 1.0) * 2.0
    assert delta <= bound, (
        f"exclude_worker_from_task cost delta ({delta:,.2f}) exceeds the bounded-degrade "
        f"threshold ({bound:,.2f}) -- penalty may be dominating round-2 cost (Pitfall 4)"
    )
    # M0 has no idle qualified replacement, so round 1's minimal-unmet lock
    # keeps M0 assigned to Pick despite the exclusion -- the override can only
    # be "respected" via the bounded round-2 penalty above, not reassignment.
    m0_pick = [r for r in result.schedule if r.contact_id == "M0" and r.task_id == "Pick"]
    assert len(m0_pick) > 0, (
        "Expected M0 to remain assigned to Pick (no qualified replacement exists); "
        "if this fails, the fixture no longer models the bounded-degrade scenario"
    )


# ---------------------------------------------------------------------------
# 3. Real-engine degeneracy detection (folded WR-05 / ENG-05)
# ---------------------------------------------------------------------------

def test_real_engine_degeneracy_detected():
    """CpSatEngine.solve() itself (not the mirrored detection loop in
    test_engine_degenerate.py) flags a demanded task family that is
    structurally impossible to serve -- small hand-built problem, deterministic
    short solve (no full-week fixture needed: the zero-supply condition doesn't
    depend on cost-round convergence).
    """
    problem = _make_starved_problem()
    engine = create_engine("cpsat")

    result = engine.solve(problem, SolverConfig(time_limit_s=10))

    assert isinstance(result.warnings, list)
    assert len(result.warnings) > 0, (
        "Expected a non-empty warnings list for a task with zero qualified supply"
    )
    assert any("Pick" in w for w in result.warnings), (
        f"Expected a warning naming function 'Pick'; got: {result.warnings}"
    )
