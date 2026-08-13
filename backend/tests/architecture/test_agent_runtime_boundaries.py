"""Executable architecture boundaries for the agent runtime seam (AC3).

This module makes mechanical the slice of AD-1 that is this story's to enforce:
domain and application code must not import the agent-runtime framework
(PydanticAI, pydantic_graph) or its telemetry SDK (Logfire). AD-1's broader
prohibition on FastAPI, SQLAlchemy, Cognito, S3, and concrete model providers
is a pre-existing repo-wide invariant this story does not add a guard for —
`FORBIDDEN_ROOT_MODULES` below intentionally covers only the agent-runtime
seam's own dependencies.
AD-19: framework messages, deferred calls, tool objects, checkpoints, and event
types never become domain, persistence, browser, or audit contracts.

These are prose in the spine and therefore unenforceable. This module makes them
mechanical.

Two design choices worth stating:

* **AST, not text search.** `application/contracts/agent_runtime.py` legitimately
  *discusses* PydanticAI in its module docstring — that documentation is valuable
  and must not be what trips the guard. Only real imports and real identifiers
  count, so docstrings and comments are invisible here.

* **The guard demonstrates its own redness.** Every check below is also run
  against synthetic violating source in `test_*_guard_actually_fails_*`. A guard
  nobody has seen go red is a guard nobody has tested, and a boundary test that
  silently stopped checking anything would otherwise look identical to a passing
  one.

Location note — a deliberate variance from AR26, recorded in the story: the
spine's structural seed lists `tests/architecture/` as a repo-root sibling of
`backend/`. pytest runs from `backend/` with `testpaths = ["tests"]` and
`backend/conftest.py` is what makes backend modules importable, so a root-level
suite would not be collected without a second rootdir convention. AC3's own list
names `backend/{api,worker,application,domain,agent,engine,adapters,migrations,evals}`
and does not include `tests/architecture`, so this placement satisfies AC3 while
keeping one rootdir.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Layers that must stay free of the framework.
GUARDED_LAYERS = ("domain", "application")

# The one package allowed to import PydanticAI.
ADAPTER_PACKAGE = "agent"

FORBIDDEN_ROOT_MODULES = ("pydantic_ai", "pydantic_graph", "logfire")

# Framework type names that must not appear as identifiers in guarded layers.
# Grouped by the category AC2 enumerates.
FRAMEWORK_TYPE_NAMES = frozenset(
    {
        # messages
        "ModelMessage",
        "ModelRequest",
        "ModelResponse",
        "ModelMessagesTypeAdapter",
        "TextPart",
        "ThinkingPart",
        "ToolCallPart",
        "ToolReturnPart",
        "SystemPromptPart",
        "UserPromptPart",
        "RetryPromptPart",
        "CompactionPart",
        # deferred calls
        "DeferredToolRequests",
        "DeferredToolResults",
        "ApprovalRequired",
        "CallDeferred",
        "ToolDenied",
        "ToolApproved",
        # framework tools / agent objects
        "Agent",
        "AgentRun",
        "AgentRunResult",
        "RunContext",
        "FunctionToolset",
        "AbstractToolset",
        "ToolDefinition",
        "FunctionModel",
        "TestModel",
        # checkpoints / limits / cancellation
        "UsageLimits",
        "UsageLimitExceeded",
        "CancellationToken",
        "RunCancelled",
        "ModelHTTPError",
        "UnexpectedModelBehavior",
        # telemetry
        "Instrumentation",
        "InstrumentationSettings",
    }
)


def _python_files(*relative: str) -> list[Path]:
    files: list[Path] = []
    for part in relative:
        root = BACKEND_ROOT / part
        if root.exists():
            files.extend(
                p for p in root.rglob("*.py") if "__pycache__" not in p.parts
            )
    return files


def _imported_modules(tree: ast.AST) -> set[str]:
    """Every module name a source file imports, dotted form preserved."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import; not used in this codebase
                continue
            if node.module:
                modules.add(node.module)
    return modules


