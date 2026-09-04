"""Gate A check registry, JUnit ingestion, and readiness-report tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.gate_a_checks import (
    AR28_INVARIANTS,
    ALL_INVARIANTS,
    GATE_A_CHECKS,
    NFR29_GATES,
    GateACheck,
    checks_for,
    contributing_stories,
    invariant_keys,
    validate_registry,
)
from scripts.junit_ingest import (
    MissingTestError,
    file_outcomes,
    parse_junit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


PYTEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" tests="4">
<testcase classname="tests.test_auth_api" name="test_ok" time="0.1" />
<testcase classname="tests.test_auth_api" name="test_ok_two" time="0.1" />
<testcase classname="tests.test_postgres_integration" name="test_needs_db" time="0.0">
  <skipped type="pytest.skip" message="PostgreSQL integration service is not available" />
</testcase>
<testcase classname="tests.test_seed_planner" name="test_bad" time="0.1">
  <failure message="boom">trace</failure>
</testcase>
</testsuite></testsuites>
"""

VITEST_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<testsuites name="vitest tests" tests="2">
  <testsuite name="src/lib/errors.test.ts" tests="2">
    <testcase classname="src/lib/errors.test.ts" name="a &gt; b" time="0.001"></testcase>
    <testcase classname="src/lib/errors.test.ts" name="a &gt; c" time="0.001"></testcase>
  </testsuite>
</testsuites>
"""

# Playwright's classname is relative to testDir (`e2e`), and every test appears
# once per browser project (hostname carries chromium / msedge).
PLAYWRIGHT_XML = """<testsuites id="" name="" tests="2">
<testsuite name="harness.spec.ts" hostname="chromium" tests="1">
<testcase name="serves the catalogue" classname="harness.spec.ts" time="1.5">
</testcase>
</testsuite>
<testsuite name="harness.spec.ts" hostname="msedge" tests="1">
<testcase name="serves the catalogue" classname="harness.spec.ts" time="1.8">
</testcase>
</testsuite>
</testsuites>
"""


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_registry_is_internally_valid():
    validate_registry()


def test_ar28_names_exactly_its_six_invariants():
    assert tuple(inv.key for inv in AR28_INVARIANTS) == (
        "postgresql_site_membership",
        "immutable_fixtures",
        "normalized_scenario_reads",
        "authenticated_readonly_scenario_data",
        "parity_tests",
        "negative_mutation_tests",
    )
    assert all(inv.authority == "AR28" for inv in AR28_INVARIANTS)


def test_accessibility_is_tracked_as_nfr29_not_as_an_ar28_invariant():
    """AR28 lists six; accessibility reaches the gate via AC1's Given + NFR29."""
    assert tuple(inv.key for inv in NFR29_GATES) == (
        "accessibility_and_responsiveness",
        # Added 2026-08-25 by Story 3.11's code review. NFR29 names
        # "idempotency ... recovery" alongside accessibility, and 3.11's proof
        # artifact was registered nowhere -- so Gate A reported green because
        # the proof was unbound, not because it held.
        "recovery_and_idempotency",
        "repair_browser_journey",
        "approval_and_audit_invariants",
        "workflow_state_semantics",
        "content_minimization",
    )
    assert all(inv.authority == "NFR29" for inv in NFR29_GATES)
    ar28_keys = {inv.key for inv in AR28_INVARIANTS}
    assert "accessibility_and_responsiveness" not in ar28_keys


def test_every_invariant_has_at_least_one_contributing_check():
    for key in invariant_keys():
        assert checks_for(key), f"invariant {key} has no contributing check"


