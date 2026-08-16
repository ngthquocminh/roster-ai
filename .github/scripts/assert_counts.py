#!/usr/bin/env python3
"""Assert a test runner actually ran the tests it claims to have run.

Exit code 0 from a test runner is a weak signal. Three failure modes in this
repo produce a green exit while proving nothing:

* `backend/tests/test_evidence_convention.py`'s `requires_git` guard SKIPS its
  commit-binding assertions when git is unavailable
  (`_bmad-output/implementation-artifacts/deferred-work.md`, the story-1.11
  review entry) — a git-less runner sweeps the whole evidence tree green.
* `backend/conftest.py::_temporary_postgres_database` calls `pytest.skip()`
  when PostgreSQL is unreachable, so all 45 `@pytest.mark.postgres` tests turn
  into skips rather than failures.
* A Playwright/Vitest project that fails to launch can report zero tests.

So every suite in `.github/workflows/ci.yml` runs through this script, which
parses the runner's own summary line and enforces a floor on passes and a
CEILING on skips. Floors (not equality) on passes so adding tests never turns
CI red; ceilings on skips because a skip that was supposed to be a pass is
precisely the failure being guarded against.

Usage:
    assert_counts.py --runner pytest --log out.txt --min-passed 864 --max-skipped 1
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# `12 passed`, `1 skipped`, `3 deselected`, `2 flaky`, ...
COUNT = re.compile(
    r"(\d+)\s+(passed|failed|skipped|deselected|error|errors|flaky|xfailed|xpassed|todo)"
)

# pytest's terminal summary: comma-separated counts closed by a duration.
PYTEST_SUMMARY = re.compile(r"\d+\s+\w+.*\bin\s+[\d.]+s")


def _tally(text: str) -> dict[str, int]:
    tally: dict[str, int] = {}
    for number, label in COUNT.findall(text):
        label = "error" if label == "errors" else label
        tally[label] = tally.get(label, 0) + int(number)
    return tally


def _pytest_counts(lines: list[str]) -> dict[str, int]:
    """The LAST summary-shaped line — earlier ones are per-file progress noise."""
    for line in reversed(lines):
        stripped = line.strip().strip("= ")
        if PYTEST_SUMMARY.search(stripped) and COUNT.search(stripped):
            return _tally(stripped)
    raise SystemExit("assert_counts: no pytest summary line found in the log")


def _vitest_counts(lines: list[str]) -> dict[str, int]:
    """Vitest prints `Tests  400 passed (400)` — read that row, not `Test Files`."""
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("Tests") and COUNT.search(stripped):
            return _tally(stripped)
    raise SystemExit("assert_counts: no vitest `Tests` summary row found in the log")


def _playwright_counts(lines: list[str]) -> dict[str, int]:
    """The list reporter's summary block: one bare `N <outcome>` per line.

    Scans the whole log rather than stopping at the first non-matching line,
    because Playwright interleaves the offending test titles between outcome
    rows:

        1 flaky
          [chromium] > foo.spec.ts:3:1 > bar
        47 passed (2.1m)

    Stopping early would read the 47 and silently drop the 1. Nothing else in
    the log — per-test rows, npm output, vite's build summary — is a bare
    number followed by one of these outcome words, so a full scan is safe.
    """
    tally: dict[str, int] = {}
    for line in lines:
        match = COUNT.fullmatch(re.sub(r"\s*\([^)]*\)$", "", line.strip()))
        if match:
            label = match.group(2)
            tally[label] = tally.get(label, 0) + int(match.group(1))
    if not tally:
        raise SystemExit("assert_counts: no playwright summary block found in the log")
    return tally


PARSERS = {
    "pytest": _pytest_counts,
    "vitest": _vitest_counts,
    "playwright": _playwright_counts,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, choices=sorted(PARSERS))
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--min-passed", type=int, required=True)
    parser.add_argument("--max-skipped", type=int, default=0)
    parser.add_argument("--min-deselected", type=int, default=None)
    parser.add_argument("--label", default="suite")
    args = parser.parse_args()

    lines = args.log.read_text(encoding="utf-8", errors="replace").splitlines()
    counts = PARSERS[args.runner](lines)

    passed = counts.get("passed", 0)
    skipped = counts.get("skipped", 0)
    deselected = counts.get("deselected", 0)
    bad = counts.get("failed", 0) + counts.get("error", 0) + counts.get("flaky", 0)

    problems: list[str] = []
    if bad:
        problems.append(f"{bad} failed/errored/flaky test(s)")
    if passed < args.min_passed:
        problems.append(
            f"only {passed} passed, expected at least {args.min_passed} — "
            "tests disappeared, or the runner never reached them"
        )
    if skipped > args.max_skipped:
        problems.append(
            f"{skipped} skipped, at most {args.max_skipped} allowed — a skip here "
            "means an environment prerequisite (git, PostgreSQL, a browser) is "
            "missing and the suite proved nothing"
        )
    if args.min_deselected is not None and deselected < args.min_deselected:
        problems.append(
            f"only {deselected} deselected, expected at least "
            f"{args.min_deselected} — the `-m \"not live\"` default may have "
            "been removed, letting live-provider tests into normal CI (NFR26)"
        )

    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing"
    if problems:
        print(f"::error::{args.label}: {summary}")
        for problem in problems:
            print(f"::error::  - {problem}")
        return 1

    print(f"{args.label}: {summary} — meets the recorded baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
