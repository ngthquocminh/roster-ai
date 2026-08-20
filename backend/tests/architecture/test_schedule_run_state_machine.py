"""Guard AD-7's ScheduleRun edges (ARCHITECTURE-SPINE.md:106-122)."""
from __future__ import annotations

import ast
from pathlib import Path


AD7_EDGES = frozenset(
    {
        ("solver_queued", "solver_running"),
        ("solver_queued", "solver_cancelled"),
        ("solver_queued", "solver_timed_out"),
        ("solver_queued", "solver_failed"),
        ("solver_running", "cancellation_requested"),
        ("cancellation_requested", "solver_cancelled"),
        ("cancellation_requested", "solver_completed"),
        ("cancellation_requested", "solver_infeasible"),
        ("cancellation_requested", "solver_timed_out"),
        ("cancellation_requested", "solver_failed"),
        ("solver_running", "solver_completed"),
        ("solver_running", "solver_infeasible"),
        ("solver_running", "solver_timed_out"),
        ("solver_running", "solver_failed"),
    }
)
ADAPTER = (
    Path(__file__).resolve().parents[2] / "adapters" / "postgres" / "schedule_run.py"
)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _string_tuple(node: ast.AST) -> tuple[str, ...]:
    assert isinstance(node, (ast.Tuple, ast.Set, ast.List))
    assert all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts)
    return tuple(item.value for item in node.elts)


def _assigned_literal(tree: ast.Module, name: str) -> tuple[str, ...]:
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    value = assignment.value
    if isinstance(value, ast.Call):
        value = value.args[0]
    return _string_tuple(value)


def _cancel_helper_edges(tree: ast.Module) -> set[tuple[str, str]]:
    edges = set()
    for method in ("cancel_queued_run", "request_cancellation"):
        function = _function(tree, method)
        call = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_cancel_transition"
        )
        values = {
            keyword.arg: keyword.value
            for keyword in call.keywords
            if keyword.arg in {"expected_status", "status"}
        }
        edges.add((values["expected_status"].value, values["status"].value))
    return edges


def _mark_running_edge(tree: ast.Module) -> tuple[str, str]:
    function = _function(tree, "mark_running")
    statuses = [
        node.comparators[0].value
        for node in ast.walk(function)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "status"
        and isinstance(node.comparators[0], ast.Constant)
    ]
    targets = [
        keyword.value.value
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "values"
        for keyword in node.keywords
        if keyword.arg == "status" and isinstance(keyword.value, ast.Constant)
    ]
    assert len(statuses) == len(targets) == 1
    return statuses[0], targets[0]


def _finalize_edges(tree: ast.Module) -> set[tuple[str, str]]:
    targets = _assigned_literal(tree, "_FINALIZE_STATUSES")
    function = _function(tree, "finalize_run")
    conditional = next(
        node.value
        for node in function.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "expected_statuses"
            for target in node.targets
        )
    )
    assert isinstance(conditional, ast.IfExp)
    assert isinstance(conditional.test, ast.Compare)
    assert conditional.test.comparators[0].value == "solver_cancelled"
    cancelled_sources = _string_tuple(conditional.body)
    other_sources = _string_tuple(conditional.orelse)
    return {
        (source, target)
        for target in targets
        for source in (
            cancelled_sources if target == "solver_cancelled" else other_sources
        )
    }


def test_every_adapter_schedule_run_transition_is_an_ad7_edge() -> None:
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"), filename=str(ADAPTER))
    adapter_edges = {
        _mark_running_edge(tree),
        *_cancel_helper_edges(tree),
        *_finalize_edges(tree),
    }

    assert adapter_edges <= AD7_EDGES


# The three extractors above enumerate the edges written by three NAMED
# functions. That is only equal to "every edge the adapter can write" while
# those three are the only writers -- an invariant nothing asserted, so the
# next story could add a fourth transition method and keep a green guard.
_SCHEDULE_RUN_WRITERS = frozenset(
    {"_cancel_transition", "mark_running", "finalize_run"}
)


def _functions_updating_schedule_run(tree: ast.Module) -> set[str]:
    """Every function containing an `update(schedule_run)` call, by name."""
    writers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "update"
                and inner.args
                and isinstance(inner.args[0], ast.Name)
                and inner.args[0].id == "schedule_run"
            ):
                writers.add(node.name)
    return writers


def test_only_the_known_helpers_write_a_schedule_run_transition() -> None:
    """Make the edge guard exhaustive rather than merely correct about three functions.

    Without this, adding a fourth `update(schedule_run)` call site writes an
    edge AD-7 may not have while
    `test_every_adapter_schedule_run_transition_is_an_ad7_edge` stays green --
    the "guard that cannot go red" pattern retro action A2 exists to prevent.
    """
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"), filename=str(ADAPTER))

    assert _functions_updating_schedule_run(tree) == _SCHEDULE_RUN_WRITERS
