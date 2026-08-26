"""Generate Story 3.12's repair-browser-journey evidence from Playwright JUnit.

Commit the implementation first, run both browser projects with the streaming
JUnit reporter on a clean tree, then invoke this generator. The ordering is the
repository evidence convention in ``docs/EVIDENCE-CONVENTION.md``.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import xml.etree.ElementTree as ET
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

OUTPUT_RELATIVE = "evidence/story-3.12/repair-browser-journey.json"
REQUIRED_PROJECTS = ("chromium", "msedge")
REQUIRED_TESTS = {
    "repair-journey.spec.ts": (
        "completes draft, run, reconnect, comparison, and exact evidence targeting"
    ),
    "repair-journey-accessibility.spec.ts": (
        "keeps repair Chat, Runs, and Results axe-clean, keyboard-operable, "
        "and semantically literal"
    ),
}
DECLARED_BINDINGS: dict[str, str] = {
    "evaluator": (
        "Playwright streaming JUnit report; both required specs must execute "
        "without failures, errors, or skips in Chromium and Microsoft Edge"
    ),
    "model": "not applicable — deterministic browser fixtures; no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": (
        "Playwright 1.62.1 production-build browser run with @axe-core/playwright "
        "4.12.1 and the committed streaming JUnit reporter"
    ),
    # NFR20 is deliberately absent. It covers zoom/reflow, text-spacing, and
    # reduced-motion, none of which these specs exercise on the repair
    # surfaces — those stay proven on Epic 1's Scenario Data surfaces only
    # (`layout-accessibility.spec.ts`, `reduced-motion.spec.ts`,
    # `responsive.spec.ts`, all `demandUrl`/`/`). AC2's Then clause names only
    # keyboard operability, focus management, and semantic status text.
    "policy": (
        "NFR18/NFR29 and UX-DR10/UX-DR13: draft-to-comparison journey, "
        "same-run reconnect, terminal outcome, exact evidence targeting, axe, "
        "keyboard, focus, and literal semantic status assertions all block release"
    ),
    "application": "local frontend production build served by Vite preview",
    "solver": "not applicable — deterministic browser fixture responses; no solver run",
}


def _count(suite: ET.Element, key: str) -> int:
    try:
        return int(suite.attrib.get(key, "0"))
    except ValueError as exc:
        raise ValueError(
            f"unreadable Playwright JUnit count {key}={suite.attrib.get(key)!r}"
        ) from exc


def parse_junit_report(path: Path) -> dict[str, dict[str, bool]]:
    """Require every named proof to run and pass in both browser projects."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"unreadable Playwright JUnit report: {exc}") from exc

    suites: dict[tuple[str, str], ET.Element] = {}
    for suite in root.iter("testsuite"):
        project = suite.attrib.get("hostname", "")
        file_name = Path(suite.attrib.get("name", "")).name
        if project in REQUIRED_PROJECTS and file_name in REQUIRED_TESTS:
            key = (project, file_name)
            if key in suites:
                raise ValueError(f"duplicate Playwright JUnit suite for {project}/{file_name}")
            suites[key] = suite

    outcomes: dict[str, dict[str, bool]] = {}
    for project in REQUIRED_PROJECTS:
        project_outcomes: dict[str, bool] = {}
        for file_name, required_title in REQUIRED_TESTS.items():
            suite = suites.get((project, file_name))
            if suite is None:
                raise ValueError(
                    f"missing required {project} Playwright suite {file_name}"
                )
            counts = {key: _count(suite, key) for key in ("tests", "failures", "errors", "skipped")}
            if counts["tests"] <= 0:
                raise ValueError(f"{project}/{file_name} collected no tests")
            if counts["failures"] or counts["errors"] or counts["skipped"]:
                raise ValueError(
                    f"{project}/{file_name} did not pass: "
                    f"failures={counts['failures']}, errors={counts['errors']}, "
                    f"skipped={counts['skipped']}"
                )
            matching = [case for case in suite.findall("testcase") if case.attrib.get("name") == required_title]
            if len(matching) != 1:
                raise ValueError(
                    f"{project}/{file_name} must contain exactly one testcase named "
                    f"{required_title!r}; found {len(matching)}"
                )
            if matching[0].find("failure") is not None or matching[0].find("skipped") is not None:
                raise ValueError(f"{project}/{file_name} testcase did not pass")
            project_outcomes[file_name] = True
        outcomes[project] = project_outcomes
    return outcomes


