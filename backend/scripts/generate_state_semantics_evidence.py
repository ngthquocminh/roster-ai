"""Generate Story 4.6 state-semantics evidence from Vitest and Playwright JUnit."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import REPO_ROOT, contract_digests, file_digest, resolve_bindings  # noqa: E402
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
    "frontend/e2e/journey-accessibility.spec.ts",
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


def _states(report: RunnerReport) -> list[str]:
    prefix = "workflow state semantics matrix > "
    states = sorted({case.name.split(prefix, 1)[-1] for case in report.cases
                     if case.file == VITEST_FILE and "/" in case.name and case.name.startswith(prefix)})
    if not states:
        raise ValueError("state matrix report contains no family/state test names")
    return states


def build_document(vitest: RunnerReport, playwright: RunnerReport, *, bindings: Mapping[str, Any], measurement_date: str, repo_root: Path) -> dict[str, Any]:
    _validate(vitest, VITEST_FILE)
    _validate(playwright, PLAYWRIGHT_FILE, projects=REQUIRED_PROJECTS)
    states = _states(vitest)
    relevant = [case for case in vitest.cases if case.file == VITEST_FILE] + [case for case in playwright.cases if case.file == PLAYWRIGHT_FILE]
    passed = bool(relevant) and all(case.status == "passed" for case in relevant)
    return {
        "story": "4.6",
        "measurement_date": measurement_date,
        "requirements": ["NFR18", "NFR20", "NFR29", "UX-DR10", "UX-DR13", "UX-DR31", "UX-DR32", "UX-DR34", "UX-DR35"],
        "results": {"states": states, "state_matrix": "passed" if all(c.status == "passed" for c in vitest.cases if c.file == VITEST_FILE) else "failed", "accessibility": "passed" if all(c.status == "passed" for c in playwright.cases if c.file == PLAYWRIGHT_FILE) else "failed"},
        "passed": passed,
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
    bindings = resolve_bindings(dict(declared_bindings), repo_root=repo_root, dataset_files=tuple(repo_root / path for path in CONTRACT_FILES), allow_dirty=allow_dirty, ignore_paths=frozenset({OUTPUT_RELATIVE}))
    document = build_document(vitest, playwright, bindings=bindings, measurement_date=measurement_date or date.today().isoformat(), repo_root=repo_root)
    destination = output_path or repo_root / OUTPUT_RELATIVE
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
    print(f"passed: {str(document['passed']).lower()}")
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
