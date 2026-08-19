"""FR23 conformance inherited automatically by every installed module.

Parametrized over `installed_modules()` so a future capability inherits every
assertion by existing. Each guard here carries a self-redness proof: a guard that
has never been shown to fail is a guard nobody has tested.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import inspect
import json
from dataclasses import replace
from pathlib import Path
import uuid
from uuid import UUID

import pytest
from pydantic_ai import models

from application.capabilities.installed import installed_modules
from application.capabilities.module import CapabilityModuleV1, validate_module
from application.capabilities.registry import (
    CapabilityGrantContextV1,
    compose_granted_capabilities,
)
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.capability_manifest import (
    CapabilityError,
    IncompleteManifestError,
)
from application.ports.agent_runtime import AgentRuntimeError
from evals.cases import case_from_mapping, load_case
from evals.report import _report_deps, runtime_for_modules

models.ALLOW_MODEL_REQUESTS = False

BACKEND_ROOT = Path(__file__).resolve().parents[1]
INSTALLED = installed_modules()

SITE = UUID(int=1)
CONVERSATION = UUID(int=2)

# Arguments that reach each module's handler. Test fixture data, not control
# flow: a test may name capabilities, core code may not.
_PROBE_ARGS = {
    "scheduling_compute": {
        "metric": "qualified_worker_count",
        "arguments": {"task_id": "pick"},
    },
    "scheduling_draft": {
        "expected_scenario_version_id": str(UUID(int=1)),
        "constraints": [],
    },
    "scheduling_inspect": {"group": "overview"},
    "shiftmind_demonstration": {"label": "alpha", "repeat": 1},
}


def _resolve(path: str) -> object:
    module_name, _, attribute = path.rpartition(".")
    return getattr(importlib.import_module(module_name), attribute)


def _probe_case(module: CapabilityModuleV1):
    """A scripted double that calls exactly this module's tool once."""
    name = module.manifest.capability_name
    arguments = {module.request_argument: _PROBE_ARGS[name]}
    return case_from_mapping({
        "case_id": f"conformance-{name}", "case_version": "1",
        "capability": name, "risk_class": "inspect",
        "prompt": f"exercise {name}",
        "scripted_turns": [
            {"tool_name": name, "arguments": arguments, "tool_call_id": "probe-1"},
            {"response_text": "done"},
        ],
        "expected_outcome": "allow",
        "expected_tool_calls": [{"tool_name": name, "arguments": arguments}],
        "expected_evidence_refs": [], "expected_visible_state": "completed",
        "expected_visible_text": "done", "scenario_fixtures": [],
    })


def _grant_context(**overrides) -> CapabilityGrantContextV1:
    base = dict(
        role="planner", site_id=SITE,
        feature_policy=frozenset(
            module.required_feature_policy for module in INSTALLED
        ),
        conversation_id=CONVERSATION, conversation_site_id=SITE,
    )
    base.update(overrides)
    return CapabilityGrantContextV1(**base)


def _imported_roots(module_name: str) -> set[str]:
    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


# --------------------------------------------------------------------------
# Declaration conformance
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", INSTALLED)
def test_installed_module_conforms(module) -> None:
    manifest = module.manifest
    validate_module(module)
    assert _resolve(manifest.input_schema_ref) is module.request_type
    assert isinstance(_resolve(manifest.output_schema_ref), type)
    assert all((BACKEND_ROOT / path).is_file() for path in manifest.evaluation_fixtures)
    assert manifest.errors
    declared_codes = {
        value.code for value in vars(importlib.import_module(module.handler.__module__)).values()
        if inspect.isclass(value) and issubclass(value, module.error_type)
    }
    # Equality, not subset: a class carrying a code the manifest never declares
    # would be an error vocabulary wider than the advertised one.
    assert declared_codes == set(manifest.errors)
    assert manifest.audit_mapping.strip() and manifest.evidence_mapping.strip()
    assert module.retryable_error_codes <= set(manifest.errors)


@pytest.mark.parametrize("module", INSTALLED)
def test_installed_module_records_its_scope_controls(module) -> None:
    """Scope-as-data (Story 2.5's convention): every control names what it does
    NOT cover, so a reduction cannot outlive the story that recorded it."""
    controls = getattr(
        importlib.import_module(module.handler.__module__), "SCOPE_CONTROLS", None
    )
    assert controls, f"{module.manifest.capability_name} declares no SCOPE_CONTROLS"
    assert all(value.strip() for value in controls.values())
    assert any("NOT COVERED" in value for value in controls.values())


