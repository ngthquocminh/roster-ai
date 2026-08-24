from __future__ import annotations

from pathlib import Path

import pytest

from evals.repair_correctness_report import (
    DECLARED_BINDINGS,
    TERMINAL_EXPECTATIONS,
    write_repair_correctness_report,
)


def test_report_aggregates_all_terminal_verdicts_and_binds_python_fixture(
    tmp_path: Path,
) -> None:
    output = tmp_path / "repair-correctness.json"
    report = write_repair_correctness_report(
        output,
        verdicts={name: True for name in TERMINAL_EXPECTATIONS},
        declared_bindings=DECLARED_BINDINGS,
        allow_dirty=True,
    )

    assert report["result"] == "passed"
    assert set(report["terminal_outcomes"]) == set(TERMINAL_EXPECTATIONS)
    assert report["correctness"]["unresolved_gap_record_ids"] == []
    dataset = report["version_bindings"]["dataset"]
    assert dataset["kind"] == "version-controlled evaluation fixture artifacts"
    assert dataset["file_count"] == 1
    assert "backend/tests/fixtures/repair_correctness.py" in dataset["files"]
    assert output.exists()


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
            declared_bindings=incomplete,
            allow_dirty=True,
        )

    assert not output.exists()
