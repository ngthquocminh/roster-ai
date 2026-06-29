"""Degeneracy detection tests (ENG-05).

Validates that SolveResult carries a warnings field and that the detection
logic in CpSatEngine correctly flags task families with real demand but zero
assigned supply, without altering solver_status.

Approach: unit-test the detection condition directly over CoverageStat
instances — no live CP-SAT solve needed, so tests stay fast and portable.
"""
from __future__ import annotations

from domain.result import CoverageStat, SolveResult, SummaryMetrics, SolverStats


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_result(**kwargs) -> SolveResult:
    """Build a minimal SolveResult for field presence checks."""
    return SolveResult(
        status="OPTIMAL",
        schedule=[],
        metrics=SummaryMetrics(),
        stats=SolverStats(
            status="OPTIMAL",
            wall_time_s=0.1,
            unmet_objective_hours=0.0,
            cost_objective=0.0,
        ),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test 1: warnings field presence (RED for Task 1)
# ---------------------------------------------------------------------------

def test_warnings_field_present_on_solve_result():
    """SolveResult without explicit warnings defaults to empty list."""
    r = _make_result()
    assert hasattr(r, "warnings"), "SolveResult must have a warnings attribute"
    assert r.warnings == [], f"Expected [], got {r.warnings!r}"
