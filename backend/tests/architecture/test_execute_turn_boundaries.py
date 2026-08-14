"""Mechanical guards for the execute-turn request boundary."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
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


def test_a_disabled_capability_is_absent_from_the_composed_grant() -> None:
    """AD-2: an ungranted capability is ABSENT, never present-and-refusing.

    The shape this replaces built `feature_policy` from the installed modules'
    own policy names, so `required_feature_policy in feature_policy` could
    never be false and installing a capability granted it. Asserted as
    behaviour rather than as "does not call installed_modules", because the
    property that matters is that something outside the module can exclude it.
    """
    from dataclasses import replace as replace_dataclass

    from application.capabilities.installed import (
        enabled_feature_policy,
        installed_modules,
    )
    from settings import default_settings

    settings = default_settings()
    every_name = {module.manifest.capability_name for module in installed_modules()}

    all_on = replace_dataclass(
        settings,
        scheduling_compute_enabled=True,
        scheduling_inspect_enabled=True,
        demonstration_enabled=True,
    )
    all_off = replace_dataclass(
        settings,
        scheduling_compute_enabled=False,
        scheduling_inspect_enabled=False,
        demonstration_enabled=False,
    )
    assert len(enabled_feature_policy(all_on)) == len(every_name)
    assert enabled_feature_policy(all_off) == frozenset()


def test_the_consequential_demonstration_module_is_off_by_default() -> None:
    """It is a harness module: risk_class "consequential", approval_policy
    "exact_action". Its ApprovalRequired suspends, and `terminal_status` maps a
    suspension to `agent_failed`, so granting it on a live turn spends a
    planner's question on a demonstration. Story 2.6's add/remove proof is
    unaffected -- it stays installed and grantable whenever the flag is on.
    """
    from application.capabilities.demonstration import demonstration_module
    from application.capabilities.installed import enabled_feature_policy
    from settings import default_settings

    policy = enabled_feature_policy(default_settings())
    assert demonstration_module().required_feature_policy not in policy


def test_a_capability_whose_feature_policy_has_no_setting_fails_loudly() -> None:
    """Fail closed on a missing switch rather than granting by default."""
    from application.capabilities.installed import enabled_feature_policy
    from application.contracts.capability_manifest import IncompleteManifestError

    class NoFlags:
        pass

    with pytest.raises(IncompleteManifestError):
        enabled_feature_policy(NoFlags())


def test_the_single_legacy_executor_allow_list_entry_still_matches() -> None:
    assert set(ALLOWED_LEAKS) == {"services/run_service.py"}
    for relative in ALLOWED_LEAKS:
        path = BACKEND_ROOT / relative
        assert path.exists()
        assert _background_primitives(path) == {"ThreadPoolExecutor"}
