"""Keyword-routed stub LLM provider — the Phase-2 default.

Production code (ships as the default provider; replaced by a real Claude
implementation in Phase 4). Uses stdlib regex to extract minimum-workers
constraints from free text, with conjunction splitting and partial-match
clarification signalling.

Design (D-08/D-09): this module builds a Claude-faithful tool_use dict
internally (type, id, name, input) and translates it to an OverrideCall before
returning. The tool_use wire format stays fully inside this module and never
crosses the LLMProvider Protocol boundary — callers only ever receive
list[OverrideCall].

Routing (D-10): text is first split on conjunctions (and/but/comma) into
fragments. Each fragment is matched against:
  1. _MIN_WORKERS_RE — full "at least N on <task>" phrasing -> OverrideCall
  2. _PARTIAL_WORKERS_RE — "more/fewer/extra workers on <task>" (no number)
     -> OverrideCall(tool="_clarification", ...) sentinel
Non-matching fragments contribute nothing.
"""
from __future__ import annotations

import re
import uuid

from domain.overrides import OverrideCall, override_id

# Splits text on conjunctions and commas to produce independent constraint fragments.
# e.g. "at least 2 on Pick and more people on packing" -> ["at least 2 on Pick",
#       "more people on packing"]
_SPLIT_RE = re.compile(r"\s*(?:,|\band\b|\bbut\b)\s*", re.IGNORECASE)

# Matches phrasings like:
#   "at least 2 on Pick"
#   "at least 2 on C Pick"
#   "minimum 3 on the Pack area"
#   "need at least 5 on Receiving"
#   "require at least 2 workers on Despatch"
# The task token group captures 1-3 words to handle multi-word task names like "C Pick".
_MIN_WORKERS_RE = re.compile(
    r"(?:at\s+least|minimum|min(?:imum)?|need\s+at\s+least|require\s+at\s+least)"
    r"\s+(\d+)\s+(?:workers?\s+)?on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)

# Matches partial phrasings that imply a min-workers constraint but lack the number.
# e.g. "more people on packing", "fewer workers on Receiving", "extra staff on Pick"
# These emit a _clarification sentinel to ask the user for the missing count.
_PARTIAL_WORKERS_RE = re.compile(
    r"(?:more|fewer|extra|additional|less)\s+(?:workers?|people|staff|headcount)\s+on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)


def _split_fragments(text: str) -> list[str]:
    """Split text on conjunctions and commas, returning non-empty stripped fragments."""
    return [f.strip() for f in _SPLIT_RE.split(text) if f.strip()]


def _to_override_call(block: dict) -> OverrideCall:
    """Translate a Claude-faithful tool_use dict to a provider-neutral OverrideCall.

    The block has keys: type, id, name, input. The OverrideCall id is the
    content-hash of (tool, args) from domain.overrides.override_id (D-05) —
    this is stable across re-submissions of the same constraint.
    """
    tool = block["name"]
    args = block["input"]
    return OverrideCall(
        id=override_id(tool, args),
        tool=tool,
        args=args,
    )


class StubLLMProvider:
    """Keyword-routed stub. Deterministic and test-friendly; no external I/O."""

    name = "stub"

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        """Extract constraint calls from text by splitting on conjunctions and matching each fragment.

        Returns list[OverrideCall] (0..many):
        - _MIN_WORKERS_RE match -> OverrideCall(tool="set_min_workers_per_task", ...)
        - _PARTIAL_WORKERS_RE match (no number) -> OverrideCall(tool="_clarification", ...)
        - No match -> nothing added
        """
        results: list[OverrideCall] = []
        fragments = _split_fragments(text)

        for fragment in fragments:
            # Try full min-workers phrasing first (has a number)
            m = _MIN_WORKERS_RE.search(fragment)
            if m is not None:
                n = int(m.group(1))
                task_token = m.group(2)
                tool_use_block = {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": "set_min_workers_per_task",
                    "input": {"task_id": task_token, "n": n},
                }
                results.append(_to_override_call(tool_use_block))
                continue

            # Try partial phrasing (no number) -> emit clarification sentinel
            pm = _PARTIAL_WORKERS_RE.search(fragment)
            if pm is not None:
                task_token = pm.group(1)
                clarification_call = OverrideCall(
                    id=f"clr_{uuid.uuid4().hex[:8]}",
                    tool="_clarification",
                    args={"question": f"How many workers minimum on '{task_token}'?"},
                )
                results.append(clarification_call)
                continue

            # No match — fragment contributes nothing

        return results
