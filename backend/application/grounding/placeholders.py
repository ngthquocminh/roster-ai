"""Pure parser for value placeholders in a model answer (G' phase 2a).

The model writes one text; every calculated value in it is a placeholder
`{{r1}}` naming a citation handle from the turn's evidence registry. The gate
replaces each placeholder with a claim built from the trusted result, so the
number the planner sees never passes through the model.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_-]+)\}\}")
# Anything the model evidently meant as a placeholder but did not write in the
# exact syntax: `{{}}`, `{{ value }}`, `{{r1}` ..., and a stray brace hugging a
# valid one (`{{{r1}}}`), which would otherwise render around the number.
_MALFORMED = re.compile(r"\{\{[^{}]*\}?\}?|\{\x00|\x00\}")


@dataclass(frozen=True)
class ProsePart:
    text: str


@dataclass(frozen=True)
class PlaceholderPart:
    handle: str


AnswerPart = ProsePart | PlaceholderPart


def parse_answer_text(text: str) -> tuple[AnswerPart, ...]:
    """Ordered prose and placeholder parts; empty prose between parts is dropped.

    A malformed placeholder is left in place as literal prose.
    """
    parts: list[AnswerPart] = []
    position = 0
    for match in _PLACEHOLDER.finditer(text):
        if match.start() > position:
            parts.append(ProsePart(text[position:match.start()]))
        parts.append(PlaceholderPart(match.group(1)))
        position = match.end()
    if position < len(text):
        parts.append(ProsePart(text[position:]))
    return tuple(part for part in parts if not isinstance(part, ProsePart) or part.text)


def placeholder_handles(text: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in _PLACEHOLDER.finditer(text))


def malformed_placeholders(text: str) -> tuple[str, ...]:
    """Placeholder-like fragments that are not the exact `{{handle}}` syntax."""
    return tuple(_MALFORMED.findall(_PLACEHOLDER.sub("\x00", text.replace("\x00", ""))))


__all__ = [
    "AnswerPart", "PlaceholderPart", "ProsePart",
    "malformed_placeholders", "parse_answer_text", "placeholder_handles",
]
