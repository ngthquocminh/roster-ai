"""Constraint use-case: parse NL text -> validate -> persist override on a scenario.

Service layer: raises plain exceptions; the router translates to HTTPException
(CLAUDE.md error-handling convention: services raise, routers translate).

Flow:
  1. Load scenario; raise if not found.
  2. Call provider.parse_constraints(text); raise ValueError if empty (no match).
  3. Load the scenario's SchedulingProblem to resolve + validate each OverrideCall:
     - task token resolved against real task ids and task names (case-insensitive
       substring match) — exactly one match required (T-01-I3, D-03).
     - n > 0 required (T-01-I6).
     - Recompute override_id with resolved args (D-05).
  4. Read-modify-write overrides JSON (dict keyed by id, D-04); idempotent overwrite.
     ScenarioRepo.update_overrides writes; caller (router via get_db) commits.
  5. Return dict {id, tool, args, parsed_constraint}.
"""
from __future__ import annotations

import json
import os
import sqlite3

from domain.overrides import OverrideCall, override_id
from ingest.input_adapter import load_problem
from llm.base import LLMProvider
from settings import default_settings
from store.repositories import ScenarioRepo


def _resolve_task(problem, token: str) -> str:
    """Resolve a human task token to a real task_id from the loaded problem.

    Strategy (case-insensitive substring):
    1. Exact match against task_id.
    2. Substring match against task_id OR task.name.
    Require exactly one match; raise ValueError naming the token and listing
    valid task names if zero or multiple match.
    """
    # Exact match first (token is already a real GUID)
    if problem.task(token) is not None:
        return token

    # Substring match against id and name
    token_lower = token.lower()
    matches = [
        t for t in problem.tasks
        if token_lower in t.task_id.lower() or token_lower in t.name.lower()
    ]

    if len(matches) == 1:
        return matches[0].task_id

    valid_names = ", ".join(f"{t.task_id!r} ({t.name!r})" for t in problem.tasks)
    if len(matches) == 0:
        raise ValueError(
            f"Unknown task reference {token!r}. Valid tasks: {valid_names}"
        )
    # Multiple matches
    matched_names = ", ".join(f"{t.task_id!r} ({t.name!r})" for t in matches)
    raise ValueError(
        f"Ambiguous task reference {token!r} matches {len(matches)} tasks: "
        f"{matched_names}. Use a more specific token."
    )


def parse_and_store(
    conn: sqlite3.Connection,
    provider: LLMProvider,
    scenario_id: str,
    text: str,
    data_dir: str | None = None,
) -> dict:
    """Parse a free-text constraint, validate it, and persist it to the scenario.

    Returns:
        dict with keys: id, tool, args, parsed_constraint.

    Raises:
        LookupError: if scenario_id does not exist (router maps to 404).
        ValueError: if text yields no constraint, task token is unknown/ambiguous,
                    or n <= 0 (router maps to 400).
    """
    repo = ScenarioRepo(conn)
    scenario = repo.get(scenario_id)
    if scenario is None:
        raise LookupError(f"Scenario {scenario_id!r} not found")

    # Parse: provider -> list[OverrideCall] (provider-neutral; no tool_use shape here)
    calls = provider.parse_constraints(text)
    if not calls:
        raise ValueError("No constraint found in text. Try phrasing like 'at least N on <task>'.")

    if data_dir is None:
        data_dir = default_settings().data_dir

    fixture_path = os.path.join(data_dir, scenario["fixture"])
    problem = load_problem(fixture_path)

    # Validate and resolve each call (Phase 1: always exactly one tool)
    resolved_calls: list[OverrideCall] = []
    for call in calls:
        tool = call.tool
        args = dict(call.args)  # mutable copy

        if tool == "set_min_workers_per_task":
            # Resolve human token to a real task_id (T-01-I3)
            resolved_task_id = _resolve_task(problem, args["task_id"])
            args["task_id"] = resolved_task_id

            # Validate n > 0 (T-01-I6)
            n = int(args["n"])
            if n <= 0:
                raise ValueError(
                    f"n must be positive, got {n}. Specify a minimum worker count >= 1."
                )
            args["n"] = n
        else:
            raise ValueError(f"Unsupported tool {tool!r}. Only 'set_min_workers_per_task' is supported.")

        # Recompute id with resolved args so the stored key reflects real ids (D-05)
        new_id = override_id(tool, args)
        resolved_calls.append(OverrideCall(id=new_id, tool=tool, args=args))

    # Merge-by-id into existing overrides (D-04: dict keyed by id, idempotent overwrite)
    existing = json.loads(scenario["overrides"] or "{}")
    for resolved in resolved_calls:
        existing[resolved.id] = {"tool": resolved.tool, "args": resolved.args}

    repo.update_overrides(scenario_id, json.dumps(existing))
    conn.commit()

    # Build response for the first (and only, Phase 1) resolved call
    result = resolved_calls[0]
    task = problem.task(result.args["task_id"])
    task_label = task.name if task else result.args["task_id"]
    parsed_constraint = (
        f"At least {result.args['n']} workers on {task_label} (every demanded hour)"
    )

    return {
        "id": result.id,
        "tool": result.tool,
        "args": result.args,
        "parsed_constraint": parsed_constraint,
    }
