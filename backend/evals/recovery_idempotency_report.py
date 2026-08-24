"""Generate Story 3.11's deterministic recovery/idempotency release proof."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from scripts.evidence_binding import REPO_ROOT, resolve_bindings


NFR35_THRESHOLD_MS = 5_000
_LIVE_WORKER_MARKER = re.compile(
    r"NFR35_LIVE_WORKER_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
)

PROOF_NODES = {
    "worker_kill": (
        "tests/test_worker_process_recovery_postgres.py::"
        "test_hard_killed_worker_is_reclaimed_and_commits_one_candidate"
    ),
    "lease_expiry": (
        "tests/test_job_leasing_postgres.py::"
        "test_expired_worker_is_fenced_and_recovered_worker_finishes_once"
    ),
    "orphan_safety": (
        "tests/test_job_leasing_postgres.py::"
        "test_mark_running_cannot_create_a_jobless_solver_running_orphan"
    ),
    "schedule_stream_reconnect": (
        "tests/test_schedule_run_stream_api.py::"
        "test_run_stream_replays_only_unseen_literal_progress"
    ),
    "conversation_stream_reconnect": (
        "tests/test_conversation_stream_api.py::"
        "test_the_last_event_id_header_wins_over_the_query_parameter"
    ),
    "command_replay": (
        "tests/test_job_leasing_postgres.py::"
        "test_enqueue_replay_and_rollback_have_exact_row_counts"
    ),
    "cancellation_race": (
        "tests/test_cancellation_race_postgres.py::"
        "test_checkpoint_2_observes_a_cancel_after_running_commit"
    ),
    "concurrent_cancellation_replay": (
        "tests/test_cancellation_race_postgres.py::"
        "test_concurrent_replay_of_one_idempotency_key_returns_the_stored_result"
    ),
    "stale_draft": (
        "tests/test_conversations_postgres.py::"
        "test_commands_refuse_stale_resource_and_stale_scenario_without_rows"
    ),
    "conflicting_cancellation_idempotency": (
        "tests/test_cancellation_race_postgres.py::"
        "test_conflicting_cancel_version_is_rejected_after_real_database_contention"
    ),
    "live_worker_latency": (
        "tests/test_worker_process_recovery_postgres.py::"
        "test_nfr35_live_worker_reaches_running_within_five_seconds"
    ),
}

FAILURE_MODE_GATES = {
    "worker kill": ("worker_kill", "orphan_safety"),
    "lease expiry": ("lease_expiry",),
    "browser reconnect": (
        "schedule_stream_reconnect",
        "conversation_stream_reconnect",
    ),
    "command replay": ("command_replay",),
    "cancellation race": (
        "cancellation_race",
        "concurrent_cancellation_replay",
    ),
    "stale draft": ("stale_draft",),
    "conflicting idempotency": ("conflicting_cancellation_idempotency",),
}

DECLARED_BINDINGS = {
    "evaluator": "pytest Story 3.11 exact recovery/idempotency proof nodes",
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": "real worker subprocess, PostgreSQL lease/fencing, command and SSE seams",
    "policy": "Story 3.11 AC1/AC2; NFR6/NFR7/NFR29/NFR35; AD-6/AD-8/AD-9",
    "application": "ShiftMind Stories 2.2-3.11 governed workflow",
    "solver": "deterministic test scheduler; solver quality is not under test",
}


def parse_live_worker_measurements(log_text: str) -> list[dict[str, object]]:
    match = _LIVE_WORKER_MARKER.search(log_text)
    return [] if match is None else json.loads(match.group(1))


def measure_recovery_suite(
    repo_root: Path = REPO_ROOT,
    *,
    subprocess_timeout_seconds: float = 180.0,
) -> tuple[dict[str, bool], list[dict[str, object]], dict[str, str]]:
    backend = repo_root / "backend"
    verdicts: dict[str, bool] = {}
    failures: dict[str, str] = {}
    live_worker_measurements: list[dict[str, object]] = []
    for name, node in PROOF_NODES.items():
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", node, "-q", "-s"],
                cwd=backend,
                text=True,
                capture_output=True,
                check=False,
                timeout=subprocess_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            verdicts[name] = False
            failures[name] = (
                f"proof gate {name} timed out after "
                f"{subprocess_timeout_seconds}s: {exc}"
            )
            continue
        verdicts[name] = completed.returncode == 0
        if name == "live_worker_latency":
            live_worker_measurements = parse_live_worker_measurements(
                completed.stdout
            )
            if len(live_worker_measurements) != 3:
                verdicts[name] = False
                failures[name] = "live worker measurement did not emit three runs"
        if completed.returncode != 0:
            failures[name] = f"{completed.stdout}\n{completed.stderr}"
    return verdicts, live_worker_measurements, failures


def write_recovery_idempotency_report(
    output_path: Path,
    *,
    verdicts: Mapping[str, bool],
    live_worker_measurements: Sequence[Mapping[str, object]],
    failures: Mapping[str, str] = {},
    declared_bindings: Mapping[str, object] = DECLARED_BINDINGS,
    resolved_bindings: Mapping[str, object] | None = None,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    if set(verdicts) != set(PROOF_NODES):
        raise ValueError("verdicts must cover exactly the named proof gates")
    bindings = resolved_bindings or resolve_bindings(
        declared_bindings,
        repo_root=repo_root,
        fixtures=(),
        dataset_files=tuple(
            repo_root / "backend" / node.split("::", 1)[0]
            for node in dict.fromkeys(PROOF_NODES.values())
        ),
        allow_dirty=allow_dirty,
    )
    measurements = [dict(item) for item in live_worker_measurements]
    latency_passed = (
        bool(verdicts["live_worker_latency"])
        and len(measurements) == 3
        and all(float(item["duration_ms"]) <= NFR35_THRESHOLD_MS for item in measurements)
    )
    gates = {
        name: {
            "node": node,
            "passed": latency_passed if name == "live_worker_latency" else bool(verdicts[name]),
        }
        for name, node in PROOF_NODES.items()
    }
    passed = all(bool(gate["passed"]) for gate in gates.values())
    report: dict[str, object] = {
        "story": "3.11",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "passed" if passed else "failed",
        "release_blocking": not passed,
        "artifact_versions": {
            "job_lease": "1",
            "run_snapshot": "1",
            "schedule_version": "1",
            "stream_cursor": "1",
            "evidence_schema": "NFR27 bindings + schema_version",
        },
        "gates": gates,
        "failure_modes": {
            mode: {
                "gates": list(names),
                "passed": all(bool(gates[name]["passed"]) for name in names),
            }
            for mode, names in FAILURE_MODE_GATES.items()
        },
        "nfr35_live_worker": {
            "clock_boundary": "committed queue acknowledgement to persisted run.running.v1",
            "threshold_ms": NFR35_THRESHOLD_MS,
            "measurements": measurements,
            "maximum_duration_ms": (
                max(float(item["duration_ms"]) for item in measurements)
                if measurements
                else None
            ),
            "passed": latency_passed,
            "scope_note": (
                "Includes real OS worker startup/polling, lease acquisition, and the "
                "queued-to-running database transition. Story 3.5's narrower "
                "run.queued.v1 read-path 'cannot fail by construction' note does "
                "not apply to this measurement. Network transit remains excluded."
            ),
        },
        "honest_gaps": [
            "mid-solve CP-SAT preemption remains NOT COVERED and has no current story owner",
            "worker deployment composition remains owned by Epic 5/6",
        ],
        "version_bindings": dict(bindings),
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
        default=REPO_ROOT / "evidence" / "story-3.11" / "recovery-idempotency.json",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    verdicts, measurements, failures = measure_recovery_suite(REPO_ROOT)
    report = write_recovery_idempotency_report(
        args.output,
        verdicts=verdicts,
        live_worker_measurements=measurements,
        failures=failures,
        allow_dirty=args.allow_dirty,
    )
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DECLARED_BINDINGS",
    "FAILURE_MODE_GATES",
    "NFR35_THRESHOLD_MS",
    "PROOF_NODES",
    "measure_recovery_suite",
    "parse_live_worker_measurements",
    "write_recovery_idempotency_report",
]
