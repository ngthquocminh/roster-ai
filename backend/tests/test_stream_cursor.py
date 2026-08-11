"""The AD-21 resume cursor: parse, reject, compare, format.

Every rejection must be the *same* typed failure. Story 2.4's Decision 5 makes
non-disclosure a control-flow property, and a caller that could branch on
"malformed" versus "impossible sequence" would be one refactor away from
turning that branch into an observable difference.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from application.contracts.stream_cursor import (
    CURSOR_REJECTED,
    MAX_SEQUENCE_DIGITS,
    StreamCursorRejectedV1,
    StreamCursorV1,
    format_event_id,
    parse_stream_cursor,
)

_STREAM = UUID("11111111-2222-3333-4444-555555555555")


def _cursor(raw: str):
    return parse_stream_cursor(raw)


# --------------------------------------------------------------------------
# accepting cases
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"{_STREAM}:0", Decimal(0)),
        (f"{_STREAM}:1", Decimal(1)),
        (f"{_STREAM}:9007199254740993", Decimal("9007199254740993")),
        (f"{_STREAM}:{'9' * MAX_SEQUENCE_DIGITS}", Decimal("9" * MAX_SEQUENCE_DIGITS)),
        (f"{str(_STREAM).upper()}:7", Decimal(7)),
    ],
)
def test_a_well_formed_cursor_parses_to_a_decimal_sequence(raw: str, expected: Decimal) -> None:
    parsed = _cursor(raw)

    assert isinstance(parsed, StreamCursorV1)
    assert parsed.stream_id == _STREAM
    assert parsed.sequence == expected
    # A str/int here is the whole bug class this contract exists to prevent.
    assert isinstance(parsed.sequence, Decimal)


def test_zero_is_a_legal_cursor_even_though_it_is_never_a_stored_sequence() -> None:
    """Allocation is `max + 1` from a coalesce-to-0 base, so the lowest stored
    sequence is 1. Cursor 0 therefore means "replay everything" and can never
    collide with a real event."""
    parsed = _cursor(f"{_STREAM}:0")

    assert isinstance(parsed, StreamCursorV1)
    assert parsed.sequence == Decimal(0)


def test_the_cursor_is_frozen_and_versioned() -> None:
    parsed = _cursor(f"{_STREAM}:1")
    assert isinstance(parsed, StreamCursorV1)
    assert parsed.schema_version == "1"
    with pytest.raises(FrozenInstanceError):
        parsed.sequence = Decimal(2)  # type: ignore[misc]


# --------------------------------------------------------------------------
# the eight rejection causes — one indistinguishable failure
# --------------------------------------------------------------------------

_REJECTIONS = {
    "missing separator": f"{_STREAM}",
    "extra separator": f"{_STREAM}:1:2",
    "non-uuid left side": "not-a-uuid:1",
    "non-numeric right side": f"{_STREAM}:abc",
    "non-integral decimal": f"{_STREAM}:1.5",
    "negative sequence": f"{_STREAM}:-1",
    "beyond 38 digits": f"{_STREAM}:{'9' * (MAX_SEQUENCE_DIGITS + 1)}",
    "empty sequence": f"{_STREAM}:",
    "empty string": "",
    "whitespace padded": f" {_STREAM}:1 ",
    "signed positive": f"{_STREAM}:+1",
    "scientific notation": f"{_STREAM}:1e3",
    "not a number literal": f"{_STREAM}:NaN",
    "infinity literal": f"{_STREAM}:Infinity",
    "empty stream id": ":1",
}


@pytest.mark.parametrize("raw", list(_REJECTIONS.values()), ids=list(_REJECTIONS))
def test_every_rejection_is_the_same_typed_failure(raw: str) -> None:
    parsed = _cursor(raw)

    assert isinstance(parsed, StreamCursorRejectedV1)
    # Identity, not just equality: callers cannot branch on the reason because
    # there is exactly one value to branch on.
    assert parsed is CURSOR_REJECTED


def test_rejection_never_returns_a_partially_parsed_value() -> None:
    """A cursor with a valid stream and a bad sequence must not leak the stream
    half — that would let a caller act on a stream identity it never validated."""
    parsed = _cursor(f"{_STREAM}:1.5")

    assert not isinstance(parsed, StreamCursorV1)
    assert not hasattr(parsed, "stream_id")
    assert not hasattr(parsed, "sequence")


def test_the_parser_never_raises_past_its_own_boundary() -> None:
    for raw in (*_REJECTIONS.values(), "\x00", "::", "a" * 500, f"{_STREAM}:٣"):
        assert parse_stream_cursor(raw) is CURSOR_REJECTED


# --------------------------------------------------------------------------
# the silent one
# --------------------------------------------------------------------------


def test_sequences_compare_numerically_not_lexicographically() -> None:
    """`"10" < "9"` is true for strings. A client resuming at 9 against a
    string comparison silently loses every event from 10 onward — no error, no
    gap indicator, just missing activity."""
    nine = _cursor(f"{_STREAM}:9")
    ten = _cursor(f"{_STREAM}:10")
    assert isinstance(nine, StreamCursorV1) and isinstance(ten, StreamCursorV1)

    assert ten.sequence > nine.sequence
    # The string comparison this contract exists to avoid says the opposite.
    assert str(ten.sequence) < str(nine.sequence)


# --------------------------------------------------------------------------
# format is the parser's inverse
# --------------------------------------------------------------------------


def test_the_sse_id_format_round_trips_through_the_parser() -> None:
    stream_id = uuid4()
    rendered = format_event_id(stream_id, Decimal("9007199254740993"))

    assert rendered == f"{stream_id}:9007199254740993"
    parsed = parse_stream_cursor(rendered)
    assert isinstance(parsed, StreamCursorV1)
    assert parsed.stream_id == stream_id
    assert parsed.sequence == Decimal("9007199254740993")
