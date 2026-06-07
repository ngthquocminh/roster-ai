"""SolveResult -> JSON-safe dict.

The lex solver can report NaN cost (when round 2 times out), and NaN is not
valid JSON, so coerce non-finite numbers to None here.
"""
from __future__ import annotations

import math
from dataclasses import asdict

from domain.result import SolveResult


def _num(x):
    if isinstance(x, (int, float)) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def serialize_result(r: SolveResult) -> dict:
    m = r.metrics
    return {
        "status": r.status,
        "metrics": {
            "total_cost": _num(m.total_cost),
            "total_unmet_hours": _num(m.total_unmet_hours),
            "scheduled_shifts": m.scheduled_shifts,
            "scheduled_members": m.scheduled_members,
            "coverage_by_function": {
                fn: {"required_h": _num(c.required_h),
                     "served_h": _num(c.served_h),
                     "pct": _num(c.pct)}
                for fn, c in m.coverage_by_function.items()
            },
            "coverage_by_day": {str(d): _num(p) for d, p in m.coverage_by_day.items()},
        },
        "stats": {
            "status": r.stats.status,
            "wall_time_s": _num(r.stats.wall_time_s),
            "unmet_objective_hours": _num(r.stats.unmet_objective_hours),
            "cost_objective": _num(r.stats.cost_objective),
        },
        "schedule": [asdict(row) for row in r.schedule],
    }
