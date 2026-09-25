"""The conversation trace-ID rule, shared by the API boundary and the publisher.

Story 5.9 Decision 6: a conversation's trace ID IS its UUID, and every request
in it hangs off one synthesized parent -- the UUID's low 64 bits, never zero.
Story 5.10 writes live-evaluation verdicts into the same traces, so the rule
lives here once (stdlib only) and `api/tracing.py` delegates to it.
"""
from __future__ import annotations

from uuid import UUID

_LOW_64_BITS = (1 << 64) - 1


def conversation_trace_ids(conversation_id: UUID) -> tuple[int, int]:
    """`(trace_id, parent_span_id)` for one conversation."""
    return conversation_id.int, (conversation_id.int & _LOW_64_BITS) or 1


def conversation_traceparent_header(conversation_id: UUID) -> str:
    """The W3C `traceparent` value naming the conversation's synthesized parent."""
    trace_id, parent = conversation_trace_ids(conversation_id)
    return f"00-{trace_id:032x}-{parent:016x}-01"


__all__ = ["conversation_trace_ids", "conversation_traceparent_header"]
