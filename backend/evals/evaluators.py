"""Evaluation extension point and Story 2.2's single tool-routing evaluator."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from application.contracts.agent_runtime import AgentRunOutcomeV1
from evals.cases import GoldenCase


RunSource = Literal["double", "live"]


@dataclass(frozen=True)
class EvalVerdict:
    passed: bool
    reason: str
    run_source: RunSource = "double"

    @property
    def authoritative(self) -> bool:
        """Only deterministic-double results may contribute release evidence."""
        return self.run_source == "double"


class Evaluator(Protocol):
    """Extension point for evaluators owned by later stories."""

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict: ...


@dataclass(frozen=True)
class ToolRoutingEvaluator:
    """Judge only tool name/arguments (or correct absence) against a case."""

    run_source: RunSource = "double"

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict:
        actual = tuple(
            (part.tool_name or "", _arguments(part.tool_args_json))
            for message in outcome.turn.messages
            if message.role == "assistant"
            for part in message.parts
            if part.kind == "tool_call"
        )
        expected = tuple(
            (call.tool_name, call.arguments) for call in case.expected_tool_calls
        )

        if case.expected_outcome in ("refuse", "clarify"):
            if actual:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"expected {case.expected_outcome} with no tool call, "
                        f"but routed to {actual[0][0]!r}"
                    ),
                )
            return self._verdict(
                passed=True,
                reason=f"matched {case.expected_outcome}: no tool call was routed",
            )

        if len(actual) != len(expected):
            return self._verdict(
                passed=False,
                reason=(
                    f"tool-call count differed: expected {len(expected)}, "
                    f"actual {len(actual)}"
                ),
            )
        for index, ((actual_name, actual_args), (expected_name, expected_args)) in enumerate(
            zip(actual, expected)
        ):
            if actual_name != expected_name:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"tool name differed at call {index}: expected "
                        f"{expected_name!r}, actual {actual_name!r}"
                    ),
                )
            if actual_args != expected_args:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"tool arguments differed at call {index}: expected "
                        f"{_stable(expected_args)}, actual {_stable(actual_args)}"
                    ),
                )
        return self._verdict(
            passed=True,
            reason=f"matched {len(expected)} expected tool route(s)",
        )

    def _verdict(self, *, passed: bool, reason: str) -> EvalVerdict:
        return EvalVerdict(
            passed=passed,
            reason=reason,
            run_source=self.run_source,
        )


def _arguments(raw: str | None) -> object:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _stable(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = ["EvalVerdict", "Evaluator", "RunSource", "ToolRoutingEvaluator"]
