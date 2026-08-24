from __future__ import annotations

from pathlib import Path

import pytest

from evals.recovery_idempotency_report import (
    PROOF_NODES,
    parse_live_worker_measurements,
    write_recovery_idempotency_report,
)


def _bindings():
    return {
        "dataset": "story 3.11 test fixtures",
        "scenario": "not applicable",
        "code": {"git_commit": "a" * 40, "working_tree_dirty": False},
    }


def test_report_is_release_blocking_when_any_exact_gate_fails(tmp_path: Path) -> None:
    verdicts = {name: True for name in PROOF_NODES}
    verdicts["worker_kill"] = False
    report = write_recovery_idempotency_report(
        tmp_path / "report.json",
        verdicts=verdicts,
        live_worker_measurements=(),
        failures={"worker_kill": "killed-worker proof failed"},
        resolved_bindings=_bindings(),
    )

    assert report["result"] == "failed"
    assert report["release_blocking"] is True
    assert report["gates"]["worker_kill"]["passed"] is False
    assert report["failures"]["worker_kill"] == "killed-worker proof failed"


def test_report_requires_every_named_gate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly"):
        write_recovery_idempotency_report(
            tmp_path / "report.json",
            verdicts={},
            live_worker_measurements=(),
            resolved_bindings=_bindings(),
        )


def test_live_worker_marker_parser_keeps_the_measured_values() -> None:
    measurements = parse_live_worker_measurements(
        'NFR35_LIVE_WORKER_MEASUREMENTS=[{"run":1,"duration_ms":12.5}]\n'
    )
    assert measurements == [{"run": 1, "duration_ms": 12.5}]

