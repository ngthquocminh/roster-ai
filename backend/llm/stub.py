"""Keyword-routed stub LLM provider — the Phase-1 default.

Production code (ships as the default provider; replaced by a real Claude
implementation in Phase 4). Uses stdlib regex to extract a minimum-workers
constraint from free text.

Design (D-08/D-09): this module builds a Claude-faithful tool_use dict
internally (type, id, name, input) and translates it to an OverrideCall before
returning. The tool_use wire format stays fully inside this module and never
crosses the LLMProvider Protocol boundary — callers only ever receive
list[OverrideCall].

Routing (D-10): a single lightweight regex handles "at least N on <token>"
phrasings. Text with no match returns []. Keep regex permissive enough for the
demo sentence; Phase 2 broadens the toolset.
"""
from __future__ import annotations

import re
import uuid

from domain.overrides import OverrideCall, override_id

# Matches phrasings like:
#   "at least 2 on Pick"
#   "at least 2 on C Pick"
#   "minimum 3 on the Pack area"
#   "need at least 5 on Receiving"
# The task token group captures 1-3 words to handle multi-word task names like "C Pick".
_MIN_WORKERS_RE = re.compile(
    r"(?:at\s+least|minimum|min|need\s+at\s+least|require\s+at\s+least)"
    r"\s+(\d+)\s+(?:workers?\s+)?on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)


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
        """Extract a min-workers constraint from text, or return [] if none found (D-10)."""
        m = _MIN_WORKERS_RE.search(text)
        if m is None:
            return []

        n = int(m.group(1))
        task_token = m.group(2)

        # Build a Claude-faithful tool_use block internally (D-09).
        # This shape mirrors what the real Anthropic SDK returns for a tool call.
        # It is constructed and consumed entirely within this module.
        tool_use_block = {
            "type": "tool_use",
            "id": f"toolu_{uuid.uuid4().hex[:16]}",
            "name": "set_min_workers_per_task",
            "input": {"task_id": task_token, "n": n},
        }

        return [_to_override_call(tool_use_block)]
