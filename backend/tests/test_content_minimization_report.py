"""Fail-closed tests for Story 5.2's evidence generator."""
from pathlib import Path

from evals.content_minimization_report import PROOF_NODES, _junit_outcome, write_report


def test_junit_outcome_requires_executed_unskipped_green_tests(tmp_path: Path) -> None:
    report = tmp_path / "result.xml"
    report.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
    assert _junit_outcome(report) == (True, "")
    report.write_text('<testsuite tests="1" failures="0" errors="0" skipped="1"/>', encoding="utf-8")
    assert _junit_outcome(report)[0] is False


def test_report_requires_every_channel_fixture_proof_node(tmp_path: Path) -> None:
    verdicts = dict.fromkeys(PROOF_NODES, True)
    verdicts.pop(next(iter(verdicts)))
    try:
        write_report(tmp_path / "report.json", verdicts=verdicts)
    except ValueError as exc:
        assert "exactly" in str(exc)
    else:
        raise AssertionError("missing proof node was accepted")


def test_proof_matrix_is_attributable_to_channel_and_fixture_class() -> None:
    assert len(PROOF_NODES) == 12
    for channel in ("c1_telemetry", "c2_logs", "c3_worker_stderr", "c4_spans"):
        for fixture in ("secrets", "prompt_injection", "adversarial"):
            node = PROOF_NODES[f"{channel}_{fixture}"]
            assert node.startswith("tests/test_content_minimization.py::")
