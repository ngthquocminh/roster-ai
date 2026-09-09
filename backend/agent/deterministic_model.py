"""Keyless deterministic model for the composed planner journey."""
from __future__ import annotations

from dataclasses import asdict
import json

from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1


def build_deterministic_model() -> FunctionModel:
    """Inspect the pinned scenario once, then return numeral-free grounded prose."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="scheduling_inspect",
                        args=json.dumps({"request": {"group": "overview"}}),
                        tool_call_id="deterministic-inspection",
                    )
                ]
            )

        output_tool = next(
            (tool for tool in info.output_tools if tool.name == "final_result"),
            None,
        )
        if output_tool is None:
            raise UnexpectedModelBehavior("final_result output tool is unavailable")
        answer = GroundedAnswerV1(
            segments=(
                GroundedProseSegmentV1(
                    text="Scenario facts are available for review."
                ),
            )
        )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool.name,
                    args=json.dumps(asdict(answer), sort_keys=True),
                    tool_call_id="deterministic-final-answer",
                )
            ]
        )

    return FunctionModel(respond)


__all__ = ["build_deterministic_model"]
