"""Lexicographic objective via solve-and-lock (CP-SAT has no native lex).

Round 1: minimize total unmet labour-hours (+ roster-unfill nudge).
Lock round 1 at its optimum, then
Round 2: minimize cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from engine.cpsat.builder import CpSatBuilder


@dataclass
class LexResult:
    status: str
    solver: cp_model.CpSolver
    round1_value: float    # scaled unmet-hours
    round2_value: float    # scaled cost
    # Round-1 solution vector, set only when round 2 found NO solution in time.
    # Re-solving for cost overwrites the solver's solution, so we snapshot the
    # unmet-optimal one and read from it instead of the (empty) solver.
    snapshot: list[int] | None = None

    def value(self, var) -> int:
        """Variable value from the round-2 solution, or the round-1 snapshot."""
        if self.snapshot is not None:
            return self.snapshot[var.Index()]
        return self.solver.Value(var)


_STATUS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


def solve_lexicographic(builder: CpSatBuilder, time_limit_s: float,
                        num_workers: int, seed: int = 42) -> LexResult:
    m = builder.m
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = int(num_workers)
    solver.parameters.random_seed = int(seed)

    # ---- round 1: unmet ----
    m.Minimize(builder.round1_unmet)
    s1 = solver.Solve(m)
    if s1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return LexResult(_STATUS.get(s1, "UNKNOWN"), solver, float("nan"), float("nan"))
    r1 = solver.ObjectiveValue()
    # Snapshot the unmet-optimal solution + its cost before round 2 overwrites it.
    snap = list(solver.ResponseProto().solution)
    cost1 = solver.Value(builder.round2_cost)

    # ---- lock round 1, minimize cost ----
    m.Add(builder.round1_unmet <= int(round(r1)))
    m.Minimize(builder.round2_cost)
    s2 = solver.Solve(m)
    if s2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Round 2 found no solution in time: fall back to the round-1 solution
        # (unmet-optimal, cost not yet minimized) via the snapshot.
        return LexResult(_STATUS.get(s2, "UNKNOWN"), solver, r1, float(cost1), snapshot=snap)
    r2 = solver.ObjectiveValue()
    return LexResult(_STATUS.get(s2, "UNKNOWN"), solver, r1, r2)
