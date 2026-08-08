"""Generate `evidence/story-1.11/gate-a-readiness-report.json`.

Composes the three Story 1.11 building blocks:

* :mod:`scripts.evidence_binding` — NFR27 bindings, refusing a dirty tree
* :mod:`scripts.gate_a_checks`    — which checks decide Gate A
* :mod:`scripts.junit_ingest`     — what the three test runners actually reported

Usage (the ordering matters — see docs/EVIDENCE-CONVENTION.md)::

    git commit code                 # tree must be clean before measuring
    # run the three suites, writing JUnit XML to _bmad-output/test-artifacts/gate-a/
    uv run --frozen python scripts/gate_a_readiness.py \
        --pytest-xml   ../_bmad-output/test-artifacts/gate-a/pytest.xml \
        --vitest-xml   ../_bmad-output/test-artifacts/gate-a/vitest.xml \
        --playwright-xml ../_bmad-output/test-artifacts/gate-a/playwright.xml

Exits non-zero on any check that is missing, unbound, skipped or failing.
AC2's "blocks the gate" is an enforcement obligation, not prose: a script that
can emit `gate_a_passed: false` and still exit 0 is not a gate.

`gate_a_passed: false` is a valid result. Do not tune the registry, relax a
check or soften a recorded outcome to reach `true` — the entire value of a
gate is that it can say no.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import (  # noqa: E402
    REPO_ROOT,
    audit_evidence_file,
    contract_digests,
    resolve_bindings,
    working_tree_status,
)
from scripts.gate_a_checks import (  # noqa: E402
    AR28_INVARIANTS,
    ALL_INVARIANTS,
    GATE_A_CHECKS,
    GateACheck,
    validate_registry,
)
from scripts.junit_ingest import (  # noqa: E402
    RunnerReport,
    file_outcomes,
    parse_junit,
)


DEFAULT_OUTPUT = REPO_ROOT / "evidence" / "story-1.11" / "gate-a-readiness-report.json"

#: Results that prove nothing. "skipped" is here on purpose: `postgres`-marked
#: tests skip cleanly with no Docker service up, and a silent skip would
#: otherwise produce a green report over an unexercised invariant.
_NON_PROVING = ("failed", "skipped", "missing")

_DECLARED_BINDINGS = {
    "evaluator": (
        "pytest (backend), Vitest 4.1.10 (frontend unit), "
        "Playwright 1.62.1 (browser) — results read from JUnit XML"
    ),
    "model": "not applicable — AgentRuntime is Epic 2, outside Gate A",
    "prompt": "not applicable — no model invocation at Gate A",
    "tool": (
        "FastAPI TestClient, PostgreSQL 18, React Testing Library with jsdom, "
        "Playwright Chromium and Microsoft Edge, axe-core"
    ),
    "policy": (
        "AR28 Gate A invariants; NFR27 version bindings; NFR29 accessibility "
        "and parity regressions block release regardless of aggregate "
        "helpfulness"
    ),
    "application": "local backend and frontend source tree",
    "solver": "not applicable — no solver run at Gate A",
}


def _fixture_entries() -> list[dict[str, str]]:
    from scripts.gate_a_cutover import default_fixtures

    return [
        {
            "fixture_id": spec.fixture_id,
            "version": spec.version,
            "contract": f"data/contract/{spec.fixture_id}.projection-v1.json",
        }
        for spec in default_fixtures()
    ]


def _evidence_result(
    check: GateACheck, *, repo_root: Path
) -> tuple[str, bool, str]:
    """Return ``(result, bound, detail)`` for an evidence-backed check."""
    path = repo_root / str(check.evidence_path)
    if not path.is_file():
        return "missing", False, f"evidence file not found: {check.evidence_path}"

    violations = audit_evidence_file(path, repo_root=repo_root)
    document = json.loads(path.read_text(encoding="utf-8"))
    passed = document.get("passed")

    if passed is True:
        result = "passed"
        detail = ""
    elif passed is False:
        result = "failed"
        detail = "recorded `passed: false`"
    else:
        result = "missing"
        detail = "evidence file records no `passed` verdict"

    # Story 1.10 records its own outstanding gate explicitly; surface it.
    manual = (
        document.get("test_evidence", {})
        .get("manual_screen_reader", {})
        .get("result")
    )
    if isinstance(manual, str) and manual.lower().startswith("not executed"):
        detail = "; ".join(filter(None, [detail, f"manual gate: {manual}"]))

    bound = not violations
    if violations:
        detail = "; ".join(filter(None, [detail, "unbound: " + "; ".join(violations)]))
    return result, bound, detail


def build_report(
    runner_reports: Iterable[RunnerReport],
    *,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
    strict_missing: bool = False,
    measurement_date: str | None = None,
) -> dict[str, Any]:
    """Evaluate every registry check and compose the readiness report."""
    validate_registry()
    reports = list(runner_reports)

    bindings = resolve_bindings(
        _DECLARED_BINDINGS, repo_root=repo_root, allow_dirty=allow_dirty
    )
    tree_dirty, _ = working_tree_status(repo_root)

    declared_files = sorted(
        {path for check in GATE_A_CHECKS for path in check.test_files}
    )
    outcomes = file_outcomes(reports, declared_files, strict=strict_missing)

    contributing: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    authority_by_key = {inv.key: inv.authority for inv in ALL_INVARIANTS}

    for check in GATE_A_CHECKS:
        authority = authority_by_key[check.invariant]
        if check.evidence_path:
            result, bound, detail = _evidence_result(check, repo_root=repo_root)
            source: Any = check.evidence_path
            source_kind = "evidence"
        else:
            per_file = {path: outcomes[path] for path in check.test_files}
            details = [
                f"{path}: {outcome.status}"
                + (f" ({outcome.detail})" if outcome.detail else "")
                for path, outcome in per_file.items()
                if outcome.status != "passed"
            ]
            if any(o.status == "failed" for o in per_file.values()):
                result = "failed"
            elif any(o.status == "missing" for o in per_file.values()):
                result = "missing"
            elif any(o.status == "skipped" for o in per_file.values()):
                result = "skipped"
            else:
                result = "passed"
            detail = "; ".join(details)
            # A test result is bound to the recorded commit only when the tree
            # the suite ran against is the tree HEAD names.
            bound = not tree_dirty
            if tree_dirty:
                detail = "; ".join(
                    filter(
                        None,
                        [
                            detail,
                            "unbound: measured on a dirty tree, so the recorded "
                            "commit does not describe what ran",
                        ],
                    )
                )
            source = {
                "runner": check.runner,
                "test_files": list(check.test_files),
                "cases": {
                    path: {
                        "status": outcome.status,
                        "total": outcome.total,
                        "passed": outcome.passed,
                        "skipped": outcome.skipped,
                        "failed": outcome.failed,
                    }
                    for path, outcome in per_file.items()
                },
            }
            source_kind = "tests"

        entry = {
            "story": check.story,
            "check": check.check,
            "description": check.description,
            "invariant": check.invariant,
            "authority": authority,
            # AC2 names this field. Null when the gate is NFR29's rather than
            # one of AR28's six, so nothing is misattributed to AR28.
            "ar28_invariant": check.invariant if authority == "AR28" else None,
            "result": result,
            "source_kind": source_kind,
            "source": source,
            "bound": bound,
        }
        if detail:
            entry["detail"] = detail
        contributing.append(entry)

        if result in _NON_PROVING or not bound:
            reason = detail or f"result: {result}"
            if not bound and "unbound" not in reason:
                reason = f"unbound; {reason}"
            blocking.append(
                {
                    "check": check.check,
                    "story": check.story,
                    "invariant": check.invariant,
                    "authority": authority,
                    "result": result,
                    "bound": bound,
                    "reason": reason,
                }
            )

    def _rollup(keys: Sequence[str]) -> dict[str, Any]:
        rolled: dict[str, Any] = {}
        for key in keys:
            entries = [e for e in contributing if e["invariant"] == key]
            failing = [e for e in entries if e["result"] in _NON_PROVING]
            unbound = [e for e in entries if not e["bound"]]
            if failing:
                status = "failed" if any(
                    e["result"] == "failed" for e in failing
                ) else failing[0]["result"]
            elif unbound:
                status = "unbound"
            else:
                status = "passed"
            title = next(inv.title for inv in ALL_INVARIANTS if inv.key == key)
            rolled[key] = {
                "title": title,
                "result": status,
                "contributing_checks": [e["check"] for e in entries],
                "blocking": [e["check"] for e in failing + unbound],
            }
        return rolled

    ar28_rollup = _rollup([inv.key for inv in AR28_INVARIANTS])
    nfr29_rollup = _rollup(
        [inv.key for inv in ALL_INVARIANTS if inv.authority == "NFR29"]
    )

    gate_a_passed = not blocking

    report: dict[str, Any] = {
        "story": "1.11",
        "requirements": ["AR28", "NFR27", "NFR29"],
        "measurement_date": measurement_date or date.today().isoformat(),
        "accountable_owner": "Product/QA",
        "fixtures": _fixture_entries(),
        "contract_digests": contract_digests(repo_root / "data" / "contract"),
        "contributing_checks": contributing,
        "ar28_invariants": ar28_rollup,
        "nfr29_gates": nfr29_rollup,
        "test_evidence": {
            report_.runner: {
                "junit_xml": str(report_.xml_path),
                "cases": len(report_.cases),
            }
            for report_ in reports
        },
        "version_bindings": bindings,
        "blocking": blocking,
        "gate_a_passed": gate_a_passed,
        "passed": gate_a_passed,
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Gate A readiness report")
    parser.add_argument("--pytest-xml", type=Path, required=True)
    parser.add_argument("--vitest-xml", type=Path, required=True)
    parser.add_argument("--playwright-xml", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="resolve bindings against a dirty tree; recorded in the report",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help=(
            "report a registry-declared test file absent from the XML instead "
            "of aborting (it still blocks the gate)"
        ),
    )
    args = parser.parse_args(argv)

    reports = [
        parse_junit(args.pytest_xml, runner="pytest"),
        parse_junit(args.vitest_xml, runner="vitest"),
        parse_junit(args.playwright_xml, runner="playwright"),
    ]

    report = build_report(
        reports,
        allow_dirty=args.allow_dirty,
        strict_missing=not args.allow_missing,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Wrote {args.output}")
    for key, rolled in report["ar28_invariants"].items():
        print(f"  [AR28] {key}: {rolled['result']}")
    for key, rolled in report["nfr29_gates"].items():
        print(f"  [NFR29] {key}: {rolled['result']}")

    if report["gate_a_passed"]:
        print("\ngate_a_passed: true")
        return 0

    print("\ngate_a_passed: false — blocked by:")
    for entry in report["blocking"]:
        print(f"  - {entry['check']} ({entry['invariant']}): {entry['reason']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