def test_story_3_12_registers_live_and_evidence_proofs_and_extends_accessibility():
    repair_checks = {check.check: check for check in GATE_A_CHECKS if check.story == "3.12"}
    assert set(repair_checks) == {
        "repair_browser_journey_proof",
        "repair_browser_journey_evidence",
        "repair_browser_journey_machinery",
    }
    assert repair_checks["repair_browser_journey_proof"].required_projects == (
        "chromium",
        "msedge",
    )
    assert repair_checks["repair_browser_journey_evidence"].evidence_path == (
        "evidence/story-3.12/repair-browser-journey.json"
    )
    # The evidence check reads a stored `passed` flag and the generator never
    # writes a failing artifact, so the flag outlives a journey that breaks.
    # Story 3.11's `recovery_idempotency_report_machinery` set the precedent:
    # no invariant may rest on a static evidence file alone.
    machinery = repair_checks["repair_browser_journey_machinery"]
    assert machinery.runner == "pytest"
    assert machinery.test_files == ("backend/tests/test_repair_journey_evidence.py",)
    assert machinery.evidence_path is None
    accessibility = next(
        check for check in GATE_A_CHECKS if check.check == "accessibility_browser_layer"
    )
    assert "frontend/e2e/repair-journey-accessibility.spec.ts" in accessibility.test_files


def test_all_ten_gate_a_stories_contribute_a_check():
    """AC2 says 'each contributing Story 1.1-1.10 check' — all ten, not four."""
    expected = {f"1.{n}" for n in range(1, 11)}
    assert expected <= set(contributing_stories())


def test_the_gate_machinery_holds_itself_to_the_gate():
    """Story 1.11's own tests are registered, so a broken convention blocks.

    Without this the report is blind to the health of the thing computing it:
    the originally shipped report was generated from a pytest run with thirteen
    `test_evidence_convention.py` cases failing, and reported every invariant
    green because those tests contributed to no check.
    """
    own = [c for c in GATE_A_CHECKS if c.story == "1.11"]
    assert own, "story 1.11 registers no check for its own machinery"
    registered = {path for c in own for path in c.test_files}
    assert "backend/tests/test_evidence_convention.py" in registered


def test_story_sort_orders_ten_after_one():
    """`float("1.10") == float("1.1")`, which made the two tie unstably."""
    order = list(contributing_stories())
    assert order.index("1.1") < order.index("1.2") < order.index("1.10")


def test_registry_covers_more_than_the_four_evidence_files():
    """A rollup limited to evidence files covers only 2 of AR28's 6."""
    invariants_with_evidence_only = set()
    for inv in ALL_INVARIANTS:
        proofs = checks_for(inv.key)
        if all(c.evidence_path for c in proofs):
            invariants_with_evidence_only.add(inv.key)
    assert not invariants_with_evidence_only, (
        "these invariants rest on evidence files alone: "
        f"{invariants_with_evidence_only}"
    )


def test_a_check_without_a_proving_artifact_is_rejected():
    with pytest.raises(ValueError, match="proving artifact"):
        GateACheck(
            check="hollow",
            story="1.1",
            invariant="immutable_fixtures",
            description="no proof",
        )


def test_a_check_declaring_files_without_a_runner_is_rejected():
    with pytest.raises(ValueError, match="runner"):
        GateACheck(
            check="runnerless",
            story="1.1",
            invariant="immutable_fixtures",
            description="files but no runner",
            test_files=("backend/tests/test_gate_a_cutover.py",),
        )


# ---------------------------------------------------------------------------
# The registry must describe reality, not the stories' historical file lists
# ---------------------------------------------------------------------------


def test_every_registered_test_file_exists_on_disk():
    """Anti-rot: Story 1.9's legacy sweep deleted files earlier stories listed."""
    missing = [
        path
        for check in GATE_A_CHECKS
        for path in check.test_files
        if not (REPO_ROOT / path).is_file()
    ]
    assert not missing, f"registered test files that no longer exist: {missing}"


def test_every_registered_evidence_file_exists_on_disk():
    missing = [
        check.evidence_path
        for check in GATE_A_CHECKS
        if check.evidence_path and not (REPO_ROOT / check.evidence_path).is_file()
    ]
    assert not missing, f"registered evidence files that do not exist: {missing}"


