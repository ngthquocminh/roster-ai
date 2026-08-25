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
    contract_digests,
    resolve_bindings,
)

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
    "policy": (
        "NFR18/NFR20/NFR29 and UX-DR10/UX-DR13: draft-to-comparison journey, "
        "same-run reconnect, exact evidence targeting, axe, keyboard, focus, "
        "and literal semantic status assertions all block release"
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


def build_document(
    outcomes: Mapping[str, Mapping[str, bool]],
    *,
    bindings: Mapping[str, Any],
    measurement_date: str,
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
        "requirements": ["NFR18", "NFR20", "NFR29", "UX-DR10", "UX-DR13"],
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
    dataset_files = tuple(
        repo_root / "frontend" / "e2e" / file_name for file_name in REQUIRED_TESTS
    )
    bindings = resolve_bindings(
        DECLARED_BINDINGS,
        repo_root=repo_root,
        dataset_files=dataset_files,
        allow_dirty=allow_dirty,
    )
    document = build_document(
        outcomes,
        bindings=bindings,
        measurement_date=measurement_date or date.today().isoformat(),
    )
    destination = repo_root / OUTPUT_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(destination.suffix + ".tmp")
    staging.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    staging.replace(destination)
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--measurement-date", default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
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