@pytest.mark.parametrize("module", INSTALLED)
def test_handler_module_has_no_adapter_or_framework_import(module) -> None:
    imported = _imported_roots(module.handler.__module__)
    assert imported.isdisjoint({"sqlalchemy", "adapters", "fastapi", "pydantic_ai"})


# --------------------------------------------------------------------------
# Self-redness: the suite's own assertions must be demonstrably failable
# --------------------------------------------------------------------------


def _synthetic_module(**overrides) -> CapabilityModuleV1:
    return replace(INSTALLED[0], **overrides)


def test_conformance_rejects_a_manifest_missing_a_required_declaration() -> None:
    invalid = _synthetic_module(
        manifest=replace(INSTALLED[0].manifest, audit_mapping="")
    )
    with pytest.raises(IncompleteManifestError, match="audit_mapping"):
        validate_module(invalid)


def test_conformance_rejects_a_module_whose_retryable_code_is_undeclared() -> None:
    invalid = _synthetic_module(retryable_error_codes=frozenset({"not_declared"}))
    with pytest.raises(IncompleteManifestError, match="undeclared"):
        validate_module(invalid)


def test_conformance_rejects_a_module_whose_request_argument_lies() -> None:
    invalid = _synthetic_module(request_argument="not_the_handler_parameter")
    with pytest.raises(IncompleteManifestError, match="request argument"):
        validate_module(invalid)


def test_conformance_rejects_a_module_that_declares_no_model_facing_view() -> None:
    """The `asdict` fallback was deleted so a capability cannot leak by omission.

    Its siblings above all prove their guard can go red; this one shipped
    without that proof, in the one suite whose stated purpose is that a guard
    nobody has seen fail is a guard nobody has tested.
    """
    invalid = _synthetic_module(model_facing_view=None)
    with pytest.raises(IncompleteManifestError, match="model may see"):
        validate_module(invalid)


def test_conformance_rejects_a_manifest_whose_schema_ref_does_not_resolve() -> None:
    """The `input_schema_ref` -> `request_type` identity check exists only in
    this suite, so its redness is proved here rather than assumed."""
    invalid = _synthetic_module(
        manifest=replace(
            INSTALLED[0].manifest,
            input_schema_ref="application.capabilities.demonstration.DemonstrationResultV1",
        )
    )
    assert _resolve(invalid.manifest.input_schema_ref) is not invalid.request_type


def test_conformance_rejects_a_manifest_whose_fixtures_are_absent_from_disk() -> None:
    """The on-disk fixture check also exists only in this suite."""
    invalid = _synthetic_module(
        manifest=replace(
            INSTALLED[0].manifest,
            evaluation_fixtures=("evals/golden/does-not-exist.json",),
        )
    )
    assert not all(
        (BACKEND_ROOT / path).is_file()
        for path in invalid.manifest.evaluation_fixtures
    )


def test_import_fence_walk_catches_a_from_import() -> None:
    """The fence walk must see `from X import Y`, not only `import X` --
    walking `ast.Import` alone was Story 2.5 review finding 7."""
    tree = ast.parse("from pydantic_ai import Tool\nimport pkgutil\n")
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported == {"pydantic_ai", "pkgutil"}


# --------------------------------------------------------------------------
# AD-15: no dynamic discovery
# --------------------------------------------------------------------------


_FORBIDDEN_DISCOVERY = {"importlib", "pkgutil", "entry_points"}


def _discovery_hits(source: str) -> set[str]:
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    # ImportFrom too: `from importlib import import_module` is the bypass the
    # previous shape of this guard could not see.
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    return (names | attributes | imports) & _FORBIDDEN_DISCOVERY


def test_installation_and_agent_packages_forbid_dynamic_discovery() -> None:
    violations = []
    # Recursive: a future subpackage must not fall outside the guard.
    for root in (BACKEND_ROOT / "application/capabilities", BACKEND_ROOT / "agent"):
        for path in root.rglob("*.py"):
            if _discovery_hits(path.read_text(encoding="utf-8")):
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert not violations


