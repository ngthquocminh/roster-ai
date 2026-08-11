"""AD-21's SSE resume cursor: ``<stream_uuid>:<sequence>``.

This is the id a browser echoes back in ``Last-Event-ID`` after a reconnect, and
it is the only thing standing between a resumed stream and either duplicated or
silently dropped activity.

Two properties are load-bearing.

**Sequences are ``Decimal``, never strings.** ``persisted_event.sequence`` is
``Numeric(38, 0)``. Compared as text, ``"10" < "9"`` — so a client resuming at
sequence 9 would be served nothing from 10 onward, with no error and no gap
indicator. Every comparison in this module and its callers goes through
:class:`~decimal.Decimal`.

**Zero is a legal cursor but never a legal stored sequence.** Allocation is
``coalesce(max(sequence), 0) + 1`` per stream, so the lowest value the table can
hold is 1. A cursor of 0 therefore unambiguously means *"replay everything"* and
can never collide with a real event.

Rejection is deliberately opaque. Story 2.4's Decision 5 makes non-disclosure a
control-flow property rather than a copywriting one, so every malformed input
collapses to the single :data:`CURSOR_REJECTED` value: a caller *cannot* branch
on the reason, because there is only one value to branch on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

SCHEMA_VERSION = "1"

#: ``persisted_event.sequence`` is ``Numeric(38, 0)`` — 38 significant digits,
#: scale 0. Anything longer is a value the column cannot hold.
MAX_SEQUENCE_DIGITS = 38

#: Digits only, on purpose. This single rule rejects the signed forms (``+1``,
#: ``-1``), the non-integral ones (``1.5``), the exponent forms (``1e3``), and
#: ``NaN``/``Infinity`` — all of which `Decimal` would otherwise happily accept
#: while none of them is a value the stream can contain. It also matches exactly
#: what the wire carries: `ActivityItemOut.sequence` is `str(Decimal)` of a
#: scale-0 column, which always renders as plain digits.
_SEQUENCE_RE = re.compile(rf"\A[0-9]{{1,{MAX_SEQUENCE_DIGITS}}}\Z")


@dataclass(frozen=True)
class StreamCursorV1:
    """A validated resume point on exactly one event stream."""

    stream_id: UUID
    sequence: Decimal
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class StreamCursorRejectedV1:
    """The one and only parse failure.

    Field-free by design: it carries no stream, no sequence, and no reason. A
    partially-parsed value would let a caller act on a stream identity it never
    validated, and a reason code would let a prober distinguish "malformed" from
    "that stream is not yours".
    """


#: The single rejection value. Compare with ``is``.
CURSOR_REJECTED = StreamCursorRejectedV1()


def parse_stream_cursor(raw: str) -> StreamCursorV1 | StreamCursorRejectedV1:
    """Parse ``<stream_uuid>:<sequence>``; never raise, never half-succeed."""
    if not isinstance(raw, str):
        return CURSOR_REJECTED
    stream_text, separator, sequence_text = raw.partition(":")
    # `partition` splits on the FIRST colon, so a third field lands in
    # `sequence_text` and is caught by the digits-only rule below.
    if not separator or not stream_text:
        return CURSOR_REJECTED
    if not _SEQUENCE_RE.match(sequence_text):
        return CURSOR_REJECTED
    try:
        stream_id = UUID(stream_text)
    except (ValueError, AttributeError, TypeError):
        return CURSOR_REJECTED
    return StreamCursorV1(stream_id=stream_id, sequence=Decimal(sequence_text))


def format_event_id(stream_id: UUID, sequence: Decimal) -> str:
    """Render AD-21's SSE ``id:`` value — the inverse of :func:`parse_stream_cursor`.

    Kept here rather than inlined in the router so the wire format has exactly
    one definition; a frame whose id the parser cannot read is a stream that
    cannot be resumed.
    """
    return f"{stream_id}:{sequence}"


__all__ = [
    "CURSOR_REJECTED",
    "MAX_SEQUENCE_DIGITS",
    "SCHEMA_VERSION",
    "StreamCursorRejectedV1",
    "StreamCursorV1",
    "format_event_id",
    "parse_stream_cursor",
]
