"""Mechanical guards for the execute-turn request boundary."""
from __future__ import annotations

import ast
import uuid
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
    never be false and installing a capability granted it.

    This asserts the property over a REAL composed grant. An earlier version
    compared `len(policy_set) == len(capability_names)` and never called
    `compose_granted_capabilities` at all -- two different quantities that
    coincide only because each module happens to declare a unique policy name,
    so the property the test is named for went unasserted. The route-source
    guard further down is its companion: this proves exclusion is possible, that
    one proves the route actually uses it.
    """
    from dataclasses import replace as replace_dataclass

    from application.capabilities.installed import (
        enabled_feature_policy,
        installed_modules,
    )
    from settings import default_settings

    from application.capabilities.registry import (
        CapabilityGrantContextV1,
        compose_granted_capabilities,
    )

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

    def _granted(configured) -> set[str]:
        # Compose the grant for real. Comparing policy-set sizes -- what this
        # test used to do -- compares two different quantities that coincide only
        # because each module happens to declare a unique policy name, and never
        # exercises the predicate the property depends on.
        return {
            module.manifest.capability_name
            for module in compose_granted_capabilities(
                CapabilityGrantContextV1(
                    role="planner",
                    site_id=uuid.UUID(int=1),
                    feature_policy=enabled_feature_policy(configured),
                    conversation_id=uuid.UUID(int=2),
                    conversation_site_id=uuid.UUID(int=1),
                ),
                installed_modules(),
            )
        }

    assert _granted(all_on) == every_name
    assert _granted(all_off) == set(), "a disabled capability must be ABSENT, not refusing"
    # And the discriminating case: turning exactly one off removes exactly it.
    compute_off = replace_dataclass(all_on, scheduling_compute_enabled=False)
    assert _granted(compute_off) == every_name - {"scheduling_compute"}


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


def test_the_execute_route_never_derives_feature_policy_from_installed_modules() -> None:
    """The guard D6 asked for, watching the line that actually regresses.

    The behavioural test above proves `enabled_feature_policy` CAN exclude a
    capability. It cannot prove the route calls it -- reverting
    `conversations.py` to
    `frozenset(module.required_feature_policy for module in installed_modules())`
    left that test, and the whole suite, green. That construction makes
    `module.required_feature_policy in context.feature_policy` unfalsifiable, so
    every installed capability is granted by construction, which is the AD-2
    violation ("an ungranted capability is ABSENT, never present-and-refusing")
    and quietly grants the consequential demonstration harness on live turns.

    Read off the route's own source, in the shape of the trap #7 guard above.
    """
    source = (BACKEND_ROOT / "api" / "routers" / "conversations.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    route = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "execute_agent_turn"
    )
    called = {
        node.func.id
        for node in ast.walk(route)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "enabled_feature_policy" in called, (
        "the route must source feature_policy from Settings"
    )
    assert "installed_modules" not in called, (
        "feature_policy derived from installed_modules() grants every capability"
    )


def test_grant_composition_and_runtime_construction_are_inside_the_failure_guard() -> None:
    """Both were outside the `try` and each can raise on a real deployment.

    `enabled_feature_policy` raises `IncompleteManifestError` for a capability
    with no settings flag, and `runtime_factory` eagerly constructs a provider
    client -- raising on a malformed `AGENT_RUNTIME_MODEL` or a missing key. The
    claim has already committed `agent_running` by then and nothing can re-claim
    it, so an exception there strands the run permanently.
    """
    source = (BACKEND_ROOT / "api" / "routers" / "conversations.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    route = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "execute_agent_turn"
    )
    guarded: set[str] = set()
    for node in ast.walk(route):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    guarded.add(child.func.id)
    for required in ("enabled_feature_policy", "compose_capabilities", "runtime_factory"):
        assert required in guarded, f"{required} must run inside the failure guard"
