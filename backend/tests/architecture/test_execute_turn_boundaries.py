"""Mechanical guards for the execute-turn request boundary."""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

from api.deps import get_site_context
from api.routers.conversations import router

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_LEAKS = {
    "services/run_service.py": "legacy SQLite solve executor; removal belongs to Gate A",
}


def _background_primitives(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if "BackgroundTasks" in names:
                found.add("BackgroundTasks")
            if "ThreadPoolExecutor" in names:
                found.add("ThreadPoolExecutor")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "asyncio" and func.attr == "create_task":
                    found.add("asyncio.create_task")
    return found


def test_execute_route_never_takes_a_request_lifetime_site_transaction() -> None:
    route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.name == "execute_agent_turn"
    )
    dependencies = {dependency.call for dependency in route.dependant.dependencies}
    assert get_site_context not in dependencies


def test_api_and_application_cannot_spawn_detached_background_work() -> None:
    guarded = tuple((BACKEND_ROOT / "api").rglob("*.py")) + tuple(
        (BACKEND_ROOT / "application").rglob("*.py")
    )
    violations = {
        path.relative_to(BACKEND_ROOT).as_posix(): sorted(found)
        for path in guarded
        if (found := _background_primitives(path))
    }
    assert not violations


def test_the_single_legacy_executor_allow_list_entry_still_matches() -> None:
    assert set(ALLOWED_LEAKS) == {"services/run_service.py"}
    for relative in ALLOWED_LEAKS:
        path = BACKEND_ROOT / relative
        assert path.exists()
        assert _background_primitives(path) == {"ThreadPoolExecutor"}