def _identifiers(tree: ast.AST) -> set[str]:
    """Identifiers actually used in code — never docstrings, never comments."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
    return names


def _root_of(module: str) -> str:
    return module.split(".")[0]


# ---------------------------------------------------------------------------
# The checks, as pure functions so they can also be run against synthetic source
# ---------------------------------------------------------------------------


def find_forbidden_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        module
        for module in _imported_modules(tree)
        if _root_of(module) in FORBIDDEN_ROOT_MODULES
    }


def find_framework_type_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return _identifiers(tree) & FRAMEWORK_TYPE_NAMES


def find_imports_of(source: str, package: str) -> set[str]:
    tree = ast.parse(source)
    return {m for m in _imported_modules(tree) if _root_of(m) == package}


def find_framework_typed_contract_fields(source: str) -> set[str]:
    """Dataclass fields typed as, or defaulting to, a framework object.

    This is the executable form of the story's capability-4 hard rule: if a
    contract field could hold a PydanticAI object, the framework has become a
    persisted contract regardless of what the docstring says.
    """
    offenders: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or statement.target is None:
                continue
            field_name = getattr(statement.target, "id", "<unknown>")
            annotation = ast.unparse(statement.annotation)
            default = ast.unparse(statement.value) if statement.value else ""
            for token in FRAMEWORK_TYPE_NAMES:
                if token in _tokens(annotation) or token in _tokens(default):
                    offenders.add(f"{node.name}.{field_name}")
    return offenders


def _tokens(expression: str) -> set[str]:
    if not expression:
        return set()
    try:
        return _identifiers(ast.parse(expression, mode="eval"))
    except SyntaxError:  # pragma: no cover - defensive
        return set()


# ---------------------------------------------------------------------------
# Guarded layers stay framework-free
# ---------------------------------------------------------------------------


def test_guarded_layers_never_import_the_framework() -> None:
    violations: list[str] = []
    for path in _python_files(*GUARDED_LAYERS):
        found = find_forbidden_imports(path.read_text(encoding="utf-8"))
        if found:
            violations.append(f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}")
    assert not violations, (
        "domain/application must not import the agent framework (AD-1, AD-19):\n"
        + "\n".join(violations)
    )


def test_guarded_layers_never_name_a_framework_type() -> None:
    violations: list[str] = []
    for path in _python_files(*GUARDED_LAYERS):
        found = find_framework_type_names(path.read_text(encoding="utf-8"))
        if found:
            violations.append(f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}")
    assert not violations, (
        "framework message/deferred-call/tool/checkpoint/telemetry type names "
        "must not appear in domain/application (AC2):\n" + "\n".join(violations)
    )


def test_the_guarded_layers_are_not_empty() -> None:
    """If the file walk silently found nothing, every check above would be
    vacuously green."""
    files = _python_files(*GUARDED_LAYERS)
    assert len(files) > 5, f"expected to scan real modules, scanned {len(files)}"
    assert any("contracts" in str(p) for p in files)
    assert any("ports" in str(p) for p in files)


# ---------------------------------------------------------------------------
# Dependency direction is one-way
# ---------------------------------------------------------------------------


def test_agent_may_import_application_and_domain() -> None:
    """The permitted direction — asserted so the test suite proves the rule has a
    direction, not merely a prohibition."""
    adapter_files = _python_files(ADAPTER_PACKAGE)
    assert adapter_files, "backend/agent/ must exist"

    imported: set[str] = set()
    for path in adapter_files:
        imported |= find_imports_of(path.read_text(encoding="utf-8"), "application")
    assert imported, "the adapter is expected to depend on the application layer"


def test_application_and_domain_never_import_the_adapter() -> None:
    violations: list[str] = []
    for path in _python_files(*GUARDED_LAYERS):
        found = find_imports_of(path.read_text(encoding="utf-8"), ADAPTER_PACKAGE)
        if found:
            violations.append(f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}")
    assert not violations, (
        "dependency direction is one-way: agent -> application/domain, never the "
        "reverse:\n" + "\n".join(violations)
    )


def test_domain_imports_nothing_outside_itself() -> None:
    """AD-1: the domain is pure."""
    allowed_roots = {"domain", "__future__"}
    violations: list[str] = []
    for path in _python_files("domain"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            root = _root_of(module)
            if root in allowed_roots:
                continue
            # stdlib is fine; another backend package is not.
            if (BACKEND_ROOT / root).is_dir():
                violations.append(f"{path.relative_to(BACKEND_ROOT)}: {module}")
    assert not violations, (
        "domain must import nothing outside itself (AD-1):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Persisted shape: no contract field may hold a framework object
# ---------------------------------------------------------------------------


def test_no_contract_field_is_typed_as_a_framework_object() -> None:
    violations: list[str] = []
    for path in _python_files("application/contracts"):
        found = find_framework_typed_contract_fields(
            path.read_text(encoding="utf-8")
        )
        if found:
            violations.append(f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}")
    assert not violations, (
        "a contract field typed as or defaulting to a framework object makes "
        "PydanticAI a persisted contract (AD-19):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# The guard demonstrates its own redness
# ---------------------------------------------------------------------------

VIOLATING_IMPORT = "from pydantic_ai.messages import ModelResponse\n"

VIOLATING_CONTRACT = """
from dataclasses import dataclass, field
from pydantic_ai.messages import ModelResponse

