"""Hand-built instances with a known optimum — validates the core engine logic."""
from __future__ import annotations

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


def _make_problem(demand_volume: float) -> SchedulingProblem:
    """2 members, both Pick-qualified at rate 10/h, each rostered 0..8h.
    One 8h template (no breaks). One outbound Pick demand band over 0..8h.
    """
    task = Task("T1", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    members = [
        Member(
            contact_id=f"M{i}", name=f"m{i}", emp_type="Full Time",
            grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=40.0,
            windows=[Window(id=f"r{i}", start_h=0.0, end_h=8.0, kind=WindowKind.ROSTER)],
            qualifications=[Qualification("T1", 10.0)],
        )
        for i in range(2)
    ]
    demand = [DemandBand("T1", DemandFamily.OUTBOUND, 0.0, 8.0, demand_volume, "OB0")]
    return SchedulingProblem(horizon_h=8.0, members=members, tasks=[task],
                             templates=[tpl], demand=demand)


def test_full_coverage_reaches_zero_unmet():
    # 80 units over 8h = 10/h; 2 members x ~9.09 units/h > 10 => fully coverable.
    res = create_engine("cpsat").solve(_make_problem(80.0), SolverConfig(time_limit_s=10))
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert res.metrics.total_unmet_hours <= 0.5
    assert res.metrics.scheduled_members == 2          # both rosters filled
    assert res.metrics.total_cost > 0


def test_undersupply_leaves_unmet():
    # 4000 units over 8h vastly exceeds 2 members' capacity => unmet must be > 0.
    res = create_engine("cpsat").solve(_make_problem(4000.0), SolverConfig(time_limit_s=10))
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert res.metrics.total_unmet_hours > 0
