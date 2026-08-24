"""Generate Story 3.10's deterministic, NFR27-bound repair proof."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
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

# The `solver_completed` fixture is the only one that produces correctness
# numbers (gap closure, locks, overtime) rather than a bare terminal-status
# verdict. It writes them to CORRECTNESS_OUTPUT_ENV as JSON when that env var
# is set, so measure_repair_suite can carry the *actually measured* values
# into the report instead of a value hand-typed once during development.
CORRECTNESS_OUTPUT_ENV = "STORY_3_10_CORRECTNESS_OUTPUT"

CORRECTNESS_KEYS = (
    "baseline_assignment_count",
    "candidate_assignment_count",
    "required_minutes",
    "served_minutes",
    "unresolved_gap_record_ids",
    "preserved_lock_count",
    "hard_violation_count",
    "baseline_overtime_minutes",
    "candidate_overtime_minutes",
)

# What the report carries when the solver_completed fixture itself failed (or
# never ran): honestly "not measured", never a stale or fabricated number.
UNMEASURED_CORRECTNESS: dict[str, object] = {key: None for key in CORRECTNESS_KEYS}


def measure_repair_suite(
    repo_root: Path = REPO_ROOT,
    *,
    subprocess_timeout_seconds: float = 180.0,
) -> tuple[dict[str, bool], dict[str, object], dict[str, str]]:
    """Run every terminal fixture independently through its own subprocess.

    Every node in TERMINAL_EXPECTATIONS runs regardless of an earlier one
    failing, so a real regression still yields a complete five-fixture
    verdict set and a `correctness` measurement (when available) rather than
    an unstructured crash that never reaches `write_repair_correctness_report`.
    """
    backend = repo_root / "backend"
    verdicts: dict[str, bool] = {}
    failures: dict[str, str] = {}
    correctness = dict(UNMEASURED_CORRECTNESS)
    with tempfile.TemporaryDirectory() as tmp_dir:
        correctness_path = Path(tmp_dir) / "correctness.json"
        for name, node in _TEST_NODES.items():
            env = dict(os.environ)
            if name == "solver_completed":
                env[CORRECTNESS_OUTPUT_ENV] = str(correctness_path)
            try:
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
                    env=env,
                    timeout=subprocess_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                verdicts[name] = False
                failures[name] = (
                    f"repair fixture {name} timed out after "
                    f"{subprocess_timeout_seconds}s: {exc}"
                )
                continue
            verdicts[name] = completed.returncode == 0
            if completed.returncode != 0:
                failures[name] = f"{completed.stdout}\n{completed.stderr}"
        if verdicts.get("solver_completed") and correctness_path.exists():
            correctness = json.loads(correctness_path.read_text(encoding="utf-8"))
    return verdicts, correctness, failures


def write_repair_correctness_report(
    output_path: Path,
    *,
    verdicts: Mapping[str, bool],
    correctness: Mapping[str, object] = UNMEASURED_CORRECTNESS,
    failures: Mapping[str, str] = {},
    declared_bindings: Mapping[str, object] = DECLARED_BINDINGS,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Resolve every binding before creating the report path."""
    if set(verdicts) != set(TERMINAL_EXPECTATIONS):
        raise ValueError("verdicts must cover exactly the five terminal fixtures")
    if set(correctness) != set(CORRECTNESS_KEYS):
        raise ValueError("correctness must cover exactly the measured fields")
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
        "correctness": dict(correctness),
        "honest_gaps": [
            "mid-solve cancellation preemption remains NOT COVERED",
            "production get_locks/get_baseline_assignments remain empty by construction",
        ],
        "version_bindings": bindings,
    }
    if failures:
        report["failures"] = dict(failures)
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
    verdicts, correctness, failures = measure_repair_suite(REPO_ROOT)
    report = write_repair_correctness_report(
        args.output,
        verdicts=verdicts,
        correctness=correctness,
        failures=failures,
        allow_dirty=args.allow_dirty,
    )
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CORRECTNESS_KEYS",
    "CORRECTNESS_OUTPUT_ENV",
    "DECLARED_BINDINGS",
    "TERMINAL_EXPECTATIONS",
    "UNMEASURED_CORRECTNESS",
    "measure_repair_suite",
    "write_repair_correctness_report",
]
