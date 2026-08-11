"""FR23 conformance inherited automatically by every installed module."""
from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from application.capabilities.installed import INSTALLED_MODULES
from application.capabilities.registry import CapabilityGrantContextV1, compose_granted_capabilities
from application.contracts.agent_runtime import AgentTurnRequestV1
from application.contracts.capability_manifest import IncompleteManifestError, validate_manifest
from evals.cases import load_case
from evals.report import _runtime_for_case
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resolve(path: str) -> object:
    module_name, _, attribute = path.rpartition(".")
    return getattr(importlib.import_module(module_name), attribute)


@pytest.mark.parametrize("module", INSTALLED_MODULES)
def test_installed_module_conforms(module) -> None:
    manifest = module.manifest
    validate_manifest(manifest)
    assert _resolve(manifest.input_schema_ref) is module.request_type
    assert isinstance(_resolve(manifest.output_schema_ref), type)
    assert all((BACKEND_ROOT / path).is_file() for path in manifest.evaluation_fixtures)
    assert manifest.errors
    declared_codes = {
        value.code for value in vars(importlib.import_module(module.handler.__module__)).values()
        if inspect.isclass(value) and issubclass(value, module.error_type)
    }
    assert set(manifest.errors) <= declared_codes
    assert manifest.audit_mapping.strip() and manifest.evidence_mapping.strip()


@pytest.mark.parametrize("module", INSTALLED_MODULES)
def test_handler_module_has_no_adapter_or_framework_import(module) -> None:
    tree = ast.parse(inspect.getsource(importlib.import_module(module.handler.__module__)))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"sqlalchemy", "adapters", "fastapi", "pydantic_ai"})


def test_conformance_guard_proves_its_own_redness() -> None:
    invalid = replace(INSTALLED_MODULES[0].manifest, audit_mapping="")
    with pytest.raises(IncompleteManifestError, match="audit_mapping"):
        validate_manifest(invalid)


def test_installation_and_agent_packages_forbid_dynamic_discovery() -> None:
    forbidden = {"importlib", "pkgutil", "entry_points"}
    violations = []
    for root in (BACKEND_ROOT / "application/capabilities", BACKEND_ROOT / "agent"):
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            imports = {
                alias.name.split(".")[0]
                for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names
            }
            if (names | imports) & forbidden:
                violations.append(path.name)
    assert not violations


def test_removed_world_keeps_scheduling_executable_without_core_changes() -> None:
    remaining = tuple(
        module for module in INSTALLED_MODULES
        if module.manifest.capability_name != "shiftmind_demonstration"
    )
    context = CapabilityGrantContextV1(
        role="planner", site_id=UUID(int=1),
        feature_policy=frozenset({"scheduling_inspect_enabled"}),
        conversation_id=UUID(int=2), conversation_site_id=UUID(int=1),
    )
    granted = compose_granted_capabilities(context, modules=remaining)
    case = load_case(BACKEND_ROOT / "evals/golden/scheduling_inspect/wednesday-demand.json")
    runtime = _runtime_for_case(case, granted)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
    assert "shiftmind_demonstration" not in runtime._agent._function_toolset.tools
    assert runtime.registered_capability_names == ("scheduling_inspect",)
    assert outcome.status == "completed"


def test_core_is_capability_name_agnostic() -> None:
    files = (
        "agent/runtime.py", "agent/capability_tools.py", "agent/translate.py",
        "application/capabilities/registry.py", "application/capabilities/module.py",
        "application/contracts/capability_manifest.py",
    )
    violations = [path for path in files if "demonstration" in (BACKEND_ROOT / path).read_text(encoding="utf-8")]
    assert not violations


def test_removed_world_retains_historical_case_versions_and_digests() -> None:
    evidence = json.loads(
        (BACKEND_ROOT.parent / "evidence/story-2.2/evaluation-harness-demonstration.json")
        .read_text(encoding="utf-8")
    )
    files = evidence["version_bindings"]["dataset"]["files"]
    for relative, binding in files.items():
        path = BACKEND_ROOT.parent / relative
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case["capability"] == "demonstration"
        assert case["case_version"] == binding["case_version"]
        normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        assert hashlib.sha256(normalized.encode("utf-8")).hexdigest() == binding["sha256"]
