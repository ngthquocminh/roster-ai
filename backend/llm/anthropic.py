"""Anthropic-backed implementation of the task-level ``LLMProvider`` seam.

Only this adapter understands Anthropic Messages API types. It converts native
tool-use blocks to the existing provider-neutral ``OverrideCall`` contract and
does not expose SDK errors or credentials across that boundary.
"""
from __future__ import annotations

import anthropic

from domain.overrides import OverrideCall
from llm.base import LLMProviderError
from llm.translate import normalize_args, to_override_call

_MAX_TOKENS = 1024

_TOOL_SCHEMAS = [
    {
        "name": "set_min_workers_per_task",
        "description": "Require at least N workers on a given task at every demanded hour.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
                "n": {"type": "integer", "description": "Minimum worker headcount"},
            },
            "required": ["task_id", "n"],
        },
    },
    {
        "name": "scale_demand",
        "description": "Scale a task's demanded volume by a multiplicative factor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
                "factor": {"type": "number", "description": "Multiplicative scale factor, e.g. 1.5"},
            },
            "required": ["task_id", "factor"],
        },
    },
    {
        "name": "lock_worker_shift",
        "description": "Keep a specific worker assigned on a specific day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "day": {"type": "integer", "description": "0-indexed day from scenario start (0=Monday)"},
            },
            "required": ["member_id", "day"],
        },
    },
    {
        "name": "exclude_worker_from_task",
        "description": "Prevent a specific worker from being assigned to a specific task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
            },
            "required": ["member_id", "task_id"],
        },
    },
    {
        "name": "set_max_hours",
        "description": "Cap a specific worker's total scheduled hours.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "max_hours": {"type": "number", "description": "Maximum total hours, e.g. 40"},
            },
            "required": ["member_id", "max_hours"],
        },
    },
]

_PARSE_SYSTEM_INSTRUCTION = (
    "You are a workforce scheduling assistant. The user describes a change to a shift "
    "schedule in plain English. Translate the request into exactly one of the provided "
    "function calls, choosing the single tool and arguments that best capture it. Use "
    "task and worker names exactly as they appear in the user's text. Call a function "
    "whenever the text expresses any scheduling constraint or change (for example a "
    "minimum headcount, scaling demand, locking or excluding a worker, or capping hours). "
    "Respond WITHOUT calling any function only when the text expresses no scheduling "
    "constraint at all."
)

_INSIGHT_PROMPT_TEMPLATE = """You are summarizing the results of a workforce schedule solve for an operator.

Using ONLY the figures present in the summary below, write a short, plain-language
report of the schedule's outcome (total cost, unmet hours, coverage, any warnings,
and any constraint overrides applied). Cite exact figures from the summary — do
not compute new numbers, percentages, or estimates that are not already present
in the summary.

Summary:
{summary}
"""


class AnthropicLLMProvider:
    """Lazy Anthropic Messages API adapter for the legacy ``LLMProvider`` seam."""

    name = "anthropic"

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _normalized_args_or_raw(args: dict) -> dict:
        """Let the application reject malformed untrusted tool arguments safely."""
        try:
            return normalize_args(args)
        except (TypeError, ValueError, OverflowError):
            return args

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        try:
            response = self._get_client().messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_PARSE_SYSTEM_INSTRUCTION,
                messages=[{"role": "user", "content": text}],
                tools=_TOOL_SCHEMAS,
            )
        except (anthropic.APIError, TypeError) as exc:
            raise LLMProviderError("Anthropic request failed") from exc
        return [
            to_override_call(
                block.name, self._normalized_args_or_raw(dict(block.input or {}))
            )
            for block in response.content
            if block.type == "tool_use"
        ]

    def generate_insights(self, summary: dict) -> str:
        try:
            response = self._get_client().messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": _INSIGHT_PROMPT_TEMPLATE.format(summary=summary)}],
            )
        except (anthropic.APIError, TypeError) as exc:
            raise LLMProviderError("Anthropic request failed") from exc
        return "".join(block.text for block in response.content if block.type == "text")