@dataclass(frozen=True)
class BadContractV1:
    schema_version: str = "1"
    raw: ModelResponse | None = None
"""

VIOLATING_REVERSE_IMPORT = "from agent.runtime import PydanticAIAgentRuntime\n"

CLEAN_CONTRACT = """
from dataclasses import dataclass

@dataclass(frozen=True)
class GoodContractV1:
    schema_version: str = "1"
    text: str | None = None
"""


def test_import_guard_actually_fails_on_a_violating_import() -> None:
    assert find_forbidden_imports(VIOLATING_IMPORT) == {"pydantic_ai.messages"}
    assert find_forbidden_imports("import pydantic_ai") == {"pydantic_ai"}
    assert find_forbidden_imports("import logfire") == {"logfire"}
    # and stays quiet on the real, clean tree shape
    assert find_forbidden_imports("from application.contracts import x") == set()


def test_type_name_guard_actually_fails_on_a_violating_identifier() -> None:
    assert find_framework_type_names("x: ModelResponse = None") == {"ModelResponse"}
    assert find_framework_type_names("a = DeferredToolRequests()") == {
        "DeferredToolRequests"
    }
    # A docstring or comment mentioning the framework is NOT a violation.
    assert find_framework_type_names('"""We never return a ModelResponse."""') == set()
    assert find_framework_type_names("# ModelResponse is forbidden here\nx = 1") == set()


def test_contract_field_guard_actually_fails_on_a_framework_typed_field() -> None:
    assert find_framework_typed_contract_fields(VIOLATING_CONTRACT) == {
        "BadContractV1.raw"
    }
    assert find_framework_typed_contract_fields(CLEAN_CONTRACT) == set()


def test_direction_guard_actually_fails_on_a_reverse_import() -> None:
    assert find_imports_of(VIOLATING_REVERSE_IMPORT, "agent") == {"agent.runtime"}
    assert find_imports_of("from application.ports import x", "agent") == set()


def test_guard_rejects_the_real_adapter_source_if_it_were_in_a_guarded_layer() -> None:
    """The strongest form: feed the guard a REAL framework-importing module and
    confirm it reports it. This is the file that would have to move into
    application/ for the boundary to actually break.
    """
    adapter_source = (BACKEND_ROOT / "agent" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert find_forbidden_imports(adapter_source), (
        "agent/runtime.py genuinely imports the framework; if the guard cannot "
        "see that, it cannot see a real violation either"
    )
    assert find_framework_type_names(adapter_source)


@pytest.mark.parametrize(
    "layer_file",
    [
        "application/contracts/agent_runtime.py",
        "application/contracts/capability_manifest.py",
        "application/contracts/grounding.py",
        "application/ports/agent_runtime.py",
    ],
)
def test_new_agent_modules_are_individually_clean(layer_file: str) -> None:
    """Named explicitly so a future refactor that deletes them fails loudly rather
    than shrinking the guard's scope in silence."""
    path = BACKEND_ROOT / layer_file
    assert path.exists(), f"{layer_file} is expected to exist"
    source = path.read_text(encoding="utf-8")
    assert find_forbidden_imports(source) == set()
    assert find_framework_type_names(source) == set()
