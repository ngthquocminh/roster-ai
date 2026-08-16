"""Decision 3's guard: no authority decision may read model output (AD-2).

Story 2.9 Decision 3 requires this in words:

    "A source-level guard asserts no branch in `capabilities/registry.py` or the
    execute route consults model output."

The behaviour is correct today -- refusal is proven by ABSENCE (an ungranted
capability is simply not registered), and the model's `RefusalV1` is
presentation only. What was missing is the mechanism keeping it correct. The
inversion these guards forbid is "register-then-refuse": granting a capability
and letting the model decline inside it, which reads as correct and puts the
authority decision downstream of a model-supplied name. Story 2.5 Decision 4
rejected exactly that shape.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Attribute names on an outcome that carry MODEL output. Reaching any of these
# while deciding what to grant is the inversion AD-2 forbids.
MODEL_OUTPUT_ATTRIBUTES = frozenset(
    {"refusal", "clarification", "answer", "output_text", "response_data"}
)

# Files that decide authority. Each composes or registers capabilities.
AUTHORITY_SOURCES = (
    "application/capabilities/registry.py",
    "application/capabilities/installed.py",
    "agent/capability_tools.py",
)


def _module(relative: str) -> ast.Module:
    return ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", AUTHORITY_SOURCES)
def test_authority_composition_never_reads_model_output(relative: str) -> None:
    """No attribute access naming a model-output field in an authority source."""
    offenders = [
        f"{relative}:{node.lineno} reads .{node.attr}"
        for node in ast.walk(_module(relative))
        if isinstance(node, ast.Attribute) and node.attr in MODEL_OUTPUT_ATTRIBUTES
    ]
    assert not offenders, (
        f"{offenders} -- an authority decision consulted model output. AD-2: the "
        "grant is composed from trusted context BEFORE the runtime is built, so "
        "an ungranted capability is absent rather than present-and-refusing."
    )


def test_the_execute_route_composes_the_grant_before_the_runtime_exists() -> None:
    """Ordering is the invariant: nothing model-produced can exist yet.

    `compose_capabilities(...)` must be called before `runtime_factory(...)`.
    If the grant were composed afterwards it could, in principle, read a model
    output -- so the ordering is what makes the absence proof structural rather
    than a matter of current authorship.
    """
    source = (BACKEND_ROOT / "api/routers/conversations.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    compose_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "compose_capabilities"
    ]
    runtime_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "runtime_factory"
    ]
    assert compose_lines, "the execute route no longer composes a grant"
    assert runtime_lines, "the execute route no longer builds a runtime"
    assert max(compose_lines) < min(runtime_lines), (
        "the capability grant must be composed BEFORE the runtime is built; "
        "composing it afterwards would let a model-supplied name reach an "
        "authority decision (AD-2, Story 2.5 Decision 4)."
    )


def test_no_capability_module_declares_a_refusal_of_its_own() -> None:
    """The model's `RefusalV1` is presentation, never an authority decision.

    A capability importing `RefusalV1` would be building the register-then-refuse
    inversion: the tool exists, and declines from inside. Refusal belongs to the
    use case, after the runtime has returned.
    """
    capability_dir = BACKEND_ROOT / "application" / "capabilities"
    offenders = []
    for path in sorted(capability_dir.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name in {"RefusalV1", "ClarificationV1"} for alias in node.names
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"{offenders} imports a model-facing dialogue contract into a capability. "
        "Registering a capability and letting the model decline inside it puts "
        "the authority decision downstream of model output (AD-2)."
    )
