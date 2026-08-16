"""Golden-dataset case schema and JSON loader.

These frozen dataclasses are evaluation infrastructure, not persisted product
contracts. ``risk_class`` is a dataset tag vocabulary that grants no authority;
Story 2.5 owns the application registry that will make authority decisions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, cast, get_args

from application.capabilities.vocabulary import RiskClassV1

RiskClass = RiskClassV1
ExpectedOutcome = Literal["allow", "refuse", "clarify"]
VisibleState = Literal["completed", "suspended", "timed_out", "failed"]
GroundingOracle = Literal[
    "supported", "version_mismatch", "missing_evidence", "argument_mismatch"
]

RISK_CLASSES: tuple[RiskClass, ...] = cast(
    tuple[RiskClass, ...], get_args(RiskClassV1)
)
EXPECTED_OUTCOMES: tuple[ExpectedOutcome, ...] = ("allow", "refuse", "clarify")
VISIBLE_STATES: tuple[VisibleState, ...] = (
    "completed",
    "suspended",
    "timed_out",
    "failed",
)
GROUNDING_ORACLES: tuple[GroundingOracle, ...] = (
    "supported", "version_mismatch", "missing_evidence", "argument_mismatch"
)


@dataclass(frozen=True)
class ScriptedModelTurn:
    """One deterministic response emitted by the generated model double.

    Exactly one of ``tool_name``, ``response_text``, ``response_data`` and
    ``response_error`` is present -- four discriminants since Story 2.9, not the
    two this docstring used to name. ``output_tool`` is a MODIFIER of
    ``response_data`` (which named structured output tool to answer through) and
    is rejected with any other discriminant. Tool-call arguments retain their
    JSON object shape so future cases remain data-only.
    """

    tool_name: str | None = None
    arguments: dict[str, object] | None = None
    tool_call_id: str | None = None
    response_text: str | None = None
    response_data: dict[str, object] | None = None
    output_tool: str = "final_result"
    response_error: Literal["provider_error"] | None = None


@dataclass(frozen=True)
class ExpectedToolCall:
    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class GoldenCase:
    """One version-controlled regression case contributed by an owning story."""

    case_id: str
    case_version: str
    capability: str
    risk_class: RiskClass
    prompt: str
    scripted_turns: tuple[ScriptedModelTurn, ...]
    expected_outcome: ExpectedOutcome
    expected_tool_calls: tuple[ExpectedToolCall, ...]
    expected_evidence_refs: tuple[str, ...]
    expected_visible_state: VisibleState
    expected_visible_text: str
    expected_grounding_outcome: GroundingOracle | None = None
    scenario_fixtures: tuple[str, ...] = ()


def load_case(path: Path) -> GoldenCase:
    """Load and validate one case file, rejecting malformed contributions."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid golden case {source}: {exc}") from exc
    return case_from_mapping(_mapping(raw, "case"), source=source)


def load_cases(directory: Path) -> tuple[GoldenCase, ...]:
    """Load every JSON case recursively; no malformed file is silently skipped."""
    return tuple(load_case(path) for path in sorted(Path(directory).rglob("*.json")))


CASE_FIELDS: frozenset[str] = frozenset(
    {
        "case_id",
        "case_version",
        "capability",
        "risk_class",
        "prompt",
        "scripted_turns",
        "expected_outcome",
        "expected_tool_calls",
        "expected_evidence_refs",
        "expected_visible_state",
        "expected_visible_text",
        "scenario_fixtures",
        "expected_grounding_outcome",
    }
)

SCRIPTED_TURN_FIELDS: frozenset[str] = frozenset(
    {
        "tool_name", "arguments", "tool_call_id", "response_text",
        "response_data", "output_tool", "response_error",
    }
)


