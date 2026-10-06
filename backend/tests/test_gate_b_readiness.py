"""Story 5.13 Task 6: the Gate B registry and readiness generator fail loudly.

Mirrors `test_gate_a_readiness.py`. Every JUnit input is synthetic and no test
calls a provider. The guards below are the ones AC1 names: an unregistered row,
a missing file, an unreadable verdict, a stale inventory, a skipped NFR35 test,
and a registered test file absent from the XML; plus D6's tag integrity, D4's
ratchet floor, and `main`'s self-audit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import gate_b_readiness
from scripts.evidence_binding import REPO_ROOT
from scripts.gate_b_checks import (
    BLOCKING_REGRESSION_CATEGORIES,
    GATE_B_CHECKS,
    GATE_B_ROWS,
    GOLDEN_CASE_FLOOR,
    LIVE_FRESHNESS_PATHS,
    PROTECTED_CASE_FLOOR,
    GateBCheck,
    GateBRow,
    checks_for,
    registered_evidence_paths,
    validate_registry,
)
from scripts.junit_ingest import MissingTestError, RunnerReport
from scripts.junit_ingest import TestCaseResult as _CaseResult

EPICS = REPO_ROOT / "_bmad-output" / "planning-artifacts" / "epics.md"
NFR35_FILE = "backend/tests/test_postgres_integration.py"
CLEAN = {
    "dataset": "d", "evaluator": "e", "model": "m", "prompt": "p", "tool": "t",
    "policy": "pol", "application": "a", "scenario": "s", "solver": "sol",
    "image": {}, "schema_version": "x",
    "code": {"git_commit": "0" * 40, "working_tree_dirty": False},
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --------------------------------------------------------------------------- registry


def test_registry_is_internally_valid() -> None:
    validate_registry()


def test_every_gate_b_row_of_the_release_gate_table_is_registered() -> None:
    """An unregistered row is a row nobody decides. Read from epics.md itself."""
    table_rows = re.findall(r"^\| ([^|]+?) \| B \|", EPICS.read_text(encoding="utf-8"), re.M)
    assert table_rows, "could not read the Release Gate table"
    assert sorted(table_rows) == sorted(row.title for row in GATE_B_ROWS)


def test_every_row_and_every_blocking_category_has_a_check() -> None:
    for row in GATE_B_ROWS:
        assert checks_for(row.key), row.key
    covered = {c.category for c in GATE_B_CHECKS if c.row == "blocking_regressions"}
    assert set(BLOCKING_REGRESSION_CATEGORIES) <= covered


def test_a_check_naming_an_unregistered_row_is_rejected() -> None:
    stray = GateBCheck(check="stray", row="not_a_row", story="x", description="d",
                       computed="golden_case_floor")
    with pytest.raises(ValueError, match="unregistered row"):
        validate_registry(GATE_B_CHECKS + (stray,))


def test_a_row_without_a_check_is_rejected() -> None:
    with pytest.raises(ValueError, match="no contributing check"):
        validate_registry(GATE_B_CHECKS, GATE_B_ROWS + (GateBRow("orphan", "Orphan"),))


def test_a_blocking_category_without_a_check_is_rejected() -> None:
    without = tuple(c for c in GATE_B_CHECKS if c.category != "recovery")
    with pytest.raises(ValueError, match="recovery"):
        validate_registry(without)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # no source at all
        {"computed": "golden_case_floor", "evidence_path": "e.json", "verdict_key": "k",
         "verdict_pass_values": ("passed",)},
        {"evidence_path": "e.json"},  # no verdict key: a stored file is not a verdict
        {"evidence_path": "e.json", "verdict_key": "k"},  # no pass value
        {"test_files": ("backend/tests/x.py",)},  # no runner
    ],
)
def test_malformed_checks_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        GateBCheck(check="c", row="tool_routing", story="x", description="d", **kwargs)


def test_every_registered_test_file_exists_on_disk() -> None:
    for check in GATE_B_CHECKS:
        for path in list(check.test_files) + [path for path, _name in check.test_cases]:
            assert (REPO_ROOT / path).is_file(), f"{check.check}: {path} does not exist"


def test_every_registered_evidence_file_exists() -> None:
    # Story 5.13's own live files once had an exemption here while Phase C had
    # not yet generated them. They are committed now, so none is exempt.
    for path in registered_evidence_paths():
        assert (REPO_ROOT / path).is_file(), path


def test_registered_evidence_files_are_deliberate() -> None:
    assert set(registered_evidence_paths()) == {
        # Gate B's own live rows (D3, D9) and the AD-16 verdict (F2, F3).
        "evidence/story-5.13/live-multi-turn-evaluation.json",
        "evidence/story-5.13/live-golden-routing.json",
        "evidence/story-5.12/live-conversation-journeys.json",
        # Imported from Gate A by name (D13); each paired there with a live
        # machinery check on the same invariant.
        "evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json",
        "evidence/story-3.11/recovery-idempotency.json",
        "evidence/story-4.5/approval-audit-invariants.json",
        "evidence/story-4.6/state-semantics-and-accessibility.json",
        "evidence/story-5.2/content-minimization-report.json",
    }


def test_the_live_conversation_row_accepts_no_exception() -> None:
    """AD-16: no release exception marks `live_conversation_journeys` passed."""
    check = next(c for c in GATE_B_CHECKS if c.check == "live_conversation_journeys_evidence")
    assert check.exception_value is None
    assert check.verdict_key == "live_conversation_journeys"


def test_nfr35_row_reads_exactly_the_four_threshold_tests_from_the_postgres_run() -> None:
    (check,) = checks_for("nfr35_internal_thresholds")
    assert check.runner == "pytest-postgres"
    names = {name for _path, name in check.test_cases}
    source = (REPO_ROOT / NFR35_FILE).read_text(encoding="utf-8")
    declared = set(re.findall(r"^def (test_nfr35_\w+_threshold)\(", source, re.M))
    assert names == declared and len(names) == 4


def test_gate_a_is_imported_not_redeclared() -> None:
    from scripts.gate_a_checks import GATE_A_CHECKS

    by_name = {c.check: c for c in GATE_A_CHECKS}
    imported = [c for c in GATE_B_CHECKS if c.gate_a_check]
    assert imported
    for check in imported:
        source = by_name[check.gate_a_check]
        assert check.test_files == source.test_files
        assert check.evidence_path == source.evidence_path


# --------------------------------------------------------------------------- synthetic runs


def _synthetic_reports(overrides: dict[str, str] | None = None,
                       case_overrides: dict[str, str] | None = None) -> dict[str, RunnerReport]:
    """JUnit reports satisfying every registered test file and named case."""
    overrides = overrides or {}
    case_overrides = case_overrides or {}
    by_runner: dict[str, list[_CaseResult]] = {}
    for check in GATE_B_CHECKS:
        if check.runner is None:
            continue
        for path in check.test_files:
            status = overrides.get(path, "passed")
            for project in (check.required_projects or ("",)):
                by_runner.setdefault(check.runner, []).append(_CaseResult(
                    file=path, name=f"synthetic::{path}", status=status,
                    runner=check.runner, project=project,
                    detail="synthetic" if status != "passed" else "",
                ))
        for path, name in check.test_cases:
            status = case_overrides.get(name, "passed")
            by_runner.setdefault(check.runner, []).append(_CaseResult(
                file=path, name=name, status=status, runner="pytest",
                detail="synthetic" if status != "passed" else "",
            ))
    return {
        runner: RunnerReport(runner=runner, xml_path=Path(f"{runner}.xml"), cases=tuple(cases))
        for runner, cases in by_runner.items()
    }


def _report(**kwargs):
    kwargs.setdefault("bindings", dict(CLEAN))
    return gate_b_readiness.build_report(kwargs.pop("reports", _synthetic_reports()), **kwargs)


def _entry(report, check_id):
    return next(e for e in report["contributing_checks"] if e["check"] == check_id)


def test_report_carries_every_shape_element_d14_names() -> None:
    report = _report()
    for key in ("rows", "contributing_checks", "test_evidence", "dataset", "honest_gaps",
                "release_exceptions", "version_bindings", "blocking", "gate_b_passed", "passed"):
        assert key in report, key
    assert report["passed"] is report["gate_b_passed"]
    assert set(report["rows"]) == {row.key for row in GATE_B_ROWS}
    assert sorted(e["check"] for e in report["contributing_checks"]) == sorted(
        c.check for c in GATE_B_CHECKS)


def test_a_failing_test_file_blocks_its_row_and_names_the_category() -> None:
    report = _report(reports=_synthetic_reports(
        {"backend/tests/test_worker_process_recovery_postgres.py": "failed"}))
    row = report["rows"]["blocking_regressions"]
    assert row["result"] == "failed"
    assert row["categories"]["recovery"]["blocking"] == ["worker_recovery"]
    entry = next(b for b in report["blocking"] if b["check"] == "worker_recovery")
    assert entry["category"] == "recovery" and entry["gate_b_commit"] == "0" * 40
    assert report["gate_b_passed"] is False


def test_a_skipped_nfr35_test_blocks_the_nfr35_row() -> None:
    report = _report(reports=_synthetic_reports(
        case_overrides={"test_nfr35_first_run_event_meets_five_second_threshold": "skipped"}))
    assert report["rows"]["nfr35_internal_thresholds"]["result"] == "skipped"
    assert any(b["check"] == "nfr35_threshold_tests" for b in report["blocking"])


def test_an_nfr35_test_absent_from_the_postgres_run_is_missing() -> None:
    reports = _synthetic_reports()
    reports["pytest-postgres"] = replace(reports["pytest-postgres"], cases=tuple(
        c for c in reports["pytest-postgres"].cases
        if c.name != "test_nfr35_sse_reconnect_replay_meets_five_second_threshold"))
    report = _report(reports=reports)
    assert report["rows"]["nfr35_internal_thresholds"]["result"] == "missing"


def test_a_registered_test_file_absent_from_the_xml_fails_loudly() -> None:
    reports = _synthetic_reports()
    reports["pytest"] = replace(reports["pytest"], cases=tuple(
        c for c in reports["pytest"].cases if c.file != "backend/tests/test_live_golden_routing.py"))
    with pytest.raises(MissingTestError, match="test_live_golden_routing.py"):
        _report(reports=reports)
    # Reported, not raised, when asked -- and it still blocks.
    report = _report(reports=reports, strict_missing=False)
    assert _entry(report, "live_routing_machinery")["result"] == "missing"
    assert report["gate_b_passed"] is False


def test_a_playwright_check_needs_every_claimed_browser() -> None:
    reports = _synthetic_reports()
    reports["playwright"] = replace(reports["playwright"], cases=tuple(
        c for c in reports["playwright"].cases if c.project != "msedge"))
    report = _report(reports=reports)
    assert _entry(report, "gate_a.accessibility_browser_layer")["result"] == "missing"


def test_a_dirty_binding_unbinds_every_test_backed_check() -> None:
    dirty = {**CLEAN, "code": {"git_commit": "0" * 40, "working_tree_dirty": True}}
    report = _report(bindings=dirty)
    tests = [e for e in report["contributing_checks"] if e["source_kind"] == "tests"]
    assert tests and not any(e["bound"] for e in tests)


# --------------------------------------------------------------------------- evidence


def _evidence_check(path: Path, **overrides) -> GateBCheck:
    base = dict(check="probe", row="tool_routing", story="5.13", description="probe",
                evidence_path=str(path), verdict_key="tool_routing",
                verdict_pass_values=("passed",), exception_value="excepted")
    base.update(overrides)
    return GateBCheck(**base)


def _ctx(**overrides) -> gate_b_readiness._Context:
    base = dict(repo_root=REPO_ROOT, gate_commit=_git("rev-parse", "HEAD"), tree_dirty=False,
                now=datetime.now(timezone.utc), dataset={})
    base.update(overrides)
    return gate_b_readiness._Context(**base)


def _write(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_a_missing_evidence_file_blocks_its_row(tmp_path: Path) -> None:
    result, bound, detail, _ = gate_b_readiness._evidence_result(
        _evidence_check(tmp_path / "absent.json"), _ctx())
    assert (result, bound) == ("missing", False)
    assert "not found" in detail


def test_an_unreadable_evidence_file_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    result, _bound, detail, _ = gate_b_readiness._evidence_result(_evidence_check(path), _ctx())
    assert result == "missing" and "unreadable" in detail


def test_an_absent_verdict_key_is_missing_even_beside_a_passed_flag(tmp_path: Path) -> None:
    """F3/D2: `passed: true` is not the declared verdict and must not count."""
    path = _write(tmp_path, {"passed": True, "readiness": "eligible"})
    result, _bound, detail, _ = gate_b_readiness._evidence_result(_evidence_check(path), _ctx())
    assert result == "missing"
    assert "no `tool_routing` verdict" in detail


def test_a_blocked_verdict_fails_and_names_its_reasons(tmp_path: Path) -> None:
    path = _write(tmp_path, {"tool_routing": "blocked",
                             "blocking_reasons": ["protected_below_threshold"]})
    result, _bound, detail, _ = gate_b_readiness._evidence_result(_evidence_check(path), _ctx())
    assert result == "failed" and "protected_below_threshold" in detail


def _exception(**overrides) -> dict:
    record = {"owner": "Minh", "rationale": "r", "scope": "s",
              "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
              "compensating_limitation": "l"}
    record.update(overrides)
    return record


def test_a_complete_exception_is_excepted_and_listed(tmp_path: Path) -> None:
    path = _write(tmp_path, {"tool_routing": "excepted", "exception": _exception(),
                             "blocking_reasons": ["overall_below_threshold"]})
    ctx = _ctx()
    result, _bound, _detail, _ = gate_b_readiness._evidence_result(_evidence_check(path), ctx)
    assert result == "excepted"
    assert ctx.release_exceptions[0]["owner"] == "Minh"
    assert ctx.release_exceptions[0]["blocking_reasons"] == ["overall_below_threshold"]


@pytest.mark.parametrize("override", [
    {"owner": ""}, {"compensating_limitation": "  "},
    {"expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
])
def test_an_incomplete_or_expired_exception_does_not_waive(tmp_path: Path, override) -> None:
    path = _write(tmp_path, {"tool_routing": "excepted", "exception": _exception(**override)})
    ctx = _ctx()
    result, _bound, _detail, _ = gate_b_readiness._evidence_result(_evidence_check(path), ctx)
    assert result == "failed"
    assert ctx.release_exceptions == []


def test_an_exception_value_is_refused_where_none_is_declared(tmp_path: Path) -> None:
    path = _write(tmp_path, {"live_conversation_journeys": "excepted", "exception": _exception()})
    check = _evidence_check(path, verdict_key="live_conversation_journeys", exception_value=None)
    result, *_ = gate_b_readiness._evidence_result(check, _ctx())
    assert result == "failed"


# --------------------------------------------------------------------------- freshness (D12)


def _last_commit_touching_freshness_paths() -> str:
    return _git("log", "-1", "--format=%H", "HEAD", "--", *LIVE_FRESHNESS_PATHS)


def test_evidence_at_the_gate_commit_is_fresh() -> None:
    head = _git("rev-parse", "HEAD")
    assert gate_b_readiness.code_ancestor_staleness(head, head, REPO_ROOT) is None


def test_an_ancestor_with_no_live_path_change_since_is_fresh() -> None:
    last = _last_commit_touching_freshness_paths()
    head = _git("rev-parse", "HEAD")
    assert gate_b_readiness.code_ancestor_staleness(last, head, REPO_ROOT) is None


def test_an_ancestor_before_a_live_path_change_is_stale() -> None:
    last = _last_commit_touching_freshness_paths()
    stale = gate_b_readiness.code_ancestor_staleness(f"{last}^", _git("rev-parse", "HEAD"), REPO_ROOT)
    assert stale and "changed" in stale


def test_a_commit_that_is_not_an_ancestor_is_stale() -> None:
    stale = gate_b_readiness.code_ancestor_staleness("f" * 40, _git("rev-parse", "HEAD"), REPO_ROOT)
    assert stale and "not an ancestor" in stale


def test_stale_passed_evidence_is_missing_and_drops_its_exception(tmp_path: Path) -> None:
    last = _last_commit_touching_freshness_paths()
    path = _write(tmp_path, {
        "tool_routing": "excepted", "exception": _exception(),
        "version_bindings": {"code": {"git_commit": f"{_git('rev-parse', last + '^')}"}},
    })
    ctx = _ctx()
    check = _evidence_check(path, freshness="code_ancestor")
    result, _bound, detail, _ = gate_b_readiness._evidence_result(check, ctx)
    assert result == "missing" and "stale" in detail
    assert ctx.release_exceptions == []


def test_a_stale_inventory_digest_makes_the_live_conversation_row_missing(monkeypatch) -> None:
    import evals.live_conversations.inventory as inventory

    monkeypatch.setattr(inventory, "capability_inventory", lambda: {"digest": "0" * 64})
    report = _report()
    entry = _entry(report, "live_conversation_inventory_fresh")
    assert entry["result"] == "missing" and "inventory_digest" in entry["detail"]
    assert report["rows"]["live_conversation_journeys"]["result"] == "missing"


def test_the_committed_live_conversation_evidence_is_fresh_today() -> None:
    report = _report()
    assert _entry(report, "live_conversation_inventory_fresh")["result"] == "passed"
    assert _entry(report, "live_conversation_configuration_fresh")["result"] == "passed"


def test_a_behavioural_digest_mismatch_makes_the_row_missing(monkeypatch) -> None:
    real = gate_b_readiness._live_conversation_document

    def _drifted(ctx):
        document = real(ctx)
        return {**document, "measured_configuration": {"behavioral_digest": "1" * 64}}

    monkeypatch.setattr(gate_b_readiness, "_live_conversation_document", _drifted)
    entry = _entry(_report(), "live_conversation_configuration_fresh")
    assert entry["result"] == "missing" and "behavioral_digest" in entry["detail"]


# --------------------------------------------------------------------------- dataset (D4-D6)


def test_the_golden_dataset_meets_the_ratchet_floor() -> None:
    """D4. Deleting a case turns this red unless the same diff lowers the floor
    in `gate_b_checks.py`, which puts the reason in front of review."""
    summary = gate_b_readiness.golden_dataset_summary()
    assert summary["total_cases"] >= GOLDEN_CASE_FLOOR
    assert summary["per_capability_shortfalls"] == []
    assert summary["protected_case_count"] >= PROTECTED_CASE_FLOOR
    assert summary["tag_integrity_violations"] == []
    assert "demonstration" in summary["excluded_capabilities"]


def test_the_floor_check_goes_red_when_a_case_is_deleted(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for name in ("golden", "golden_multi_turn"):
        shutil.copytree(REPO_ROOT / "backend" / "evals" / name, root / "backend" / "evals" / name)
    victim = next((root / "backend" / "evals" / "golden" / "scheduling_inspect").glob("*.json"))
    victim.unlink()
    summary = gate_b_readiness.golden_dataset_summary(root)
    assert summary["total_cases"] == GOLDEN_CASE_FLOOR - 1
    ctx = _ctx(dataset=summary)
    check = next(c for c in GATE_B_CHECKS if c.computed == "golden_case_floor")
    result, detail, _artifact = gate_b_readiness._computed_result(check, ctx)
    assert result == "failed" and "below the floor" in detail


def test_a_capability_below_four_cases_fails_its_floor() -> None:
    summary = gate_b_readiness.golden_dataset_summary()
    short = {**summary, "per_capability_shortfalls": ["scheduling_compute"],
             "per_capability": {**summary["per_capability"], "scheduling_compute": 3}}
    check = next(c for c in GATE_B_CHECKS if c.computed == "per_capability_floor")
    result, detail, _artifact = gate_b_readiness._computed_result(check, _ctx(dataset=short))
    assert result == "failed" and "scheduling_compute (3)" in detail


def _golden(case_id: str):
    from evals.cases import load_cases

    return next(c for c in load_cases(REPO_ROOT / "backend" / "evals" / "golden")
                if c.case_id == case_id)


def test_tag_integrity_rejects_a_consequential_case_without_a_consequential_call() -> None:
    risk = gate_b_readiness._manifest_risk_by_capability()
    case = replace(_golden("scheduling-inspect-wednesday-workers"), risk_class="consequential")
    violations = gate_b_readiness.tag_integrity_violations([case], risk)
    assert violations and "consequential" in violations[0]


def test_tag_integrity_rejects_a_prohibited_case_that_does_not_refuse() -> None:
    risk = gate_b_readiness._manifest_risk_by_capability()
    case = replace(_golden("scheduling-inspect-wednesday-workers"), risk_class="prohibited")
    violations = gate_b_readiness.tag_integrity_violations([case], risk)
    assert violations and "prohibited" in violations[0]


def test_tag_integrity_reads_the_deterministic_outcome_not_the_live_one() -> None:
    """F9: two injection cases expect a live `allow`; their deterministic refuse holds."""
    risk = gate_b_readiness._manifest_risk_by_capability()
    case = _golden("scheduling-inspect-injection-fixture-field")
    assert case.live_expected_outcome == "allow"
    assert gate_b_readiness.tag_integrity_violations([case], risk) == []


def test_tag_integrity_rejects_a_consequential_call_under_an_unprotected_tag() -> None:
    """The converse: a consequential call must not escape the protected population."""
    risk = gate_b_readiness._manifest_risk_by_capability()
    case = replace(_golden("scheduling-baseline-approval-required"), risk_class="inspect")
    violations = gate_b_readiness.tag_integrity_violations([case], risk)
    assert violations and "tagged 'inspect'" in violations[0]
    # A case on an excluded capability counts toward no floor and is not judged.
    assert gate_b_readiness.tag_integrity_violations(
        [case], risk, counted_tags={"scheduling_inspect"}) == []


def test_protected_floor_counts_only_release_allowed_capabilities() -> None:
    summary = gate_b_readiness.golden_dataset_summary()
    assert "demonstration-repeat-with-approval" not in summary["protected_cases"]
    assert summary["protected_case_count"] == len(summary["protected_cases"])


# --------------------------------------------------------------------------- main


_PYTEST_XML = """<?xml version="1.0"?><testsuites><testsuite name="pytest" timestamp="2999-01-01T00:00:00">
<testcase classname="tests.test_x" name="test_a"/></testsuite></testsuites>"""
_VITEST_XML = """<?xml version="1.0"?><testsuites><testsuite name="v" timestamp="2999-01-01T00:00:00Z">
<testcase classname="src/x.test.ts" name="a"/></testsuite></testsuites>"""


def test_main_refuses_to_report_success_over_its_own_unbound_output(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(gate_b_readiness, "build_report", lambda *_a, **_k: {
        "gate_b_passed": True, "blocking": [], "rows": {}})
    monkeypatch.setattr(gate_b_readiness, "deterministic_regression_coverage", lambda: {})
    monkeypatch.setattr(gate_b_readiness, "audit_evidence_file",
                        lambda *_a, **_k: ("git_commit deadbeef touches no code file",))
    xml = {}
    for name, body in (("pytest", _PYTEST_XML), ("postgres", _PYTEST_XML),
                       ("vitest", _VITEST_XML), ("playwright", _VITEST_XML)):
        xml[name] = tmp_path / f"{name}.xml"
        xml[name].write_text(body, encoding="utf-8")
    exit_code = gate_b_readiness.main([
        "--pytest-xml", str(xml["pytest"]), "--postgres-xml", str(xml["postgres"]),
        "--vitest-xml", str(xml["vitest"]), "--playwright-xml", str(xml["playwright"]),
        "--output", str(output), "--allow-dirty", "--allow-missing",
    ])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "UNBOUND" in out and "gate_b_passed: true" not in out
    assert output.exists()


def test_main_exits_non_zero_when_gate_b_did_not_pass(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(gate_b_readiness, "build_report", lambda *_a, **_k: {
        "gate_b_passed": False, "rows": {"tool_routing": {"result": "missing"}},
        "blocking": [{"check": "live_golden_routing", "row": "tool_routing",
                      "category": None, "reason": "evidence file not found"}]})
    monkeypatch.setattr(gate_b_readiness, "deterministic_regression_coverage", lambda: {})
    monkeypatch.setattr(gate_b_readiness, "audit_evidence_file", lambda *_a, **_k: ())
    xml = tmp_path / "x.xml"
    xml.write_text(_PYTEST_XML, encoding="utf-8")
    exit_code = gate_b_readiness.main([
        "--pytest-xml", str(xml), "--postgres-xml", str(xml), "--vitest-xml", str(xml),
        "--playwright-xml", str(xml), "--output", str(tmp_path / "r.json"),
        "--allow-dirty", "--allow-missing",
    ])
    assert exit_code == 1
    assert "live_golden_routing (tool_routing)" in capsys.readouterr().out


def test_a_live_marked_test_is_not_expected_in_the_default_run(tmp_path) -> None:
    """`-m "not live"` deselects live tests on every ordinary run (NFR26), so
    they are not missing coverage. Story 5.13's real report was blocked on the
    two live tests in test_evaluation_harness.py. Mutation: make `_is_live_marked`
    return False and both assertions redden."""
    from scripts.junit_ingest import declared_pytest_cases

    module = tmp_path / "test_mixed.py"
    module.write_text(
        "import pytest\n"
        "def test_plain():\n    pass\n"
        "@pytest.mark.postgres\ndef test_other_mark():\n    pass\n"
        "@pytest.mark.live\ndef test_live():\n    pass\n"
        "@pytest.mark.live(reason='x')\ndef test_live_call():\n    pass\n"
        "@pytest.mark.live\nclass TestLive:\n    def test_inside(self):\n        pass\n"
        "class TestPlain:\n    @pytest.mark.live\n    def test_method_live(self):\n        pass\n"
        "    def test_method(self):\n        pass\n",
        encoding="utf-8",
    )
    assert declared_pytest_cases(module) == ("test_method", "test_other_mark", "test_plain")

    harness = declared_pytest_cases(REPO_ROOT / "backend/tests/test_evaluation_harness.py")
    assert "test_golden_cases_against_live_agent_are_non_authoritative" not in harness
    assert "test_live_multi_turn_suite_is_bounded_and_non_authoritative" not in harness



# --------------------------------------------------------------------------- review patches


def test_a_donor_measured_at_another_commit_is_refused(tmp_path: Path) -> None:
    donor = _write(tmp_path, {"version_bindings": {"code": {
        "git_commit": _git("rev-parse", "HEAD~1"), "working_tree_dirty": False}}})
    with pytest.raises(SystemExit, match="but HEAD is"):
        gate_b_readiness.donor_code_binding(donor)


def test_a_donor_without_a_code_binding_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="records no"):
        gate_b_readiness.donor_code_binding(_write(tmp_path, {"version_bindings": {}}))


def test_a_donor_at_head_is_accepted(tmp_path: Path) -> None:
    head = _git("rev-parse", "HEAD")
    donor = _write(tmp_path, {"version_bindings": {"code": {
        "git_commit": head, "working_tree_dirty": False}}})
    # allow_dirty: this test must not depend on the developer's working tree.
    assert gate_b_readiness.donor_code_binding(donor, allow_dirty=True)["git_commit"] == head


def test_a_failed_diff_is_stale_not_fresh(monkeypatch) -> None:
    def fake_git(repo_root, *args):
        failed = args[0] == "diff"
        return subprocess.CompletedProcess(args, 128 if failed else 0, "", "fatal: bad object")

    monkeypatch.setattr(gate_b_readiness, "_git", fake_git)
    stale = gate_b_readiness.code_ancestor_staleness("a" * 40, "b" * 40, REPO_ROOT)
    assert stale and "could not diff" in stale


def test_the_inventory_freshness_check_records_both_digests() -> None:
    check = next(c for c in GATE_B_CHECKS if c.computed == "live_conversation_inventory_fresh")
    _result, _detail, artifact = gate_b_readiness._computed_result(check, _ctx())
    assert artifact["current_inventory_digest"]
    assert "evidence_inventory_digest" in artifact


def test_live_recorded_results_are_derived_from_the_routing_evidence(tmp_path: Path) -> None:
    check = next(c for c in GATE_B_CHECKS if c.check == "live_golden_routing")
    target = tmp_path / str(check.evidence_path)
    target.parent.mkdir(parents=True)
    results = [
        {"case_id": "p", "risk_class": "prohibited", "capability": "scheduling_inspect",
         "counted": True, "policy_passed": False, "grounding_passed": None},
        {"case_id": "g", "risk_class": "inspect", "capability": "scheduling_inspect",
         "counted": True, "policy_passed": True, "grounding_passed": False},
        {"case_id": "o", "risk_class": "compute", "capability": "scheduling_optimize",
         "counted": False, "not_run_reason": "not_offered_on_chat_path"},
    ]
    target.write_text(json.dumps({"runs": [{"results": results}] * 2}), encoding="utf-8")
    ctx = _ctx(repo_root=tmp_path, dataset={
        "release_allowed_capabilities": ["scheduling_inspect", "scheduling_optimize"]})
    disclosed = gate_b_readiness.live_routing_disclosure(ctx)
    assert disclosed["policy_failures"] == [
        {"case_id": "p", "risk_class": "prohibited", "counted": True, "runs_failed": 2}]
    assert [item["case_id"] for item in disclosed["grounding_failures"]] == ["g"]
    assert disclosed["not_offered_on_chat_path"] == ["o"]
    assert disclosed["release_allowed_capabilities_without_a_counted_live_case"] == [
        "scheduling_optimize"]


@pytest.mark.parametrize(
    "commit",
    [
        # Changed application/use_cases/execute_turn.py, outside D12's first paths.
        "3b97f890692faac901a3aae1552ceaf13a8b4c40",
        # Changed only evals/evaluators.py: how a live case is graded.
        "9225fcfdd621720ffb24b6c0a673240adcc31442",
    ],
)
def test_a_change_to_what_the_model_sees_or_how_it_is_graded_is_stale(commit: str) -> None:
    """Story 5.13 review: e8cb369 changed live outcomes from application/use_cases/."""
    stale = gate_b_readiness.code_ancestor_staleness(_git("rev-parse", f"{commit}^"), commit, REPO_ROOT)
    assert stale and "changed" in stale
