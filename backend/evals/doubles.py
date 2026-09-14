"""Case-driven deterministic PydanticAI model doubles.

This is the only harness module that constructs a framework model. Network
requests are disabled at module scope, and callers still execute through the
real ``PydanticAIAgentRuntime`` adapter rather than a parallel agent loop.
"""
from __future__ import annotations

import ast
import json

from pydantic_ai import ModelHTTPError, UnexpectedModelBehavior, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.cases import GoldenCase, GoldenTurn, ScriptedModelTurn

models.ALLOW_MODEL_REQUESTS = False


def build_model_double(case: GoldenCase) -> FunctionModel:
    """Build a deterministic response sequence solely from versioned case data."""
    return build_scripted_double(case.scripted_turns, label=case.case_id)


def build_scripted_double(
    scripted_turns: tuple[ScriptedModelTurn, ...],
    *,
    label: str,
    history_response_offset: int = 0,
) -> FunctionModel:
    """Build a double over one turn's own scripted responses only.

    Story 5.6: a multi-turn scenario injects PRIOR turns' owned history into
    this turn's `run_sync` call (`agent/runtime.py:run_turn`'s
    `message_history=`), so the framework messages this double receives
    already carry responses this turn's script never authored. Counting
    `ModelResponse` instances across the WHOLE message list -- as the
    single-turn double always could, because it never received injected
    history -- would misindex into `scripted_turns` from the very first call.
    `history_response_offset` is the count of `ModelResponse`s the CALLER
    already knows the injected history itself contributes (one per non-empty
    assistant `AgentMessageV1` -- see `agent/translate.py:to_framework_messages`),
    subtracted so `response_index` always starts at 0 for THIS turn's own
    first response. A single-turn case passes no history and leaves this 0,
    so its behaviour is unchanged byte-for-byte.
    """

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        response_index = (
            sum(isinstance(message, ModelResponse) for message in messages)
            - history_response_offset
        )
        if response_index < 0:
            raise UnexpectedModelBehavior(
                f"golden turn {label!r} received fewer injected responses than "
                f"declared (history_response_offset={history_response_offset})"
            )
        try:
            turn = scripted_turns[response_index]
        except IndexError as exc:
            raise UnexpectedModelBehavior(
                f"golden turn {label!r} exhausted its scripted turns "
                f"at response {response_index}"
            ) from exc
        if turn.history_lookup is not None:
            turn = _resolve_history_lookup(turn, messages)
        return _to_model_response(turn, info)

    return FunctionModel(respond)


def history_response_offset_for(history_messages: tuple) -> int:
    """Count the `ModelResponse`s `to_framework_messages` will build from an
    already-truncated `AgentTurnV1.messages` tuple -- one per non-empty
    ``assistant`` `AgentMessageV1` (`agent/translate.py:_from_response`
    silently drops an assistant message translated to zero parts).
    """
    return sum(
        1
        for message in history_messages
        if message.role == "assistant" and message.parts
    )


def _dig(value: object, path: tuple[str | int, ...]) -> object:
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, (list, tuple)):
                raise KeyError(f"cannot index {value!r} with {key!r}")
            value = value[key]
        else:
            if not isinstance(value, dict):
                raise KeyError(f"cannot key {value!r} with {key!r}")
            value = value[key]
    return value


def _deep_set(container: dict, path: tuple[str | int, ...], value: object) -> dict:
    """Return a COPY of `container` with `value` set at `path`.

    Never mutates the case's own scripted argument template in place -- a
    shared mutable default would leak a resolved value from one evaluated run
    into the next.
    """
    if not path:
        raise ValueError("history_lookup.arg_path must not be empty")
    root = json.loads(json.dumps(container))
    cursor = root
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return root


