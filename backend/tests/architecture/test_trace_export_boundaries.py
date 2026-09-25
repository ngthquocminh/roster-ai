"""Story 5.9's export-boundary architecture guards (Decisions 1, 2, 4 and 5).

Four rules, each a pure function run against the real tree and against
synthetic violating source:

1. One boundary. The OpenTelemetry SDK, exporter and instrumentation packages
   are imported only by `adapters/telemetry/spans.py` and `api/tracing.py`; any
   `opentelemetry.*` is additionally allowed only in `agent/runtime.py` (the API
   facade, for the run-correlation capability). `logfire` is imported by no
   runtime root, and is not a runtime dependency.
2. F1: the only tracked files naming `AGENT_TRACE_CONTENT_MODE` are a declared
   set, and the only ones containing `synthetic-eval` are `settings.py` (the
   constant) and the live-eval compose override (which sets it).
3. `db.statement` is exported verbatim, so every `text(...)` and
   `.exec_driver_sql(...)` argument must be a string literal: placeholders
   only, never a value built into SQL.

What these do not cover: they are AST/text walks over this repository. A
third-party package that builds its own exporter is invisible to them, and a
person who sets the content mode by hand on a real deployment gets content
export (F1's documented residual, `docs/CONFIGURATION.md`).
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

#: Same walk as `test_telemetry_boundaries.NON_TEST_BACKEND_ROOTS`.
NON_TEST_BACKEND_ROOTS = (
    "adapters", "agent", "api", "application", "config", "domain", "engine",
    "evals", "fixtures", "ingest", "llm", "migrations", "scripts", "services",
    "store", "worker",
)
#: Decision 1's `logfire` ban: the runtime roots plus backend-root modules.
#: `evals/` and `scripts/` are not runtime (Story 5.10 owns `logfire` there).
LOGFIRE_BANNED_ROOTS = (
    "api", "worker", "agent", "application", "domain", "adapters", "engine",
    "services", "store", "ingest", "llm", "config",
)
SDK_PREFIXES = ("opentelemetry.sdk", "opentelemetry.exporter", "opentelemetry.instrumentation")
SDK_ALLOWED = frozenset({"adapters/telemetry/spans.py", "api/tracing.py"})
#: Story 5.10: the publisher writes verdict spans through the API facade so they
#: carry their own instrumentation scope (`shiftmind.live_eval`), which the
#: sanitizer categorizes; Logfire's `span()` would emit them under scope
#: `logfire`, exported with no attributes. Its SDK imports stay forbidden:
#: `SDK_ALLOWED` is unchanged.
LOGFIRE_PUBLISHER = "evals/live_conversations/logfire_publish.py"
FACADE_ALLOWED = SDK_ALLOWED | {"agent/runtime.py", LOGFIRE_PUBLISHER}
#: Story 5.10 Decision 1: the Logfire SDK and pydantic-evals, in one file.
EVAL_TOOLING_PACKAGES = ("logfire", "pydantic_evals")
#: Story 5.10 Decision 2: dev group only, exact.
EVAL_TOOLING_DEV_PINS = {"logfire": "5.1.0", "pydantic-evals": "2.27.0"}

OTEL_PINS = {
    "opentelemetry-sdk": "1.44.0",
    "opentelemetry-exporter-otlp-proto-http": "1.44.0",
    "opentelemetry-instrumentation-fastapi": "0.65b0",
    "opentelemetry-instrumentation-sqlalchemy": "0.65b0",
    "opentelemetry-instrumentation-httpx": "0.65b0",
}

CONTENT_MODE_VAR = "AGENT_TRACE_CONTENT_MODE"
CONTENT_MODE_VALUE = "synthetic-eval"
OVERRIDE = "backend/evals/live_conversations/compose.override.yml"
#: Each tracked file allowed to name the variable, with its reason.
CONTENT_MODE_VAR_FILES = {
    "backend/settings.py": "reads it",
    "backend/conftest.py": "pops it so the test process is keyless (Decision 3)",
    "backend/evals/live_conversations/configuration.py": (
        "excludes it from behavioral_digest (Decision 13)"
    ),
    OVERRIDE: "sets it for the disposable live-evaluation stack",
}
CONTENT_MODE_VALUE_FILES = frozenset({"backend/settings.py", OVERRIDE})


def _python_files(*roots: str) -> list[Path]:
    files = [
        path
        for root in roots
        for path in (BACKEND_ROOT / root).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    return files


def _backend_root_modules() -> list[Path]:
    return [path for path in BACKEND_ROOT.glob("*.py") if path.name != "conftest.py"]


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
            # `from opentelemetry import sdk` names the SDK too.
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


# --- rule 1: one boundary ---------------------------------------------------


def boundary_violations(relative: str, source: str) -> set[str]:
    """Imports in `relative` that the one-boundary rule forbids."""
    found: set[str] = set()
    for module in _imported_modules(source):
        if any(_under(module, prefix) for prefix in SDK_PREFIXES):
            if relative not in SDK_ALLOWED:
                found.add(module)
        elif _under(module, "opentelemetry") and relative not in FACADE_ALLOWED:
            found.add(module)
    return found


def logfire_imports(source: str) -> set[str]:
    return {module for module in _imported_modules(source) if _under(module, "logfire")}


def eval_tooling_imports(source: str) -> set[str]:
    return {
        module
        for module in _imported_modules(source)
        if any(_under(module, package) for package in EVAL_TOOLING_PACKAGES)
    }


def test_opentelemetry_is_imported_only_at_the_export_boundary() -> None:
    files = _python_files(*NON_TEST_BACKEND_ROOTS) + _backend_root_modules()
    violations = {
        _relative(path): found
        for path in files
        if (found := boundary_violations(_relative(path), path.read_text(encoding="utf-8")))
    }
    assert not violations
    # Non-vacuity: the boundary modules exist and really import what they own.
    spans = (BACKEND_ROOT / "adapters/telemetry/spans.py").read_text(encoding="utf-8")
    tracing = (BACKEND_ROOT / "api/tracing.py").read_text(encoding="utf-8")
    assert any(_under(m, "opentelemetry.sdk") for m in _imported_modules(spans))
    assert any(_under(m, "opentelemetry.instrumentation") for m in _imported_modules(tracing))


def test_no_runtime_root_imports_logfire() -> None:
    files = _python_files(*LOGFIRE_BANNED_ROOTS) + _backend_root_modules()
    violations = {
        _relative(path): found
        for path in files
        if (found := logfire_imports(path.read_text(encoding="utf-8")))
    }
    assert not violations


def test_logfire_and_pydantic_evals_are_imported_by_the_publisher_only() -> None:
    """Stricter than the runtime-root ban above: `evals/` and `scripts/` too."""
    files = _python_files(*NON_TEST_BACKEND_ROOTS) + _backend_root_modules()
    importers = {
        _relative(path)
        for path in files
        if eval_tooling_imports(path.read_text(encoding="utf-8"))
    }
    assert importers == {LOGFIRE_PUBLISHER}
    # Non-vacuity: the publisher really imports both.
    publisher = eval_tooling_imports(
        (BACKEND_ROOT / LOGFIRE_PUBLISHER).read_text(encoding="utf-8")
    )
    assert {module.split(".")[0] for module in publisher} == set(EVAL_TOOLING_PACKAGES)


def runtime_dependencies(pyproject: str) -> list[str]:
    """The quoted requirement strings of `[project].dependencies`."""
    block = re.search(r"(?ms)^\[project\].*?^dependencies\s*=\s*\[(.*?)^\]", pyproject)
    assert block is not None, "no [project].dependencies block"
    return re.findall(r'^\s*"([^"]+)"', block.group(1), flags=re.M)


def dependency_pin_violations(pyproject: str) -> list[str]:
    requirements = runtime_dependencies(pyproject)
    problems = [
        requirement for requirement in requirements
        if re.match(r"logfire\b(?!-api)", requirement)
        or re.match(r"pydantic-evals\b", requirement)
    ]
    for name, version in OTEL_PINS.items():
        if f"{name}=={version}" not in requirements:
            problems.append(f"{name} is not pinned exactly to {version}")
    return problems


def dev_dependencies(pyproject: str) -> list[str]:
    """The quoted requirement strings of `[dependency-groups].dev`."""
    block = re.search(r"(?ms)^\[dependency-groups\].*?^dev\s*=\s*\[(.*?)^\]", pyproject)
    assert block is not None, "no [dependency-groups].dev block"
    return re.findall(r'^\s*"([^"]+)"', block.group(1), flags=re.M)


def dev_pin_violations(pyproject: str) -> list[str]:
    requirements = dev_dependencies(pyproject)
    return [
        f"{name} is not pinned exactly to {version} in the dev group"
        for name, version in EVAL_TOOLING_DEV_PINS.items()
        if f"{name}=={version}" not in requirements
    ]


def test_eval_tooling_is_pinned_exactly_in_the_dev_group() -> None:
    assert dev_pin_violations(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ) == []


def test_logfire_is_not_a_runtime_dependency_and_otel_pins_are_exact() -> None:
    assert dependency_pin_violations(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ) == []


# --- rule 2: F1, content mode in exactly one config file ---------------------


def _tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in output.splitlines() if line]


def _in_scope(path: str) -> bool:
    # `evidence/**` holds generated measurement records (Story 5.2's report
    # names the content modes it proved); no process reads them as config.
    return not (
        path.startswith(("docs/", "_bmad-output/", "backend/tests/", "evidence/"))
        or path.endswith(".md")
    )


def content_mode_violations(files: dict[str, str]) -> set[str]:
    """Files (path -> text) naming the variable or the value outside the allowed sets."""
    return {
        path for path, text in files.items()
        if (CONTENT_MODE_VAR in text and path not in CONTENT_MODE_VAR_FILES)
        or (CONTENT_MODE_VALUE in text and path not in CONTENT_MODE_VALUE_FILES)
    }


def test_only_the_live_eval_override_sets_a_non_off_content_mode() -> None:
    texts: dict[str, str] = {}
    for path in _tracked_files():
        if not _in_scope(path):
            continue
        try:
            texts[path] = (REPO_ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
    assert content_mode_violations(texts) == set()
    # Positively: the override sets the mode on both services, so the guard
    # cannot pass on an empty world.
    services = yaml.safe_load(texts[OVERRIDE])["services"]
    for service in ("api", "worker"):
        assert services[service]["environment"][CONTENT_MODE_VAR] == CONTENT_MODE_VALUE
    assert "docker-compose.yml" in texts and "backend/.env.example" in texts


def test_content_mode_guard_detects_synthetic_violations() -> None:
    cases = {
        "docker-compose.yml": (
            "services:\n  api:\n    environment:\n"
            "      AGENT_TRACE_CONTENT_MODE: synthetic-eval\n"
        ),
        "backend/.env.example": "AGENT_TRACE_CONTENT_MODE=synthetic-eval\n",
        ".github/workflows/deploy.yml": (
            "jobs:\n  d:\n    env:\n      AGENT_TRACE_CONTENT_MODE: synthetic-eval\n"
        ),
        "infra/task-definition.json": (
            '{"environment": [{"name": "AGENT_TRACE_CONTENT_MODE", '
            '"value": "synthetic-eval"}]}'
        ),
        # The value alone, reached some other way, still counts.
        "infra/other.json": '{"mode": "synthetic-eval"}',
    }
    assert content_mode_violations(cases) == set(cases)
    # The evidence exclusion is a scope rule only; config paths stay in scope.
    assert not _in_scope("evidence/story-5.2/content-minimization-report.json")
    assert all(_in_scope(path) for path in cases)
    assert content_mode_violations({OVERRIDE: cases["docker-compose.yml"]}) == set()
    # conftest may name the variable but never the value.
    assert content_mode_violations(
        {"backend/conftest.py": 'os.environ["AGENT_TRACE_CONTENT_MODE"] = "synthetic-eval"'}
    ) == {"backend/conftest.py"}


# --- rule 3: placeholder-only SQL --------------------------------------------

_TEXT_FACTORIES = frozenset({
    "sqlalchemy.text", "sqlalchemy.sql.text", "sqlalchemy.sql.expression.text",
})
_SQLALCHEMY_MODULES = frozenset({"sqlalchemy", "sqlalchemy.sql", "sqlalchemy.sql.expression"})


def _is_literal(node: ast.AST) -> bool:
    # Implicit concatenation of literals is already one `Constant` in the AST.
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def nonliteral_sql(source: str) -> list[str]:
    """`text(...)` / `.exec_driver_sql(...)` calls whose SQL is not a literal.

    `text` is resolved through the module's imports, as the engine guard in
    `test_telemetry_boundaries.py` resolves `create_engine`. `store/db.py`'s
    SQLite `conn.execute(f"PRAGMA ...")` is neither construct and is out of
    this rule's reach by construction -- SQLAlchemy never sees it.
    """
    tree = ast.parse(source)
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name] = alias.name
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        sql_call = False
        if isinstance(func, ast.Name):
            sql_call = bindings.get(func.id) in _TEXT_FACTORIES
        elif isinstance(func, ast.Attribute):
            if func.attr == "exec_driver_sql":
                sql_call = True
            elif func.attr == "text" and isinstance(func.value, ast.Name):
                sql_call = bindings.get(func.value.id) in _SQLALCHEMY_MODULES
        if sql_call and (not node.args or not _is_literal(node.args[0])):
            offenders.append(ast.unparse(node))
    return offenders


def test_sql_passed_to_sqlalchemy_is_always_a_literal() -> None:
    files = _python_files(*NON_TEST_BACKEND_ROOTS) + _backend_root_modules()
    violations = {
        _relative(path): found
        for path in files
        if (found := nonliteral_sql(path.read_text(encoding="utf-8")))
    }
    assert not violations
    # Non-vacuity: the walk sees real SQL sites.
    assert any(
        "exec_driver_sql" in path.read_text(encoding="utf-8")
        for path in _python_files("worker")
    )


def test_each_guard_detects_synthetic_violating_source() -> None:
    assert boundary_violations("api/routers/runs.py", "import opentelemetry.sdk.trace") == {
        "opentelemetry.sdk.trace"
    }
    assert boundary_violations(
        "application/x.py", "from opentelemetry import trace"
    ) == {"opentelemetry", "opentelemetry.trace"}
    assert boundary_violations(
        "agent/runtime.py", "from opentelemetry.exporter.otlp.proto.http import X"
    )
    assert boundary_violations("agent/runtime.py", "from opentelemetry import trace") == set()
    assert boundary_violations(
        "adapters/telemetry/spans.py", "from opentelemetry.sdk.trace import TracerProvider"
    ) == set()
    assert logfire_imports("import logfire\nimport logfire_api") == {"logfire"}
    assert eval_tooling_imports(
        "import logfire_api\nfrom pydantic_evals import Dataset\nimport logfire"
    ) == {"pydantic_evals", "pydantic_evals.Dataset", "logfire"}
    assert boundary_violations(LOGFIRE_PUBLISHER, "from opentelemetry import trace") == set()
    assert boundary_violations(
        LOGFIRE_PUBLISHER, "from opentelemetry.sdk.trace import TracerProvider"
    )
    assert dependency_pin_violations(
        '[project]\ndependencies = [\n    "pydantic-evals==2.27.0",\n]\n'
    )
    assert dev_pin_violations(
        '[dependency-groups]\ndev = [\n    "logfire>=5.1.0",\n    "pydantic-evals==2.27.0",\n]\n'
    ) == ["logfire is not pinned exactly to 5.1.0 in the dev group"]
    assert dependency_pin_violations(
        '[project]\ndependencies = [\n    "logfire>=4",\n'
        '    "opentelemetry-sdk>=1.44.0",\n]\n'
    )
    for evasion in (
        'from sqlalchemy import text\ntext(f"SELECT {x}")',
        'import sqlalchemy as sa\nsa.text("SELECT " + x)',
        'from sqlalchemy.sql import text as t\nt(query)',
        'connection.exec_driver_sql("SET ROLE %s" % role)',
        'connection.exec_driver_sql("SELECT {}".format(x))',
    ):
        assert nonliteral_sql(evasion), evasion
    assert not nonliteral_sql(
        'from sqlalchemy import text\ntext("SELECT 1 " "FROM t WHERE id = :id")'
    )
    assert not nonliteral_sql('from string import Template as text\ntext(f"{x}")')
