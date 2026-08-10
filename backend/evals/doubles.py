"""Case-driven deterministic PydanticAI model doubles.

This is the only harness module that constructs a framework model. Network
requests are disabled at module scope, and callers still execute through the
real ``PydanticAIAgentRuntime`` adapter rather than a parallel agent loop.
"""
from __future__ import annotations

import json

from pydantic_ai import UnexpectedModelBehavior, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.cases import GoldenCase, ScriptedModelTurn

models.ALLOW_MODEL_REQUESTS = False


def build_model_double(case: GoldenCase) -> FunctionModel:
    """Build a deterministic response sequence solely from versioned case data."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        response_index = sum(
            isinstance(message, ModelResponse) for message in messages
        )
        try:
            turn = case.scripted_turns[response_index]
        except IndexError as exc:
            raise UnexpectedModelBehavior(
                f"golden case {case.case_id!r} exhausted its scripted turns "
                f"at response {response_index}"
            ) from exc
        return _to_model_response(turn)

    return FunctionModel(respond)


def _to_model_response(turn: ScriptedModelTurn) -> ModelResponse:
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
        raise UnexpectedModelBehavior("scripted text response is incomplete")
    return ModelResponse(parts=[TextPart(content=turn.response_text)])


__all__ = ["build_model_double"]
