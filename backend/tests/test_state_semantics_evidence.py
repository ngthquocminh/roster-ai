from pathlib import Path

import pytest

from scripts.generate_state_semantics_evidence import DECLARED_BINDINGS, OUTPUT_RELATIVE, generate

REPO_ROOT = Path(__file__).resolve().parents[2]
PREFIX = "workflow state semantics matrix &gt; "


def _reports(
    root: Path,
    *,
    state_status: str = "",
    skipped: bool = False,
    omit_edge: bool = False,
    states: tuple[str, ...] = ("message/planner message",),
    declared: int | None = 1,
    declare_twice: bool = False,
    omit_vitest_file: bool = False,
    omit_playwright_file: bool = False,
) -> tuple[Path, Path]:
    outcome = "<skipped/>" if skipped else state_status
    cases = "".join(
        f'<testcase classname="src/test/stateMatrix.test.tsx" name="{PREFIX}{state}">{outcome}</testcase>'
        for state in states
    )
    # The suite publishes `STATE_MATRIX.length` through a case name so the count
    # crosses the JUnit boundary; the generator reconciles the emitted states
    # against it. A filtered run drops this case, which is a refusal.
    declarations = "" if declared is None else "".join(
        f'<testcase classname="src/test/stateMatrix.test.tsx" name="{PREFIX}declares {declared} states"/>'
        for _ in range(2 if declare_twice else 1)
    )
    suite_name = "src/other.test.tsx" if omit_vitest_file else "src/test/stateMatrix.test.tsx"
    classname = suite_name
    vitest = root / "vitest.xml"
    vitest.write_text(
        f'<testsuites><testsuite name="{suite_name}" tests="1">'
        f"{cases.replace('src/test/stateMatrix.test.tsx', classname)}"
        f"{declarations.replace('src/test/stateMatrix.test.tsx', classname)}"
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    spec = "other.spec.ts" if omit_playwright_file else "journey-accessibility.spec.ts"
    suites = [
        f'<testsuite name="{spec}" hostname="{project}" tests="1">'
        f'<testcase classname="{spec}" name="keeps journey clean"/></testsuite>'
        for project in ("chromium", "msedge")
        if not (omit_edge and project == "msedge")
    ]
    playwright = root / "playwright.xml"
    playwright.write_text(f'<testsuites>{"".join(suites)}</testsuites>', encoding="utf-8")
    return vitest, playwright


def _generate(tmp_path: Path, **kwargs):
    vitest, playwright = _reports(tmp_path, **kwargs)
    return generate(
        vitest_path=vitest,
        playwright_path=playwright,
        repo_root=REPO_ROOT,
        output_path=tmp_path / "evidence.json",
        allow_dirty=True,
    )


def test_all_pass_writes_passed_true(tmp_path: Path) -> None:
    document = _generate(tmp_path)
    assert document["passed"] is True
    assert "frontend/e2e/support/apiStubs.ts" in document["tested_artifact_digests"]
    assert "frontend/e2e/support/repairJourneyStubState.ts" in document["tested_artifact_digests"]


def test_failing_source_writes_passed_false(tmp_path: Path) -> None:
    document = _generate(tmp_path, state_status='<failure message="boom"/>')
    assert document["passed"] is False


def test_states_exclude_aggregate_case_names_carrying_a_slash(tmp_path: Path) -> None:
    """`covers … text and role/name trees` is a test title, not a state.

    Filtering on "contains a slash" admitted it, and it shipped in the artifact as
    a 61st entry against a 60-entry matrix.
    """
    document = _generate(
        tmp_path,
        states=("message/planner message", "covers all ten AC1 families with role/name trees"),
        declared=1,
    )
    assert document["results"]["states"] == ["message/planner message"]


def test_measurement_pins_the_xml_each_verdict_came_from(tmp_path: Path) -> None:
    document = _generate(tmp_path)
    for source in ("vitest", "playwright"):
        entry = document["measurement"][source]
        assert entry["junit_xml"].endswith(".xml")
        assert len(entry["sha256"]) == 64
        assert "run_started" in entry


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"skipped": True}, id="a skipped case is not a pass"),
        pytest.param({"omit_edge": True}, id="a chromium-only run misses a required project"),
        pytest.param({"declared": None}, id="a filtered run drops the count declaration"),
        pytest.param({"declared": 7}, id="declared count disagrees with emitted states"),
        pytest.param({"declare_twice": True}, id="the matrix declares its size twice"),
        pytest.param({"omit_vitest_file": True}, id="the vitest spec is absent from the report"),
        pytest.param({"omit_playwright_file": True}, id="the playwright spec is absent from the report"),
    ],
)
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
        generate(
            vitest_path=vitest,
            playwright_path=playwright,
            repo_root=REPO_ROOT,
            output_path=output,
            allow_dirty=True,
            declared_bindings=bindings,
        )
    assert not output.exists()
