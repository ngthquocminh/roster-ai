"""Read JUnit XML from pytest, Vitest and Playwright into per-file outcomes.

All three runners emit JUnit natively, so this adds no dependency:

    uv run --frozen pytest --junitxml=<path>
    npx vitest run --reporter=junit --outputFile=<path>
    PLAYWRIGHT_JUNIT_OUTPUT_NAME=<path> npx playwright test --reporter=junit

Each writes a different test identity, all three verified against real output:

===========  ====================================  ==========================
runner       `classname`                           resolves to
===========  ====================================  ==========================
pytest       ``tests.test_auth_api`` (dotted)      ``backend/tests/....py``
Vitest       ``src/lib/errors.test.ts`` (path)     ``frontend/...``
Playwright   ``harness.spec.ts`` (path, testDir)   ``frontend/e2e/...``
===========  ====================================  ==========================

Playwright additionally puts the *project* name in `hostname` (``chromium``,
``msedge``) where pytest and Vitest put the machine name, so browser-level
coverage is recoverable from the XML and is checked rather than assumed.

Three rules here carry the gate:

1. A registry-declared file absent from the XML raises. Without that the
   registry silently decays the first time a test is renamed or deleted, and
   the report keeps claiming a check that no longer runs.
2. A skipped test is not a passed test. `postgres`-marked tests skip *cleanly*
   when no PostgreSQL service is up, and a skip serialises as `<skipped/>`
   inside a `<testcase>` — it looks present. Treated as not proven so that
   running the gate without Docker up cannot produce a green report that
   proves nothing.
3. A *deselected* test is not a passed test either, and unlike a skip it leaves
   no trace at all in the XML. `pyproject.toml` already ships
   ``addopts = -m "not live"``, so any further ``-m`` narrowing silently drops
   cases from a file that still reports `passed` on the ones that remain. See
   :func:`missing_pytest_cases`, which recovers the expected case names from
   the test sources themselves rather than trusting the XML to be complete.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence
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


class MalformedJUnitError(RuntimeError):
    """A JUnit XML file exists but cannot be parsed."""


@dataclass(frozen=True)
class TestCaseResult:
    file: str
    name: str
    status: CaseStatus
    detail: str = ""
    runner: str = ""
    #: Playwright's browser project (`chromium`, `msedge`). Empty for the other
    #: runners, whose `hostname` is the machine rather than a project.
    project: str = ""


@dataclass(frozen=True)
class RunnerReport:
    runner: str
    xml_path: Path
    cases: tuple[TestCaseResult, ...]
    #: Earliest `testsuite/@timestamp` in the file — when the run actually
    #: started. The gate asserts this postdates the commit it binds to, which
    #: is what stops a stale XML from being read as a fresh result.
    timestamp: str = ""


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
    #: Playwright browser projects this file actually ran under.
    projects: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# identity normalization
# ---------------------------------------------------------------------------


def _strip_describe_chain(value: str) -> str:
    for separator in _DESCRIBE_SEPARATORS:
        if separator in value:
            value = value.split(separator, 1)[0]
    return value.strip()


def _strip_relative_prefix(value: str) -> str:
    """Drop leading `./` / `../` segments without touching a dot-directory.

    `str.lstrip("./")` strips a *character set*, so it also eats the leading dot
    of `.storybook/a.test.ts` and turns `../src/x` into `src/x`. Both produce a
    silently wrong path and then a bogus missing-test failure.
    """
    while True:
        if value.startswith("./"):
            value = value[2:]
        elif value.startswith("../"):
            value = value[3:]
        else:
            return value


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
    candidate = "/".join(parts[: last_module + 1]) + ".py"
    # Running pytest from the repo root instead of `backend/` yields
    # `backend.tests.test_x`, which would otherwise be prefixed a second time
    # into `backend/backend/tests/test_x.py`. `_normalize_path_style` guards
    # this for the other two runners; pytest needs it too.
    if candidate.startswith(f"{_PYTEST_ROOT}/"):
        return candidate
    return f"{_PYTEST_ROOT}/{candidate}"


def _normalize_path_style(value: str, root: str) -> str | None:
    candidate = _strip_relative_prefix(
        _strip_describe_chain(value).replace("\\", "/")
    )
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
    try:
        root = ElementTree.parse(xml_path).getroot()
    except ElementTree.ParseError as exc:
        raise MalformedJUnitError(
            f"JUnit XML for {runner} is not parseable ({xml_path}): {exc}. A "
            "run killed mid-write leaves a truncated file, which must block "
            "the gate rather than be read as an empty result."
        ) from exc
    cases: list[TestCaseResult] = []
    timestamps: list[str] = []
    for suite in root.iter("testsuite"):
        suite_name = suite.get("name", "")
        stamp = suite.get("timestamp", "")
        if stamp:
            timestamps.append(stamp)
        # Playwright puts the browser project here; the other two put the
        # machine name, which is not a project and must not be recorded as one.
        project = suite.get("hostname", "") if runner == "playwright" else ""
        # Only this suite's *direct* testcase children. `iter()` recurses, and
        # `root.iter("testsuite")` already yields nested suites in their own
        # right — using both would count every nested case once per ancestor.
        for case in suite.findall("testcase"):
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
                    project=project,
                )
            )
    return RunnerReport(
        runner=runner,
        xml_path=xml_path,
        cases=tuple(cases),
        timestamp=min(timestamps) if timestamps else "",
    )


# ---------------------------------------------------------------------------
# deselection detection
# ---------------------------------------------------------------------------

#: pytest appends `[param]` to a parametrized case name.
_PARAM_SUFFIX = re.compile(r"\[.*\]$", re.DOTALL)


def declared_pytest_cases(module_path: Path) -> tuple[str, ...]:
    """Every test function name a pytest module defines, read from its source.

    The XML cannot answer "was anything deselected?" — a deselected case is
    simply absent, indistinguishable from a case that never existed. The source
    can, so the expected set is recovered by parsing rather than by trusting a
    hand-maintained list in the registry.
    """
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ()
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("test_"):
                        names.append(item.name)
    return tuple(sorted(names))


def missing_pytest_cases(
    reports: Iterable[RunnerReport],
    declared_files: Sequence[str],
    *,
    repo_root: Path,
) -> Mapping[str, tuple[str, ...]]:
    """Test functions that exist in source but produced no case in the XML.

    A non-empty result means the run did not cover what the registry claims —
    almost always an `-m` selector narrowing the suite. Reported per file.
    """
    observed: dict[str, set[str]] = {}
    for report in reports:
        if report.runner != "pytest":
            continue
        for case in report.cases:
            base = _PARAM_SUFFIX.sub("", case.name)
            observed.setdefault(case.file, set()).add(base)

    gaps: dict[str, tuple[str, ...]] = {}
    for path in declared_files:
        if not path.endswith(".py"):
            continue
        expected = declared_pytest_cases(repo_root / path)
        if not expected:
            continue
        seen = observed.get(path, set())
        absent = tuple(name for name in expected if name not in seen)
        if absent:
            gaps[path] = absent
    return gaps


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
            projects=tuple(sorted({c.project for c in cases if c.project})),
        )
    return outcomes


__all__ = [
    "CaseStatus",
    "FileOutcome",
    "FileStatus",
    "MalformedJUnitError",
    "MissingTestError",
    "RunnerReport",
    "Runner",
    "TestCaseResult",
    "declared_pytest_cases",
    "file_outcomes",
    "missing_pytest_cases",
    "normalize_identity",
    "parse_junit",
]
