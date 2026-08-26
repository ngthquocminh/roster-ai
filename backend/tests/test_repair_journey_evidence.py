from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_repair_journey_evidence import (
    REQUIRED_PROJECTS,
    REQUIRED_TESTS,
    build_document,
    junit_provenance,
    parse_junit_report,
)


def _junit(
    *,
    skipped: int = 0,
    omit_edge: bool = False,
    case_outcome: str = "",
    tests: int | None = None,
    duplicate: bool = False,
    title_suffix: str = "",
    timestamp: str = "2026-08-25T03:23:25Z",
) -> str:
    """Build a Playwright-shaped JUnit report.

    ``case_outcome`` injects a per-testcase child WITHOUT touching the
    suite-level counts, which is the only way to reach the per-testcase guard —
    ``skipped=1`` trips the counts guard first, so those branches went untested.
    """
    suites: list[str] = []
    for project in REQUIRED_PROJECTS:
        if omit_edge and project == "msedge":
            continue
        for file_name, title in REQUIRED_TESTS.items():
            outcome = "<skipped/>" if skipped else case_outcome
            suite = (
                f'<testsuite name="{file_name}" hostname="{project}" '
                f'timestamp="{timestamp}" tests="{tests if tests is not None else 1}" '
                f'failures="0" errors="0" skipped="{skipped}">'
                f'<testcase name="{title}{title_suffix}" classname="{file_name}">{outcome}</testcase>'
                "</testsuite>"
            )
            suites.append(suite)
            if duplicate:
                suites.append(suite)
    return f'<testsuites tests="{len(suites)}">{"".join(suites)}</testsuites>'


def test_junit_parser_requires_both_projects_and_both_specs(tmp_path: Path) -> None:
    report = tmp_path / "playwright.xml"
    report.write_text(_junit(), encoding="utf-8")

    outcomes = parse_junit_report(report)

    assert set(outcomes) == set(REQUIRED_PROJECTS)
    assert all(set(files) == set(REQUIRED_TESTS) for files in outcomes.values())
    assert all(passed for files in outcomes.values() for passed in files.values())


@pytest.mark.parametrize(
    ("xml", "message"),
    (
        pytest.param(_junit(omit_edge=True), "msedge", id="missing-project"),
        pytest.param(_junit(skipped=1), "skipped", id="skip-is-not-pass"),
        pytest.param("<testsuites>", "unreadable", id="malformed"),
        # The four paths below had no coverage before this review; the parser is
        # the only thing standing between a broken browser run and a green
        # evidence artifact, so each fail-closed guard needs its own test.
        pytest.param(
            _junit(case_outcome='<failure message="boom">boom</failure>'),
            "did not pass",
            id="testcase-failure-child",
        ),
        pytest.param(
            _junit(case_outcome="<skipped/>"),
            "did not pass",
            id="testcase-skipped-child",
        ),
        pytest.param(_junit(tests=0), "collected no tests", id="empty-suite"),
        pytest.param(_junit(duplicate=True), "duplicate", id="duplicate-suite"),
        pytest.param(_junit(title_suffix=" (renamed)"), "exactly one", id="wrong-testcase-name"),
    ),
)
def test_junit_parser_fails_closed(xml: str, message: str, tmp_path: Path) -> None:
    report = tmp_path / "playwright.xml"
    report.write_text(xml, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        parse_junit_report(report)


def test_evidence_document_exposes_gate_readable_verdict(tmp_path: Path) -> None:
    report = tmp_path / "playwright.xml"
    report.write_text(_junit(), encoding="utf-8")
    bindings = {"code": {"git_commit": "a" * 40, "working_tree_dirty": False}}

    document = build_document(
        parse_junit_report(report),
        bindings=bindings,
        measurement_date="2026-08-25",
    )

    assert document["passed"] is True
    assert document["results"] == {
        "journey_completion": "passed",
        "run_id_survives_reconnect": "passed",
        "evidence_link_resolves": "passed",
        "axe_browser": "passed",
        "keyboard_operable": "passed",
        "focus_management": "passed",
        "semantic_status_text": "passed",
    }
    assert document["version_bindings"] == bindings


def test_evidence_document_discloses_that_results_alias_two_spec_verdicts(
    tmp_path: Path,
) -> None:
    """Seven result keys are derived from two booleans; say so in the artifact."""
    report = tmp_path / "playwright.xml"
    report.write_text(_junit(), encoding="utf-8")

    document = build_document(
        parse_junit_report(report), bindings={}, measurement_date="2026-08-25"
    )

    derivation = document["results_derivation"]
    assert set(derivation) - {"note"} == set(document["results"])
    assert set(derivation.values()) - {derivation["note"]} == set(REQUIRED_TESTS)
    assert "NFR20" not in document["requirements"]


def test_junit_provenance_pins_the_measured_xml(tmp_path: Path) -> None:
    report = tmp_path / "playwright.xml"
    report.write_text(_junit(), encoding="utf-8")

    entry = junit_provenance(report, {}, repo_root=tmp_path)

    assert entry["junit_xml"] == "playwright.xml"
    assert len(entry["sha256"]) == 64
    assert entry["run_started"] == "2026-08-25T03:23:25Z"
    assert "stale" not in entry


def test_junit_provenance_flags_a_run_that_predates_its_bound_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`resolve_bindings` proves the tree was clean, not that the run matches it."""
    report = tmp_path / "playwright.xml"
    report.write_text(_junit(timestamp="2020-01-01T00:00:00Z"), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.generate_repair_journey_evidence.commit_date",
        lambda *_args, **_kwargs: "2026-08-25T03:23:02Z",
    )

    entry = junit_provenance(
        report, {"code": {"git_commit": "a" * 40}}, repo_root=tmp_path
    )

    assert "predates the commit" in entry["stale"]