def test_api_parity_binds_a_test_that_still_exists():
    """File-granularity binding cannot notice a deleted test; this can.

    `api_parity` declares `test_postgres_integration.py`, which holds ~50 cases.
    `file_outcomes()` rolls up per file and `declared_pytest_cases()` recovers
    expectations from that same source, so deleting the one test that actually
    proves API parity removes the expectation along with the proof — the file
    still passes and the check still reports green over nothing.

    That is precisely the failure the 2026-08-18 swap was meant to end, so the
    binding is pinned by name here until the check can bind a node id.
    """
    from scripts.junit_ingest import declared_pytest_cases

    check = next(c for c in GATE_A_CHECKS if c.check == "api_parity")
    assert check.test_files == ("backend/tests/test_postgres_integration.py",)

    declared = declared_pytest_cases(REPO_ROOT / check.test_files[0])
    assert (
        "test_gate_a_projection_api_matches_every_contract_record_for_both_fixtures"
        in declared
    ), "api_parity's proving test is gone; the check now proves nothing"


def test_registered_evidence_files_are_the_five_known_ones():
    """A stored `passed` flag answering a present-tense question is a category
    error the registry tolerates only where a shared CI runner cannot reproduce
    the measurement. Keep that set small and named, so growth is deliberate.

    It shrank from four to three on 2026-08-18: Story 1.9's
    `viewer_parity_evidence` was replaced by `api_parity`, a live pytest check
    (see `gate_a_checks.py`). The 1.9 evidence file still exists and is still a
    true record of its commit — it is simply no longer a verdict about today.
    Adding a fourth is a decision, not a detail.
    """
    declared = {c.evidence_path for c in GATE_A_CHECKS if c.evidence_path}
    assert declared == {
        "evidence/story-1.4/nfr35-scenario-data-load.json",
        "evidence/story-1.5/nfr35-evidence-target-resolution.json",
        "evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json",
        # Grew back to four deliberately on 2026-08-25 (Story 3.11 code
        # review): the recovery/idempotency proof declared itself
        # release-blocking while being read by nothing. It is paired with a
        # live pytest check on its generator, so the invariant does not rest
        # on a stored flag alone.
        "evidence/story-3.11/recovery-idempotency.json",
        # Story 3.12 pairs this clean-tree browser measurement with the live
        # Playwright journey check registered on the same invariant.
        "evidence/story-3.12/repair-browser-journey.json",
        # Story 4.5 deliberately adds a sixth stored measurement and pairs it
        # with a live machinery check so the invariant never rests on a flag.
        "evidence/story-4.5/approval-audit-invariants.json",
        # Story 4.6 pairs this two-runner measurement with live Vitest,
        # Playwright, and generator-machinery checks on the same invariant.
        "evidence/story-4.6/state-semantics-and-accessibility.json",
        # Story 5.2 deliberately extends NFR29 with content minimization and
        # pairs this stored verdict with live generator-machinery coverage.
        "evidence/story-5.2/content-minimization-report.json",
    }


def test_runner_matches_the_file_location():
    for check in GATE_A_CHECKS:
        for path in check.test_files:
            if check.runner == "pytest":
                assert path.startswith("backend/tests/")
            elif check.runner == "playwright":
                assert path.startswith("frontend/e2e/")
            elif check.runner == "vitest":
                assert path.startswith("frontend/src/")


def test_vitest_registered_files_are_inside_the_configured_include():
    """`frontend/vite.config.ts` scopes test.include to src/**."""
    for check in GATE_A_CHECKS:
        if check.runner == "vitest":
            for path in check.test_files:
                assert path.startswith("frontend/src/"), (
                    f"{path} is outside Vitest's src/** include and would "
                    "never appear in the XML"
                )


def test_storys_gate_a_guards_are_registered_by_name():
    """Story 1.9's three guards must remain contributing checks."""
    registered = {p for c in GATE_A_CHECKS for p in c.test_files}
    for guard in (
        "frontend/src/features/scenario-data/ScenarioDataParity.test.tsx",
        "frontend/src/test/scenarioDataBoundaries.test.ts",
        "frontend/src/test/legacyReachability.test.ts",
    ):
        assert guard in registered


