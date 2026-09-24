"""Generate Story 5.2's deterministic content-minimization evidence.

Story 5.9 extended it: C4 now asserts on what the real OTLP exporter receives,
four exported span channels (C5-C8) join the matrix, and the report records
the export boundary itself.
"""
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
from settings import TRACE_CONTENT_SYNTHETIC_EVAL

ARTIFACT_CONTRACT_MODULES = {
    "telemetry_record": "backend/application/contracts/telemetry.py",
    "json_log_boundary": "backend/adapters/telemetry/json_logs.py",
    "span_export_policy": "backend/adapters/telemetry/span_policy.py",
    "span_export_boundary": "backend/adapters/telemetry/spans.py",
}
ARTIFACT_DECLARED_VERSIONS = {
    "telemetry_record": "1",
    "json_log_boundary": "1",
    "span_export_policy": "1",
    "span_export_boundary": "1",
}

#: Every credential-bearing environment variable the secrets class seeds with a
#: synthetic canary. Declared here so the generator never imports a test
#: module; `test_content_minimization_report.py` pins it equal to the suite's
#: `CREDENTIAL_CANARIES`, so the two cannot drift.
CREDENTIAL_ENV_VARS = (
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OIDC_CLIENT_SECRET",
    "CSRF_SECRET",
    "AGENT_RUNTIME_API_KEY",
    "ROSTERAI_DATABASE_URL",
    "ROSTERAI_PROVISIONING_DATABASE_URL",
    "LOGFIRE_TOKEN",
)

CHANNELS = (
    "C1 telemetry JSON",
    "C2 fallback JSON logs",
    "C3 worker stderr",
    "C4 exported agent spans",
    "C5 exported HTTP server spans",
    "C6 exported HTTP client spans",
    "C7 exported database spans",
    "C8 exported worker spans",
)

EXPORT_BOUNDARY = {
    "policy_module": "backend/adapters/telemetry/span_policy.py",
    "boundary_module": "backend/adapters/telemetry/spans.py",
    "content_modes": ["off", TRACE_CONTENT_SYNTHETIC_EVAL],
    "default_content_mode": "off",
    "exception_events": "exception.type only",
    "status_description": "never exported",
    "url_query": "stripped",
    "sql_parameters": "placeholders only; status description dropped",
    "client_trace_context": "discarded on every route",
    "observed_at": "OTLP protobuf payload captured at the real OTLPSpanExporter",
}

