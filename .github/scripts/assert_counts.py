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
import json
import re
import sys
from pathlib import Path

# `12 passed`, `1 skipped`, `3 deselected`, `2 flaky`, ...
COUNT = re.compile(
    r"(\d+)\s+(passed|failed|skipped|deselected|error|errors|flaky|xfailed|xpassed|todo)"
)

# pytest's terminal summary: comma-separated counts closed by a duration.
PYTEST_SUMMARY = re.compile(r"\d+\s+\w+.*\bin\s+[\d.]+s")

# CSI/OSC escapes. Several of these runners colourize whenever CI is set, even
# when their output is piped, and a colour code in front of the summary label is
# enough to make a naive prefix match miss the row entirely.
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def _clean(line: str) -> str:
    """Strip escapes and surrounding whitespace so matching sees plain text."""
    return ANSI.sub("", line).replace("\r", "").strip()


def _fail(runner: str, expected: str, lines: list[str]) -> "SystemExit":
    """Fail with the evidence attached.

    A bare "no summary row found" is a dead end: the log is on the runner, the
    reader is not. Printing the tail turns the next occurrence into a one-glance
    diagnosis instead of another round trip.
    """
    tail = [_clean(line) for line in lines[-40:]]
    tail = [line for line in tail if line]
    body = "\n".join(f"    {line}" for line in tail) or "    (log is empty)"
    return SystemExit(
        f"::error::assert_counts: could not find the {runner} summary "
        f"({expected}) in a {len(lines)}-line log.\n"
        f"  Last {len(tail)} non-blank line(s):\n{body}"
    )


def _tally(text: str) -> dict[str, int]:
    tally: dict[str, int] = {}
    for number, label in COUNT.findall(text):
        label = "error" if label == "errors" else label
        tally[label] = tally.get(label, 0) + int(number)
    return tally


def _pytest_counts(lines: list[str]) -> dict[str, int]:
    """The LAST summary-shaped line — earlier ones are per-file progress noise."""
    for line in reversed(lines):
        stripped = _clean(line).strip("= ")
        if PYTEST_SUMMARY.search(stripped) and COUNT.search(stripped):
            return _tally(stripped)
    raise _fail("pytest", "e.g. `864 passed, 1 skipped in 53.46s`", lines)


# `Tests  400 passed (400)`, and the `Test Files  63 passed (63)` row above it.
# Matched anywhere in the line rather than as a prefix: the label is indented,
# and under a colour-enabled reporter it is preceded by escape codes.
VITEST_TESTS = re.compile(r"(?<!Test )\bTests\b\s+(?P<counts>\d+.*)")
VITEST_FILES = re.compile(r"\bTest Files\b\s+(?P<counts>\d+.*)")


def _vitest_counts(lines: list[str]) -> dict[str, int]:
    """Read the `Tests` row; fall back to `Test Files` only to report honestly.

    Text scraping is the FALLBACK path. CI feeds this the JSON reporter's output
    instead (see `_json_counts`), because the human-readable summary row is not a
    contract — it moved once already and cost a CI round trip. This path stays
    for local use and so a missing JSON file still produces a real diagnosis.

    The `Test Files` fallback never satisfies a test-count baseline on its own —
    it exists so that a reporter change which drops the per-test row produces a
    message naming what it did find, rather than a bare "not found".
    """
    for line in reversed(lines):
        match = VITEST_TESTS.search(_clean(line))
        if match and COUNT.search(match.group("counts")):
            return _tally(match.group("counts"))

    for line in reversed(lines):
        match = VITEST_FILES.search(_clean(line))
        if match and COUNT.search(match.group("counts")):
            raise SystemExit(
                "::error::assert_counts: the vitest log has a `Test Files` row "
                f"({match.group('counts').strip()}) but no `Tests` row. The "
                "reporter emitted file-level results only, so the per-test "
                "baseline cannot be checked — pin a reporter that prints both."
            )

    raise _fail("vitest", "e.g. `Tests  400 passed (400)`", lines)


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
        match = COUNT.fullmatch(re.sub(r"\s*\([^)]*\)$", "", _clean(line)))
        if match:
            label = match.group(2)
            tally[label] = tally.get(label, 0) + int(match.group(1))
    if not tally:
        raise _fail("playwright", "e.g. `48 passed (2.1m)`", lines)
    return tally


