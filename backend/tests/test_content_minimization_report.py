"""Fail-closed tests for Story 5.2's evidence generator."""
import ast
from pathlib import Path

from evals.content_minimization_report import (
    MATRIX_NODES,
    PROOF_NODES,
    SURFACE_NODES,
    _junit_outcome,
    write_report,
)

SUITE = Path(__file__).resolve().parent / "test_content_minimization.py"


def _declared_test_names() -> set[str]:
    tree = ast.parse(SUITE.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


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
    """Twelve cells must be twelve DIFFERENT tests that actually exist.

    The previous version asserted only that each name existed and started with
    the module prefix, so it passed unchanged with all twelve cells pointing at
    a single test -- which is what had shipped. Distinctness is the whole point
    of the matrix: without it a red cell is not attributable to a channel
    (code review of story-5.2).
    """
    declared = _declared_test_names()

    assert len(MATRIX_NODES) == 12
    for channel in ("c1_telemetry", "c2_logs", "c3_worker_stderr", "c4_spans"):
        for fixture in ("secrets", "prompt_injection", "adversarial"):
            node = MATRIX_NODES[f"{channel}_{fixture}"]
            assert node.startswith("tests/test_content_minimization.py::")

    # Distinct: twelve cells, twelve different node ids.
    assert len(set(MATRIX_NODES.values())) == 12, "matrix cells share a test"

    # Real: every node names a test function that exists in the suite, so a
    # rename or deletion reddens here instead of silently measuring nothing.
    for name, node in PROOF_NODES.items():
        function = node.split("::")[-1]
        assert function in declared, f"{name} names a missing test: {function}"

    # Surface nodes are additional, never a substitute for a matrix cell.
    assert set(PROOF_NODES) == set(MATRIX_NODES) | set(SURFACE_NODES)
    assert not set(MATRIX_NODES) & set(SURFACE_NODES)


def test_failure_details_never_carry_child_process_output() -> None:
    """A red node's pytest output holds the very canaries the report denies."""
    rendered = (
        Path(__file__).resolve().parents[1] / "evals/content_minimization_report.py"
    ).read_text(encoding="utf-8")
    assert "completed.stdout" not in rendered
    assert "completed.stderr" not in rendered
