from pathlib import Path

import pytest

from scripts.generate_state_semantics_evidence import DECLARED_BINDINGS, OUTPUT_RELATIVE, generate


def _reports(root: Path, *, state_status: str = "", skipped: bool = False, omit_edge: bool = False) -> tuple[Path, Path]:
    vitest = root / "vitest.xml"
    outcome = "<skipped/>" if skipped else state_status
    vitest.write_text(f'<testsuites><testsuite name="src/test/stateMatrix.test.tsx" tests="1"><testcase classname="src/test/stateMatrix.test.tsx" name="workflow state semantics matrix &gt; message/planner message">{outcome}</testcase></testsuite></testsuites>', encoding="utf-8")
    suites = []
    for project in ("chromium", "msedge"):
        if omit_edge and project == "msedge":
            continue
        suites.append(f'<testsuite name="journey-accessibility.spec.ts" hostname="{project}" tests="1"><testcase classname="journey-accessibility.spec.ts" name="keeps journey clean"/></testsuite>')
    playwright = root / "playwright.xml"
    playwright.write_text(f'<testsuites>{"".join(suites)}</testsuites>', encoding="utf-8")
    return vitest, playwright


def _generate(tmp_path: Path, **kwargs):
    vitest, playwright = _reports(tmp_path, **kwargs)
    return generate(vitest_path=vitest, playwright_path=playwright, repo_root=Path(__file__).resolve().parents[2], output_path=tmp_path / "evidence.json", allow_dirty=True)


def test_all_pass_writes_passed_true(tmp_path: Path) -> None:
    document = _generate(tmp_path)
    assert document["passed"] is True
    assert "frontend/e2e/support/apiStubs.ts" in document["tested_artifact_digests"]
    assert "frontend/e2e/support/repairJourneyStubState.ts" in document["tested_artifact_digests"]


def test_failing_source_writes_passed_false(tmp_path: Path) -> None:
    document = _generate(tmp_path, state_status='<failure message="boom"/>')
    assert document["passed"] is False


@pytest.mark.parametrize("kwargs", [{"skipped": True}, {"omit_edge": True}])
def test_refused_report_writes_nothing(tmp_path: Path, kwargs: dict) -> None:
    output = tmp_path / "evidence.json"
    with pytest.raises(ValueError):
        _generate(tmp_path, **kwargs)
    assert not output.exists()


def test_missing_declared_binding_names_key_and_writes_nothing(tmp_path: Path) -> None:
    vitest, playwright = _reports(tmp_path)
    output = tmp_path / "evidence.json"
    bindings = {key: value for key, value in DECLARED_BINDINGS.items() if key != "policy"}
    with pytest.raises(ValueError, match="policy"):
        generate(vitest_path=vitest, playwright_path=playwright, repo_root=Path(__file__).resolve().parents[2], output_path=output, allow_dirty=True, declared_bindings=bindings)
    assert not output.exists()
