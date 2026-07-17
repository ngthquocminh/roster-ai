"""Constraint use-case: parse NL text -> validate -> persist override on a scenario.

Service layer: raises only LookupError (unknown scenario_id); all per-call
validation failures are returned in the structured body as rejected[] or
clarification_needed (CLAUDE.md error-handling convention: services raise for
caller-level errors, partial failures go to the response body).

Flow:
  1. Load scenario; raise LookupError if not found.
  2. Call provider.parse_constraints(text) -> list[OverrideCall].
  3. Partition out _clarification sentinel calls (tool == "_clarification").
  4. Set no_constraint_found when no real tool calls AND no clarification signal.
  5. For each real call: resolve + validate, bucket into applied/rejected/clarification.
  6. Read-modify-write overrides JSON for applied entries only (D-04/D-05); idempotent overwrite.
  7. Return {applied, rejected, clarification_needed, no_constraint_found}.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import NamedTuple

from domain.overrides import OverrideCall, override_id
from ingest.input_adapter import load_problem
from llm.base import LLMProvider
from settings import default_settings
from store.repositories import ScenarioRepo


class _ResolveResult(NamedTuple):
    """Result of resolving a human token to a real domain id.

    Exactly one field is non-None:
    - resolved_id: single match found
    - error: zero matches (token unknown)
    - clarification: multiple matches (token ambiguous)
    """

    resolved_id: str | None
    error: str | None
    clarification: str | None


def _dedupe_by_key(items, key_fn):
    """Collapse `items` to one entry per `key_fn(item)`, keeping first occurrence.

    The ingest adapter creates one Member (and could in principle create one
    Task) object per underlying row, so the same real-world entity can appear
    more than once in `problem.members`/`problem.tasks`. Both ambiguity
    counting and "valid options" listings must count/list distinct entities,
    not distinct rows (CR-01/WR-04).
    """
    seen: dict = {}
    for item in items:
        seen.setdefault(key_fn(item), item)
    return list(seen.values())


def _resolve_task(problem, token: str) -> _ResolveResult:
    """Resolve a human task token to a real task_id from the loaded problem.

    Strategy (case-insensitive substring):
    1. Exact match against task_id.
    2. Substring match against task_id OR task.name.
    Returns a _ResolveResult (never raises).
    """
    # Exact match first (token is already a real GUID)
    if problem.task(token) is not None:
        return _ResolveResult(resolved_id=token, error=None, clarification=None)

    # Substring match against id and name
    token_lower = token.lower()
    matches = [
        t for t in problem.tasks
        if token_lower in t.task_id.lower() or token_lower in t.name.lower()
    ]

    if len(matches) == 1:
        return _ResolveResult(resolved_id=matches[0].task_id, error=None, clarification=None)

    valid_names = ", ".join(f"{t.name!r} ({t.task_id})" for t in problem.tasks)
    if len(matches) == 0:
        return _ResolveResult(
            resolved_id=None,
            error=f"Unknown task {token!r}. Valid tasks: {valid_names}",
            clarification=None,
        )

    # Multiple matches — ask for clarification
    matched_names = ", ".join(f"{t.name!r}" for t in matches)
    return _ResolveResult(
        resolved_id=None,
        error=None,
        clarification=f"{token!r} matches multiple tasks: {matched_names}. Which did you mean?",
    )


def _resolve_member(problem, token: str) -> _ResolveResult:
    """Resolve a human member token to a real contact_id from the loaded problem.

    Strategy (case-insensitive substring):
    1. Exact match against contact_id.
    2. Substring match against contact_id OR member name.
    Returns a _ResolveResult (never raises).
    """
    # Exact match first
    exact = [m for m in problem.members if m.contact_id == token]
    if exact:
        return _ResolveResult(resolved_id=token, error=None, clarification=None)

    # Substring match against id and name
    token_lower = token.lower()
    raw_matches = [
        m for m in problem.members
        if token_lower in m.contact_id.lower() or token_lower in m.name.lower()
    ]
    # Dedupe by contact_id — multiple roster/availability rows for the same
    # person must not be treated as multiple distinct candidates (CR-01).
    matches = _dedupe_by_key(raw_matches, lambda m: m.contact_id)

    if len(matches) == 1:
        return _ResolveResult(resolved_id=matches[0].contact_id, error=None, clarification=None)

    valid_names = ", ".join(
        f"{m.name!r} ({m.contact_id})"
        for m in _dedupe_by_key(problem.members, lambda m: m.contact_id)
    )
    if len(matches) == 0:
        return _ResolveResult(
            resolved_id=None,
            error=f"Unknown member {token!r}. Valid members: {valid_names}",
            clarification=None,
        )

    # Multiple distinct people matched — ask for clarification
    matched_names = ", ".join(f"{m.name!r}" for m in matches)
    return _ResolveResult(
        resolved_id=None,
        error=None,
        clarification=f"{token!r} matches multiple members: {matched_names}. Which did you mean?",
    )


def parse_and_store(
    conn: sqlite3.Connection,
    provider: LLMProvider,
    scenario_id: str,
    text: str,
    data_dir: str | None = None,
) -> dict:
    """Parse a free-text constraint, validate it, and persist valid overrides to the scenario.

    Returns:
        dict with keys: applied, rejected, clarification_needed, no_constraint_found.

    Raises:
        LookupError: if scenario_id does not exist (router maps to 404).
        All per-call validation failures are bucketed into rejected[] or clarification_needed
        in the return body — they never raise (D-01/VAL-02/VAL-03).
    """
    repo = ScenarioRepo(conn)
    scenario = repo.get(scenario_id)
    if scenario is None:
        raise LookupError(f"Scenario {scenario_id!r} not found")

    # Parse: provider -> list[OverrideCall] (provider-neutral; no tool_use shape here)
    calls = provider.parse_constraints(text)

    if data_dir is None:
        data_dir = default_settings().data_dir

    fixture_path = os.path.join(data_dir, scenario["fixture"])
    problem = load_problem(fixture_path)

    # Partition _clarification sentinel signals before processing real tool calls
    applied: list[dict] = []
    rejected: list[dict] = []
    clarification_needed: str | None = None

    tool_calls: list[OverrideCall] = []
    for call in calls:
        if call.tool == "_clarification":
            # Use the first clarification question only
            if clarification_needed is None:
                clarification_needed = call.args.get("question", "Please clarify your constraint.")
        else:
            tool_calls.append(call)

    # no_constraint_found only when no real tool calls AND no clarification signal emitted
    no_constraint_found = (not tool_calls and clarification_needed is None)

    for call in tool_calls:
        tool = call.tool
        args = dict(call.args)  # mutable copy

        if tool == "set_min_workers_per_task":
            # Resolve human task token to a real task_id (VAL-02)
            rr = _resolve_task(problem, args["task_id"])
            if rr.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr.clarification
                continue
            if rr.error is not None:
                rejected.append({"tool": tool, "error": rr.error})
                continue
            resolved_task_id = rr.resolved_id
            args["task_id"] = resolved_task_id

            # Validate n > 0 (VAL-01)
            n = int(args["n"])
            if n <= 0:
                rejected.append({
                    "tool": tool,
                    "error": f"n must be positive, got {n}. Specify a minimum worker count >= 1.",
                })
                continue
            args["n"] = n

            task = problem.task(resolved_task_id)
            task_label = task.name if task else resolved_task_id
            parsed_constraint = f"At least {n} workers on {task_label} (every demanded hour)"
            applied.append({
                "id": override_id(tool, args),
                "tool": tool,
                "args": args,
                "parsed_constraint": parsed_constraint,
            })

        elif tool == "scale_demand":
            # Resolve task token (VAL-02)
            rr = _resolve_task(problem, args["task_id"])
            if rr.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr.clarification
                continue
            if rr.error is not None:
                rejected.append({"tool": tool, "error": rr.error})
                continue
            args["task_id"] = rr.resolved_id

            # Validate factor > 0 (VAL-01/T-02-05)
            factor = float(args["factor"])
            if factor <= 0:
                rejected.append({
                    "tool": tool,
                    "error": (
                        f"factor must be positive, got {factor}. "
                        "Use a value > 0 (e.g. 1.5 to scale demand up by 50%)."
                    ),
                })
                continue
            args["factor"] = factor

            task = problem.task(rr.resolved_id)
            task_label = task.name if task else rr.resolved_id
            parsed_constraint = f"Scale demand for {task_label} by {factor}x"
            applied.append({
                "id": override_id(tool, args),
                "tool": tool,
                "args": args,
                "parsed_constraint": parsed_constraint,
            })

        elif tool == "lock_worker_shift":
            # Resolve member token (VAL-02/D-11)
            rr = _resolve_member(problem, args["member_id"])
            if rr.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr.clarification
                continue
            if rr.error is not None:
                rejected.append({"tool": tool, "error": rr.error})
                continue
            args["member_id"] = rr.resolved_id

            # Validate day within scenario horizon (VAL-01/T-02-07)
            day = int(args["day"])
            max_day = int(problem.horizon_h // 24) - 1
            if day < 0 or day > max_day:
                rejected.append({
                    "tool": tool,
                    "error": (
                        f"day {day} is outside the scenario horizon. "
                        f"Valid days: 0..{max_day} "
                        f"(horizon is {problem.horizon_h:.0f}h = {max_day + 1} days)."
                    ),
                })
                continue
            args["day"] = day

            # Resolve member name for the parsed_constraint echo
            member = next((m for m in problem.members if m.contact_id == rr.resolved_id), None)
            member_name = member.name if member else rr.resolved_id
            parsed_constraint = f"Keep {member_name} scheduled on day {day}"
            applied.append({
                "id": override_id(tool, args),
                "tool": tool,
                "args": args,
                "parsed_constraint": parsed_constraint,
            })

        elif tool == "exclude_worker_from_task":
            # Resolve both member and task tokens (VAL-02/D-11)
            rr_member = _resolve_member(problem, args["member_id"])
            rr_task = _resolve_task(problem, args["task_id"])

            # Collect any clarification or rejection from either resolution
            got_clarification = False
            if rr_member.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr_member.clarification
                got_clarification = True
            if rr_task.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr_task.clarification
                got_clarification = True
            if got_clarification:
                continue

            if rr_member.error is not None:
                rejected.append({"tool": tool, "error": rr_member.error})
                continue
            if rr_task.error is not None:
                rejected.append({"tool": tool, "error": rr_task.error})
                continue

            args["member_id"] = rr_member.resolved_id
            args["task_id"] = rr_task.resolved_id

            member = next((m for m in problem.members if m.contact_id == rr_member.resolved_id), None)
            member_name = member.name if member else rr_member.resolved_id
            task = problem.task(rr_task.resolved_id)
            task_label = task.name if task else rr_task.resolved_id
            parsed_constraint = f"Exclude {member_name} from {task_label}"
            applied.append({
                "id": override_id(tool, args),
                "tool": tool,
                "args": args,
                "parsed_constraint": parsed_constraint,
            })

        elif tool == "set_max_hours":
            # Resolve member token (VAL-02/D-11)
            rr = _resolve_member(problem, args["member_id"])
            if rr.clarification is not None:
                if clarification_needed is None:
                    clarification_needed = rr.clarification
                continue
            if rr.error is not None:
                rejected.append({"tool": tool, "error": rr.error})
                continue
            args["member_id"] = rr.resolved_id

            # Validate max_hours > 0 (VAL-01/T-02-06)
            max_hours = float(args["max_hours"])
            if max_hours <= 0:
                rejected.append({
                    "tool": tool,
                    "error": (
                        f"max_hours must be positive, got {max_hours}. "
                        "Specify a weekly hour cap > 0."
                    ),
                })
                continue
            args["max_hours"] = max_hours

            member = next((m for m in problem.members if m.contact_id == rr.resolved_id), None)
            member_name = member.name if member else rr.resolved_id
            parsed_constraint = f"Cap {member_name} at {max_hours} hours per week (soft)"
            applied.append({
                "id": override_id(tool, args),
                "tool": tool,
                "args": args,
                "parsed_constraint": parsed_constraint,
            })

        else:
            rejected.append({
                "tool": tool,
                "error": (
                    f"Unsupported tool {tool!r}. "
                    "Supported tools: set_min_workers_per_task, scale_demand, "
                    "lock_worker_shift, exclude_worker_from_task, set_max_hours."
                ),
            })

    # Persist ONLY applied entries; rejected/clarification are response-only (T-02-02)
    if applied:
        existing = json.loads(scenario["overrides"] or "{}")
        for entry in applied:
            existing[entry["id"]] = {
                "tool": entry["tool"],
                "args": entry["args"],
                "parsed_constraint": entry["parsed_constraint"],  # D-02
            }
        repo.update_overrides(scenario_id, json.dumps(existing))
        conn.commit()

    return {
        "applied": applied,
        "rejected": rejected,
        "clarification_needed": clarification_needed,
        "no_constraint_found": no_constraint_found,
    }
