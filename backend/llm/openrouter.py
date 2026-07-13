"""OpenRouter-backed LLM provider (quick-260713-pn3) — a second, network-backed
`LLMProvider` implementation, selectable alongside "stub" and "gemini" via
`LLM_PROVIDER=openrouter`.

OpenRouter exposes an OpenAI-API-compatible Chat Completions endpoint, so this
module uses the official `openai` Python SDK pointed at OpenRouter's base URL
instead of a bespoke HTTP client. Tool/function calling drives
`parse_constraints`; a plain chat completion drives `generate_insights`. Both
operations share the single provider-neutral translation point,
`llm.translate.to_override_call` (D-07) — the vendor tool-call payload never
leaves `parse_constraints` (D-02), mirroring `llm/gemini.py`'s shape exactly.

SECURITY (T-04-01 / T-pn3-01): the API key must never be interpolated into any
string, log line, or exception message in this module. It only ever flows
into `OpenAI(api_key=...)`.
"""
from __future__ import annotations

import json

import openai
from openai import OpenAI

from domain.overrides import OverrideCall
from llm.base import LLMProviderError
from llm.translate import normalize_args, to_override_call

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Tool schemas — same five tools as llm/gemini.py / llm/stub.py, in the OpenAI
# Chat Completions tool shape so all three providers route identical
# (name, args) pairs through the same translate seam.
# ---------------------------------------------------------------------------

_SET_MIN_WORKERS = {
    "type": "function",
    "function": {
        "name": "set_min_workers_per_task",
        "description": "Require at least N workers on a given task at every demanded hour.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
                "n": {"type": "integer", "description": "Minimum worker headcount"},
            },
            "required": ["task_id", "n"],
        },
    },
}

_SCALE_DEMAND = {
    "type": "function",
    "function": {
        "name": "scale_demand",
        "description": "Scale a task's demanded volume by a multiplicative factor.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
                "factor": {
                    "type": "number",
                    "description": "Multiplicative scale factor, e.g. 1.5",
                },
            },
            "required": ["task_id", "factor"],
        },
    },
}

_LOCK_WORKER_SHIFT = {
    "type": "function",
    "function": {
        "name": "lock_worker_shift",
        "description": "Keep a specific worker assigned on a specific day.",
        "parameters": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "day": {
                    "type": "integer",
                    "description": "0-indexed day from scenario start (0=Monday)",
                },
            },
            "required": ["member_id", "day"],
        },
    },
}

_EXCLUDE_WORKER_FROM_TASK = {
    "type": "function",
    "function": {
        "name": "exclude_worker_from_task",
        "description": "Prevent a specific worker from being assigned to a specific task.",
        "parameters": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
            },
            "required": ["member_id", "task_id"],
        },
    },
}

_SET_MAX_HOURS = {
    "type": "function",
    "function": {
        "name": "set_max_hours",
        "description": "Cap a specific worker's total scheduled hours.",
        "parameters": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
                "max_hours": {"type": "number", "description": "Maximum total hours, e.g. 40"},
            },
            "required": ["member_id", "max_hours"],
        },
    },
}

_TOOL_SCHEMAS = [
    _SET_MIN_WORKERS,
    _SCALE_DEMAND,
    _LOCK_WORKER_SHIFT,
    _EXCLUDE_WORKER_FROM_TASK,
    _SET_MAX_HOURS,
]

# Steers parse_constraints toward reliably calling a tool for terse
# constraint text (e.g. "at least 2 on Pick") while still allowing zero
# calls for genuinely non-constraint text — tool_choice="auto" stays the
# enforcement point for NLC-03, this instruction only reduces spurious
# declines. Verbatim intent mirror of llm/gemini.py's _PARSE_SYSTEM_INSTRUCTION.
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

# Verbatim mirror of llm/gemini.py's _INSIGHT_PROMPT_TEMPLATE — the
# insight_service grounding guard (D-06) stays the real enforcement net; the
# prompt only instructs the model to cite supplied figures only.
_INSIGHT_PROMPT_TEMPLATE = """You are summarizing the results of a workforce schedule solve for an operator.

Using ONLY the figures present in the summary below, write a short, plain-language
report of the schedule's outcome (total cost, unmet hours, coverage, any warnings,
and any constraint overrides applied). Cite exact figures from the summary — do
not compute new numbers, percentages, or estimates that are not already present
in the summary.

Summary:
{summary}
"""


class OpenRouterLLMProvider:
    """Real, network-backed `LLMProvider` using OpenRouter's OpenAI-compatible
    Chat Completions API.

    Client construction is deferred to first use (`_get_client`) rather than
    performed in `__init__`, mirroring `GeminiLLMProvider`. This keeps
    `create_provider("openrouter", settings=...)` keyless (D-04) — the key is
    only needed once an actual API call is about to be made.
    """

    name = "openrouter"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = OpenAI(base_url=_OPENROUTER_BASE_URL, api_key=self._api_key)
        return self._client

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        """Extract constraint calls from text via OpenRouter tool calling.

        tool_choice="auto" lets the model legitimately decline to call any
        tool for non-constraint text (matches the stub's "no constraint found"
        behavior, NLC-03). The vendor tool-call payload never leaves this
        method — each call's JSON-string arguments are parsed and unpacked to
        a plain (name, args) pair before `to_override_call` (D-02).
        """
        try:
            response = self._get_client().chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _PARSE_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": text},
                ],
                tools=_TOOL_SCHEMAS,
                tool_choice="auto",
            )
        except openai.OpenAIError as exc:
            raise LLMProviderError("OpenRouter request failed") from exc
        if not response.choices:
            return []
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            return []
        calls: list[OverrideCall] = []
        for tc in tool_calls:
            raw_args = tc.function.arguments
            args = json.loads(raw_args) if raw_args else {}
            calls.append(to_override_call(tc.function.name, normalize_args(args)))
        return calls

    def generate_insights(self, summary: dict) -> str:
        """Generate a plain-text insight report from a run summary (no tools).

        The Phase-3 grounding guard in insight_service remains the enforcement
        net against fabricated figures; this prompt only reduces the chance of
        a rejection by instructing the model to cite supplied figures only.
        """
        prompt = _INSIGHT_PROMPT_TEMPLATE.format(summary=summary)
        try:
            response = self._get_client().chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.OpenAIError as exc:
            raise LLMProviderError("OpenRouter request failed") from exc
        # An empty choices list or a null content (blocked/empty completion)
        # degrades to "" rather than crashing an otherwise-successful solve.
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""
