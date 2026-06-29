"""Keyword-routed stub LLM provider — the Phase-2 default.

Production code (ships as the default provider; replaced by a real Claude
implementation in Phase 4). Uses stdlib regex to extract scheduling constraints
from free text, with conjunction splitting and partial-match clarification
signalling.

Design (D-08/D-09): this module builds a Claude-faithful tool_use dict
internally (type, id, name, input) and translates it to an OverrideCall before
returning. The tool_use wire format stays fully inside this module and never
crosses the LLMProvider Protocol boundary — callers only ever receive
list[OverrideCall].

Routing (D-10): text is first split on conjunctions (and/but/comma) into
fragments. Each fragment is matched against each tool regex in priority order.
Non-matching fragments contribute nothing.

Tools supported (Phase 2, NLC-02):
  1. set_min_workers_per_task — "at least N on <task>"
  2. scale_demand             — "scale <task> demand by Nx"
  3. lock_worker_shift        — "keep <member> on <day-name>"
  4. exclude_worker_from_task — "exclude <member> from <task>"
  5. set_max_hours            — "cap <member> at N hours"
  _clarification sentinel     — "more/fewer workers on <task>" (no number)
"""
from __future__ import annotations

import re
import uuid

from domain.overrides import OverrideCall, override_id

# Splits text on conjunctions and commas to produce independent constraint fragments.
# e.g. "at least 2 on Pick and more people on packing" -> ["at least 2 on Pick",
#       "more people on packing"]
_SPLIT_RE = re.compile(r"\s*(?:,|\band\b|\bbut\b)\s*", re.IGNORECASE)

# Day-name -> 0-indexed int matching int(sv.start_h // 24) in the builder.
# (Assumption A1: day numbering starts at 0 from scenario start.)
_DAY_MAP: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ---- Tool 1: set_min_workers_per_task ----
# Matches phrasings like:
#   "at least 2 on Pick" / "minimum 3 on the Pack area" / "require at least 2 workers on C Pick"
# The task token group captures 1-3 words to handle multi-word task names like "C Pick".
_MIN_WORKERS_RE = re.compile(
    r"(?:at\s+least|minimum|min(?:imum)?|need\s+at\s+least|require\s+at\s+least)"
    r"\s+(\d+)\s+(?:workers?\s+)?on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)

# ---- Tool 2: scale_demand ----
# Matches phrasings like:
#   "scale C Pick demand by 1.5x" / "increase Pick volume by 2x" / "boost Amb Rec workload by 3x"
# The task token is greedy {0,2} but regex backtracks before demand/volume/workload keyword.
_SCALE_DEMAND_RE = re.compile(
    r"(?:increase|scale|boost)\s+(\w+(?:\s+\w+){0,2})\s+(?:demand|volume|workload)\s+by\s+(\d+(?:\.\d+)?)x?",
    re.IGNORECASE,
)

# ---- Tool 3: lock_worker_shift ----
# Matches phrasings like:
#   "keep Alice on Tuesday" / "lock Bob on Monday" / "assign Gary on 0"
# Day captured as a day-name or numeric integer.
_LOCK_SHIFT_RE = re.compile(
    r"(?:keep|lock|assign)\s+(\w+(?:\s+\w+)?)\s+on\s+"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d+)",
    re.IGNORECASE,
)

# ---- Tool 4: exclude_worker_from_task ----
# Matches phrasings like:
#   "exclude Alice from Pick" / "remove Bob from C Pick" / "don't assign Gary to Receiving"
_EXCLUDE_RE = re.compile(
    r"(?:exclude|remove|don'?t\s+assign)\s+(\w+(?:\s+\w+)?)\s+(?:from|to)\s+(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)

# ---- Tool 5: set_max_hours ----
# Matches phrasings like:
#   "cap Alice at 40 hours" / "limit Bob to 35 hours" / "maximum Gary 48 hours"
_MAX_HOURS_RE = re.compile(
    r"(?:cap|limit|max(?:imum)?)\s+(\w+(?:\s+\w+)?)\s+(?:at|to)\s+(\d+(?:\.\d+)?)\s+hours?",
    re.IGNORECASE,
)

# ---- Partial match: _clarification sentinel ----
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

        Returns list[OverrideCall] (0..many per fragment):
        - _MIN_WORKERS_RE match       -> set_min_workers_per_task OverrideCall
        - _SCALE_DEMAND_RE match      -> scale_demand OverrideCall
        - _LOCK_SHIFT_RE match        -> lock_worker_shift OverrideCall
        - _EXCLUDE_RE match           -> exclude_worker_from_task OverrideCall
        - _MAX_HOURS_RE match         -> set_max_hours OverrideCall
        - _PARTIAL_WORKERS_RE match   -> _clarification sentinel OverrideCall
        - No match                    -> fragment contributes nothing
        """
        results: list[OverrideCall] = []
        fragments = _split_fragments(text)

        for fragment in fragments:
            # Tool 1: set_min_workers_per_task — full phrasing with a number
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

            # Tool 2: scale_demand — "scale/increase/boost <task> demand by Nx"
            m = _SCALE_DEMAND_RE.search(fragment)
            if m is not None:
                task_token = m.group(1).strip()
                factor = float(m.group(2))
                tool_use_block = {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": "scale_demand",
                    "input": {"task_id": task_token, "factor": factor},
                }
                results.append(_to_override_call(tool_use_block))
                continue

            # Tool 3: lock_worker_shift — "keep/lock/assign <member> on <day>"
            m = _LOCK_SHIFT_RE.search(fragment)
            if m is not None:
                member_token = m.group(1).strip()
                day_str = m.group(2).lower()
                # Convert day name to 0-indexed int; fall back to int parse for numeric
                if day_str in _DAY_MAP:
                    day = _DAY_MAP[day_str]
                else:
                    try:
                        day = int(day_str)
                    except ValueError:
                        day = 0
                tool_use_block = {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": "lock_worker_shift",
                    "input": {"member_id": member_token, "day": day},
                }
                results.append(_to_override_call(tool_use_block))
                continue

            # Tool 4: exclude_worker_from_task — "exclude/remove/don't assign <member> from/to <task>"
            m = _EXCLUDE_RE.search(fragment)
            if m is not None:
                member_token = m.group(1).strip()
                task_token = m.group(2).strip()
                tool_use_block = {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": "exclude_worker_from_task",
                    "input": {"member_id": member_token, "task_id": task_token},
                }
                results.append(_to_override_call(tool_use_block))
                continue

            # Tool 5: set_max_hours — "cap/limit/max <member> at/to N hours"
            m = _MAX_HOURS_RE.search(fragment)
            if m is not None:
                member_token = m.group(1).strip()
                max_hours = float(m.group(2))
                tool_use_block = {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": "set_max_hours",
                    "input": {"member_id": member_token, "max_hours": max_hours},
                }
                results.append(_to_override_call(tool_use_block))
                continue

            # Partial phrasing (no number) -> emit clarification sentinel
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
