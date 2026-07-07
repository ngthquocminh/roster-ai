"""Calibration sweep harness for the four *_PENALTY constants (ENG-04, D-08).

Not a test -- a derivation script. Loads the committed full-week fixture,
solves a wage-only baseline, then re-solves with a satisfiable
`set_min_workers_per_task` override at a range of MIN_WORKERS_PENALTY scales,
printing the resulting total_cost delta and solver status per scale so the
values landed in config/constants.py (Task 3) can be justified against real
wage-cost magnitudes rather than picked in isolation (Pitfall 4).

    cd backend && uv run python scripts/calibrate_penalties.py
"""
from __future__ import annotations

import os
import sys

# Make the backend package root importable regardless of invocation cwd,
# mirroring conftest.py's bootstrap (this script lives in backend/scripts/,
# one level below run.py, so Python's implicit script-dir sys.path entry
# points at scripts/, not backend/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.overrides import OverrideCall, override_id  # noqa: E402
from engine.base import SolverConfig, create_engine  # noqa: E402
from ingest.input_adapter import load_problem  # noqa: E402

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(_BACKEND_DIR, "..", "data", "sample_tiny_input.json")

# Candidate scales to sweep for MIN_WORKERS_PENALTY (existing placeholder: 100_000).
SCALES = (10_000, 50_000, 100_000, 250_000, 500_000)


def run_case(problem, overrides, penalty_overrides: dict[str, int]):
    """Solve `problem` with `overrides` under temporarily-patched penalty constants.

    Saves and restores every constant named in `penalty_overrides` so this
    script never leaves config.constants mutated as a side effect (T-04-07).
    """
    import config.constants as C

    saved = {k: getattr(C, k) for k in penalty_overrides}
    for k, v in penalty_overrides.items():
        setattr(C, k, v)
    try:
        engine = create_engine("cpsat")
        return engine.solve(problem, SolverConfig(time_limit_s=60, overrides=overrides))
    finally:
        for k, v in saved.items():
            setattr(C, k, v)


def _pick_demanded_task_id(problem) -> str:
    """Resolve a real demanded task id from the loaded problem (no hardcoded placeholder)."""
    demanded_ids = {d.task_id for d in problem.demand}
    for t in problem.tasks:
        if t.task_id in demanded_ids:
            return t.task_id
    raise RuntimeError("No demanded task found in fixture; cannot calibrate.")


if __name__ == "__main__":
    problem = load_problem(FIXTURE)
    print(
        f"Loaded fixture: members={len(problem.members)} tasks={len(problem.tasks)} "
        f"demand_bands={len(problem.demand)} horizon={problem.horizon_h:.0f}h"
    )

    baseline = run_case(problem, [], {})
    baseline_cost = baseline.metrics.total_cost or 0.0
    print(f"baseline total_cost: {baseline_cost:,.2f}  status={baseline.status}")

    task_id = _pick_demanded_task_id(problem)
    print(f"sweeping MIN_WORKERS_PENALTY with set_min_workers_per_task(task_id={task_id!r}, n=3)\n")

    print(f"{'scale':>10}  {'total_cost_delta':>18}  {'status':<10}")
    for scale in SCALES:
        args = {"task_id": task_id, "n": 3}
        ov = OverrideCall(
            id=override_id("set_min_workers_per_task", args),
            tool="set_min_workers_per_task",
            args=args,
        )
        result = run_case(problem, [ov], {"MIN_WORKERS_PENALTY": scale})
        delta = (result.metrics.total_cost or 0.0) - baseline_cost
        print(f"{scale:>10}  {delta:>18,.2f}  {result.status:<10}")

    # Post-run invariant: config.constants must be unchanged (save/restore worked).
    import config.constants as C

    print(f"\npost-run MIN_WORKERS_PENALTY (must be unchanged): {C.MIN_WORKERS_PENALTY}")
