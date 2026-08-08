"""Read JUnit XML from pytest, Vitest and Playwright into per-file outcomes.

All three runners emit JUnit natively, so this adds no dependency:

    uv run --frozen pytest --junitxml=<path>
    npx vitest run --reporter=junit --outputFile=<path>
    PLAYWRIGHT_JUNIT_OUTPUT_NAME=<path> npx playwright test --reporter=junit

Each writes a different test identity, all three verified against real output:

===========  ====================================  ==========================
runner       `classname`                           resolves to
===========  ====================================  ==========================
pytest       ``tests.test_auth_api`` (dotted)      ``backend/tests/…​.py``
Vitest       ``src/lib/errors.test.ts`` (path)     ``frontend/…``
Playwright   ``harness.spec.ts`` (path, testDir)   ``frontend/e2e/…``
===========  ====================================  ==========================

Two rules here carry the gate:

1. A registry-declared file absent from the XML raises. Without that the
   registry silently decays the first time a test is renamed or deleted, and
   the report keeps claiming a check that no longer runs.
2. A skipped test is not a passed test. `postgres`-marked tests skip *cleanly*
   when no PostgreSQL service is up, and a skip serialises as `<skipped/>`
   inside a `<testcase>` — it looks present. Treated as not proven so that
   running the gate without Docker up cannot produce a green report that
   proves nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence
from xml.etree import ElementTree

Runner = Literal["pytest", "vitest", "playwright"]
CaseStatus = Literal["passed", "failed", "skipped"]
FileStatus = Literal["passed", "failed", "skipped", "missing"]

#: Playwright resolves `classname` against its testDir, not the frontend root.
_PLAYWRIGHT_TEST_DIR = "frontend/e2e"
_VITEST_ROOT = "frontend"
_PYTEST_ROOT = "backend"

#: Playwright joins a describe chain onto the file with this separator.
_DESCRIBE_SEPARATORS = (" › ", " > ")


class MissingTestError(RuntimeError):
    """A registry-declared test file produced no cases in the XML."""


@dataclass(frozen=True)
class TestCaseResult:
    file: str
    name: str
    status: CaseStatus
    detail: str = ""
    runner: str = ""


@dataclass(frozen=True)
class RunnerReport:
    runner: str
    xml_path: Path
    cases: tuple[TestCaseResult, ...]


@dataclass(frozen=True)
class FileOutcome:
    file: str
    status: FileStatus
    total: int = 0
    passed: int = 0
    skipped: int = 0
    failed: int = 0
    detail: str = ""
    runners: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# identity normalization
# ---------------------------------------------------------------------------


def _strip_describe_chain(value: str) -> str:
    for separator in _DESCRIBE_SEPARATORS:
        if separator in value:
            value = value.split(separator, 1)[0]
    return value.strip()


def _normalize_pytest(classname: str) -> str | None:
    parts = [p for p in classname.split(".") if p]
    if not parts:
        return None
    # `tests.test_x.TestClass` -> tests/test_x.py: keep through the last
    # segment that names a test module, dropping any class segment after it.
    last_module = max(
        (i for i, part in enumerate(parts) if part.startswith("test_")),
        default=len(parts) - 1,
    )
    return f"{_PYTEST_ROOT}/" + "/".join(parts[: last_module + 1]) + ".py"


def _normalize_path_style(value: str, root: str) -> str | None:
    candidate = _strip_describe_chain(value).replace("\\", "/").lstrip("./")
    if not candidate:
        return None
    if candidate.startswith(f"{root}/"):
        return candidate
    return f"{root}/{candidate}"


def normalize_identity(
    *, runner: Runner, classname: str, suite_name: str
) -> str | None:
    """Resolve one testcase to a repo-relative file path."""
    raw = (classname or suite_name or "").strip()
    if not raw:
        return None
    if runner == "pytest":
        return _normalize_pytest(raw)
    if runner == "vitest":
        return _normalize_path_style(raw, _VITEST_ROOT)
    if runner == "playwright":
        return _normalize_path_style(raw, _PLAYWRIGHT_TEST_DIR)
    raise ValueError(f"unknown runner: {runner!r}")


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _case_status(case: ElementTree.Element) -> tuple[CaseStatus, str]:
    for child in case:
        tag = child.tag.lower()
        if tag == "skipped":
            return "skipped", (child.get("message") or child.get("type") or "")
        if tag in ("failure", "error"):
            return "failed", (child.get("message") or "")
    return "passed", ""


def parse_junit(xml_path: Path, *, runner: Runner) -> RunnerReport:
    xml_path = Path(xml_path)
    if not xml_path.is_file():
        raise FileNotFoundError(
            f"JUnit XML not found for {runner}: {xml_path}. The gate cannot "
            "read a result that was never produced."
        )
    root = ElementTree.parse(xml_path).getroot()
    cases: list[TestCaseResult] = []
    for suite in root.iter("testsuite"):
        suite_name = suite.get("name", "")
        for case in suite.iter("testcase"):
            file = normalize_identity(
                runner=runner,
                classname=case.get("classname", ""),
                suite_name=suite_name,
            )
            if file is None:
                continue
            status, detail = _case_status(case)
            cases.append(
                TestCaseResult(
                    file=file,
                    name=case.get("name", ""),
                    status=status,
                    detail=detail,
                    runner=runner,
                )
            )
    return RunnerReport(runner=runner, xml_path=xml_path, cases=tuple(cases))


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def file_outcomes(
    reports: Iterable[RunnerReport],
    declared_files: Sequence[str],
    *,
    strict: bool = True,
) -> dict[str, FileOutcome]:
    """Roll up per-file outcomes for every ``declared_files`` entry.

    ``strict`` raises :class:`MissingTestError` when a declared file produced
    no cases; set it False only when the caller wants to report the gap rather
    than abort on it.
    """
    by_file: dict[str, list[TestCaseResult]] = {path: [] for path in declared_files}
    for report in reports:
        for case in report.cases:
            if case.file in by_file:
                by_file[case.file].append(case)

    missing = [path for path, cases in by_file.items() if not cases]
    if missing and strict:
        raise MissingTestError(
            "Registry-declared test file(s) produced no results in the JUnit "
            "XML. Either the test was renamed/deleted and the registry is "
            "stale, or the run did not include it:\n  "
            + "\n  ".join(sorted(missing))
        )

    outcomes: dict[str, FileOutcome] = {}
    for path, cases in by_file.items():
        if not cases:
            outcomes[path] = FileOutcome(
                file=path,
                status="missing",
                detail="no testcase for this file appeared in the JUnit XML",
            )
            continue
        failed = [c for c in cases if c.status == "failed"]
        skipped = [c for c in cases if c.status == "skipped"]
        passed = [c for c in cases if c.status == "passed"]
        if failed:
            status: FileStatus = "failed"
            detail = f"{len(failed)} failing case(s): " + "; ".join(
                f"{c.name}: {c.detail}".strip(": ") for c in failed[:3]
            )
        elif skipped:
            # Not proven. A skip looks present in the XML but ran nothing.
            status = "skipped"
            detail = f"{len(skipped)} skipped case(s): " + "; ".join(
                f"{c.name}: {c.detail}".strip(": ") for c in skipped[:3]
            )
        else:
            status = "passed"
            detail = ""
        outcomes[path] = FileOutcome(
            file=path,
            status=status,
            total=len(cases),
            passed=len(passed),
            skipped=len(skipped),
            failed=len(failed),
            detail=detail,
            runners=tuple(sorted({c.runner for c in cases})),
        )
    return outcomes


__all__ = [
    "CaseStatus",
    "FileOutcome",
    "FileStatus",
    "MissingTestError",
    "RunnerReport",
    "Runner",
    "TestCaseResult",
    "file_outcomes",
    "normalize_identity",
    "parse_junit",
]
