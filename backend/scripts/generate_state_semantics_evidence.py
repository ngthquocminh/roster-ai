"""Generate Story 4.6 state-semantics evidence from Vitest and Playwright JUnit."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import (  # noqa: E402
    REPO_ROOT,
    audit_evidence_file,
    commit_date,
    contract_digests,
    file_digest,
    resolve_bindings,
)
from scripts.gate_a_readiness import _postdates  # noqa: E402
from scripts.junit_ingest import RunnerReport, parse_junit  # noqa: E402

OUTPUT_RELATIVE = "evidence/story-4.6/state-semantics-and-accessibility.json"
REQUIRED_PROJECTS = ("chromium", "msedge")
VITEST_FILE = "frontend/src/test/stateMatrix.test.tsx"
PLAYWRIGHT_FILE = "frontend/e2e/journey-accessibility.spec.ts"
DECLARED_BINDINGS = {
    "evaluator": "Vitest and Playwright JUnit; skips and missing projects are refusals",
    "model": "not applicable — deterministic UI fixtures",
    "prompt": "not applicable — no model invocation",
    "tool": "Vitest 4.1.10, jest-axe, Playwright and @axe-core/playwright",
    "policy": "NFR18/NFR20/NFR29 and UX-DR10/13/31/32/34/35",
    "application": "local frontend production build served by Vite preview",
    "solver": "not applicable — no solver run",
}
CONTRACT_FILES = (
    "frontend/src/test/stateMatrix.tsx",
    "frontend/src/test/stateMatrix.test.tsx",
    # 27 of the 60 matrix states come from here. Without it a change to
    # PRIMITIVE_FIXTURES alters what was tested while every recorded digest in
    # this artifact stays valid.
    "frontend/src/components/primitives/fixtures.tsx",
    "frontend/e2e/journey-accessibility.spec.ts",
    # Decision 10's widened contrast scans live here. The pass/fail verdict below
    # is computed from the journey spec alone — this spec is owned by Story 1.10's
    # `accessibility_browser_layer` check — but its version is part of what this
    # story measured, so it is bound rather than left unrecorded.
    "frontend/e2e/accessibility.spec.ts",
    "frontend/e2e/support/apiStubs.ts",
    "frontend/e2e/support/repairJourneyStubState.ts",
)


def _validate(report: RunnerReport, required_file: str, *, projects: tuple[str, ...] = ()) -> None:
    cases = [case for case in report.cases if case.file == required_file]
    if not cases:
        raise ValueError(f"required test absent from {report.runner} report: {required_file}")
    if all(case.status == "skipped" for case in cases):
        raise ValueError(f"{required_file} executed no tests; all cases were skipped")
    if any(case.status == "skipped" for case in cases):
        raise ValueError(f"{required_file} contains skipped tests")
    if projects:
        present = {case.project for case in cases}
        missing = set(projects) - present
        if missing:
            raise ValueError(f"missing required Playwright project(s): {', '.join(sorted(missing))}")


PREFIX = "workflow state semantics matrix > "
#: A per-state case is named `family/state`. Matching on "contains a slash" also
#: matched the aggregate case "…text and role/name trees", which shipped in the
#: artifact as a 61st "state" against a 60-entry matrix. Anchor on the shape.
STATE_NAME = re.compile(r"^[a-z][a-z-]*/\S")
DECLARED_COUNT = re.compile(r"^declares (\d+) states$")


def _matrix_case_names(report: RunnerReport) -> list[str]:
    return [case.name.split(PREFIX, 1)[-1] for case in report.cases
            if case.file == VITEST_FILE and case.name.startswith(PREFIX)]


def _states(report: RunnerReport) -> list[str]:
    names = _matrix_case_names(report)
    states = sorted({name for name in names if STATE_NAME.match(name)})
    if not states:
        raise ValueError("state matrix report contains no family/state test names")

    # Decision 9: a state must not be present in the module and missing from the
    # run. The suite publishes `STATE_MATRIX.length` through its own case name so
    # the count survives into the XML — a Vitest assertion can only see the module,
    # never the report, and a filtered or sharded run OMITS cases rather than
    # marking them skipped, so the skip rule in `_validate` does not catch it.
    declared = [match.group(1) for match in map(DECLARED_COUNT.match, names) if match]
    if not declared:
        raise ValueError(
            "state matrix report is missing its `declares N states` case — the run "
            "was filtered or sharded, so the emitted cases are not the whole matrix"
        )
    if len(declared) > 1:
        raise ValueError(f"state matrix report declares its size {len(declared)} times")
    if int(declared[0]) != len(states):
        raise ValueError(
            f"state matrix declares {declared[0]} states but the report emitted "
            f"{len(states)} — the run did not cover the whole matrix"
        )
    return states


def _measurement(path: Path, report: RunnerReport, bindings: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    """Pin the XML each verdict was computed from.

    `resolve_bindings` proves the working TREE was clean; nothing tied the
    MEASUREMENT to it, so an XML from another branch or an earlier commit produced
    identical-looking bound evidence. Mirrors `generate_repair_journey_evidence.
    junit_provenance`, but reads the timestamp off `RunnerReport` rather than
    re-parsing the XML — Decision 8 forbids a third parser.
    """
    try:
        relative = path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        relative = path.as_posix()

    entry: dict[str, Any] = {"junit_xml": relative}
    try:
        entry["sha256"] = file_digest(path)
    except OSError:
        entry["sha256"] = "unavailable — XML could not be read for digesting"
    entry["run_started"] = report.timestamp

    commit = (bindings.get("code") or {}).get("git_commit")
    if commit and report.timestamp:
        try:
            committed = commit_date(str(commit), repo_root)
        except Exception:  # noqa: BLE001
            committed = ""
        if committed and not _postdates(report.timestamp, committed):
            entry["stale"] = (
                f"run started {report.timestamp}, which predates the commit it is "
                f"bound to ({commit} at {committed}) — these results did not come "
                "from the tree this evidence names"
            )
    return entry


def build_document(vitest: RunnerReport, playwright: RunnerReport, *, bindings: Mapping[str, Any], measurement_date: str, repo_root: Path, measurement: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _validate(vitest, VITEST_FILE)
    _validate(playwright, PLAYWRIGHT_FILE, projects=REQUIRED_PROJECTS)
    states = _states(vitest)
    relevant = [case for case in vitest.cases if case.file == VITEST_FILE] + [case for case in playwright.cases if case.file == PLAYWRIGHT_FILE]
    passed = bool(relevant) and all(case.status == "passed" for case in relevant)
    return {
        "story": "4.6",
        "measurement_date": measurement_date,
        "requirements": ["NFR18", "NFR20", "NFR29", "UX-DR10", "UX-DR13", "UX-DR31", "UX-DR32", "UX-DR34", "UX-DR35"],
        "results": {
            "states": states,
            "state_matrix": "passed" if all(c.status == "passed" for c in vitest.cases if c.file == VITEST_FILE) else "failed",
            "accessibility": "passed" if all(c.status == "passed" for c in playwright.cases if c.file == PLAYWRIGHT_FILE) else "failed",
            # Say what the verdict covers. `accessibility` is the journey spec only;
            # the widened approval contrast scans in `e2e/accessibility.spec.ts` are
            # bound by digest above but gated by Story 1.10's browser-layer check.
            "accessibility_scope": PLAYWRIGHT_FILE,
            # jsdom computes neither colour nor geometry, so the component layer runs
            # with `color-contrast` and `target-size` disabled; both are proven in the
            # browser layer instead. Disclosed so a reader does not read the WCAG tag
            # list as covering contrast at this layer.
            "state_matrix_excluded_rules": ["color-contrast", "target-size"],
        },
        "passed": passed,
        "measurement": dict(measurement or {}),
        "contract_digests": contract_digests(repo_root / "data" / "contract"),
        "tested_artifact_digests": {path: file_digest(repo_root / path) for path in CONTRACT_FILES},
        "version_bindings": dict(bindings),
    }


def generate(*, vitest_path: Path, playwright_path: Path, repo_root: Path = REPO_ROOT, output_path: Path | None = None, measurement_date: str | None = None, allow_dirty: bool = False, declared_bindings: Mapping[str, str] = DECLARED_BINDINGS) -> dict[str, Any]:
    required = set(DECLARED_BINDINGS)
    missing = required - set(declared_bindings)
    if missing:
        raise ValueError(f"missing declared binding: {', '.join(sorted(missing))}")
    vitest = parse_junit(vitest_path, runner="vitest")
    playwright = parse_junit(playwright_path, runner="playwright")
    _validate(vitest, VITEST_FILE)
    _validate(playwright, PLAYWRIGHT_FILE, projects=REQUIRED_PROJECTS)
    destination = output_path or repo_root / OUTPUT_RELATIVE
    try:
        ignored = destination.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        ignored = OUTPUT_RELATIVE
    bindings = resolve_bindings(dict(declared_bindings), repo_root=repo_root, dataset_files=tuple(repo_root / path for path in CONTRACT_FILES), allow_dirty=allow_dirty, ignore_paths=frozenset({OUTPUT_RELATIVE, ignored}))
    measurement = {
        "vitest": _measurement(vitest_path, vitest, bindings, repo_root),
        "playwright": _measurement(playwright_path, playwright, bindings, repo_root),
    }
    document = build_document(vitest, playwright, bindings=bindings, measurement_date=measurement_date or date.today().isoformat(), repo_root=repo_root, measurement=measurement)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(".json.tmp")
    try:
        staging.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        staging.replace(destination)
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vitest-junit", type=Path, required=True)
    parser.add_argument("--playwright-junit", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    document = generate(vitest_path=args.vitest_junit, playwright_path=args.playwright_junit, allow_dirty=args.allow_dirty)
    # The sibling generator audits its own output before reporting success; a
    # document that binds cleanly can still violate the NFR27 convention.
    violations = audit_evidence_file(REPO_ROOT / OUTPUT_RELATIVE, repo_root=REPO_ROOT)
    print(f"{'ok' if not violations else 'UNBOUND':8s} {OUTPUT_RELATIVE}")
    print(f"         - passed: {str(document['passed']).lower()}")
    for violation in violations:
        print(f"         ! {violation}")
    for source, entry in document.get("measurement", {}).items():
        if "stale" in entry:
            print(f"         ! {source}: {entry['stale']}")
    return 0 if document["passed"] and not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
