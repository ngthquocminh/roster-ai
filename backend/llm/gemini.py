"""Gemini-backed LLM provider (LLM-02) — the first real, network-backed
`LLMProvider` implementation.

Uses the current unified `google-genai` SDK (`from google import genai`), NOT
the legacy `google.generativeai` package. Function calling drives
`parse_constraints`; plain text generation drives `generate_insights`. Both
operations share the single provider-neutral translation point,
`llm.translate.to_override_call` (D-07) — the vendor `FunctionCall` object
never leaves `parse_constraints` (D-02).

Tool-calling mode is AUTO (never ANY): genuinely non-constraint text must be
able to yield zero function calls, matching the stub's "no constraint found"
behavior (NLC-03). `AutomaticFunctionCallingConfig(disable=True)` is set as a
defense-in-depth guard even though the five declared tools carry no attached
callables (Pitfall 1, RESEARCH.md).

SECURITY (T-04-01): the API key must never be interpolated into any string,
log line, or exception message in this module. It only ever flows into
`genai.Client(api_key=...)`.
"""
from __future__ import annotations

from google import genai
from google.genai import types

from domain.overrides import OverrideCall
from llm.translate import to_override_call

# ---------------------------------------------------------------------------
# Tool schemas — one FunctionDeclaration per stub tool (mirrors llm/stub.py's
# five arg shapes so Gemini and the stub route the same (name, args) pairs
# through the same to_override_call helper).
# ---------------------------------------------------------------------------

_SET_MIN_WORKERS = types.FunctionDeclaration(
    name="set_min_workers_per_task",
    description="Require at least N workers on a given task at every demanded hour.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
            "n": {"type": "integer", "description": "Minimum worker headcount"},
        },
        "required": ["task_id", "n"],
    },
)

_SCALE_DEMAND = types.FunctionDeclaration(
    name="scale_demand",
    description="Scale a task's demanded volume by a multiplicative factor.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
            "factor": {"type": "number", "description": "Multiplicative scale factor, e.g. 1.5"},
        },
        "required": ["task_id", "factor"],
    },
)

_LOCK_WORKER_SHIFT = types.FunctionDeclaration(
    name="lock_worker_shift",
    description="Keep a specific worker assigned on a specific day.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
            "day": {"type": "integer", "description": "0-indexed day from scenario start (0=Monday)"},
        },
        "required": ["member_id", "day"],
    },
)

_EXCLUDE_WORKER_FROM_TASK = types.FunctionDeclaration(
    name="exclude_worker_from_task",
    description="Prevent a specific worker from being assigned to a specific task.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
            "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
        },
        "required": ["member_id", "task_id"],
    },
)

_SET_MAX_HOURS = types.FunctionDeclaration(
    name="set_max_hours",
    description="Cap a specific worker's total scheduled hours.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "member_id": {"type": "string", "description": "Worker name or id, e.g. 'Alice'"},
            "max_hours": {"type": "number", "description": "Maximum total hours, e.g. 40"},
        },
        "required": ["member_id", "max_hours"],
    },
)

_TOOL_SCHEMAS = [
    _SET_MIN_WORKERS,
    _SCALE_DEMAND,
    _LOCK_WORKER_SHIFT,
    _EXCLUDE_WORKER_FROM_TASK,
    _SET_MAX_HOURS,
]

_INSIGHT_PROMPT_TEMPLATE = """You are summarizing the results of a workforce schedule solve for an operator.

Using ONLY the figures present in the summary below, write a short, plain-language
report of the schedule's outcome (total cost, unmet hours, coverage, any warnings,
and any constraint overrides applied). Cite exact figures from the summary — do
not compute new numbers, percentages, or estimates that are not already present
in the summary.

Summary:
{summary}
"""


class GeminiLLMProvider:
    """Real, network-backed `LLMProvider` using the Gemini Developer API.

    Client construction is deferred to first use (`_get_client`) rather than
    performed in `__init__`. `genai.Client(api_key=...)` raises immediately
    when no key is resolvable — constructing it eagerly would make
    `create_provider("gemini", settings=...)` itself require a key even when
    the caller only wants to inspect `.name` or inject a fake client for unit
    tests, which would break the keyless-default-CI invariant (D-04). The key
    is only ever needed once an actual API call is about to be made, at which
    point a real key is required anyway.
    """

    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        """Extract constraint calls from text via Gemini native function calling.

        AUTO tool-calling mode lets the model legitimately decline to call any
        tool for non-constraint text (matches the stub's "no constraint found"
        behavior, NLC-03). The vendor `FunctionCall` object never leaves this
        method — each call is unpacked to a plain (name, args) pair before
        `to_override_call` (D-02).
        """
        response = self._get_client().models.generate_content(
            model=self._model,
            contents=text,
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=_TOOL_SCHEMAS)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        calls = response.function_calls or []
        return [to_override_call(fc.name, dict(fc.args)) for fc in calls]

    def generate_insights(self, summary: dict) -> str:
        """Generate a plain-text insight report from a run summary (no tools).

        The Phase-3 grounding guard in insight_service remains the enforcement
        net against fabricated figures; this prompt only reduces the chance of
        a rejection by instructing the model to cite supplied figures only.
        """
        prompt = _INSIGHT_PROMPT_TEMPLATE.format(summary=summary)
        response = self._get_client().models.generate_content(model=self._model, contents=prompt)
        return response.text
