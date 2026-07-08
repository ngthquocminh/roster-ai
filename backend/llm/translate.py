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

# Canonical types for the numeric constraint args across every tool. Providers
# may hand back the same value with a different Python type (e.g. Gemini can
# return n as 2.0 even under an "integer" schema); normalizing here keeps the
# content-hash override_id identical regardless of provider (D-06 parity).
_INT_ARGS = frozenset({"n", "day"})
_FLOAT_ARGS = frozenset({"factor", "max_hours"})


def normalize_args(args: dict) -> dict:
    """Coerce known numeric constraint args to canonical types.

    Casts n/day to int and factor/max_hours to float so the same constraint
    yields the same override_id across providers (the stub already produces
    these types; this brings other providers into parity). Unknown keys and
    None values pass through untouched. Returns a new dict.
    """
    out = dict(args)
    for key in _INT_ARGS:
        if out.get(key) is not None:
            out[key] = int(out[key])
    for key in _FLOAT_ARGS:
        if out.get(key) is not None:
            out[key] = float(out[key])
    return out


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
