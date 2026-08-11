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
    BACKEND_ROOT / "application/capabilities/__init__.py",
    BACKEND_ROOT / "application/capabilities/vocabulary.py",
    BACKEND_ROOT / "application/capabilities/deps.py",
    BACKEND_ROOT / "application/capabilities/registry.py",
    BACKEND_ROOT / "application/capabilities/scheduling_inspect.py",
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


def test_new_conversation_application_modules_are_framework_free() -> None:
    paths = GUARDED + tuple(sorted((BACKEND_ROOT / "application/use_cases").rglob("*.py")))
    violations = {
        key: sorted(found)
        for p in paths
        if (key := p.relative_to(BACKEND_ROOT).as_posix()) not in ALLOWED_LEAKS
        and (found := forbidden_imports(p.read_text(encoding="utf-8")))
    }
    assert not violations


def test_boundary_guard_actually_fails_on_a_sqlalchemy_import() -> None:
    assert forbidden_imports("from sqlalchemy import Connection") == {"sqlalchemy"}
    assert forbidden_imports("from typing import Any") == set()
    assert all(path.exists() for path in GUARDED), "guard scope must not shrink silently"


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