# ---------------------------------------------------------------------------
# Registry drift — the committed report must describe the live registry
# ---------------------------------------------------------------------------


COMMITTED_READINESS_REPORT = (
    REPO_ROOT / "evidence" / "story-1.11" / "gate-a-readiness-report.json"
)


def _committed_report() -> dict:
    return json.loads(COMMITTED_READINESS_REPORT.read_text(encoding="utf-8"))


def test_committed_readiness_report_covers_exactly_the_live_registry():
    """The release-blocking artifact must not describe a registry that no
    longer exists.

    Epic 4 retrospective action A5. `approval_and_audit_invariants` — Story
    4.5's whole invariant — was ABSENT from this committed report at `8b2b5b1`,
    so the artifact that decides release described a stale registry for an
    entire story before a later commit silently caught it up. Nothing compared
    the two, so nothing failed.

    Regenerating the report is mandatory for any story that adds a Gate A
    check (`docs/GATE-A-RUNBOOK.md`); this test is what makes forgetting it
    loud. It asserts identity, not counts: a check renamed in the registry and
    not regenerated fails here even though the totals still match.
    """
    reported = {entry["check"] for entry in _committed_report()["contributing_checks"]}
    registered = {check.check for check in GATE_A_CHECKS}

    assert reported == registered, (
        "gate-a-readiness-report.json is out of date with GATE_A_CHECKS. "
        f"missing from the report: {sorted(registered - reported)}; "
        f"stale in the report: {sorted(reported - registered)}. "
        "Regenerate it per docs/GATE-A-RUNBOOK.md and commit the result."
    )


def test_committed_readiness_report_covers_exactly_the_live_nfr29_gates():
    """The same drift, one level up: an accessibility invariant can be added to
    `NFR29_GATES` without the artifact naming it.

    Split from the check-level assertion above because the two fail for
    different reasons and a story adding an invariant should be told which one
    it forgot.
    """
    reported = set(_committed_report()["nfr29_gates"])
    registered = {gate.key for gate in NFR29_GATES}

    assert reported == registered, (
        "gate-a-readiness-report.json's nfr29_gates is out of date. "
        f"missing from the report: {sorted(registered - reported)}; "
        f"stale in the report: {sorted(reported - registered)}."
    )


# ---------------------------------------------------------------------------
# JUnit ingestion — identity normalization across three runners
# ---------------------------------------------------------------------------