@pytest.mark.parametrize(
    "source",
    [
        "from pkgutil import iter_modules\n",
        "from importlib import import_module\n",
        "import importlib\n",
        "from importlib.metadata import entry_points\n",
    ],
)
def test_dynamic_discovery_guard_catches_every_bypass_shape(source) -> None:
    assert _discovery_hits(source)


# --------------------------------------------------------------------------
# AC2: grant composition, and absence when ungranted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", INSTALLED)
def test_each_module_is_granted_only_by_its_declared_requirements(module) -> None:
    name = module.manifest.capability_name

    granted = compose_granted_capabilities(
        _grant_context(feature_policy=frozenset({module.required_feature_policy})),
        modules=INSTALLED,
    )
    # A context carrying only this module's policy grants ONLY this module.
    assert tuple(item.manifest.capability_name for item in granted) == (name,)

    for context in (
        _grant_context(role="viewer"),
        _grant_context(feature_policy=frozenset()),
        _grant_context(site_id=UUID(int=99)),
        _grant_context(revoked_conversation_ids=frozenset({CONVERSATION})),
    ):
        assert compose_granted_capabilities(context, modules=INSTALLED) == ()


@pytest.mark.parametrize("module", INSTALLED)
def test_an_ungranted_module_is_absent_from_the_tool_set(module) -> None:
    name = module.manifest.capability_name
    others = tuple(item for item in INSTALLED if item.manifest.capability_name != name)
    runtime = runtime_for_modules(_probe_case(module), others)

    assert name not in runtime._agent._function_toolset.tools
    assert name not in runtime.registered_capability_names

    # A model-supplied call to the absent name cannot execute: nothing named it
    # is registered, so no tool result for it can appear.
    try:
        outcome = runtime.run_turn(AgentTurnRequestV1(prompt="call the absent tool"))
    except AgentRuntimeError:
        return
    assert all(result.tool_name != name for result in outcome.tool_results)


# --------------------------------------------------------------------------
# AC3: declared failures cross the port with declared codes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", INSTALLED)
def test_a_declared_capability_failure_maps_to_a_declared_failure_reason(module) -> None:
    """Every installed module must be drivable to its own declared failure, and
    the observed `failure_reason` must be one its manifest advertises."""
    runtime = runtime_for_modules(_probe_case(module), (module,))
    runtime._deps = replace(
        _report_deps(), remaining_budget=AgentBudgetV1(tool_calls_limit=0)
    )

    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="exercise the failure"))

    assert outcome.status == "failed"
    assert outcome.failure_reason in set(module.manifest.errors)


class _UndeclaredFailure(CapabilityError):
    code = "definitely_not_declared"


def test_an_undeclared_failure_code_never_crosses_the_port() -> None:
    """The invariant that makes the widened `failure_reason` type safe: a code
    absent from every granted manifest is an owned runtime error, not a
    stable-looking reason nobody declared.

    Driven through a real granted module whose handler raises an undeclared
    code -- not by patching the framework's tool object, which would exercise a
    path no capability actually takes.
    """
    base = next(
        module for module in INSTALLED
        if module.manifest.capability_name == "shiftmind_demonstration"
    )

    def undeclared_handler(deps, payload, manifest):
        del deps, payload, manifest
        raise _UndeclaredFailure("this code is in no manifest")

    module = replace(base, handler=undeclared_handler)
    runtime = runtime_for_modules(_probe_case(base), (module,))

    assert "definitely_not_declared" not in runtime._declared_error_codes()
    with pytest.raises(AgentRuntimeError, match="not declared"):
        runtime.run_turn(AgentTurnRequestV1(prompt="exercise the failure"))


# --------------------------------------------------------------------------
# AC3/AC4: core names no capability; removal is a real composition
# --------------------------------------------------------------------------


def test_core_is_capability_name_agnostic() -> None:
    files = (
        "agent/runtime.py", "agent/capability_tools.py", "agent/translate.py",
        "application/capabilities/registry.py", "application/capabilities/module.py",
        "application/contracts/capability_manifest.py",
    )
    # Both installed names, per Task 4 -- not only the one this story added.
    literals = ("demonstration", "scheduling_compute", "scheduling_inspect")
    violations = [
        f"{path}:{literal}"
        for path in files
        for literal in literals
        if literal in (BACKEND_ROOT / path).read_text(encoding="utf-8")
    ]
    assert not violations


