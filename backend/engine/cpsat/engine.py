"""CpSatEngine — builds, solves (lexicographic), and extracts a SolveResult."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict

from config import constants as C
from domain.problem import SchedulingProblem
from domain.result import (
    CoverageStat,
    ScheduleRow,
    SolveResult,
    SolverStats,
    SummaryMetrics,
)
from engine.base import SolverConfig
from engine.cpsat.builder import CpSatBuilder
from engine.cpsat.objective import solve_lexicographic


class CpSatEngine:
    name = "cpsat"

    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult:
        builder = CpSatBuilder(problem).build()
        lex = solve_lexicographic(builder, config.time_limit_s, config.num_workers, config.seed)

        if lex.status in ("INFEASIBLE", "MODEL_INVALID", "UNKNOWN") and math.isnan(lex.round1_value):
            return SolveResult(
                status=lex.status, schedule=[],
                metrics=SummaryMetrics(),
                stats=SolverStats(lex.status, lex.solver.WallTime(), float("nan"), float("nan")),
            )

        solver = lex.solver
        func_of = {t.task_id: t.function for t in problem.tasks}

        # ---- schedule rows ----
        schedule = []
        used_shifts, used_members = set(), set()
        for tv in builder.task_vars:
            if solver.Value(tv.var) == 1:
                sv = tv.shift
                used_shifts.add(sv.var.Name())
                used_members.add(sv.member.contact_id)
                schedule.append(ScheduleRow(
                    contact_id=sv.member.contact_id,
                    member_name=sv.member.name,
                    task_id=tv.task_id,
                    function=func_of.get(tv.task_id, "Unknown"),
                    shift_id=sv.var.Name(),
                    start_h=tv.start_h,
                    end_h=tv.end_h,
                ))
        schedule.sort(key=lambda r: (r.contact_id, r.start_h))

        # ---- coverage metrics (required vs served labour-hours) ----
        req_func: Dict[str, float] = defaultdict(float)
        unmet_func: Dict[str, float] = defaultdict(float)
        req_day: Dict[int, float] = defaultdict(float)
        unmet_day: Dict[int, float] = defaultdict(float)

        for tid, per_hour in builder.vol_demand.items():
            if builder.is_ind.get(tid):
                continue
            ref = max(builder._ref_rate.get(tid, C.DEFAULT_TASK_RATE), 1e-9)
            fn = func_of.get(tid, "Unknown")
            for h, dvol in per_hour.items():
                hrs = dvol / ref
                req_func[fn] += hrs
                req_day[h // 24] += hrs
        for tid, per_hour in builder.hc_demand.items():
            fn = func_of.get(tid, "Indirect")
            for h, dhc in per_hour.items():
                req_func[fn] += dhc
                req_day[h // 24] += dhc

        for (tid, h), var in builder.unmet_vol.items():
            ref = max(builder._ref_rate.get(tid, C.DEFAULT_TASK_RATE), 1e-9)
            hrs = solver.Value(var) / C.VOL_SCALE / ref
            unmet_func[func_of.get(tid, "Unknown")] += hrs
            unmet_day[h // 24] += hrs
        for (tid, h), var in builder.unmet_hc.items():
            hrs = float(solver.Value(var))
            unmet_func[func_of.get(tid, "Indirect")] += hrs
            unmet_day[h // 24] += hrs

        coverage_by_function = {
            fn: CoverageStat(required_h=req, served_h=max(0.0, req - unmet_func.get(fn, 0.0)))
            for fn, req in sorted(req_func.items())
        }
        coverage_by_day = {
            day: (max(0.0, req - unmet_day.get(day, 0.0)) / req if req > 1e-9 else 1.0)
            for day, req in sorted(req_day.items())
        }
        total_unmet_hours = sum(unmet_func.values())
        total_cost = (lex.round2_value / C.COST_SCALE) if not math.isnan(lex.round2_value) else float("nan")

        metrics = SummaryMetrics(
            coverage_by_function=coverage_by_function,
            coverage_by_day=coverage_by_day,
            total_cost=total_cost,
            total_unmet_hours=total_unmet_hours,
            scheduled_shifts=len(used_shifts),
            scheduled_members=len(used_members),
        )
        stats = SolverStats(
            status=lex.status,
            wall_time_s=solver.WallTime(),
            unmet_objective_hours=(lex.round1_value / C.HOUR_SCALE) if not math.isnan(lex.round1_value) else float("nan"),
            cost_objective=total_cost,
        )
        return SolveResult(status=lex.status, schedule=schedule, metrics=metrics, stats=stats)
