"""Executable AD-1 boundary for Story 2.3's new application modules.

Scope is deliberately narrow and stated as data, not prose: ``GUARDED`` plus
everything under ``application/use_cases/``. Modules in ``ALLOWED_LEAKS`` are
known violations this guard does not cover.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GUARDED = (
    BACKEND_ROOT / "application/contracts/activity.py",
    BACKEND_ROOT / "application/contracts/persisted_event.py",
    # Story 2.4's cursor contract. Added here rather than left uncovered: a
    # guard whose file list stops growing with the layer it guards quietly
    # becomes a claim about coverage it no longer has.
    BACKEND_ROOT / "application/contracts/stream_cursor.py",
    BACKEND_ROOT / "application/ports/conversation.py",
)

# Swept whole, not enumerated: Story 2.5's capability package will grow (2.6
# adds and removes modules under it), and a hand-maintained file list would let
# the next module in silently unguarded.
SWEPT_PACKAGES = (
    BACKEND_ROOT / "application/use_cases",
    BACKEND_ROOT / "application/capabilities",
    # Story 2.9's new application packages. This list must grow with the layer
    # it guards -- a sweep whose file list stops growing quietly becomes a claim
    # about coverage it no longer has (this module's own stated rule).
    BACKEND_ROOT / "application/clarification",
    BACKEND_ROOT / "application/grounding",
    BACKEND_ROOT / "application/contracts",
)

# Known, ticketed AD-1 violations outside this guard's coverage. Tracked in
# `_bmad-output/implementation-artifacts/deferred-work.md` under "Deferred
# from: story-2-3 creation (2026-08-10)", whose definition of done is deleting
# the entry here — so it is a real, greppable value rather than a comment.
ALLOWED_LEAKS = {
    "application/ports/scenario_catalogue.py": "deferred-work.md story-2-3 creation (2026-08-10)",
}


def forbidden_imports(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.split(".")[0] in {"sqlalchemy", "fastapi"})
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] in {"sqlalchemy", "fastapi"}:
            found.add(node.module)
    return found


def guarded_paths() -> tuple[Path, ...]:
    swept = tuple(
        sorted(p for package in SWEPT_PACKAGES for p in package.rglob("*.py"))
    )
    return GUARDED + swept


def test_new_conversation_application_modules_are_framework_free() -> None:
    violations = {
        key: sorted(found)
        for p in guarded_paths()
        if (key := p.relative_to(BACKEND_ROOT).as_posix()) not in ALLOWED_LEAKS
        and (found := forbidden_imports(p.read_text(encoding="utf-8")))
    }
    assert not violations


def test_boundary_guard_actually_fails_on_a_sqlalchemy_import() -> None:
    assert forbidden_imports("from sqlalchemy import Connection") == {"sqlalchemy"}
    assert forbidden_imports("import fastapi") == {"fastapi"}
    assert forbidden_imports("from typing import Any") == set()
    assert all(path.exists() for path in GUARDED), "guard scope must not shrink silently"
    assert all(p.is_dir() for p in SWEPT_PACKAGES), "swept package must not vanish"


def test_the_sweep_actually_covers_the_capability_package() -> None:
    """A sweep that matches nothing is a guard that guards nothing."""
    covered = {p.relative_to(BACKEND_ROOT).as_posix() for p in guarded_paths()}
    assert "application/capabilities/scheduling_inspect.py" in covered
    assert "application/capabilities/registry.py" in covered
    assert "application/use_cases/read_scenario_facts.py" in covered
    capability_modules = {c for c in covered if c.startswith("application/capabilities/")}
    assert len(capability_modules) >= 5


def test_every_allowed_leak_still_exists_and_still_leaks() -> None:
    """A suppression that outlives its violation is a lie about coverage.

    If someone fixes `scenario_catalogue.py` without deleting its entry, this
    fails and points at the ledger item that is now closeable.
    """
    for relative in ALLOWED_LEAKS:
        path = BACKEND_ROOT / relative
        assert path.exists(), f"{relative} is allow-listed but no longer exists"
        assert forbidden_imports(path.read_text(encoding="utf-8")), (
            f"{relative} no longer leaks — delete its ALLOWED_LEAKS entry and "
            "close the deferred-work item"
        )
