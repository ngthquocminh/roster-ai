from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_repair_journey_evidence import (
    REQUIRED_PROJECTS,
    REQUIRED_TESTS,
    build_document,
    parse_junit_report,
)


def _junit(*, skipped: int = 0, omit_edge: bool = False) -> str:
    suites: list[str] = []
    for project in REQUIRED_PROJECTS:
        if omit_edge and project == "msedge":
            continue
        for file_name, title in REQUIRED_TESTS.items():
            outcome = "<skipped/>" if skipped else ""
            suites.append(
                f'<testsuite name="{file_name}" hostname="{project}" tests="1" '
                f'failures="0" errors="0" skipped="{skipped}">'
                f'<testcase name="{title}" classname="{file_name}">{outcome}</testcase>'
                "</testsuite>"
            )
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
