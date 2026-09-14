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
class HistoryLookupV1:
    """Story 5.6: instructs the multi-turn double to READ a value out of the
    injected owned history rather than replaying one hardcoded in the case
    script. This is what makes the double "observe and validate" a trusted
    antecedent instead of merely reproducing one by coincidence -- Decision 3
    of the 5.6 story spec: "a response-index-only double is not evidence."

    ``source_tool_name`` names the capability whose most-recent
    ``ToolReturnPart`` in the accumulated framework messages carries the
    antecedent. ``field_path`` descends into that result (after
    ``ast.literal_eval`` of its stringified content, since a raw resumed
    transcript stores tool-result content as text -- see
    ``agent/translate.py:_from_request``) to the value that gets deep-set into
    this scripted turn's ``arguments`` at ``arg_path``.

    ``require_field`` is an optional extra consistency check: (path, expected)
    evaluated against the SAME parsed result. It is how a "stale antecedent"
    case proves fail-closed behaviour without inventing model-side judgement --
    the check simply fails when the persisted fact has moved on.
    """

    source_tool_name: str
    field_path: tuple[str | int, ...]
    arg_path: tuple[str | int, ...]
    require_field: tuple[tuple[str | int, ...], object] | None = None
    require_present: bool = True


@dataclass(frozen=True)
class ScriptedModelTurn:
    """One deterministic response emitted by the generated model double.

    Exactly one of ``tool_name``, ``response_text``, ``response_data`` and
    ``response_error`` is present -- four discriminants since Story 2.9, not the
    two this docstring used to name. ``output_tool`` is a MODIFIER of
    ``response_data`` (which named structured output tool to answer through) and
    is rejected with any other discriminant. Tool-call arguments retain their
    JSON object shape so future cases remain data-only.

    ``history_lookup`` is additive (Story 5.6): when present on a ``tool_name``
    turn, the double resolves it against the accumulated messages BEFORE
    emitting the call, deep-setting the extracted value into ``arguments`` at
    the declared path. Single-turn cases never set it and are unaffected.
    """

    tool_name: str | None = None
    arguments: dict[str, object] | None = None
    tool_call_id: str | None = None
    response_text: str | None = None
    response_data: dict[str, object] | None = None
    output_tool: str = "final_result"
    response_error: Literal["provider_error"] | None = None
    history_lookup: HistoryLookupV1 | None = None


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
    # Deterministic security simulations may include an attempted call to an
    # unavailable tool. A real provider was never offered that tool, so its
    # separately authored live expectation can require a direct refusal.
    # `None` deliberately means the canonical deterministic expectation applies.
    live_expected_tool_calls: tuple[ExpectedToolCall, ...] | None = None
    # Some deterministic cases intentionally script a malformed model answer to
    # prove a grounding oracle. A live provider should instead be held to the
    # truthful supported result it receives from the capability.
    live_expected_grounding_outcome: GroundingOracle | None = None
    live_expected_evidence_refs: tuple[str, ...] | None = None
    live_expected_outcome: ExpectedOutcome | None = None
    live_eligible: bool = True


HistoryModeV1 = Literal["independent", "raw_turn", "rehydrated_activities"]
HISTORY_MODES: tuple[HistoryModeV1, ...] = (
    "independent", "raw_turn", "rehydrated_activities",
)