PARSERS = {
    "pytest": _pytest_counts,
    "vitest": _vitest_counts,
    "playwright": _playwright_counts,
}


def _json_counts(runner: str, document: object) -> dict[str, int]:
    """Read counts from a machine-readable report.

    Preferred over scraping a terminal summary, which is presentation and can
    change between minor versions. pytest stays on text: its summary is the only
    place `deselected` appears, and JUnit XML does not carry it.
    """
    if not isinstance(document, dict):
        raise SystemExit(f"::error::assert_counts: {runner} report is not a JSON object")

    if runner == "vitest":
        # jest-compatible shape. `pending` is vitest's word for skipped.
        return {
            "passed": int(document.get("numPassedTests", 0)),
            "failed": int(document.get("numFailedTests", 0)),
            "skipped": int(document.get("numPendingTests", 0))
            + int(document.get("numTodoTests", 0)),
        }

    if runner == "playwright":
        stats = document.get("stats")
        if not isinstance(stats, dict):
            raise SystemExit(
                "::error::assert_counts: playwright report has no `stats` block"
            )
        # `expected` is a pass; `unexpected` is a failure. `flaky` is counted
        # separately and always fails the gate — see the module docstring.
        return {
            "passed": int(stats.get("expected", 0)),
            "failed": int(stats.get("unexpected", 0)),
            "flaky": int(stats.get("flaky", 0)),
            "skipped": int(stats.get("skipped", 0)),
        }

    raise SystemExit(f"::error::assert_counts: no JSON reader for runner {runner!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, choices=sorted(PARSERS))
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--min-passed", type=int, required=True)
    parser.add_argument("--max-skipped", type=int, default=0)
    parser.add_argument("--min-deselected", type=int, default=None)
    parser.add_argument("--label", default="suite")
    args = parser.parse_args()

    if not args.log.is_file():
        raise SystemExit(
            f"::error::assert_counts: {args.log} does not exist. The runner "
            "produced no report, which means it never got far enough to write "
            "one - check the preceding step, not this one."
        )

    raw = args.log.read_text(encoding="utf-8", errors="replace")
    source = "text"
    if raw.lstrip().startswith("{"):
        # A machine-readable report. Detected by content rather than by a flag
        # so the same invocation keeps working if a step is switched between a
        # JSON reporter and a piped console log.
        try:
            counts = _json_counts(args.runner, json.loads(raw))
            source = "json"
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"::error::assert_counts: {args.log} starts like JSON but does "
                f"not parse ({exc}). A truncated report usually means the runner "
                "was killed mid-write."
            ) from exc
    else:
        counts = PARSERS[args.runner](raw.splitlines())

    passed = counts.get("passed", 0)
    skipped = counts.get("skipped", 0)
    deselected = counts.get("deselected", 0)
    bad = counts.get("failed", 0) + counts.get("error", 0) + counts.get("flaky", 0)

    problems: list[str] = []
    if bad:
        problems.append(f"{bad} failed/errored/flaky test(s)")
    if passed < args.min_passed:
        problems.append(
            f"only {passed} passed, expected at least {args.min_passed} - "
            "tests disappeared, or the runner never reached them"
        )
    if skipped > args.max_skipped:
        problems.append(
            f"{skipped} skipped, at most {args.max_skipped} allowed - a skip here "
            "means an environment prerequisite (git, PostgreSQL, a browser) is "
            "missing and the suite proved nothing"
        )
    if args.min_deselected is not None and deselected < args.min_deselected:
        problems.append(
            f"only {deselected} deselected, expected at least "
            f"{args.min_deselected} - the `-m \"not live\"` default may have "
            "been removed, letting live-provider tests into normal CI (NFR26)"
        )

    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing"
    if problems:
        print(f"::error::{args.label}: {summary}")
        for problem in problems:
            print(f"::error::  - {problem}")
        return 1

    print(f"{args.label}: {summary} (via {source} report) - meets the recorded baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
