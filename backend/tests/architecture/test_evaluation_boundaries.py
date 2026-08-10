"""Executable boundaries for Story 2.2's deterministic evaluation harness."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = BACKEND_ROOT / "evals"
REVERSE_GUARDED_ROOTS = (BACKEND_ROOT / "domain", BACKEND_ROOT / "application")
MODEL_CONSTRUCTORS = frozenset({"FunctionModel", "TestModel"})


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def constructs_pydantic_model(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in MODEL_CONSTRUCTORS
        for node in ast.walk(tree)
    )


def disables_model_requests_at_module_scope(source: str) -> bool:
    """Recognize only a top-level ``models.ALLOW_MODEL_REQUESTS = False``."""
    tree = ast.parse(source)
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not isinstance(statement.value, ast.Constant) or statement.value.value is not False:
            continue
        for target in statement.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "ALLOW_MODEL_REQUESTS"
                and isinstance(target.value, ast.Name)
                and target.value.id == "models"
            ):
                return True
    return False


def imports_package(source: str, package: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.split(".")[0] == package)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and node.module.split(".")[0] == package
        ):
            found.add(node.module)
    return found


def test_every_eval_model_builder_disables_live_requests_at_module_scope() -> None:
    builders: list[Path] = []
    violations: list[str] = []
    for path in _python_files(EVALS_ROOT):
        source = path.read_text(encoding="utf-8")
        if constructs_pydantic_model(source):
            builders.append(path)
            if not disables_model_requests_at_module_scope(source):
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert builders, "expected at least one deterministic model builder under evals/"
    assert not violations, (
        "eval model builders must set models.ALLOW_MODEL_REQUESTS = False at "
        f"module scope: {violations}"
    )


def test_application_and_domain_never_import_evals() -> None:
    violations: list[str] = []
    for root in REVERSE_GUARDED_ROOTS:
        for path in _python_files(root):
            found = imports_package(path.read_text(encoding="utf-8"), "evals")
            if found:
                violations.append(f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}")
    assert not violations, (
        "dependency direction is evals -> agent/application/domain, never the reverse:\n"
        + "\n".join(violations)
    )


def test_network_guard_actually_fails_on_a_violating_builder() -> None:
    violating = """
from pydantic_ai.models.function import FunctionModel
model = FunctionModel(lambda messages, info: None)
"""
    nested_only = """
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
def too_late():
    models.ALLOW_MODEL_REQUESTS = False
model = FunctionModel(lambda messages, info: None)
"""
    clean = """
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
models.ALLOW_MODEL_REQUESTS = False
model = FunctionModel(lambda messages, info: None)
"""
    assert constructs_pydantic_model(violating)
    assert not disables_model_requests_at_module_scope(violating)
    assert not disables_model_requests_at_module_scope(nested_only)
    assert disables_model_requests_at_module_scope(clean)


def test_direction_guard_actually_fails_on_a_reverse_import() -> None:
    assert imports_package("from evals.cases import GoldenCase", "evals") == {
        "evals.cases"
    }
    assert imports_package("from application.ports import x", "evals") == set()
