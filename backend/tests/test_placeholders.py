"""G' phase 2a: the `{{handle}}` value-placeholder parser."""
from __future__ import annotations

import pytest

from application.grounding.placeholders import (
    PlaceholderPart,
    ProsePart,
    malformed_placeholders,
    parse_answer_text,
    placeholder_handles,
)


def test_text_is_split_into_ordered_prose_and_placeholder_parts() -> None:
    assert parse_answer_text("Wednesday outbound needs {{r1}}.") == (
        ProsePart("Wednesday outbound needs "), PlaceholderPart("r1"), ProsePart("."),
    )
    assert parse_answer_text("{{r1}}{{r2}}") == (PlaceholderPart("r1"), PlaceholderPart("r2"))
    assert parse_answer_text("") == ()


def test_plain_text_with_numerals_is_one_prose_part() -> None:
    text = "1. Draft\n2. Run at 06:00 for Grid P 8GR"
    assert parse_answer_text(text) == (ProsePart(text),)
    assert placeholder_handles(text) == ()
    assert malformed_placeholders(text) == ()


@pytest.mark.parametrize("text", ["{{}}", "{{ value }}", "{{r1}", "{{r 1}}"])
def test_near_miss_syntax_is_malformed_and_stays_literal(text) -> None:
    assert malformed_placeholders(f"a {text} b")
    assert placeholder_handles(f"a {text} b") == ()
    assert parse_answer_text(f"a {text} b") == (ProsePart(f"a {text} b"),)


def test_a_valid_placeholder_is_never_reported_malformed() -> None:
    assert placeholder_handles("x {{r1}} y {{a_b-9}}") == ("r1", "a_b-9")
    assert malformed_placeholders("x {{r1}} y {{a_b-9}}") == ()


def test_a_stray_brace_hugging_a_valid_placeholder_is_malformed() -> None:
    assert malformed_placeholders("x {{{r1}}} y")
    assert malformed_placeholders("x {{r1}} y") == ()
