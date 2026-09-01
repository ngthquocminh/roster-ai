"""Generate Story 4.5's deterministic approval/audit release proof."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from xml.etree import ElementTree

from scripts.evidence_binding import REPO_ROOT, resolve_bindings


PROOF_NODES = {
    "initial_promotion": "tests/test_approval_audit_invariants_postgres.py::test_initial_promotion_is_exactly_once",
    "replacement": "tests/test_approval_audit_invariants_postgres.py::test_replacement_is_exactly_once",
    "mismatch": "tests/test_approval_audit_invariants_postgres.py::test_business_mismatch_terminalizes_stale",
    "expiry": "tests/test_approval_audit_invariants_postgres.py::test_expiry_terminalizes_expired",
    "rejection": "tests/test_approval_audit_invariants_postgres.py::test_rejection_terminalizes_rejected",
    "replay": "tests/test_approval_audit_invariants_postgres.py::test_command_replay_is_idempotent",
    "overdue_reads": "tests/test_approval_audit_invariants_postgres.py::test_overdue_reads_are_pure",
    "fault_consume": "tests/test_approval_audit_invariants_postgres.py::test_faulted_tx2_rolls_back_and_retries_once[consume]",
    "fault_baseline": "tests/test_approval_audit_invariants_postgres.py::test_faulted_tx2_rolls_back_and_retries_once[baseline]",
    "fault_audit": "tests/test_approval_audit_invariants_postgres.py::test_faulted_tx2_rolls_back_and_retries_once[audit]",
    "fault_event": "tests/test_approval_audit_invariants_postgres.py::test_faulted_tx2_rolls_back_and_retries_once[event]",
    "evidence_resolution": "tests/test_approval_audit_invariants_postgres.py::test_audit_evidence_refs_resolve_by_group",
    "version_mismatch": "tests/test_approval_audit_invariants_postgres.py::test_superseding_scenario_version_reports_version_mismatch",
    "telemetry_independence": "tests/test_approval_governance_postgres.py::test_authoritative_audit_survives_a_failing_span_exporter",
    "audit_integrity": "tests/test_approval_audit_invariants_postgres.py::test_audit_uniqueness_covers_the_closed_outcome_vocabulary",
}

FAILURE_MODE_GATES = {
    "initial promotion": ("initial_promotion",),
    "replacement": ("replacement",),
    "stale/expired/rejected": ("mismatch", "expiry", "rejection"),
    "reconnect": ("overdue_reads",),
    "idempotent replay": ("replay",),
    "rollback": ("fault_consume", "fault_baseline", "fault_audit", "fault_event"),
    "audit integrity": ("evidence_resolution", "version_mismatch", "telemetry_independence", "audit_integrity"),
}

DECLARED_BINDINGS = {
    "evaluator": "pytest Story 4.5 exact approval/audit proof nodes",
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": "real FastAPI approval route, PostgreSQL transaction and evidence resolvers",
    "policy": "Story 4.5 AC1-AC4; NFR8/NFR9/NFR10/NFR29; EAD-6/EAD-7/EAD-10",
    "application": "ShiftMind Epic 4 consequential approval workflow",
    "solver": "seeded deterministic candidates; solver quality is not under test",
}


def _junit_outcome(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "pytest produced no JUnit report"
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError) as exc:
        return False, f"unreadable JUnit report: {exc}"
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    executed = totals["tests"] - totals["skipped"]
    if totals["tests"] <= 0:
        return False, "no test was collected for this node"
    if executed <= 0:
        return False, "every test for this node was skipped, so nothing was proven"
    if totals["failures"] or totals["errors"]:
        return False, f"{totals['failures']} failure(s), {totals['errors']} error(s)"
    if totals["skipped"]:
        return False, f"{totals['skipped']} test(s) skipped, so the gate is incomplete"
    return True, ""


def measure_approval_audit_suite(repo_root: Path = REPO_ROOT, *, subprocess_timeout_seconds: float = 180.0):
    verdicts: dict[str, bool] = {}
    failures: dict[str, str] = {}
    for name, node in PROOF_NODES.items():
        with tempfile.TemporaryDirectory() as staging:
            junit = Path(staging) / "result.xml"
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
                    cwd=repo_root / "backend", text=True, capture_output=True,
                    timeout=subprocess_timeout_seconds, check=False,
                )
                passed, detail = _junit_outcome(junit)
                output = f"{detail}\n{completed.stdout}\n{completed.stderr}".strip()
            except subprocess.TimeoutExpired as exc:
                passed = False
                output = f"proof gate timed out after {subprocess_timeout_seconds}s: {exc}"
        verdicts[name] = passed
        if not passed:
            failures[name] = output
    return verdicts, failures


def write_approval_audit_report(output_path: Path, *, verdicts: Mapping[str, bool], failures: Mapping[str, str] | None = None, declared_bindings: Mapping[str, object] = DECLARED_BINDINGS, repo_root: Path = REPO_ROOT, allow_dirty: bool = False):
    if set(verdicts) != set(PROOF_NODES):
        raise ValueError("verdicts must cover exactly the named proof gates")
    missing = sorted(set(DECLARED_BINDINGS) - set(declared_bindings))
    if missing:
        raise ValueError(f"missing declared binding: {missing[0]}")
    destination = Path(output_path)
    try:
        own_output = destination.resolve().relative_to(repo_root.resolve()).as_posix()
        ignore_paths = frozenset({own_output})
    except ValueError:
        ignore_paths = frozenset()
    dataset_files = tuple(
        repo_root / "backend" / relative
        for relative in dict.fromkeys(node.split("::", 1)[0] for node in PROOF_NODES.values())
    )
    bindings = resolve_bindings(declared_bindings, repo_root=repo_root, fixtures=(), dataset_files=dataset_files, allow_dirty=allow_dirty, ignore_paths=ignore_paths)
    gates = {name: {"node": PROOF_NODES[name], "passed": bool(value)} for name, value in verdicts.items()}
    passed = all(item["passed"] for item in gates.values())
    report = {
        "story": "4.5", "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed, "result": "passed" if passed else "failed",
        "release_blocking": not passed,
        "failed_gates": sorted(name for name, item in gates.items() if not item["passed"]),
        "gates": gates,
        "failure_modes": {mode: {"gates": list(names), "passed": all(gates[name]["passed"] for name in names)} for mode, names in FAILURE_MODE_GATES.items()},
        "honest_gaps": [
            "NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6",
            "TX2 infrastructure faults leave no durable server-side attempt row",
            "locks and baseline-assignments evidence references are structurally not_found",
        ],
        "version_bindings": dict(bindings),
    }
    if failures:
        report["failures"] = dict(failures)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "evidence/story-4.5/approval-audit-invariants.json")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    verdicts, failures = measure_approval_audit_suite()
    report = write_approval_audit_report(args.output, verdicts=verdicts, failures=failures, allow_dirty=args.allow_dirty)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