@dataclass(frozen=True)
class GoldenTurn:
    """Story 5.6: one turn of a versioned multi-turn scenario.

    Deliberately NOT a `GoldenCase` (which also carries `case_version`,
    `scenario_fixtures`, and grounding fields that are case-level, not
    per-turn) -- but its evaluation-facing field NAMES mirror `GoldenCase`
    exactly (`expected_outcome`, `expected_tool_calls`, `live_expected_*`) so
    `ToolRoutingEvaluator` and `PolicyOutcomeEvaluator` (Story 2.2/2.9) can
    judge one turn's outcome UNCHANGED, by duck typing, per Decision 1: reuse
    the current evaluation authority rather than build a second one.

    ``capabilities`` grants exactly these modules for this turn's runtime --
    NOT the case-level singular `capability` tag `GoldenCase` uses, because a
    negative "unauthorized" scenario must be able to grant a DIFFERENT set on
    a later turn than an earlier one granted (Decision 4: installed-but-
    ungranted modules are unavailable).

    ``history_mode`` selects how this turn's `execute_turn(..., history=...)`
    argument is built from every prior turn's outcome in the same case:

    - ``independent``: `history=()` -- always used for a case's first turn.
    - ``raw_turn``: `history=<previous turn's raw AgentTurnV1>`, the exact
      "owned resume transcript" mechanism the approval-resume path already
      uses (api/routers/approvals.py). Preserves real tool-call/tool-result
      content verbatim, which is what proves genuine trusted-antecedent use
      (Decision 2/3) -- never a second, invented raw-persistence mechanism.
    - ``rehydrated_activities``: `history=<tuple[ActivityItemV1, ...]>` built
      from every prior turn via the SAME production `rehydrate_history()`
      (Decision: "must invoke execute_turn / rehydrate_history"), which
      carries planner-VISIBLE text only -- proving the ordinary conversational
      path and its 100-message bound (AC5), never tool-result bodies.

    ``raw_turn_padding`` appends N synthetic filler messages after the prior
    turn's real messages before `execute_turn`'s `HISTORY_MESSAGE_BOUND` slice
    -- the mechanism the truncated-antecedent fault case uses to push a real
    antecedent out of the provider-bound window without inventing a second
    bound.

    ``filler_activity_count`` prepends N synthetic old `PlannerMessageActivityV1`
    entries (durable, but old enough to fall outside the window) ahead of the
    real prior activities when `history_mode == "rehydrated_activities"` --
    the long-history proof for AC5.
    """

    prompt: str
    capabilities: tuple[str, ...]
    scripted_turns: tuple[ScriptedModelTurn, ...]
    expected_outcome: ExpectedOutcome
    expected_tool_calls: tuple[ExpectedToolCall, ...]
    expected_visible_state: VisibleState
    expected_visible_text: str
    history_mode: HistoryModeV1 = "independent"
    raw_turn_padding: int = 0
    filler_activity_count: int = 0
    # `ToolRoutingEvaluator` (Decision 1's REUSED evaluator) judges only
    # ATTEMPTED assistant tool calls -- it cannot distinguish "attempted and
    # rejected by the trust boundary" from "attempted and actually executed".
    # An `unauthorized`-antecedent case needs exactly that distinction: the
    # model may still attempt the call (and `expected_tool_calls` still
    # records the attempt, matching `injection-chat-text.json`'s precedent),
    # but a real capability RESULT must never appear once the boundary held.
    # `None` means "not checked" -- every case predating this field.
    expected_tool_result_names: tuple[str, ...] | None = None
    live_expected_tool_calls: tuple[ExpectedToolCall, ...] | None = None
    live_expected_outcome: ExpectedOutcome | None = None


@dataclass(frozen=True)
class MultiTurnGoldenCase:
    """Story 5.6: one version-controlled multi-turn regression scenario.

    ``capability`` is a case-level dataset-classification TAG, not an
    authority grant -- each turn's OWN ``capabilities`` tuple governs what its
    runtime actually registers. It exists so `scripts/evidence_binding.py`'s
    unmodified golden-dataset NFR27 binding (which requires every `.json`
    dataset file to carry `case_id`/`case_version`/`capability`/`risk_class`)
    can bind this dataset exactly like the single-turn one, rather than this
    story widening a shared binding module it does not own.
    """

    case_id: str
    case_version: str
    capability: str
    risk_class: RiskClass
    scenario_fixtures: tuple[str, ...]
    turns: tuple[GoldenTurn, ...]
    live_eligible: bool = True


MULTI_TURN_CASE_FIELDS: frozenset[str] = frozenset(
    {
        "case_id", "case_version", "capability", "risk_class",
        "scenario_fixtures", "turns", "live_eligible",
    }
)

GOLDEN_TURN_FIELDS: frozenset[str] = frozenset(
    {
        "prompt", "capabilities", "scripted_turns", "expected_outcome",
        "expected_tool_calls", "expected_visible_state", "expected_visible_text",
        "history_mode", "raw_turn_padding", "filler_activity_count",
        "expected_tool_result_names",
        "live_expected_tool_calls", "live_expected_outcome",
    }
)


