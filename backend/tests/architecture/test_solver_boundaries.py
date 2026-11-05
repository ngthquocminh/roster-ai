"""Structural proof for the governed application/CP-SAT boundary (AC2)."""
from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = ("application", "adapters", "api", "engine")
# Story 1.4's immutable projection normalization already shares only the
# source-time parser; it imports no SchedulingProblem or solver result shape.
LEGACY_INGEST_IMPORTERS = {"adapters/postgres/scenario_projection.py"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_solver_libraries_and_legacy_shapes_stay_inside_engine() -> None:
    offenders = {}
    for root in PRODUCTION_ROOTS:
        for path in (BACKEND / root).rglob("*.py"):
            relative = path.relative_to(BACKEND).as_posix()
            imports = _imports(path)
            forbidden = {
                name for name in imports
                if (name == "ortools" or name.startswith("ortools."))
                or name == "domain.result" or name.startswith("domain.result.")
                or name == "ingest" or name.startswith("ingest.")
            }
            if (
                root != "engine"
                and forbidden
                and relative not in LEGACY_INGEST_IMPORTERS
            ):
                offenders[relative] = sorted(forbidden)
    assert offenders == {}


def test_no_application_adapter_or_api_module_imports_engine() -> None:
    """The solver is reached only through the worker composition; the last
    `api/` importers left with the v0.3/v0.4 run routes."""
    importers = set()
    for root in ("application", "adapters", "api"):
        for path in (BACKEND / root).rglob("*.py"):
            if any(name == "engine" or name.startswith("engine.") for name in _imports(path)):
                importers.add(path.relative_to(BACKEND).as_posix())
    assert importers == set()


def test_governed_adapter_is_the_only_contract_engine_bridge() -> None:
    bridges = set()
    for path in (BACKEND / "engine").rglob("*.py"):
        imports = _imports(path)
        if any(name.startswith("application.contracts") for name in imports):
            bridges.add(path.relative_to(BACKEND).as_posix())
    assert bridges == {"engine/governed_adapter.py"}


def test_import_detector_can_observe_a_forbidden_boundary() -> None:
    tree = ast.parse("from ortools.sat.python import cp_model")
    assert any(
        isinstance(node, ast.ImportFrom) and node.module.startswith("ortools")
        for node in ast.walk(tree)
    )
