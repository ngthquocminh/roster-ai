from pathlib import Path

import pytest

from evals.approval_audit_report import DECLARED_BINDINGS, PROOF_NODES, _junit_outcome, write_approval_audit_report


def _verdicts(value=True):
    return {name: value for name in PROOF_NODES}


def _junit(path: Path, *, tests=1, failures=0, errors=0, skipped=0):
    path.write_text(f'<testsuites><testsuite tests="{tests}" failures="{failures}" errors="{errors}" skipped="{skipped}"/></testsuites>', encoding="utf-8")
    return path


def test_all_pass_writes_a_non_blocking_report(tmp_path):
    output = tmp_path / "report.json"
    report = write_approval_audit_report(output, verdicts=_verdicts(), allow_dirty=True)
    assert report["passed"] is True
    assert report["release_blocking"] is False
    assert output.exists()


def test_one_failure_writes_a_release_blocking_report(tmp_path):
    output = tmp_path / "report.json"
    verdicts = _verdicts()
    verdicts["fault_audit"] = False
    report = write_approval_audit_report(output, verdicts=verdicts, failures={"fault_audit": "boom"}, allow_dirty=True)
    assert report["passed"] is False
    assert report["release_blocking"] is True
    assert report["failures"] == {"fault_audit": "boom"}
    assert output.exists()


def test_incomplete_verdict_refuses_to_write(tmp_path):
    output = tmp_path / "report.json"
    with pytest.raises(ValueError, match="exactly"):
        write_approval_audit_report(output, verdicts={}, allow_dirty=True)
    assert not output.exists()


def test_missing_binding_refuses_to_write(tmp_path):
    output = tmp_path / "report.json"
    bindings = dict(DECLARED_BINDINGS)
    bindings.pop("policy")
    with pytest.raises(ValueError, match="policy"):
        write_approval_audit_report(output, verdicts=_verdicts(), declared_bindings=bindings, allow_dirty=True)
    assert not output.exists()


def test_all_skipped_junit_is_not_a_pass(tmp_path):
    passed, detail = _junit_outcome(_junit(tmp_path / "result.xml", tests=1, skipped=1))
    assert passed is False
    assert "skipped" in detail
