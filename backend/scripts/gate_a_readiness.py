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
    NFR27_BINDING_KEYS,
    REPO_ROOT,
    audit_evidence_drift,
    audit_evidence_file,
    commit_date,
    contract_digests,
    file_digest,
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
    missing_pytest_cases,
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
    """Return ``(result, bound, detail)`` for an evidence-backed check.

    This reads a PAST measurement and returns it as a PRESENT verdict. That is a
    category error, accepted deliberately for the three checks whose measurement
    a shared CI runner cannot reproduce — it is NOT a sign that evidence files need
    an expiry mechanism. Evidence is a historical record: "at commit X, this
    measurement produced this result", true forever and reproduced by checking out
    X. See :func:`evidence_binding.audit_evidence_file`'s docstring for why its
    rules are monotone by design, and `deferred-work.md:103` for the re-framing
    (the ledger's original "evidence has no expiry" heading states the problem
    wrongly).

    Twenty-five of the thirty-three registry checks take fresh JUnit XML instead
    and do not come through here; eight are evidence-backed. Do not hand-edit
    these numbers -- `test_registered_evidence_files_are_deliberate` recomputes
    them from `GATE_A_CHECKS`, so they cannot drift again (the counts read
    "seventeen of twenty" against a registry of thirty-three until the code
    review of story-5.2).
    """
    path = repo_root / str(check.evidence_path)
    if not path.is_file():
        return "missing", False, f"evidence file not found: {check.evidence_path}"

    violations = audit_evidence_file(path, repo_root=repo_root)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001
        # `audit_evidence_file` already reports this cleanly; re-reading it here
        # with a bare `json.loads` used to kill the run instead, so the gate
        # produced a stack trace and no artifact rather than a verdict.
        return "missing", False, f"unreadable evidence file: {exc}"
    if not isinstance(document, dict):
        return "missing", False, "evidence file is not a JSON object"

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

    # A manual gate is a check no automated suite can substitute for, so it is
    # held to the same standard as everything else: it must affirmatively
    # record a pass. Anything else — "not executed", "cancelled", "pending",
    # a reworded phrase nobody anticipated — is not proven and blocks on its
    # own account. Surfacing it only in `detail` (as this did originally) meant
    # flipping the file's own `passed` to true would have made an un-executed
    # screen-reader pass vanish from the verdict entirely.
    for label, manual in _manual_gates(document):
        if not manual.strip().lower().startswith("pass"):
            detail = "; ".join(filter(None, [detail, f"manual gate {label}: {manual}"]))
            if result == "passed":
                result = "failed"

    bound = not violations
    if violations:
        detail = "; ".join(filter(None, [detail, "unbound: " + "; ".join(violations)]))

    drift = audit_evidence_drift(path, repo_root=repo_root)
    if drift:
        # Observations, not violations: the world moved on since the
        # measurement. Recorded so it is visible, never allowed to block.
        detail = "; ".join(filter(None, [detail, "drift: " + "; ".join(drift)]))
    return result, bound, detail


