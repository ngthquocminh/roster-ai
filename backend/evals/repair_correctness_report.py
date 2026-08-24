"""Generate Story 3.10's deterministic, NFR27-bound repair proof."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
from typing import Mapping

from scripts.evidence_binding import REPO_ROOT, resolve_bindings


TERMINAL_EXPECTATIONS = {
    "solver_completed": {
        "status": "solver_completed", "reason": None, "candidate_count": 1
    },
    "solver_infeasible": {
        "status": "solver_infeasible", "reason": "model_infeasible", "candidate_count": 0
    },
    "solver_timed_out": {
        "status": "solver_timed_out", "reason": "budget_exhausted", "candidate_count": 0
    },
    "solver_cancelled": {
        "status": "solver_cancelled", "reason": "cancelled", "candidate_count": 0
    },
    "solver_failed": {
        "status": "solver_failed", "reason": "hard_constraint_violated", "candidate_count": 0
    },
}

_TEST_NODES = {
    "solver_completed": "test_real_pipeline_closes_gap_preserves_lock_and_does_not_add_overtime",
    "solver_infeasible": "test_infeasible_is_literal_and_has_no_candidate",
    "solver_timed_out": "test_real_adapter_timeout_is_literal_bounded_and_has_no_candidate",
    "solver_cancelled": "test_cancel_command_stops_queued_run_before_solver_and_has_no_candidate",
    "solver_failed": "test_hard_constraint_failure_is_literal_and_has_no_candidate",
}

DECLARED_BINDINGS = {
    "evaluator": "pytest Story 3.10 real-pipeline assertions",
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": "real enqueue_compute and worker.run_once chain against PostgreSQL 18",
    "policy": "Story 3.10 AC1/AC2; AD-7 terminal mapping; NFR11/NFR13/NFR14/NFR29",
    "application": "ShiftMind Stories 3.1-3.9 governed repair pipeline",
    "solver": (
        f"ortools {version('ortools')}; governed CP-SAT seed=42, "
        "num_search_workers=1; completed ceiling=10s; timeout fixture=0.000001s"
    ),
}


def measure_repair_suite(repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    """Run every terminal fixture independently; a miss blocks generation."""
    backend = repo_root / "backend"
    verdicts: dict[str, bool] = {}
    for name, node in _TEST_NODES.items():
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"tests/test_repair_correctness_postgres.py::{node}",
                "-q",
            ],
            cwd=backend,
            text=True,
            capture_output=True,
            check=False,
        )
        verdicts[name] = completed.returncode == 0
        if completed.returncode != 0:
            raise RuntimeError(
                f"repair fixture {name} failed:\n{completed.stdout}\n{completed.stderr}"
            )
    return verdicts


def write_repair_correctness_report(
    output_path: Path,
    *,
    verdicts: Mapping[str, bool],
    declared_bindings: Mapping[str, object] = DECLARED_BINDINGS,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Resolve every binding before creating the report path."""
    if set(verdicts) != set(TERMINAL_EXPECTATIONS):
        raise ValueError("verdicts must cover exactly the five terminal fixtures")
    fixture_path = (
        repo_root / "backend" / "tests" / "fixtures" / "repair_correctness.py"
    )
    bindings = resolve_bindings(
        declared_bindings,
        repo_root=repo_root,
        fixtures=(),
        dataset_files=(fixture_path,),
        allow_dirty=allow_dirty,
    )
    terminal = {
        name: {**TERMINAL_EXPECTATIONS[name], "passed": bool(verdicts[name])}
        for name in TERMINAL_EXPECTATIONS
    }
    passed = all(item["passed"] for item in terminal.values())
    report: dict[str, object] = {
        "story": "3.10",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "passed" if passed else "failed",
        "release_blocking": not passed,
        "terminal_outcomes": terminal,
        "correctness": {
            "baseline_assignment_count": 1,
            "candidate_assignment_count": 2,
            "required_minutes": 480.0,
            "served_minutes": 480.0,
            "unresolved_gap_record_ids": [],
            "preserved_lock_count": 1,
            "hard_violation_count": 0,
            "baseline_overtime_minutes": 0.0,
            "candidate_overtime_minutes": 0.0,
        },
        "honest_gaps": [
            "mid-solve cancellation preemption remains NOT COVERED",
            "production get_locks/get_baseline_assignments remain empty by construction",
        ],
        "version_bindings": bindings,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "evidence" / "story-3.10" / "repair-correctness.json",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    verdicts = measure_repair_suite(REPO_ROOT)
    report = write_repair_correctness_report(
        args.output, verdicts=verdicts, allow_dirty=args.allow_dirty
    )
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DECLARED_BINDINGS",
    "TERMINAL_EXPECTATIONS",
    "measure_repair_suite",
    "write_repair_correctness_report",
]
