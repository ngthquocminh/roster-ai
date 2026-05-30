"""CLI: load a weekly fixture -> solve -> print metrics + a schedule sample.

    python run.py ../data/sample_tiny_input.json
"""
from __future__ import annotations

import sys
import time

from engine.base import SolverConfig, create_engine
from ingest.input_adapter import load_problem


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "../data/sample_tiny_input.json"
    engine_name = argv[2] if len(argv) > 2 else "cpsat"
    time_limit_s = float(argv[3]) if len(argv) > 3 else 60.0

    print(f"Loading {path} ...")
    problem = load_problem(path)
    print(f"  members={len(problem.members)} tasks={len(problem.tasks)} "
          f"templates={len(problem.templates)} demand_bands={len(problem.demand)} "
          f"horizon={problem.horizon_h:.0f}h")

    engine = create_engine(engine_name)
    t = time.time()
    result = engine.solve(problem, SolverConfig(time_limit_s=time_limit_s))
    print(f"\nSolved with '{engine.name}' in {time.time() - t:.1f}s  -> status={result.status}")

    m = result.metrics
    print(f"\nObjective:  unmet={m.total_unmet_hours:.1f} labour-hours   "
          f"cost=${m.total_cost:,.0f}")
    print(f"Scheduled:  {m.scheduled_shifts} shifts, {m.scheduled_members} members, "
          f"{len(result.schedule)} task assignments")

    print("\nCoverage by function:")
    for fn, cov in m.coverage_by_function.items():
        bar = "#" * int(cov.pct * 20)
        print(f"  {fn:<12} {cov.served_h:7.1f}/{cov.required_h:7.1f} h  "
              f"{cov.pct*100:5.1f}%  {bar}")

    print("\nCoverage by day:")
    for day, pct in m.coverage_by_day.items():
        print(f"  day {day}: {pct*100:5.1f}%")

    print("\nSchedule sample (first 12 rows):")
    for r in result.schedule[:12]:
        print(f"  {r.member_name[:20]:<20} {r.function:<10} "
              f"{r.start_h:5.1f}-{r.end_h:5.1f}  shift={r.shift_id[-12:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