_TEST = "tests/test_content_minimization.py::"
#: One DISTINCT test per channel x fixture class, so a red cell is attributable
#: to a channel and a fixture class rather than to "the suite". The previous
#: shape named twelve cells over six tests, which the machinery test could not
#: detect because it only checked that the names existed (code review of
#: story-5.2); `test_proof_matrix_is_attributable_to_channel_and_fixture_class`
#: now enforces distinctness and existence.
MATRIX_NODES = {
    "c1_telemetry_secrets": _TEST + "test_c1_telemetry_drops_secret_bearing_labels",
    "c1_telemetry_prompt_injection": _TEST + "test_c1_telemetry_drops_prompt_injection_text_in_unknown_labels",
    "c1_telemetry_adversarial": _TEST + "test_c1_telemetry_bounds_adversarial_label_keys_and_values",
    "c2_logs_secrets": _TEST + "test_c2_logs_drop_statement_parameters_and_secret_exception_text",
    "c2_logs_prompt_injection": _TEST + "test_c2_logs_drop_prompt_injection_text_from_message_and_arguments",
    "c2_logs_adversarial": _TEST + "test_c2_logs_neutralize_adversarial_arguments_and_third_party_records",
    "c3_worker_stderr_secrets": _TEST + "test_c3_worker_stderr_withholds_secret_exception_text",
    "c3_worker_stderr_prompt_injection": _TEST + "test_c3_worker_stderr_withholds_prompt_injection_text",
    "c3_worker_stderr_adversarial": _TEST + "test_c3_worker_stderr_withholds_adversarial_exception_text",
    "c4_spans_secrets": _TEST + "test_c4_spans_withhold_secret_prompt_and_tool_content",
    "c4_spans_prompt_injection": _TEST + "test_c4_spans_withhold_pinned_prompt_injection_text",
    "c4_spans_adversarial": _TEST + "test_c4_spans_withhold_exception_content_on_the_provider_error_path",
    "c5_http_server_spans_secrets": _TEST + "test_c5_http_server_spans_withhold_secret_headers_and_query",
    "c5_http_server_spans_prompt_injection": _TEST + "test_c5_http_server_spans_withhold_prompt_injection_text",
    "c5_http_server_spans_adversarial": _TEST + "test_c5_http_server_spans_withhold_adversarial_paths_and_exception_text",
    "c6_http_client_spans_secrets": _TEST + "test_c6_http_client_spans_withhold_the_key_and_query",
    "c6_http_client_spans_prompt_injection": _TEST + "test_c6_http_client_spans_withhold_prompt_injection_text",
    "c6_http_client_spans_adversarial": _TEST + "test_c6_http_client_spans_withhold_adversarial_url_parts_and_errors",
    "c7_database_spans_secrets": _TEST + "test_c7_database_spans_withhold_bound_secret_values",
    "c7_database_spans_prompt_injection": _TEST + "test_c7_database_spans_withhold_bound_prompt_injection_text",
    "c7_database_spans_adversarial": _TEST + "test_c7_database_spans_withhold_bound_adversarial_values_and_errors",
    "c8_worker_spans_secrets": _TEST + "test_c8_worker_spans_withhold_secret_exception_text",
    "c8_worker_spans_prompt_injection": _TEST + "test_c8_worker_spans_withhold_prompt_injection_text",
    "c8_worker_spans_adversarial": _TEST + "test_c8_worker_spans_withhold_adversarial_exception_and_status_text",
}
#: Configuration surfaces that are not per-channel but are release-blocking.
#: `settings_repr_credentials` is Decision 10's class-1 sweep, which the first
#: matrix left bound to no node at all, so `passed: true` did not depend on it.
SURFACE_NODES = {
    "settings_repr_credentials": _TEST + "test_every_credential_environment_value_is_absent_from_settings_repr",
    "instrumentation_binary_capture": _TEST + "test_both_instrumentation_constructors_disable_binary_capture",
    "telemetry_label_type_safety": _TEST + "test_c1_telemetry_survives_a_non_string_label_value",
    "worker_process_logger_ownership": _TEST + "test_worker_run_as_a_process_still_renders_an_owned_event",
    # Story 5.9's export boundary.
    "export_content_mode_key_set": _TEST + "test_export_content_mode_key_set",
    "export_keyless_constructs_no_exporter": _TEST + "test_export_keyless_constructs_no_exporter",
    "export_client_trace_context_discarded": _TEST + "test_export_client_trace_context_discarded",
    "export_agent_raw_key_drift": _TEST + "test_export_agent_raw_key_drift",
}
PROOF_NODES = MATRIX_NODES | SURFACE_NODES
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
    "tool": "demonstration tool double, JSON logging boundary and span export boundary",
    "policy": "Story 5.2 AC1/AC2, Story 5.9 AC3/AC4/AC6; NFR3/NFR4/NFR5/NFR27/NFR29/NFR30",
    "application": "ShiftMind Story 5.2 telemetry boundaries and Story 5.9 export boundary",
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
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
                    cwd=repo_root / "backend", capture_output=True, text=True, timeout=180, check=False,
                )
            except subprocess.TimeoutExpired:
                # Fail closed. Letting this escape crashed the generator, which
                # left the previous `passed: true` report in place and kept
                # Gate A green on a node that never completed.
                verdicts[name] = False
                failures[name] = "pytest node exceeded the 180s timeout"
                continue
            passed, detail = _junit_outcome(junit)
        verdicts[name] = passed and completed.returncode == 0
        if not verdicts[name]:
            # `detail` only -- never the child's captured stdout/stderr. A red
            # node's output carries the canaries and the pinned injection text
            # this report exists to prove absent, and the report is committed
            # (code review of story-5.2).
            failures[name] = detail or f"pytest exited {completed.returncode}"
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
        "channels": list(CHANNELS),
        # Every fixture named here is DRIVEN by a proof node above. The pinned
        # injection cases are read off disk by the suite's `_injection_prompts`
        # and pushed through every channel; they were previously only
        # hashed as `dataset_files`, i.e. cited rather than reused (code review
        # of story-5.2).
        "fixtures": {
            "secrets": {
                "description": "synthetic canaries in every credential-bearing environment variable",
                "environment_variables": list(CREDENTIAL_ENV_VARS),
            },
            "prompt_injection": list(PINNED_INJECTION_CASE_IDS),
            "adversarial": [
                "control character", "newline", "oversized label",
                "% directive in a log argument", "identifier label key",
                "computed label key", "non-string label value",
            ],
        },
        "export_boundary": dict(EXPORT_BOUNDARY),
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