def _resolve_history_lookup(
    turn: ScriptedModelTurn, messages: list[ModelMessage]
) -> ScriptedModelTurn:
    """Extract a trusted value out of the ALREADY-OBSERVED messages.

    Story 5.6 Decision 3: "The double must observe/validate history and
    dependency; a response-index-only double is not evidence." The lookup
    scans for the LATEST matching `ToolReturnPart` across the full message
    list -- prior turns' raw history included -- so a broken rehydration, a
    dropped tool result, or a truncated window all surface here as a missing
    antecedent, never as a silently-reused hardcoded value.
    """
    lookup = turn.history_lookup
    assert lookup is not None
    found: object | None = None
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == lookup.source_tool_name:
                found = part.content
    if found is None:
        if lookup.require_present:
            raise UnexpectedModelBehavior(
                f"required antecedent tool result for {lookup.source_tool_name!r} "
                "is absent from the observed history"
            )
        return turn
    # A resumed raw turn stores tool-result content as TEXT
    # (`agent/translate.py:_from_request`); a same-run in-flight result is
    # still the live Python object. Both are handled without a special case.
    parsed = found if not isinstance(found, str) else ast.literal_eval(found)
    if lookup.require_field is not None:
        check_path, expected = lookup.require_field
        try:
            actual = _dig(parsed, check_path)
        except (KeyError, IndexError, TypeError) as exc:
            raise UnexpectedModelBehavior(
                f"antecedent consistency check failed: {check_path} is absent "
                f"from the observed result ({exc})"
            ) from None
        if actual != expected:
            raise UnexpectedModelBehavior(
                f"antecedent consistency check failed at {check_path}: expected "
                f"{expected!r}, actual {actual!r} -- treating as stale"
            )
    try:
        value = _dig(parsed, lookup.field_path)
    except (KeyError, IndexError, TypeError) as exc:
        raise UnexpectedModelBehavior(
            f"antecedent field {lookup.field_path} is absent from the observed "
            f"result ({exc})"
        ) from None
    assert turn.arguments is not None  # `history_lookup` requires `tool_name`
    resolved_arguments = _deep_set(turn.arguments, lookup.arg_path, value)
    return ScriptedModelTurn(
        tool_name=turn.tool_name,
        arguments=resolved_arguments,
        tool_call_id=turn.tool_call_id,
    )


def build_multi_turn_double(
    turn: GoldenTurn, *, label: str, history_response_offset: int = 0
) -> FunctionModel:
    """`GoldenTurn` counterpart of `build_model_double`."""
    return build_scripted_double(
        turn.scripted_turns, label=label, history_response_offset=history_response_offset
    )


def _to_model_response(turn: ScriptedModelTurn, info: AgentInfo) -> ModelResponse:
    if turn.response_error == "provider_error":
        raise ModelHTTPError(status_code=503, model_name="double", body="overloaded")
    if turn.tool_name is not None:
        if turn.arguments is None or turn.tool_call_id is None:
            raise UnexpectedModelBehavior("scripted tool call is incomplete")
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=turn.tool_name,
                    args=json.dumps(turn.arguments, sort_keys=True),
                    tool_call_id=turn.tool_call_id,
                )
            ]
        )
    if turn.response_text is None:
        if turn.response_data is None:
            raise UnexpectedModelBehavior("scripted structured response is incomplete")
        output_tool = next(
            (tool for tool in info.output_tools if tool.name == turn.output_tool),
            None,
        )
        if output_tool is None:
            raise UnexpectedModelBehavior(
                f"scripted output tool {turn.output_tool!r} is absent; available tools: "
                f"{', '.join(tool.name for tool in info.output_tools) or '(none)'}"
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool.name,
                    args=json.dumps(turn.response_data, sort_keys=True),
                    tool_call_id="scripted-final-answer",
                )
            ]
        )
    return ModelResponse(parts=[TextPart(content=turn.response_text)])


__all__ = [
    "build_model_double",
    "build_multi_turn_double",
    "build_scripted_double",
    "history_response_offset_for",
]
