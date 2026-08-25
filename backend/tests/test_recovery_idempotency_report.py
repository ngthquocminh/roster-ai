from __future__ import annotations

from pathlib import Path

import pytest

from evals import recovery_idempotency_report as report_module
from evals.recovery_idempotency_report import (
    ARTIFACT_CONTRACT_MODULES,
    DECLARED_BINDINGS,
    FAILURE_MODE_GATES,
    NFR35_EXPECTED_MEASUREMENTS,
    PROOF_NODES,
    _junit_outcome,
    artifact_versions,
    measure_recovery_suite,
    parse_live_worker_measurements,
    write_recovery_idempotency_report,
)


def _measurements(duration_ms: float = 60.0):
    return [
        {
            "run": index + 1,
            "event": "run.running.v1",
            "duration_ms": duration_ms,
            "cold_start": index == 0,
            "poll_interval_seconds": 1.0,
            "poll_resolution_ms": 5.0,
        }
        for index in range(NFR35_EXPECTED_MEASUREMENTS)
    ]


def _junit(path: Path, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="pytest" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" skipped="{skipped}">'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def test_report_passes_and_binds_every_proof_node_through_the_real_resolver(
    tmp_path: Path,
) -> None:
    """The dataset binding must come from `resolve_bindings()`, never a literal.

    There is deliberately no `resolved_bindings=` escape hatch: hand-supplying a
    `code` block is the exact defect `docs/EVIDENCE-CONVENTION.md` exists to
    prevent, and the bypass also left the dataset path — the one that needed a
    post-generation fix in `8901cf4` — with no coverage at all.
    """
    output = tmp_path / "recovery-idempotency.json"
    report = write_recovery_idempotency_report(
        output,
        verdicts={name: True for name in PROOF_NODES},
        live_worker_measurements=_measurements(),
        declared_bindings=DECLARED_BINDINGS,
        allow_dirty=True,
    )

    assert report["passed"] is True
    assert report["result"] == "passed"
    assert report["release_blocking"] is False
    assert report["failed_gates"] == []
    assert set(report["gates"]) == set(PROOF_NODES)
    assert all(mode["passed"] for mode in report["failure_modes"].values())
    assert set(report["failure_modes"]) == set(FAILURE_MODE_GATES)

    dataset = report["version_bindings"]["dataset"]
    assert dataset["kind"] == "version-controlled evaluation fixture artifacts"
    # One entry per distinct test file behind the proof nodes -- derived, so a
    # duplicated binding (the `8901cf4` defect) shows up here as a count drift.
    expected_files = {node.split("::", 1)[0] for node in PROOF_NODES.values()}
    assert dataset["file_count"] == len(expected_files)
    for relative_path in expected_files:
        assert f"backend/{relative_path}" in dataset["files"]
    assert report["version_bindings"]["code"]["git_commit"]
    assert output.exists()


def test_top_level_passed_is_present_because_gate_a_reads_that_key(
    tmp_path: Path,
) -> None:
    """`scripts/gate_a_readiness.py` reads a TOP-LEVEL `passed` boolean.

    Emitting only `result` made the artifact read as "missing" by the one gate
    that could bind it, which is how a release-blocking file bound to nothing.
    """
    verdicts = {name: True for name in PROOF_NODES}
    verdicts["worker_kill"] = False
    report = write_recovery_idempotency_report(
        tmp_path / "report.json",
        verdicts=verdicts,
        live_worker_measurements=_measurements(),
        failures={"worker_kill": "killed-worker proof failed"},
        allow_dirty=True,
    )

    assert report["passed"] is False
    assert report["result"] == "failed"
    assert report["release_blocking"] is True
    assert report["failed_gates"] == ["worker_kill"]
    assert report["gates"]["worker_kill"]["passed"] is False
    assert report["failure_modes"]["worker kill"]["passed"] is False
    assert report["failures"]["worker_kill"] == "killed-worker proof failed"


def test_report_requires_every_named_gate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly"):
        write_recovery_idempotency_report(
            tmp_path / "report.json",
            verdicts={},
            live_worker_measurements=(),
            allow_dirty=True,
        )


@pytest.mark.parametrize(
    "measurements",
    (
        pytest.param([], id="no-measurements"),
        pytest.param(_measurements()[:2], id="too-few-runs"),
        pytest.param(
            [{**item, "duration_ms": 5_001.0} for item in _measurements()],
            id="over-threshold",
        ),
        pytest.param(
            [{**item, "duration_ms": "fast"} for item in _measurements()],
            id="non-numeric-duration",
        ),
    ),
)
def test_latency_gate_fails_closed_on_any_unusable_measurement(
    tmp_path: Path, measurements
) -> None:
    report = write_recovery_idempotency_report(
        tmp_path / "report.json",
        verdicts={name: True for name in PROOF_NODES},
        live_worker_measurements=measurements,
        allow_dirty=True,
    )

    assert report["nfr35_live_worker"]["passed"] is False
    assert report["gates"]["live_worker_latency"]["passed"] is False
    assert report["release_blocking"] is True


