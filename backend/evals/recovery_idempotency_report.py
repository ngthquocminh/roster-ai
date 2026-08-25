"""Generate Story 3.11's deterministic recovery/idempotency release proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree import ElementTree

from scripts.evidence_binding import REPO_ROOT, resolve_bindings


NFR35_THRESHOLD_MS = 5_000
#: Four jobs are measured; the first is the cold-start run and is reported as
#: such rather than discarded, so `scope_note`'s startup claim is literally true.
NFR35_EXPECTED_MEASUREMENTS = 4
_LIVE_WORKER_MARKER = re.compile(
    r"NFR35_LIVE_WORKER_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
)

#: Contract modules whose version literals `artifact_versions` asserts. Digested
#: so a V2 edit moves the binding even if the literal is not bumped — AC2's
#: "artifact versions" must be derived, not a hand-typed string.
ARTIFACT_CONTRACT_MODULES = {
    "job_lease": "backend/application/contracts/job_lease.py",
    "run_snapshot": "backend/application/contracts/run_snapshot.py",
    "schedule_version": "backend/application/contracts/schedule_version.py",
    "stream_cursor": "backend/application/contracts/stream_cursor.py",
}
ARTIFACT_DECLARED_VERSIONS = {
    "job_lease": "1",
    "run_snapshot": "1",
    "schedule_version": "1",
    "stream_cursor": "1",
}

PROOF_NODES = {
    # ---- worker kill -------------------------------------------------------
    "worker_kill": (
        "tests/test_worker_process_recovery_postgres.py::"
        "test_hard_killed_worker_is_reclaimed_and_commits_one_candidate"
    ),
    "worker_kill_orphan_safety": (
        "tests/test_job_leasing_postgres.py::"
        "test_mark_running_cannot_create_a_jobless_solver_running_orphan"
    ),
    # ---- lease expiry ------------------------------------------------------
    "lease_expiry": (
        "tests/test_job_leasing_postgres.py::"
        "test_expired_worker_is_fenced_and_recovered_worker_finishes_once"
    ),
    "lease_expiry_stale_worker_writes_no_candidate": (
        "tests/test_job_leasing_postgres.py::"
        "test_a_stale_worker_writes_no_candidate_and_the_current_epoch_writes_exactly_one"
    ),
    "lease_expiry_transient_failure_stays_leasable": (
        "tests/test_job_leasing_postgres.py::"
        "test_transient_failure_after_lease_stays_leasable_for_recovery"
    ),
    "lease_expiry_fatal_failure_is_terminal": (
        "tests/test_job_leasing_postgres.py::"
        "test_fatal_failure_after_lease_is_terminal_and_never_released"
    ),
    # ---- browser reconnect -------------------------------------------------
    "schedule_stream_replay": (
        "tests/test_schedule_run_stream_api.py::"
        "test_run_stream_replays_only_unseen_literal_progress"
    ),
    "schedule_stream_header_cursor": (
        "tests/test_schedule_run_stream_api.py::"
        "test_header_cursor_wins_and_foreign_cursor_performs_zero_queries"
    ),
    "conversation_stream_replay": (
        "tests/test_conversation_stream_api.py::"
        "test_the_stream_opens_with_a_heartbeat_then_replays_every_outstanding_event"
    ),
    "conversation_stream_cursor_strictly_greater": (
        "tests/test_conversation_stream_api.py::"
        "test_a_cursor_replays_only_strictly_greater_sequences"
    ),
    "conversation_stream_header_precedence": (
        "tests/test_conversation_stream_api.py::"
        "test_the_last_event_id_header_wins_over_the_query_parameter"
    ),
    # ---- command replay ----------------------------------------------------
    "command_replay": (
        "tests/test_job_leasing_postgres.py::"
        "test_enqueue_replay_and_rollback_have_exact_row_counts"
    ),
    "concurrent_cancellation_replay": (
        "tests/test_cancellation_race_postgres.py::"
        "test_concurrent_replay_of_one_idempotency_key_returns_the_stored_result"
    ),
    # ---- cancellation race -------------------------------------------------
    "cancellation_race": (
        "tests/test_cancellation_race_postgres.py::"
        "test_checkpoint_2_observes_a_cancel_after_running_commit"
    ),
    # ---- stale draft -------------------------------------------------------
    "stale_draft": (
        "tests/test_conversations_postgres.py::"
        "test_commands_refuse_stale_resource_and_stale_scenario_without_rows"
    ),
    # ---- conflicting idempotency ------------------------------------------
    "conflicting_cancellation_idempotency": (
        "tests/test_cancellation_race_postgres.py::"
        "test_conflicting_cancel_version_is_rejected_after_real_database_contention"
    ),
    "conflicting_cancel_bundle": (
        "tests/test_cancellation_race_postgres.py::"
        "test_cancel_bundle_replay_conflict_and_rollback_cover_all_three_writes"
    ),
    "conflicting_cancel_command_version": (
        "tests/test_cancel_schedule_run.py::"
        "test_cancel_command_conflicts_when_expected_version_changes_on_replay"
    ),
    "conflicting_enqueue_version": (
        "tests/test_enqueue_compute.py::"
        "test_enqueue_compute_rejects_same_key_with_a_different_expected_version"
    ),
    "conflicting_conversation_version": (
        "tests/test_conversations_postgres.py::"
        "test_replaying_a_key_against_another_expected_version_conflicts"
    ),
    "conflicting_conversation_body": (
        "tests/test_conversations_postgres.py::"
        "test_same_idempotency_key_with_another_body_conflicts_without_applying"
    ),
    "conflicting_api_409_mapping": (
        "tests/test_schedule_runs_api.py::"
        "test_cancellation_route_maps_command_problems"
    ),
    # ---- NFR35 live worker -------------------------------------------------
    "live_worker_latency": (
        "tests/test_worker_process_recovery_postgres.py::"
        "test_nfr35_live_worker_reaches_running_within_five_seconds"
    ),
}

#: AC1's seven named failure modes, each bound to every gate Decision 2's table
#: enumerated plus the gates this story added. A mode may reuse a gate that
#: genuinely proves both (enqueue replay covers replay AND body-hash conflict);
#: no mode borrows another's only proof.
FAILURE_MODE_GATES = {
    "worker kill": ("worker_kill", "worker_kill_orphan_safety"),
    "lease expiry": (
        "lease_expiry",
        "lease_expiry_stale_worker_writes_no_candidate",
        "lease_expiry_transient_failure_stays_leasable",
        "lease_expiry_fatal_failure_is_terminal",
    ),
    "browser reconnect": (
        "schedule_stream_replay",
        "schedule_stream_header_cursor",
        "conversation_stream_replay",
        "conversation_stream_cursor_strictly_greater",
        "conversation_stream_header_precedence",
    ),
    "command replay": ("command_replay", "concurrent_cancellation_replay"),
    "cancellation race": ("cancellation_race", "concurrent_cancellation_replay"),
    "stale draft": ("stale_draft",),
    "conflicting idempotency": (
        "conflicting_cancellation_idempotency",
        "conflicting_cancel_bundle",
        "conflicting_cancel_command_version",
        "conflicting_enqueue_version",
        "conflicting_conversation_version",
        "conflicting_conversation_body",
        "conflicting_api_409_mapping",
    ),
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
    """Read the measurement marker, tolerating a malformed payload.

    Decision 4 requires this generator never to raise mid-loop: a node whose
    marker cannot be read is a failed gate, not a crash that destroys the whole
    report after every other node has already run.
    """
    match = _LIVE_WORKER_MARKER.search(log_text)
    if match is None:
        return []
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _measurements_are_well_formed(
    measurements: Sequence[Mapping[str, object]],
) -> bool:
    return len(measurements) == NFR35_EXPECTED_MEASUREMENTS and all(
        isinstance(item.get("duration_ms"), (int, float))
        and not isinstance(item.get("duration_ms"), bool)
        for item in measurements
    )


def artifact_versions(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    """Derive the artifact-version block AC2 requires the failure to name."""
    versions: dict[str, object] = {"algorithm": "sha256"}
    for name, relative_path in sorted(ARTIFACT_CONTRACT_MODULES.items()):
        source = repo_root / relative_path
        # A missing contract module means the version literal below is asserting
        # something that no longer exists; fail loudly rather than record it.
        digest = hashlib.sha256(
            source.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        versions[name] = {
            "version": ARTIFACT_DECLARED_VERSIONS[name],
            "module": relative_path,
            "sha256": digest,
        }
    versions["evidence_schema"] = "NFR27 bindings + schema_version"
    return versions


def _junit_outcome(report_path: Path) -> tuple[bool, str]:
    """Return (gate really passed, detail) from pytest's own JUnit report.

    A process exit code is not enough. `governed_postgres_engine` calls
    `pytest.skip` when PostgreSQL is unreachable, and an all-skipped run exits
    0 — so a return-code check stamps every PostgreSQL gate `passed` against
    zero executed assertions. A gate must have RUN to be proven.
    """
    if not report_path.exists():
        return False, "pytest produced no JUnit report"
    try:
        root = ElementTree.parse(report_path).getroot()
    except ElementTree.ParseError as exc:
        return False, f"unreadable JUnit report: {exc}"
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, 0) or 0)
    if totals["tests"] == 0:
        return False, "no test was collected for this node"
    executed = totals["tests"] - totals["skipped"]
    if executed <= 0:
        return False, "every test for this node was skipped, so nothing was proven"
    if totals["failures"] or totals["errors"]:
        return (
            False,
            f"{totals['failures']} failure(s), {totals['errors']} error(s)",
        )
    if totals["skipped"]:
        return False, f"{totals['skipped']} test(s) skipped, so the gate is incomplete"
    return True, ""


@dataclass(frozen=True)
class _NodeOutput:
    stdout: str
    stderr: str


def _run_proof_node(
    node: str,
    *,
    cwd: Path,
    junit_path: Path,
    timeout_seconds: float,
) -> tuple[_NodeOutput, bool]:
    """Run one node, tearing down its whole process tree on timeout.

    A worker-kill gate spawns `worker/main.py` as a grandchild. Killing only the
    pytest child would leave that worker alive and still leasing from the
    throwaway database, poisoning every later gate — so the node gets its own
    process group (POSIX) and the group is signalled as a unit.
    """
    popen_kwargs: dict[str, object] = {}
    if hasattr(os, "killpg") and hasattr(os, "setsid"):
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            node,
            "-q",
            "-s",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit_path}",
        ],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **popen_kwargs,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return _NodeOutput(stdout or "", stderr or ""), False
    except subprocess.TimeoutExpired:
        if popen_kwargs:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
        else:
            process.kill()
        stdout, stderr = process.communicate()
        return _NodeOutput(stdout or "", stderr or ""), True


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
        with tempfile.TemporaryDirectory() as staging:
            junit_path = Path(staging) / "result.xml"
            completed, timed_out = _run_proof_node(
                node,
                cwd=backend,
                junit_path=junit_path,
                timeout_seconds=subprocess_timeout_seconds,
            )
            if timed_out:
                verdicts[name] = False
                failures[name] = (
                    f"proof gate {name} timed out after "
                    f"{subprocess_timeout_seconds}s\n"
                    f"{completed.stdout}\n{completed.stderr}"
                )
                continue
            ran_and_passed, detail = _junit_outcome(junit_path)
        verdicts[name] = ran_and_passed
        if name == "live_worker_latency":
            live_worker_measurements = parse_live_worker_measurements(
                completed.stdout
            )
            if ran_and_passed and not _measurements_are_well_formed(
                live_worker_measurements
            ):
                verdicts[name] = False
                detail = (
                    "live worker measurement did not emit "
                    f"{NFR35_EXPECTED_MEASUREMENTS} well-formed runs"
                )
        if not verdicts[name]:
            failures[name] = (
                f"{detail}\n{completed.stdout}\n{completed.stderr}".strip()
            )
    return verdicts, live_worker_measurements, failures


def write_recovery_idempotency_report(
    output_path: Path,
    *,
    verdicts: Mapping[str, bool],
    live_worker_measurements: Sequence[Mapping[str, object]],
    failures: Mapping[str, str] | None = None,
    declared_bindings: Mapping[str, object] = DECLARED_BINDINGS,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    if set(verdicts) != set(PROOF_NODES):
        raise ValueError("verdicts must cover exactly the named proof gates")
    destination = Path(output_path)
    try:
        own_output = destination.resolve().relative_to(repo_root.resolve()).as_posix()
        ignore_paths = frozenset({own_output})
    except ValueError:
        # Written outside the repo (a test's tmp_path); nothing to exempt.
        ignore_paths = frozenset()
    bindings = resolve_bindings(
        declared_bindings,
        repo_root=repo_root,
        fixtures=(),
        dataset_files=tuple(
            repo_root / "backend" / relative_path
            for relative_path in dict.fromkeys(
                node.split("::", 1)[0] for node in PROOF_NODES.values()
            )
        ),
        allow_dirty=allow_dirty,
        # Regenerating necessarily dirties this file; without the exemption the
        # next run refuses before doing any work.
        ignore_paths=ignore_paths,
    )
    measurements = [dict(item) for item in live_worker_measurements]
    latency_passed = bool(verdicts["live_worker_latency"]) and (
        _measurements_are_well_formed(measurements)
        and all(
            float(item["duration_ms"]) <= NFR35_THRESHOLD_MS for item in measurements
        )
    )
    gates = {
        name: {
            "node": node,
            "passed": latency_passed if name == "live_worker_latency" else bool(verdicts[name]),
        }
        for name, node in PROOF_NODES.items()
    }
    passed = all(bool(gate["passed"]) for gate in gates.values())
    failed_gates = sorted(name for name, gate in gates.items() if not gate["passed"])
    report: dict[str, object] = {
        "story": "3.11",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Top-level `passed` is the contract `scripts/gate_a_readiness.py` reads.
        # Anything else is recorded by that gate as "missing", which is why this
        # artifact silently bound to nothing before review.
        "passed": passed,
        "result": "passed" if passed else "failed",
        "release_blocking": not passed,
        "failed_gates": failed_gates,
        "artifact_versions": artifact_versions(repo_root),
        "gates": gates,
        "failure_modes": {
            mode: {
                "gates": list(names),
                "passed": all(bool(gates[name]["passed"]) for name in names),
            }
            for mode, names in FAILURE_MODE_GATES.items()
        },
        "nfr35_live_worker": {
            "clock_boundary": (
                "committed queue acknowledgement (job row flipped to `queued` "
                "and committed) to persisted run.running.v1"
            ),
            "threshold_ms": NFR35_THRESHOLD_MS,
            "measurements": measurements,
            "maximum_duration_ms": (
                max(
                    float(item["duration_ms"])
                    for item in measurements
                    if isinstance(item.get("duration_ms"), (int, float))
                )
                if _measurements_are_well_formed(measurements)
                else None
            ),
            "passed": latency_passed,
            "scope_note": (
                "Run 1 is the cold-start run and is REPORTED, not discarded, so "
                "the startup claim is literal: it carries whatever worker "
                "process start-up remains after launch. Runs 2-4 are warm. Each "
                "measurement records the poll interval it ran under and the "
                "poller resolution that bounds its precision. Network transit "
                "and the HTTP handler time from POST receipt to committed "
                "acknowledgement both remain EXCLUDED — no current release "
                "requirement assigns that narrower delta. Story 3.5's narrower "
                "run.queued.v1 read-path 'cannot fail by construction' note "
                "does not apply to this measurement."
            ),
        },
        "honest_gaps": [
            "mid-solve CP-SAT preemption remains NOT COVERED and has no current story owner",
            "worker deployment AND runtime-factory composition remain owned by Epic 5/6; "
            "the entry point has no non-test factory today",
            "recorded dataset digests are not yet re-verified by any drift check",
        ],
        "version_bindings": dict(bindings),
    }
    if failures:
        report["failures"] = dict(failures)
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
    "ARTIFACT_CONTRACT_MODULES",
    "DECLARED_BINDINGS",
    "FAILURE_MODE_GATES",
    "NFR35_EXPECTED_MEASUREMENTS",
    "NFR35_THRESHOLD_MS",
    "PROOF_NODES",
    "artifact_versions",
    "measure_recovery_suite",
    "parse_live_worker_measurements",
    "write_recovery_idempotency_report",
]