def test_removed_world_keeps_scheduling_executable_without_core_changes() -> None:
    """AC4's removal proof. The runtime is built from the COMPOSED set verbatim,
    never re-filtered downstream, so the removal is what decides the outcome."""
    context = _grant_context()
    case = load_case(
        BACKEND_ROOT / "evals/golden/scheduling_inspect/wednesday-demand.json"
    )

    # Positive control: with the full installed set, demonstration IS present.
    # Without this the removed-world assertion below could pass vacuously.
    full = compose_granted_capabilities(context, modules=INSTALLED)
    present = runtime_for_modules(case, full)
    assert "shiftmind_demonstration" in present._agent._function_toolset.tools

    # Removed world: not installed, therefore not granted, therefore not rendered.
    remaining = tuple(
        module for module in INSTALLED
        if module.manifest.capability_name != "shiftmind_demonstration"
    )
    granted = compose_granted_capabilities(context, modules=remaining)
    runtime = runtime_for_modules(case, granted)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))

    assert "shiftmind_demonstration" not in runtime._agent._function_toolset.tools
    assert runtime.registered_capability_names == tuple(
        module.manifest.capability_name for module in granted
    )
    assert outcome.status == "completed"


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


def test_every_installed_module_declares_a_model_facing_view() -> None:
    """There is no default view, so a new capability cannot leak by omission.

    `validate_module` rejects a module that declares nothing; this asserts the
    installed set actually carries one rather than relying on a default that no
    longer exists.
    """
    for module in installed_modules():
        assert callable(module.model_facing_view), module.manifest.capability_name


def test_scheduling_compute_never_hands_the_model_its_computed_value() -> None:
    """`scheduling_compute`'s premise: the model cites the number, never holds it.

    Asserted over the module's PROJECTED output, which is stronger than
    inspecting a list of field names.

    NOTE what this does NOT establish, because an earlier version of this
    docstring claimed it and the claim was false: there is no repo-wide "no
    capability hands the model a quantity" invariant. `scheduling_inspect`
    deliberately hands the model rows and counts -- that is its entire purpose --
    and rehydrated history carries prior claim values so a follow-up question can
    resolve against them. Grounding does not rest on the model being ignorant of
    numbers; it rests on the gate refusing to render any number that is not a
    verified citation, and on the prose rule, which the adapter now enforces
    in-loop so an echoed numeral costs a retry rather than the whole turn.
    """
    from application.capabilities.scheduling_compute import (
        SchedulingComputeResultV1,
        scheduling_compute_module,
    )
    from application.contracts.grounding import ClaimArgumentsV1

    result = SchedulingComputeResultV1(
        metric="required_headcount_minutes",
        arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
        value=4321,
        unit="minutes",
        evidence_refs=(),
        scenario_version_id=uuid.UUID(int=7),
        result_id="c0ffee",
        consumed_row_count=99,
    )
    projected = scheduling_compute_module().model_facing_view(result)
    rendered = json.dumps(dataclasses.asdict(projected))

    assert "4321" not in rendered
    assert "99" not in rendered
    assert projected.matched == "some"
    assert projected.result_id == "c0ffee"
    assert not any(
        isinstance(getattr(projected, field.name), (int, float))
        and not isinstance(getattr(projected, field.name), bool)
        for field in dataclasses.fields(projected)
    )


def test_scheduling_draft_never_hands_the_model_proposal_contents() -> None:
    """The draft output is a citation; every planner-visible field is trusted."""
    from application.capabilities.scheduling_draft import (
        SchedulingDraftResultV1,
        scheduling_draft_module,
    )
    from application.contracts.proposal import ProposalV1

    result = SchedulingDraftResultV1(
        result_id="c0ffee",
        proposal=ProposalV1(consequence_summary="must remain on the trusted path"),
    )
    projected = scheduling_draft_module().model_facing_view(result)
    rendered = json.dumps(dataclasses.asdict(projected))

    assert rendered == '{"draft_id": "c0ffee", "schema_version": "1"}'
    assert "must remain" not in rendered