def test_artifact_versions_are_derived_from_the_contract_modules() -> None:
    versions = artifact_versions()

    assert versions["algorithm"] == "sha256"
    for name, relative_path in ARTIFACT_CONTRACT_MODULES.items():
        assert versions[name]["module"] == relative_path
        assert len(versions[name]["sha256"]) == 64
        assert versions[name]["version"] == "1"


def test_measurement_marker_tolerates_a_malformed_payload() -> None:
    assert parse_live_worker_measurements("no marker here") == []
    assert parse_live_worker_measurements(
        "NFR35_LIVE_WORKER_MEASUREMENTS=[not json]"
    ) == []
    assert parse_live_worker_measurements(
        'NFR35_LIVE_WORKER_MEASUREMENTS=[{"duration_ms": 1.5}]'
    ) == [{"duration_ms": 1.5}]


@pytest.mark.parametrize(
    ("counts", "expected", "detail_fragment"),
    (
        pytest.param({"tests": 1}, True, "", id="one-real-pass"),
        pytest.param(
            {"tests": 1, "skipped": 1},
            False,
            "skipped",
            id="skip-is-not-a-pass",
        ),
        pytest.param({"tests": 0}, False, "no test was collected", id="node-vanished"),
        pytest.param({"tests": 1, "failures": 1}, False, "failure", id="failure"),
        pytest.param({"tests": 1, "errors": 1}, False, "error", id="error"),
    ),
)
def test_a_gate_must_actually_run_to_count_as_passed(
    tmp_path: Path, counts, expected, detail_fragment
) -> None:
    """PostgreSQL being down must never read as a passed gate.

    `governed_postgres_engine` calls `pytest.skip` when the database is
    unreachable and an all-skipped run exits 0, so a return-code check stamped
    every PostgreSQL gate `passed` against zero executed assertions.
    """
    passed, detail = _junit_outcome(_junit(tmp_path / "r.xml", **counts))

    assert passed is expected
    assert detail_fragment in detail


def test_missing_or_unreadable_junit_report_fails_closed(tmp_path: Path) -> None:
    assert _junit_outcome(tmp_path / "absent.xml") == (
        False,
        "pytest produced no JUnit report",
    )
    broken = tmp_path / "broken.xml"
    broken.write_text("<testsuite", encoding="utf-8")
    passed, detail = _junit_outcome(broken)
    assert passed is False
    assert "unreadable JUnit report" in detail


def test_measure_recovery_suite_records_a_timeout_as_a_failed_gate(
    monkeypatch, tmp_path: Path
) -> None:
    """A hung node must produce a `failed` entry, never crash the whole run."""
    calls: list[str] = []

    def fake_run(node, *, cwd, junit_path, timeout_seconds):
        calls.append(node)
        timed_out = node == PROOF_NODES["worker_kill"]
        if not timed_out:
            _junit(junit_path, tests=1)
            if node == PROOF_NODES["live_worker_latency"]:
                import json as _json

                return (
                    report_module._NodeOutput(
                        "NFR35_LIVE_WORKER_MEASUREMENTS="
                        + _json.dumps(_measurements()),
                        "",
                    ),
                    False,
                )
        return report_module._NodeOutput("captured stdout", "captured stderr"), timed_out

    monkeypatch.setattr(report_module, "_run_proof_node", fake_run)
    verdicts, measurements, failures = measure_recovery_suite(tmp_path)

    assert len(calls) == len(PROOF_NODES)
    assert verdicts["worker_kill"] is False
    assert "timed out" in failures["worker_kill"]
    assert verdicts["lease_expiry"] is True
    assert len(measurements) == NFR35_EXPECTED_MEASUREMENTS
    # Every other gate still ran: one hung node must not abort the sweep.
    assert sum(1 for value in verdicts.values() if value) == len(PROOF_NODES) - 1


def test_measure_recovery_suite_fails_the_latency_gate_without_measurements(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_run(node, *, cwd, junit_path, timeout_seconds):
        _junit(junit_path, tests=1)
        return report_module._NodeOutput("", ""), False

    monkeypatch.setattr(report_module, "_run_proof_node", fake_run)
    verdicts, measurements, failures = measure_recovery_suite(tmp_path)

    assert measurements == []
    assert verdicts["live_worker_latency"] is False
    assert "well-formed runs" in failures["live_worker_latency"]