def junit_provenance(
    path: Path, bindings: Mapping[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Pin the XML the verdict was computed from.

    ``resolve_bindings`` proves only that the working tree was clean when this
    ran — nothing tied the *measurement* to that tree, so an XML from another
    branch, an older commit, or another machine produced identical-looking
    "bound" evidence. Mirrors ``gate_a_readiness._xml_provenance``: a
    repo-relative path, a sha256 (the artifacts directory is gitignored, so the
    digest is the binding rather than an existence check), the run's own
    timestamp, and a ``stale`` marker when the run predates the bound commit.
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

    run_started = ""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        root = None
    if root is not None:
        for suite in root.iter("testsuite"):
            run_started = suite.attrib.get("timestamp", "")
            if run_started:
                break
    entry["run_started"] = run_started

    commit = (bindings.get("code") or {}).get("git_commit")
    if commit and run_started:
        try:
            committed = commit_date(str(commit), repo_root)
        except Exception:  # noqa: BLE001
            committed = ""
        if committed and not _postdates(run_started, committed):
            entry["stale"] = (
                f"run started {run_started}, which predates the commit it is "
                f"bound to ({commit} at {committed}) — these results did not "
                "come from the tree this evidence names"
            )
    return entry


def build_document(
    outcomes: Mapping[str, Mapping[str, bool]],
    *,
    bindings: Mapping[str, Any],
    measurement_date: str,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    journey_passed = all(
        outcomes.get(project, {}).get("repair-journey.spec.ts") is True
        for project in REQUIRED_PROJECTS
    )
    accessibility_passed = all(
        outcomes.get(project, {}).get("repair-journey-accessibility.spec.ts") is True
        for project in REQUIRED_PROJECTS
    )
    passed = journey_passed and accessibility_passed
    result = "passed" if passed else "failed"
    return {
        "story": "3.12",
        "requirements": ["NFR18", "NFR29", "UX-DR10", "UX-DR13"],
        "measurement_date": measurement_date,
        "environment": {
            "description": "local production frontend build exercised by Playwright",
            "operating_system": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "browser_projects": list(REQUIRED_PROJECTS),
            "network_transit": "none; deterministic same-origin API route fixtures",
        },
        "protocol": {
            "reporter": "frontend/e2e/support/streaming-junit-reporter.mjs",
            "required_specs": dict(REQUIRED_TESTS),
            "all_projects_must_pass": True,
            "skips_are_failures": True,
            "measurement": dict(provenance or {}),
        },
        # Every key in `results` below reports the pass/fail of the SPEC FILE
        # that contains its assertions — not an independent measurement. The
        # generator reads a JUnit report, which carries one testcase per spec,
        # so there are two verdicts here wearing seven names. Recorded rather
        # than removed because Decision 5 asked for names that say which AC
        # clause each proof serves; a reader must not mistake the shape for a
        # per-assertion ledger.
        "results_derivation": {
            "note": (
                "Each results key reports the pass/fail of the spec file "
                "containing its assertions, not an independent measurement."
            ),
            "journey_completion": "repair-journey.spec.ts",
            "run_id_survives_reconnect": "repair-journey.spec.ts",
            "evidence_link_resolves": "repair-journey.spec.ts",
            "axe_browser": "repair-journey-accessibility.spec.ts",
            "keyboard_operable": "repair-journey-accessibility.spec.ts",
            "focus_management": "repair-journey-accessibility.spec.ts",
            "semantic_status_text": "repair-journey-accessibility.spec.ts",
        },
        "results": {
            "journey_completion": result if journey_passed else "failed",
            "run_id_survives_reconnect": result if journey_passed else "failed",
            "evidence_link_resolves": result if journey_passed else "failed",
            "axe_browser": result if accessibility_passed else "failed",
            "keyboard_operable": result if accessibility_passed else "failed",
            "focus_management": result if accessibility_passed else "failed",
            "semantic_status_text": result if accessibility_passed else "failed",
        },
        "project_outcomes": {
            project: dict(files) for project, files in outcomes.items()
        },
        "passed": passed,
        "contract_digests": contract_digests(REPO_ROOT / "data" / "contract"),
        "version_bindings": dict(bindings),
    }


def generate(
    *,
    junit_path: Path,
    repo_root: Path = REPO_ROOT,
    measurement_date: str | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    outcomes = parse_junit_report(junit_path)
    # The two spec files alone do not determine what was measured: every value
    # they assert — the run-status progression, the metric deltas, the evidence
    # refs, the proposal shape — lives in the stub modules. Binding only the
    # specs let those change with no drift reported, so the artifact claimed to
    # pin a measurement it did not.
    dataset_files = tuple(
        repo_root / "frontend" / "e2e" / file_name for file_name in REQUIRED_TESTS
    ) + (
        repo_root / "frontend" / "e2e" / "support" / "repairJourneyStubState.ts",
        repo_root / "frontend" / "e2e" / "support" / "apiStubs.ts",
    )
    bindings = resolve_bindings(
        DECLARED_BINDINGS,
        repo_root=repo_root,
        dataset_files=dataset_files,
        allow_dirty=allow_dirty,
        # This generator's own output is written below; without it a second
        # consecutive run before committing fails with DirtyTreeError.
        # `gate_a_readiness.build_report` forwards ignore_paths for the same reason.
        ignore_paths=frozenset({OUTPUT_RELATIVE}),
    )
    document = build_document(
        outcomes,
        bindings=bindings,
        measurement_date=measurement_date or date.today().isoformat(),
        provenance=junit_provenance(junit_path, bindings, repo_root),
    )
    destination = repo_root / OUTPUT_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(destination.suffix + ".tmp")
    try:
        staging.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        staging.replace(destination)
    except OSError:
        # Never leave a .json.tmp sibling behind — it dirties the tree and the
        # next resolve_bindings call refuses on it.
        staging.unlink(missing_ok=True)
        raise
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--measurement-date", default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    if args.measurement_date is not None:
        # Written verbatim into the artifact; reject a malformed value here
        # rather than shipping an unparseable date in bound evidence.
        try:
            date.fromisoformat(args.measurement_date)
        except ValueError:
            parser.error(
                f"--measurement-date must be ISO 8601 (YYYY-MM-DD); got {args.measurement_date!r}"
            )
    document = generate(
        junit_path=args.junit,
        measurement_date=args.measurement_date,
        allow_dirty=args.allow_dirty,
    )
    violations = audit_evidence_file(REPO_ROOT / OUTPUT_RELATIVE, repo_root=REPO_ROOT)
    print(f"{'ok' if not violations else 'UNBOUND':8s} {OUTPUT_RELATIVE}")
    print(f"         - passed: {document['passed']}")
    for violation in violations:
        print(f"         ! {violation}")
    return 0 if document["passed"] and not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