def case_from_mapping(raw: Mapping[str, object], *, source: Path | None = None) -> GoldenCase:
    label = str(source) if source is not None else "case"
    # Every field is required and no unknown field is tolerated. A misspelled key
    # would otherwise fall through to a default and silently weaken what the case
    # asserts — `scenario_fixtures` in particular feeds the NFR27 `scenario`
    # binding, where a silent empty reads as "no scenario fixture touched".
    unknown = sorted(set(raw) - CASE_FIELDS)
    if unknown:
        raise ValueError(
            f"{label} has unknown field(s) {', '.join(unknown)}; allowed fields "
            f"are {', '.join(sorted(CASE_FIELDS))}"
        )
    risk = _string(raw.get("risk_class"), f"{label}.risk_class")
    if risk not in RISK_CLASSES:
        raise ValueError(
            f"{label}.risk_class {risk!r} is outside the allowed vocabulary: "
            f"{', '.join(RISK_CLASSES)}"
        )
    outcome = _string(raw.get("expected_outcome"), f"{label}.expected_outcome")
    if outcome not in EXPECTED_OUTCOMES:
        raise ValueError(f"{label}.expected_outcome {outcome!r} is invalid")
    visible_state = _string(
        raw.get("expected_visible_state"), f"{label}.expected_visible_state"
    )
    if visible_state not in VISIBLE_STATES:
        raise ValueError(f"{label}.expected_visible_state {visible_state!r} is invalid")

    scripted = tuple(
        _scripted_turn(item, f"{label}.scripted_turns[{index}]")
        for index, item in enumerate(_list(raw.get("scripted_turns"), "scripted_turns"))
    )
    if not scripted:
        raise ValueError(f"{label}.scripted_turns must contain at least one turn")

    expected_calls = tuple(
        _expected_tool_call(item, f"{label}.expected_tool_calls[{index}]")
        for index, item in enumerate(
            _list(raw.get("expected_tool_calls"), "expected_tool_calls")
        )
    )

    grounding_oracle = _optional_string(
        raw.get("expected_grounding_outcome"),
        f"{label}.expected_grounding_outcome",
    )
    if grounding_oracle is not None and grounding_oracle not in GROUNDING_ORACLES:
        raise ValueError(
            f"{label}.expected_grounding_outcome {grounding_oracle!r} is invalid"
        )

    return GoldenCase(
        case_id=_string(raw.get("case_id"), f"{label}.case_id"),
        case_version=_string(raw.get("case_version"), f"{label}.case_version"),
        capability=_string(raw.get("capability"), f"{label}.capability"),
        risk_class=cast(RiskClass, risk),
        prompt=_string(raw.get("prompt"), f"{label}.prompt"),
        scripted_turns=scripted,
        expected_outcome=cast(ExpectedOutcome, outcome),
        expected_tool_calls=expected_calls,
        expected_evidence_refs=tuple(
            _string(value, f"{label}.expected_evidence_refs")
            for value in _list(
                raw.get("expected_evidence_refs"), "expected_evidence_refs"
            )
        ),
        expected_visible_state=cast(VisibleState, visible_state),
        expected_visible_text=_string(
            raw.get("expected_visible_text"), f"{label}.expected_visible_text",
            allow_empty=True,
        ),
        expected_grounding_outcome=cast(GroundingOracle | None, grounding_oracle),
        scenario_fixtures=tuple(
            _string(value, f"{label}.scenario_fixtures")
            for value in _list(raw.get("scenario_fixtures"), "scenario_fixtures")
        ),
    )


def _scripted_turn(value: object, label: str) -> ScriptedModelTurn:
    raw = _mapping(value, label)
    unknown = sorted(set(raw) - SCRIPTED_TURN_FIELDS)
    if unknown:
        raise ValueError(f"{label} has unknown field(s) {', '.join(unknown)}")
    tool_name = _optional_string(raw.get("tool_name"), f"{label}.tool_name")
    response_text = _optional_string(
        raw.get("response_text"), f"{label}.response_text", allow_empty=True
    )
    response_data_raw = raw.get("response_data")
    response_data = (
        None if response_data_raw is None
        else dict(_mapping(response_data_raw, f"{label}.response_data"))
    )
    response_error = _optional_string(
        raw.get("response_error"), f"{label}.response_error"
    )
    if response_error not in (None, "provider_error"):
        raise ValueError(f"{label}.response_error {response_error!r} is invalid")
    output_tool = _optional_string(raw.get("output_tool"), f"{label}.output_tool")
    if sum(
        value is not None
        for value in (tool_name, response_text, response_data, response_error)
    ) != 1:
        raise ValueError(
            f"{label} must declare exactly one of tool_name, response_text, "
            "response_data, or response_error"
        )
    # Checked BEFORE the `response_error` early return. Previously that return
    # ran first, so `{"response_error": ..., "output_tool": ...}` silently
    # discarded `output_tool` while the same pairing with `tool_name` raised --
    # two different behaviours for one authoring mistake.
    if output_tool is not None and response_data is None:
        raise ValueError(f"{label}.output_tool requires response_data")
    if response_error is not None:
        return ScriptedModelTurn(response_error="provider_error")
    if response_data is not None:
        return ScriptedModelTurn(
            response_data=response_data,
            output_tool=output_tool or "final_result",
        )
    if tool_name is None:
        return ScriptedModelTurn(response_text=response_text)
    return ScriptedModelTurn(
        tool_name=tool_name,
        arguments=dict(_mapping(raw.get("arguments"), f"{label}.arguments")),
        tool_call_id=_string(raw.get("tool_call_id"), f"{label}.tool_call_id"),
    )


def _expected_tool_call(value: object, label: str) -> ExpectedToolCall:
    raw = _mapping(value, label)
    return ExpectedToolCall(
        tool_name=_string(raw.get("tool_name"), f"{label}.tool_name"),
        arguments=dict(_mapping(raw.get("arguments"), f"{label}.arguments")),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_string(
    value: object, label: str, *, allow_empty: bool = False
) -> str | None:
    if value is None:
        return None
    return _string(value, label, allow_empty=allow_empty)


__all__ = [
    "CASE_FIELDS",
    "ExpectedOutcome",
    "ExpectedToolCall",
    "GoldenCase",
    "GROUNDING_ORACLES",
    "GroundingOracle",
    "RiskClass",
    "SCRIPTED_TURN_FIELDS",
    "ScriptedModelTurn",
    "VisibleState",
    "case_from_mapping",
    "load_case",
    "load_cases",
]
