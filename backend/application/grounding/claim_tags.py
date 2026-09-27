"""Pure parser for `<claim>` record-fact tags in a model answer (G' phase 2b).

The model wraps a fact read from a record as
`<claim ev='w3' field='qualifications' value='T1'>Ana is qualified for T1</claim>`.
The gate checks `ev`/`field`/`value` against the trusted record; this module
only finds the tags. A malformed tag -- unclosed, nested, or missing one of the
three attributes -- is never a fact: its inner text is kept as plain prose and
the tag syntax is dropped, so the planner never sees raw markup.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

REQUIRED_ATTRIBUTES = ("ev", "field", "value")

_TAG = re.compile(r"(<claim(?=[\s>])[^<>]*>|</claim\s*>)", re.IGNORECASE)
_ATTRIBUTE = re.compile(r"""([A-Za-z_]+)\s*=\s*(?:'([^']*)'|"([^"]*)")""")


@dataclass(frozen=True)
class PlainTextPart:
    text: str


@dataclass(frozen=True)
class FactTagPart:
    text: str
    ev: str
    field: str
    value: str


TagPart = PlainTextPart | FactTagPart


def _attributes(open_tag: str) -> dict[str, str]:
    return {
        match.group(1).lower(): match.group(2) if match.group(2) is not None else match.group(3)
        for match in _ATTRIBUTE.finditer(open_tag)
    }


def parse_claim_tags(text: str) -> tuple[TagPart, ...]:
    """Ordered text and well-formed fact-tag parts; adjacent text is merged."""
    parts: list[TagPart] = []

    def emit_text(value: str) -> None:
        if not value:
            return
        if parts and isinstance(parts[-1], PlainTextPart):
            parts[-1] = PlainTextPart(parts[-1].text + value)
        else:
            parts.append(PlainTextPart(value))

    depth = 0
    nested = False
    attributes: dict[str, str] = {}
    inner: list[str] = []
    for token in _TAG.split(text):
        if not token:
            continue
        if token.lower().startswith("<claim"):
            if depth == 0:
                attributes, inner, nested = _attributes(token), [], False
            else:
                nested = True
            depth += 1
        elif token.lower().startswith("</claim"):
            if depth == 0:
                continue  # an orphan closing tag: drop the syntax
            depth -= 1
            if depth == 0:
                body = "".join(inner)
                # An empty value is a legitimate claim (an empty field); an
                # empty ev cannot cite anything.
                well_formed = all(name in attributes for name in REQUIRED_ATTRIBUTES)
                if not nested and well_formed and attributes["ev"]:
                    parts.append(FactTagPart(
                        text=body, ev=attributes["ev"], field=attributes["field"],
                        value=attributes["value"],
                    ))
                else:
                    emit_text(body)
        elif depth:
            inner.append(token)
        else:
            emit_text(token)
    if depth:
        emit_text("".join(inner))  # unclosed: its text survives as prose
    return tuple(parts)


def fact_handles(text: str) -> tuple[str, ...]:
    return tuple(part.ev for part in parse_claim_tags(text) if isinstance(part, FactTagPart))


__all__ = [
    "FactTagPart", "REQUIRED_ATTRIBUTES", "TagPart", "PlainTextPart",
    "fact_handles", "parse_claim_tags",
]
