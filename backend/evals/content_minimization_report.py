"""Generate Story 5.2's deterministic content-minimization evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from xml.etree import ElementTree

from scripts.evidence_binding import REPO_ROOT, resolve_bindings

ARTIFACT_CONTRACT_MODULES = {
    "telemetry_record": "backend/application/contracts/telemetry.py",
    "json_log_boundary": "backend/adapters/telemetry/json_logs.py",
}
ARTIFACT_DECLARED_VERSIONS = {"telemetry_record": "1", "json_log_boundary": "1"}

_TEST = "tests/test_content_minimization.py::"
PROOF_NODES = {
    "c1_telemetry_secrets": _TEST + "test_telemetry_sink_drops_unknown_labels_and_truncates_allowed_values",
    "c1_telemetry_prompt_injection": _TEST + "test_telemetry_sink_drops_unknown_labels_and_truncates_allowed_values",
    "c1_telemetry_adversarial": _TEST + "test_telemetry_sink_drops_unknown_labels_and_truncates_allowed_values",
    "c2_logs_secrets": _TEST + "test_application_log_drops_statement_parameters_and_exception_text",
    "c2_logs_prompt_injection": _TEST + "test_application_log_drops_statement_parameters_and_exception_text",
    "c2_logs_adversarial": _TEST + "test_third_party_log_replaces_message_with_fixed_event",
    "c3_worker_stderr_secrets": _TEST + "test_worker_error_path_does_not_write_exception_content_to_stderr",
    "c3_worker_stderr_prompt_injection": _TEST + "test_worker_error_path_does_not_write_exception_content_to_stderr",
    "c3_worker_stderr_adversarial": _TEST + "test_worker_error_path_does_not_write_exception_content_to_stderr",
    "c4_spans_secrets": _TEST + "test_observed_spans_are_allow_listed_and_drop_prompt_and_tool_content",
    "c4_spans_prompt_injection": _TEST + "test_observed_spans_are_allow_listed_and_drop_prompt_and_tool_content",
    "c4_spans_adversarial": _TEST + "test_both_instrumentation_constructors_disable_binary_capture",
}
PINNED_INJECTION_CASE_IDS = (
    "scheduling-baseline-injection-chat-text",
    "scheduling-inspect-injection-chat-text",
    "scheduling-inspect-injection-fixture-field",
    "scheduling-inspect-injection-tool-output",
)
GOLDEN_FILES = (
    "backend/evals/golden/scheduling_baseline/injection-chat-text.json",
    "backend/evals/golden/scheduling_inspect/injection-chat-text.json",
    "backend/evals/golden/scheduling_inspect/injection-fixture-field.json",
    "backend/evals/golden/scheduling_inspect/injection-tool-output.json",
)
DECLARED_BINDINGS = {
    "evaluator": "pytest Story 5.2 content-minimization suite",
    "model": "deterministic FunctionModel; no external provider",
    "prompt": "synthetic canaries and four pinned prompt-injection cases",
    "tool": "demonstration tool double and JSON logging boundary",
    "policy": "Story 5.2 AC1/AC2; NFR3/NFR4/NFR5/NFR27/NFR29/NFR30",
    "application": "ShiftMind Story 5.2 telemetry boundaries",
    "solver": "not applicable — no scheduling solve",
}


def artifact_versions(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    result: dict[str, object] = {"algorithm": "sha256"}
    for name, relative in ARTIFACT_CONTRACT_MODULES.items():
        result[name] = {
            "version": ARTIFACT_DECLARED_VERSIONS[name],
            "module": relative,
            "sha256": hashlib.sha256((repo_root / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        }
    return result


def _junit_outcome(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "pytest produced no JUnit report"
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        return False, f"unreadable JUnit report: {exc}"
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = {key: sum(int(suite.get(key, 0) or 0) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    if totals["tests"] <= 0:
        return False, "no test was collected"
    if totals["skipped"]:
        return False, f"{totals['skipped']} test(s) skipped"
    if totals["failures"] or totals["errors"]:
        return False, f"{totals['failures']} failure(s), {totals['errors']} error(s)"
    return True, ""


def measure(repo_root: Path = REPO_ROOT) -> tuple[dict[str, bool], dict[str, str]]:
    verdicts: dict[str, bool] = {}
    failures: dict[str, str] = {}
    for name, node in PROOF_NODES.items():
        with tempfile.TemporaryDirectory() as directory:
            junit = Path(directory) / "result.xml"
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
                cwd=repo_root / "backend", capture_output=True, text=True, timeout=180, check=False,
            )
            passed, detail = _junit_outcome(junit)
        verdicts[name] = passed and completed.returncode == 0
        if not verdicts[name]:
            failures[name] = f"{detail}\n{completed.stdout}\n{completed.stderr}".strip()
    return verdicts, failures


def write_report(output_path: Path, *, verdicts: Mapping[str, bool], failures: Mapping[str, str] | None = None, repo_root: Path = REPO_ROOT) -> dict[str, object]:
    if set(verdicts) != set(PROOF_NODES):
        raise ValueError("verdicts must cover exactly the named proof nodes")
    destination = Path(output_path)
    try:
        own_output = destination.resolve().relative_to(repo_root.resolve()).as_posix()
        ignore_paths = frozenset({own_output})
    except ValueError:
        ignore_paths = frozenset()
    bindings = resolve_bindings(
        DECLARED_BINDINGS, repo_root=repo_root, fixtures=(),
        dataset_files=tuple(repo_root / path for path in GOLDEN_FILES),
        ignore_paths=ignore_paths,
    )
    passed = all(verdicts.values())
    report: dict[str, object] = {
        "story": "5.2", "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed, "result": "passed" if passed else "failed", "release_blocking": not passed,
        "channels": ["C1 telemetry JSON", "C2 fallback JSON logs", "C3 worker stderr", "C4 OpenTelemetry spans"],
        "fixtures": {"secrets": "seven synthetic configuration canaries", "prompt_injection": list(PINNED_INJECTION_CASE_IDS), "adversarial": ["control characters", "newline", "oversized label", "% directive", "identifier label key", "computed label key"]},
        "artifact_versions": artifact_versions(repo_root),
        "proof_nodes": {name: {"node": PROOF_NODES[name], "passed": bool(value)} for name, value in verdicts.items()},
        "version_bindings": dict(bindings),
    }
    if failures:
        report["failures"] = dict(failures)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "evidence/story-5.2/content-minimization-report.json")
    args = parser.parse_args(argv)
    verdicts, failures = measure(REPO_ROOT)
    report = write_report(args.output, verdicts=verdicts, failures=failures)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
