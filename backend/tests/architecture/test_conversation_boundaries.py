"""Executable AD-1 boundary for Story 2.3's new application modules.

The legacy ``application/ports/scenario_catalogue.py`` SQLAlchemy import is
explicitly outside this new-module guard. It is tracked under
``deferred-work.md``: "Deferred from: story-2-3 creation (2026-08-10)"; deleting
that suppression is the ledger item's definition of done.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GUARDED = (
    BACKEND_ROOT / "application/contracts/activity.py",
    BACKEND_ROOT / "application/contracts/persisted_event.py",
    BACKEND_ROOT / "application/ports/conversation.py",
)


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
    violations = {str(p.relative_to(BACKEND_ROOT)): sorted(found) for p in paths if (found := forbidden_imports(p.read_text(encoding="utf-8")))}
    assert not violations


def test_boundary_guard_actually_fails_on_a_sqlalchemy_import() -> None:
    assert forbidden_imports("from sqlalchemy import Connection") == {"sqlalchemy"}
    assert forbidden_imports("from typing import Any") == set()