def _xml_provenance(
    report: RunnerReport, bindings: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    """Describe the JUnit XML a runner's results came from.

    Three things beyond the case count, all of which the original report
    lacked:

    * a **repo-relative path**, not the absolute machine-local one that made
      the recorded source unreachable from any other checkout;
    * a **sha256**, so the artifact the verdict was computed from is pinned
      even though `_bmad-output/test-artifacts/` is deliberately gitignored;
    * the run's own **timestamp**, checked against the commit date of
      `code.git_commit`.

    The digest is deliberately the binding here rather than an existence check.
    Adding `junit_xml` to `_PATH_HINT_KEYS` would demand the file be present at
    audit time, which — for a gitignored artifact — would permanently unbind
    this report on every machine except the one that generated it.
    """
    try:
        relative = Path(report.xml_path).resolve().relative_to(repo_root).as_posix()
    except ValueError:
        relative = Path(report.xml_path).as_posix()

    entry: dict[str, Any] = {
        "junit_xml": relative,
        "cases": len(report.cases),
        "run_started": report.timestamp,
    }
    try:
        entry["sha256"] = file_digest(Path(report.xml_path))
    except OSError:
        entry["sha256"] = "unavailable — XML could not be read for digesting"

    commit = (bindings.get("code") or {}).get("git_commit")
    if commit and report.timestamp:
        try:
            committed = commit_date(str(commit), repo_root)
        except Exception:  # noqa: BLE001
            committed = ""
        if committed and not _postdates(report.timestamp, committed):
            entry["stale"] = (
                f"run started {report.timestamp}, which predates the commit it "
                f"is bound to ({commit} at {committed}) — these results did not "
                "come from the tree this report names"
            )
    return entry


def _postdates(run_stamp: str, commit_stamp: str) -> bool:
    """True when the test run started at or after the commit was made.

    Both are ISO 8601 but not in the same shape: pytest writes a local offset,
    Vitest and Playwright write `Z`. Compared as instants, never as text.
    """
    from datetime import datetime, timezone

    def _parse(value: str) -> Any:
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    run = _parse(run_stamp)
    made = _parse(commit_stamp)
    if run is None or made is None:
        return True
    return run >= made


def _validate_supplied_bindings(bindings: Any) -> None:
    """Reject a pre-resolved binding block that does not meet NFR27."""
    if not isinstance(bindings, dict):
        raise ValueError(
            f"bindings must be a mapping, got {type(bindings).__name__}"
        )
    missing = [key for key in NFR27_BINDING_KEYS if key not in bindings]
    if missing:
        raise ValueError(
            "Pre-resolved bindings are missing NFR27 key(s): "
            f"{', '.join(missing)}. Resolve them through "
            "`evidence_binding.resolve_bindings()` rather than composing the "
            "block by hand."
        )
    if "schema_version" not in bindings:
        raise ValueError("Pre-resolved bindings are missing `schema_version`.")
    code = bindings.get("code")
    if not isinstance(code, dict) or not code.get("git_commit"):
        raise ValueError(
            "Pre-resolved bindings must carry `code.git_commit`; without it "
            "nothing ties the recorded results to a tree."
        )


def _manual_gates(document: dict[str, Any]) -> list[tuple[str, str]]:
    """Every manual-gate result recorded under `test_evidence`.

    Defensive about shape: `test_evidence` and its members are author-written
    and an evidence file listing several manual passes as a list is a perfectly
    plausible future shape, which the original chained `.get(...)` would have
    crashed on.
    """
    evidence = document.get("test_evidence")
    if not isinstance(evidence, dict):
        return []
    found: list[tuple[str, str]] = []
    for label, entry in evidence.items():
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            if "manual" in label or "manual" in key or "screen_reader" in label:
                if isinstance(value, str) and key in ("result", "outcome", "status"):
                    found.append((label, value))
    return found


def build_report(
    runner_reports: Iterable[RunnerReport],
    *,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
    strict_missing: bool = False,
    measurement_date: str | None = None,
    bindings: dict[str, Any] | None = None,
    ignore_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Evaluate every registry check and compose the readiness report.

    ``bindings`` accepts a binding block already resolved by the caller. It
    exists for the one case where several evidence files are regenerated in a
    single pass: `resolve_bindings()` refuses a dirty tree, so every binding
    set must be resolved *before* the first file is written. Callers that
    regenerate only this report should leave it unset and let the clean-tree
    check run here.

    ``ignore_paths`` is this report's own output file (and its `.tmp` staging
    sibling), forwarded to `resolve_bindings()`. Writing the report dirties the
    tree, so without the exemption a second consecutive run refused before
    doing any work — the two-commit dance. Only that file is exempted; a stray
    uncommitted source change still refuses.
    """
    validate_registry()
    reports = list(runner_reports)

    if bindings is None:
        bindings = resolve_bindings(
            _DECLARED_BINDINGS,
            repo_root=repo_root,
            allow_dirty=allow_dirty,
            ignore_paths=ignore_paths,
        )
    else:
        # A caller-supplied block bypasses `resolve_bindings()`, and with it the
        # dirty-tree refusal that is this module's whole safety mechanism. The
        # original guard was `if bindings is None`, so `bindings={}` sailed
        # through and produced `version_bindings: {}` with every check marked
        # bound. Validate what the caller hands over instead of trusting it.
        _validate_supplied_bindings(bindings)
    # Read the tree state out of the binding block rather than sampling it
    # again here. The binding block records the tree as it was when the
    # bindings were resolved, which is the authoritative moment — re-sampling
    # would report the tree as dirty merely because earlier files in the same
    # regeneration pass have already been written.
    tree_dirty = bool(bindings.get("code", {}).get("working_tree_dirty"))

    declared_files = sorted(
        {path for check in GATE_A_CHECKS for path in check.test_files}
    )
    outcomes = file_outcomes(reports, declared_files, strict=strict_missing)
    report_provenance = {
        report_.runner: _xml_provenance(report_, bindings, repo_root)
        for report_ in reports
    }

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
            # A check that is both failing and unbound appears in both lists;
            # de-duplicate so it is named once.
            blocked_names: list[str] = []
            for entry_ in failing + unbound:
                if entry_["check"] not in blocked_names:
                    blocked_names.append(entry_["check"])
            rolled[key] = {
                "title": title,
                "result": status,
                "contributing_checks": [e["check"] for e in entries],
                "blocking": blocked_names,
            }
        return rolled

    ar28_rollup = _rollup([inv.key for inv in AR28_INVARIANTS])
    nfr29_rollup = _rollup(
        [inv.key for inv in ALL_INVARIANTS if inv.authority == "NFR29"]
    )
    ac2_rollup = _rollup(
        [inv.key for inv in ALL_INVARIANTS if inv.authority == "AC2"]
    )

    # Run-level gates. These are properties of the measurement itself rather
    # than of any one registry check, so they are appended after the per-check
    # loop — but they block exactly the same way.
    for path, absent in sorted(
        missing_pytest_cases(reports, declared_files, repo_root=repo_root).items()
    ):
        blocking.append(
            {
                "check": "pytest_case_coverage",
                "story": "1.11",
                "invariant": "measurement_integrity",
                "authority": "AC2",
                "result": "missing",
                "bound": False,
                "reason": (
                    f"{path}: {len(absent)} test function(s) defined in source "
                    f"produced no case in the JUnit XML ({', '.join(absent[:3])}"
                    f"{', …' if len(absent) > 3 else ''}). A deselected test "
                    "leaves no trace in the XML, so this cannot be read as a pass."
                ),
            }
        )

    for report_ in reports:
        stale = report_provenance.get(report_.runner, {}).get("stale")
        if stale:
            blocking.append(
                {
                    "check": f"{report_.runner}_xml_provenance",
                    "story": "1.11",
                    "invariant": "measurement_integrity",
                    "authority": "AC2",
                    "result": "missing",
                    "bound": False,
                    "reason": stale,
                }
            )

    for check in GATE_A_CHECKS:
        if not check.required_projects:
            continue
        for path in check.test_files:
            covered = set(outcomes[path].projects)
            absent_projects = [p for p in check.required_projects if p not in covered]
            if absent_projects:
                blocking.append(
                    {
                        "check": check.check,
                        "story": check.story,
                        "invariant": check.invariant,
                        "authority": authority_by_key[check.invariant],
                        "result": "missing",
                        "bound": False,
                        "reason": (
                            f"{path} ran under {sorted(covered) or 'no'} project(s); "
                            f"this check claims proof on "
                            f"{', '.join(check.required_projects)}"
                        ),
                    }
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
        "ac2_gates": ac2_rollup,
        "test_evidence": report_provenance,
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
        "--code-from",
        type=Path,
        default=None,
        help=(
            "reuse the `version_bindings.code` block of an evidence file "
            "regenerated earlier in this same clean-tree pass. Needed because "
            "writing those files dirties the tree; the block still names the "
            "commit that was measured. Refused if that block is itself dirty."
        ),
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

    # This command's own output is what dirties the tree, so exempt it — both
    # the final path and the `.tmp` staging sibling written just below. Without
    # this, run 2 of 2 dies on DirtyTreeError before doing any work; with it, an
    # uncommitted source change still refuses exactly as before.
    output_exemptions = frozenset(
        {
            str(args.output),
            str(args.output.with_suffix(args.output.suffix + ".tmp")),
        }
    )

    bindings = None
    if args.code_from:
        donor = json.loads(args.code_from.read_text(encoding="utf-8"))
        donor_code = (donor.get("version_bindings") or {}).get("code")
        bindings = resolve_bindings(
            _DECLARED_BINDINGS,
            repo_root=REPO_ROOT,
            code_binding=donor_code,
            ignore_paths=output_exemptions,
        )

    report = build_report(
        reports,
        allow_dirty=args.allow_dirty,
        strict_missing=not args.allow_missing,
        bindings=bindings,
        ignore_paths=output_exemptions,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Written via a temp file and renamed. A crash or full disk mid-write would
    # otherwise leave a truncated evidence file, and the repo-wide convention
    # sweep parses every `evidence/**/*.json` — so a half-written report breaks
    # the suite at collection rather than failing an assertion.
    staging = args.output.with_suffix(args.output.suffix + ".tmp")
    staging.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    staging.replace(args.output)

    print(f"Wrote {args.output}")

    # Audit our OWN output, the way generate_repair_journey_evidence.main()
    # already does. This module audits every other evidence file it reads
    # (`_evidence_result`) but never the report it writes, so it could — and
    # did — print `gate_a_passed: true` over an artifact bound to a docs-only
    # commit. `_is_code_path` excludes `docs/`, `evidence/`, `_bmad-output/`
    # and `*.md`, so generating while HEAD is a doc or evidence commit
    # produces a report that proves nothing about the behaviour it measured.
    # The repo-wide convention sweep catches it, but only if someone re-runs
    # that suite after this step — and the runbook's step 3 is "commit the
    # report", not "re-run the sweep". Fail here instead.
    self_violations = audit_evidence_file(args.output, repo_root=REPO_ROOT)
    if self_violations:
        print("\nUNBOUND — this report violates docs/EVIDENCE-CONVENTION.md:")
        for violation in self_violations:
            print(f"  ! {violation}")
        print(
            "\nThe report was written but must not be committed as-is. If the "
            "binding names a non-code commit, commit the code first (or land a "
            "code-touching commit), re-run the measurements so they postdate "
            "it, and regenerate."
        )
        return 1

    for key, rolled in report["ar28_invariants"].items():
        print(f"  [AR28] {key}: {rolled['result']}")
    for key, rolled in report["nfr29_gates"].items():
        print(f"  [NFR29] {key}: {rolled['result']}")
    for key, rolled in report["ac2_gates"].items():
        print(f"  [AC2]  {key}: {rolled['result']}")

    if report["gate_a_passed"]:
        print("\ngate_a_passed: true")
        return 0

    print("\ngate_a_passed: false — blocked by:")
    for entry in report["blocking"]:
        print(f"  - {entry['check']} ({entry['invariant']}): {entry['reason']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
