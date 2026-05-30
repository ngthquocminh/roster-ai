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

    # ---- lock round 1, minimize cost ----
    m.Add(builder.round1_unmet <= int(round(r1)))
    m.Minimize(builder.round2_cost)
    s2 = solver.Solve(m)
    if s2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # round 1 solution still valid; report it with its cost
        return LexResult(_STATUS.get(s2, "UNKNOWN"), solver, r1, float("nan"))
    r2 = solver.ObjectiveValue()
    return LexResult(_STATUS.get(s2, "UNKNOWN"), solver, r1, r2)
