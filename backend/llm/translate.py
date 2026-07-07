"""Shared provider-neutral translation point (D-07).

Every LLMProvider implementation (stub, and the real provider added in a later
plan) calls `to_override_call` as the single place a (tool_name, args) pair
becomes a domain `OverrideCall`. No vendor payload shape crosses this boundary —
a Claude-style tool_use dict, a Gemini function-call object, or any other
provider-specific wire format must be unpacked into a plain (name, args) pair by
the caller before it reaches this module (upholds Phase 1 D-08/D-09 and Phase 4
D-02).
"""
from __future__ import annotations

from domain.overrides import OverrideCall, override_id


def to_override_call(tool_name: str, args: dict) -> OverrideCall:
    """Translate a (tool_name, args) pair into a provider-neutral OverrideCall.

    The id is the content-hash of (tool_name, args) from domain.overrides.override_id
    (D-05) — stable across re-submissions of the same constraint.
    """
    return OverrideCall(
        id=override_id(tool_name, args),
        tool=tool_name,
        args=args,
    )