def load_multi_turn_case(path: Path) -> MultiTurnGoldenCase:
    """Load and validate one multi-turn case file, mirroring `load_case`."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid multi-turn golden case {source}: {exc}") from exc
    return multi_turn_case_from_mapping(_mapping(raw, "case"), source=source)


def load_multi_turn_cases(directory: Path) -> tuple[MultiTurnGoldenCase, ...]:
    """Load every JSON case recursively; no malformed file is silently skipped."""
    return tuple(
        load_multi_turn_case(path) for path in sorted(Path(directory).rglob("*.json"))
    )


def multi_turn_case_from_mapping(
    raw: Mapping[str, object], *, source: Path | None = None
) -> MultiTurnGoldenCase:
    label = str(source) if source is not None else "case"
    unknown = sorted(set(raw) - MULTI_TURN_CASE_FIELDS)
    if unknown:
        raise ValueError(
            f"{label} has unknown field(s) {', '.join(unknown)}; allowed fields "
            f"are {', '.join(sorted(MULTI_TURN_CASE_FIELDS))}"
        )
    risk = _string(raw.get("risk_class"), f"{label}.risk_class")
    if risk not in RISK_CLASSES:
        raise ValueError(
            f"{label}.risk_class {risk!r} is outside the allowed vocabulary: "
            f"{', '.join(RISK_CLASSES)}"
        )
    turns_raw = _list(raw.get("turns"), "turns")
    if not turns_raw:
        raise ValueError(f"{label}.turns must contain at least one turn")
    turns = tuple(
        _golden_turn(item, f"{label}.turns[{index}]") for index, item in enumerate(turns_raw)
    )
    if turns[0].history_mode != "independent":
        raise ValueError(f"{label}.turns[0].history_mode must be 'independent'")
    live_eligible = raw.get("live_eligible", True)
    if not isinstance(live_eligible, bool):
        raise ValueError(f"{label}.live_eligible must be boolean")
    return MultiTurnGoldenCase(
        case_id=_string(raw.get("case_id"), f"{label}.case_id"),
        case_version=_string(raw.get("case_version"), f"{label}.case_version"),
        capability=_string(raw.get("capability"), f"{label}.capability"),
        risk_class=cast(RiskClass, risk),
        scenario_fixtures=tuple(
            _string(value, f"{label}.scenario_fixtures")
            for value in _list(raw.get("scenario_fixtures"), "scenario_fixtures")
        ),
        turns=turns,
        live_eligible=live_eligible,
    )


def _golden_turn(value: object, label: str) -> GoldenTurn:
    raw = _mapping(value, label)
    unknown = sorted(set(raw) - GOLDEN_TURN_FIELDS)
    if unknown:
        raise ValueError(f"{label} has unknown field(s) {', '.join(unknown)}")
    outcome = _string(raw.get("expected_outcome"), f"{label}.expected_outcome")
    if outcome not in EXPECTED_OUTCOMES:
        raise ValueError(f"{label}.expected_outcome {outcome!r} is invalid")
    visible_state = _string(
        raw.get("expected_visible_state"), f"{label}.expected_visible_state"
    )
    if visible_state not in VISIBLE_STATES:
        raise ValueError(f"{label}.expected_visible_state {visible_state!r} is invalid")
    history_mode = _string(raw.get("history_mode"), f"{label}.history_mode")
    if history_mode not in HISTORY_MODES:
        raise ValueError(
            f"{label}.history_mode {history_mode!r} is invalid; allowed: "
            f"{', '.join(HISTORY_MODES)}"
        )
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
    live_expected_calls = (
        None
        if "live_expected_tool_calls" not in raw
        else tuple(
            _expected_tool_call(item, f"{label}.live_expected_tool_calls[{index}]")
            for index, item in enumerate(
                _list(raw.get("live_expected_tool_calls"), "live_expected_tool_calls")
            )
        )
    )
    live_outcome = _optional_string(raw.get("live_expected_outcome"), f"{label}.live_expected_outcome")
    if live_outcome is not None and live_outcome not in EXPECTED_OUTCOMES:
        raise ValueError(f"{label}.live_expected_outcome {live_outcome!r} is invalid")
    raw_turn_padding = raw.get("raw_turn_padding", 0)
    if not isinstance(raw_turn_padding, int) or isinstance(raw_turn_padding, bool) or raw_turn_padding < 0:
        raise ValueError(f"{label}.raw_turn_padding must be a non-negative integer")
    filler_activity_count = raw.get("filler_activity_count", 0)
    if (
        not isinstance(filler_activity_count, int)
        or isinstance(filler_activity_count, bool)
        or filler_activity_count < 0
    ):
        raise ValueError(f"{label}.filler_activity_count must be a non-negative integer")
    expected_tool_result_names = (
        None
        if "expected_tool_result_names" not in raw
        else tuple(
            _string(value, f"{label}.expected_tool_result_names")
            for value in _list(raw.get("expected_tool_result_names"), "expected_tool_result_names")
        )
    )
    return GoldenTurn(
        prompt=_string(raw.get("prompt"), f"{label}.prompt"),
        capabilities=tuple(
            _string(value, f"{label}.capabilities")
            for value in _list(raw.get("capabilities"), "capabilities")
        ),
        scripted_turns=scripted,
        expected_outcome=cast(ExpectedOutcome, outcome),
        expected_tool_calls=expected_calls,
        expected_visible_state=cast(VisibleState, visible_state),
        expected_visible_text=_string(
            raw.get("expected_visible_text"), f"{label}.expected_visible_text",
            allow_empty=True,
        ),
        history_mode=cast(HistoryModeV1, history_mode),
        raw_turn_padding=raw_turn_padding,
        filler_activity_count=filler_activity_count,
        expected_tool_result_names=expected_tool_result_names,
        live_expected_tool_calls=live_expected_calls,
        live_expected_outcome=cast(ExpectedOutcome | None, live_outcome),
    )


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
        "live_expected_tool_calls",
        "live_expected_grounding_outcome",
        "live_expected_evidence_refs",
        "live_expected_outcome",
        "live_eligible",
    }
)

SCRIPTED_TURN_FIELDS: frozenset[str] = frozenset(
    {
        "tool_name", "arguments", "tool_call_id", "response_text",
        "response_data", "output_tool", "response_error", "history_lookup",
    }
)

HISTORY_LOOKUP_FIELDS: frozenset[str] = frozenset(
    {"source_tool_name", "field_path", "arg_path", "require_field", "require_present"}
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
    live_expected_calls = (
        None
        if "live_expected_tool_calls" not in raw
        else tuple(
            _expected_tool_call(
                item, f"{label}.live_expected_tool_calls[{index}]"
            )
            for index, item in enumerate(
                _list(raw.get("live_expected_tool_calls"), "live_expected_tool_calls")
            )
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
    live_grounding_oracle = _optional_string(
        raw.get("live_expected_grounding_outcome"),
        f"{label}.live_expected_grounding_outcome",
    )
    if live_grounding_oracle is not None and live_grounding_oracle not in GROUNDING_ORACLES:
        raise ValueError(
            f"{label}.live_expected_grounding_outcome {live_grounding_oracle!r} is invalid"
        )
    live_evidence_refs = (
        None
        if "live_expected_evidence_refs" not in raw
        else tuple(
            _string(value, f"{label}.live_expected_evidence_refs")
            for value in _list(raw.get("live_expected_evidence_refs"), "live_expected_evidence_refs")
        )
    )
    live_outcome = _optional_string(raw.get("live_expected_outcome"), f"{label}.live_expected_outcome")
    if live_outcome is not None and live_outcome not in EXPECTED_OUTCOMES:
        raise ValueError(f"{label}.live_expected_outcome {live_outcome!r} is invalid")
    live_eligible = raw.get("live_eligible", True)
    if not isinstance(live_eligible, bool):
        raise ValueError(f"{label}.live_eligible must be boolean")

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
        live_expected_tool_calls=live_expected_calls,
        live_expected_grounding_outcome=cast(GroundingOracle | None, live_grounding_oracle),
        live_expected_evidence_refs=live_evidence_refs,
        live_expected_outcome=cast(ExpectedOutcome | None, live_outcome),
        live_eligible=live_eligible,
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
    history_lookup_raw = raw.get("history_lookup")
    if history_lookup_raw is not None and tool_name is None:
        raise ValueError(f"{label}.history_lookup requires tool_name")
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
        history_lookup=(
            None
            if history_lookup_raw is None
            else _history_lookup(history_lookup_raw, f"{label}.history_lookup")
        ),
    )


def _history_lookup(value: object, label: str) -> HistoryLookupV1:
    raw = _mapping(value, label)
    unknown = sorted(set(raw) - HISTORY_LOOKUP_FIELDS)
    if unknown:
        raise ValueError(f"{label} has unknown field(s) {', '.join(unknown)}")
    require_field_raw = raw.get("require_field")
    require_field: tuple[tuple[str | int, ...], object] | None = None
    if require_field_raw is not None:
        pair = _list(require_field_raw, f"{label}.require_field")
        if len(pair) != 2:
            raise ValueError(f"{label}.require_field must be [path, expected_value]")
        require_field = (
            tuple(_list(pair[0], f"{label}.require_field[0]")),
            pair[1],
        )
    require_present = raw.get("require_present", True)
    if not isinstance(require_present, bool):
        raise ValueError(f"{label}.require_present must be boolean")
    return HistoryLookupV1(
        source_tool_name=_string(raw.get("source_tool_name"), f"{label}.source_tool_name"),
        field_path=tuple(_list(raw.get("field_path"), f"{label}.field_path")),
        arg_path=tuple(_list(raw.get("arg_path"), f"{label}.arg_path")),
        require_field=require_field,
        require_present=require_present,
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
    "GoldenTurn",
    "GOLDEN_TURN_FIELDS",
    "GROUNDING_ORACLES",
    "GroundingOracle",
    "HistoryLookupV1",
    "HistoryModeV1",
    "HISTORY_LOOKUP_FIELDS",
    "HISTORY_MODES",
    "MultiTurnGoldenCase",
    "MULTI_TURN_CASE_FIELDS",
    "RiskClass",
    "SCRIPTED_TURN_FIELDS",
    "ScriptedModelTurn",
    "VisibleState",
    "case_from_mapping",
    "load_case",
    "load_cases",
    "load_multi_turn_case",
    "load_multi_turn_cases",
    "multi_turn_case_from_mapping",
]