def test_pytest_dotted_classname_normalizes_to_a_repo_relative_path(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    assert {c.file for c in report.cases} == {
        "backend/tests/test_auth_api.py",
        "backend/tests/test_postgres_integration.py",
        "backend/tests/test_seed_planner.py",
    }


def test_vitest_path_classname_normalizes_to_a_repo_relative_path(tmp_path):
    report = parse_junit(_write(tmp_path, "v.xml", VITEST_XML), runner="vitest")
    assert {c.file for c in report.cases} == {"frontend/src/lib/errors.test.ts"}


def test_playwright_classname_is_resolved_against_its_test_dir(tmp_path):
    report = parse_junit(
        _write(tmp_path, "w.xml", PLAYWRIGHT_XML), runner="playwright"
    )
    assert {c.file for c in report.cases} == {"frontend/e2e/harness.spec.ts"}
    # One case per browser project.
    assert len(report.cases) == 2


def test_statuses_are_read_from_the_case_children(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    by_name = {c.name: c.status for c in report.cases}
    assert by_name["test_ok"] == "passed"
    assert by_name["test_needs_db"] == "skipped"
    assert by_name["test_bad"] == "failed"


# ---------------------------------------------------------------------------
# Aggregation — the anti-rot and skipped-is-not-passed rules
# ---------------------------------------------------------------------------


def test_a_file_whose_cases_all_pass_is_passed(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    outcomes = file_outcomes([report], ["backend/tests/test_auth_api.py"])
    assert outcomes["backend/tests/test_auth_api.py"].status == "passed"


def test_a_skipped_test_is_not_a_passed_test(tmp_path):
    """postgres-marked tests skip cleanly with no Docker; that proves nothing."""
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    outcome = file_outcomes(
        [report], ["backend/tests/test_postgres_integration.py"]
    )["backend/tests/test_postgres_integration.py"]
    assert outcome.status == "skipped"
    assert outcome.status != "passed"
    assert "not available" in outcome.detail


def test_a_failing_case_makes_the_file_failed(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    outcomes = file_outcomes([report], ["backend/tests/test_seed_planner.py"])
    assert outcomes["backend/tests/test_seed_planner.py"].status == "failed"


def test_a_registry_declared_file_absent_from_the_xml_fails_loudly(tmp_path):
    """Without this the registry silently decays the first time a test moves."""
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    with pytest.raises(MissingTestError, match="test_identity_schema"):
        file_outcomes(
            [report],
            ["backend/tests/test_identity_schema.py"],
            strict=True,
        )


def test_absent_file_is_reported_as_missing_when_not_strict(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    outcomes = file_outcomes(
        [report], ["backend/tests/test_identity_schema.py"], strict=False
    )
    assert outcomes["backend/tests/test_identity_schema.py"].status == "missing"


def test_outcomes_merge_across_runner_reports(tmp_path):
    reports = [
        parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest"),
        parse_junit(_write(tmp_path, "v.xml", VITEST_XML), runner="vitest"),
    ]
    outcomes = file_outcomes(
        reports,
        ["backend/tests/test_auth_api.py", "frontend/src/lib/errors.test.ts"],
    )
    assert outcomes["backend/tests/test_auth_api.py"].status == "passed"
    assert outcomes["frontend/src/lib/errors.test.ts"].status == "passed"


def test_playwright_file_needs_every_browser_project_green(tmp_path):
    failing = PLAYWRIGHT_XML.replace(
        '<testcase name="serves the catalogue" classname="harness.spec.ts" time="1.8">\n</testcase>',
        '<testcase name="serves the catalogue" classname="harness.spec.ts" time="1.8">'
        '<failure message="edge broke">trace</failure></testcase>',
    )
    report = parse_junit(_write(tmp_path, "w.xml", failing), runner="playwright")
    outcomes = file_outcomes([report], ["frontend/e2e/harness.spec.ts"])
    assert outcomes["frontend/e2e/harness.spec.ts"].status == "failed"


def test_case_counts_are_recorded_for_the_report(tmp_path):
    report = parse_junit(_write(tmp_path, "p.xml", PYTEST_XML), runner="pytest")
    outcome = file_outcomes([report], ["backend/tests/test_auth_api.py"])[
        "backend/tests/test_auth_api.py"
    ]
    assert outcome.total == 2
    assert outcome.passed == 2


# ---------------------------------------------------------------------------
# Readiness report generation
# ---------------------------------------------------------------------------


def _synthetic_reports(status: str = "passed", overrides: dict | None = None):
    """Build JUnit reports that satisfy every registry-declared file."""
    from scripts.junit_ingest import RunnerReport, TestCaseResult

    overrides = overrides or {}
    by_runner: dict[str, list] = {}
    for check in GATE_A_CHECKS:
        if not check.runner:
            continue
        for path in check.test_files:
            case_status = overrides.get(path, status)
            by_runner.setdefault(check.runner, []).append(
                TestCaseResult(
                    file=path,
                    name=f"synthetic::{path}",
                    status=case_status,
                    detail="synthetic" if case_status != "passed" else "",
                    runner=check.runner,
                )
            )
    return [
        RunnerReport(runner=runner, xml_path=Path(f"{runner}.xml"), cases=tuple(cases))
        for runner, cases in by_runner.items()
    ]


def test_report_carries_every_shape_element_ac2_names():
    from scripts.gate_a_readiness import build_report

    report = build_report(_synthetic_reports(), allow_dirty=True)
    for key in (
        "story",
        "measurement_date",
        "accountable_owner",
        "fixtures",
        "contract_digests",
        "contributing_checks",
        "ar28_invariants",
        "version_bindings",
        "blocking",
        "gate_a_passed",
    ):
        assert key in report, f"report is missing {key}"
    assert report["accountable_owner"] == "Product/QA"
    assert "schema_version" in report["version_bindings"]


def test_every_registry_check_appears_once_in_contributing_checks():
    from scripts.gate_a_readiness import build_report

    report = build_report(_synthetic_reports(), allow_dirty=True)
    ids = [entry["check"] for entry in report["contributing_checks"]]
    assert sorted(ids) == sorted(c.check for c in GATE_A_CHECKS)


def test_contributing_check_entries_carry_their_invariant_and_binding():
    from scripts.gate_a_readiness import build_report

    report = build_report(_synthetic_reports(), allow_dirty=True)
    for entry in report["contributing_checks"]:
        assert entry["story"]
        assert entry["invariant"]
        assert entry["result"]
        assert entry["source"]
        assert isinstance(entry["bound"], bool)


def test_accessibility_check_is_not_attributed_to_an_ar28_invariant():
    from scripts.gate_a_readiness import build_report

    report = build_report(_synthetic_reports(), allow_dirty=True)
    entries = {e["check"]: e for e in report["contributing_checks"]}
    a11y = entries["accessibility_browser_layer"]
    assert a11y["authority"] == "NFR29"
    assert a11y["ar28_invariant"] is None
    assert set(report["ar28_invariants"]) == {
        inv.key for inv in AR28_INVARIANTS
    }


def test_a_failing_test_file_blocks_the_gate_and_is_named():
    from scripts.gate_a_readiness import build_report

    target = "backend/tests/test_gate_a_mutation_audit.py"
    report = build_report(
        _synthetic_reports(overrides={target: "failed"}), allow_dirty=True
    )
    assert report["gate_a_passed"] is False
    assert report["blocking"], "a bare false with no blocking[] is not acceptable"
    named = " ".join(str(b) for b in report["blocking"])
    assert "backend_mutation_denial" in named
    assert report["ar28_invariants"]["negative_mutation_tests"]["result"] != "passed"


def test_a_skipped_test_file_blocks_the_gate():
    """Running without Docker Postgres must not produce a green report."""
    from scripts.gate_a_readiness import build_report

    target = "backend/tests/test_postgres_integration.py"
    report = build_report(
        _synthetic_reports(overrides={target: "skipped"}), allow_dirty=True
    )
    assert report["gate_a_passed"] is False
    named = " ".join(str(b) for b in report["blocking"])
    assert "site_membership_and_authentication" in named


def test_blocking_entries_name_the_exact_gate_per_nfr29():
    from scripts.gate_a_readiness import build_report

    report = build_report(
        _synthetic_reports(overrides={"frontend/e2e/responsive.spec.ts": "failed"}),
        allow_dirty=True,
    )
    entry = next(
        b for b in report["blocking"] if b["check"] == "accessibility_browser_layer"
    )
    assert entry["invariant"] == "accessibility_and_responsiveness"
    assert entry["reason"]


def test_generation_on_a_dirty_tree_records_the_override():
    from scripts.gate_a_readiness import build_report

    report = build_report(_synthetic_reports(), allow_dirty=True)
    if report["version_bindings"]["code"]["working_tree_dirty"]:
        assert report["version_bindings"]["binding_override"]


def test_unbound_evidence_blocks_the_gate(tmp_path, monkeypatch):
    """AC2: any missing or unbound contributing result blocks the gate."""
    from scripts import gate_a_readiness

    report = gate_a_readiness.build_report(_synthetic_reports(), allow_dirty=True)
    evidence_entries = [
        e for e in report["contributing_checks"] if e["source_kind"] == "evidence"
    ]
    assert evidence_entries, "expected evidence-backed checks"
    for entry in evidence_entries:
        if not entry["bound"]:
            assert any(
                b["check"] == entry["check"] for b in report["blocking"]
            ), f"{entry['check']} is unbound but does not block"


def test_main_refuses_to_report_success_over_its_own_unbound_output(
    tmp_path, monkeypatch, capsys
):
    """It audited every other evidence file but never the one it wrote.

    Regression for a Story 3.12 review miss: the readiness report was generated
    while HEAD was a docs-only commit, so `code.git_commit` touched no code
    file. `_is_code_path` excludes `docs/`, `evidence/`, `_bmad-output/` and
    `*.md`, so the artifact proved nothing about the behaviour it measured —
    and `main()` still printed `gate_a_passed: true` and exited 0. The repo-wide
    convention sweep caught it, but only on a later run; CI found it, a human
    did not.
    """
    from scripts import gate_a_readiness

    output = tmp_path / "report.json"
    monkeypatch.setattr(
        gate_a_readiness,
        "build_report",
        lambda *_a, **_k: {
            "gate_a_passed": True,
            "blocking": [],
            "ar28_invariants": {},
            "nfr29_gates": {},
            "ac2_gates": {},
        },
    )
    monkeypatch.setattr(
        gate_a_readiness,
        "audit_evidence_file",
        lambda *_a, **_k: ("git_commit deadbeef touches no code file",),
    )

    exit_code = gate_a_readiness.main(
        [
            "--pytest-xml", str(_write(tmp_path, "pytest.xml", PYTEST_XML)),
            "--vitest-xml", str(_write(tmp_path, "vitest.xml", VITEST_XML)),
            "--playwright-xml", str(_write(tmp_path, "playwright.xml", PLAYWRIGHT_XML)),
            "--output", str(output),
            "--allow-dirty",
            "--allow-missing",
        ]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "UNBOUND" in out
    assert "touches no code file" in out
    # The file is still written — the operator needs to see it — but the
    # non-zero exit is what stops it being committed.
    assert output.exists()
    assert "gate_a_passed: true" not in out


def test_build_report_accepts_pre_resolved_bindings():
    """Regenerating several evidence files in one pass needs this.

    `resolve_bindings()` refuses a dirty tree, so writing the first evidence
    file would make the second file's resolution fail. All binding sets must be
    resolved while the tree is still clean.
    """
    from scripts.evidence_binding import resolve_bindings
    from scripts.gate_a_readiness import build_report

    pre = resolve_bindings(
        {
            "evaluator": "pre-resolved",
            "model": "not applicable",
            "prompt": "not applicable",
            "tool": "pre-resolved",
            "policy": "pre-resolved",
            "application": "pre-resolved",
            "solver": "not applicable",
        },
        allow_dirty=True,
    )
    report = build_report(_synthetic_reports(), bindings=pre)
    assert report["version_bindings"] is pre
    assert report["version_bindings"]["evaluator"] == "pre-resolved"


def test_boundness_comes_from_the_binding_block_not_a_live_resample():
    """Earlier writes in the same pass must not mark later checks unbound.

    The binding block records the tree state at resolution time. Re-sampling
    `git status` while building the report would see the evidence files the
    same regeneration pass has already written and wrongly report every
    test-backed check as unbound.
    """
    from scripts.gate_a_readiness import build_report

    clean = {
        "dataset": "d", "evaluator": "e", "model": "m", "prompt": "p",
        "tool": "t", "policy": "pol", "application": "a", "scenario": "s",
        "solver": "sol", "image": {}, "schema_version": "x",
        "code": {"git_commit": "abc123", "working_tree_dirty": False},
    }
    report = build_report(_synthetic_reports(), bindings=clean)
    test_backed = [
        e for e in report["contributing_checks"] if e["source_kind"] == "tests"
    ]
    assert test_backed
    assert all(e["bound"] for e in test_backed)

    dirty = {**clean, "code": {"git_commit": "abc123", "working_tree_dirty": True}}
    report = build_report(_synthetic_reports(), bindings=dirty)
    test_backed = [
        e for e in report["contributing_checks"] if e["source_kind"] == "tests"
    ]
    assert not any(e["bound"] for e in test_backed)
