from __future__ import annotations

from pathlib import Path

import pytest

from evals.repair_correctness_report import (
    CORRECTNESS_KEYS,
    DECLARED_BINDINGS,
    TERMINAL_EXPECTATIONS,
    UNMEASURED_CORRECTNESS,
    write_repair_correctness_report,
)


_MEASURED_CORRECTNESS = {
    "baseline_assignment_count": 1,
    "candidate_assignment_count": 2,
    "required_minutes": 480.0,
    "served_minutes": 480.0,
    "unresolved_gap_record_ids": [],
    "preserved_lock_count": 1,
    "hard_violation_count": 0,
    "baseline_overtime_minutes": 0.0,
    "candidate_overtime_minutes": 0.0,
}


def test_report_aggregates_all_terminal_verdicts_and_binds_python_fixture(
    tmp_path: Path,
) -> None:
    output = tmp_path / "repair-correctness.json"
    report = write_repair_correctness_report(
        output,
        verdicts={name: True for name in TERMINAL_EXPECTATIONS},
        correctness=_MEASURED_CORRECTNESS,
        declared_bindings=DECLARED_BINDINGS,
        allow_dirty=True,
    )

    assert report["result"] == "passed"
    assert report["release_blocking"] is False
    assert set(report["terminal_outcomes"]) == set(TERMINAL_EXPECTATIONS)
    assert report["correctness"] == _MEASURED_CORRECTNESS
    assert "failures" not in report
    dataset = report["version_bindings"]["dataset"]
    assert dataset["kind"] == "version-controlled evaluation fixture artifacts"
    assert dataset["file_count"] == 1
    assert "backend/tests/fixtures/repair_correctness.py" in dataset["files"]
    assert output.exists()


def test_a_failing_fixture_still_produces_a_blocking_report_not_a_crash(
    tmp_path: Path,
) -> None:
    """The report schema's failure branch must be reachable: a real miss on
    any terminal fixture is recorded as `result: "failed"` /
    `release_blocking: true` naming which fixture failed, not an
    unstructured crash that never writes an evidence artifact."""
    output = tmp_path / "repair-correctness.json"
    verdicts = {name: True for name in TERMINAL_EXPECTATIONS}
    verdicts["solver_infeasible"] = False

    report = write_repair_correctness_report(
        output,
        verdicts=verdicts,
        correctness=_MEASURED_CORRECTNESS,
        failures={"solver_infeasible": "assertion failed: wrong reason"},
        declared_bindings=DECLARED_BINDINGS,
        allow_dirty=True,
    )

    assert report["result"] == "failed"
    assert report["release_blocking"] is True
    assert report["terminal_outcomes"]["solver_infeasible"]["passed"] is False
    assert report["failures"] == {"solver_infeasible": "assertion failed: wrong reason"}
    assert output.exists()


def test_unmeasured_correctness_is_honestly_null_not_a_stale_number(
    tmp_path: Path,
) -> None:
    """When solver_completed itself fails (or never ran), the report must not
    fall back to a fabricated or stale correctness figure."""
    output = tmp_path / "repair-correctness.json"
    verdicts = {name: True for name in TERMINAL_EXPECTATIONS}
    verdicts["solver_completed"] = False

    report = write_repair_correctness_report(
        output,
        verdicts=verdicts,
        correctness=UNMEASURED_CORRECTNESS,
        declared_bindings=DECLARED_BINDINGS,
        allow_dirty=True,
    )

    assert report["result"] == "failed"
    assert all(value is None for value in report["correctness"].values())


def test_correctness_must_cover_exactly_the_measured_fields(tmp_path: Path) -> None:
    output = tmp_path / "repair-correctness.json"
    incomplete = dict(_MEASURED_CORRECTNESS)
    del incomplete["hard_violation_count"]

    with pytest.raises(ValueError, match="correctness"):
        write_repair_correctness_report(
            output,
            verdicts={name: True for name in TERMINAL_EXPECTATIONS},
            correctness=incomplete,
            declared_bindings=DECLARED_BINDINGS,
            allow_dirty=True,
        )
    assert not output.exists()


def test_missing_binding_is_rejected_before_any_report_is_written(
    tmp_path: Path,
) -> None:
    output = tmp_path / "missing" / "repair-correctness.json"
    incomplete = dict(DECLARED_BINDINGS)
    del incomplete["policy"]

    with pytest.raises(ValueError, match="policy"):
        write_repair_correctness_report(
            output,
            verdicts={name: True for name in TERMINAL_EXPECTATIONS},
            correctness=_MEASURED_CORRECTNESS,
            declared_bindings=incomplete,
            allow_dirty=True,
        )

    assert not output.exists()


def test_correctness_keys_match_the_measured_correctness_fixture() -> None:
    assert set(_MEASURED_CORRECTNESS) == set(CORRECTNESS_KEYS)
