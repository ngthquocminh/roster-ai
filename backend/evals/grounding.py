"""Deterministic grounding oracle driver for Story 2.7 golden cases.

The results this feeds the gate are the REAL ones the governed capability
produced during the scripted turn, captured through `deps.tool_result_sink` --
the same trusted path the request route uses. Nothing here constructs a
capability result.

That matters more than it looks. The previous driver fabricated a
`SchedulingComputeResultV1` keyed by whatever `result_id` the case cited and
branched its contents on the case's own expected outcome, so every case passed
by construction and the calculator was never exercised. Two of this story's
severe defects -- a row bound that fails closed on real data, and volume demand
multiplied into minutes -- survived precisely because of that.
"""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.grounding.gate import ground_answer
from evals.cases import GoldenCase

# A version other than the fixture's, used only to model the one condition that
# cannot arise from case data alone: the pinned scenario version moving between
# the tool call and display. The RESULT is still the calculator's own -- only
# the pin the gate checks against differs, which is exactly what happens when a
# scenario is re-versioned mid-turn.
ROTATED_VERSION = UUID(int=999)


def ground_case_outcome(
    case: GoldenCase,
    outcome: AgentRunOutcomeV1,
    deps: AgentDepsV1,
    results: tuple[object, ...],
) -> AgentRunOutcomeV1:
    """Drive the authored path through the real gate over real tool results."""
    if outcome.answer is None or case.expected_grounding_outcome is None:
        return outcome
    trusted = {
        value.result_id: value
        for value in results
        if isinstance(getattr(value, "result_id", None), str)
    }
    if case.expected_grounding_outcome == "version_mismatch":
        deps = replace(deps, scenario_version_id=ROTATED_VERSION)
    return replace(
        outcome, grounded_response=ground_answer(outcome.answer, deps, trusted)
    )


__all__ = ["ROTATED_VERSION", "ground_case_outcome"]
