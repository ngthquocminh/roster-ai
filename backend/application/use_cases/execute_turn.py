"""Execute and ground one already-claimed planner turn."""
from __future__ import annotations

from dataclasses import replace

from application.contracts.agent_runtime import (
    AgentMessageV1,
    AgentPartV1,
    AgentRunOutcomeV1,
    AgentTurnRequestV1,
    AgentTurnV1,
)
from application.contracts.activity import AgentResponseActivityV1, ActivityItemV1, PlannerMessageActivityV1
from application.contracts.grounding import GroundedClaimV1, GroundedProseSegmentV1, GroundedResponseV1
from application.grounding.gate import ground_answer
from application.ports.agent_runtime import AgentRuntime
from application.capabilities.deps import AgentDepsV1


def execute_turn(
    runtime: AgentRuntime,
    deps: AgentDepsV1,
    *,
    prompt: str,
    calculation_results: list[object],
    history: tuple[ActivityItemV1, ...] = (),
) -> AgentRunOutcomeV1:
    """Run outside a database transaction, then bind claims to raw tool results."""
    outcome = runtime.run_turn(
        AgentTurnRequestV1(prompt=prompt, history=rehydrate_history(history))
    )
    if outcome.status != "completed" or outcome.answer is None:
        return outcome
    by_id = {
        value.result_id: value
        for value in calculation_results
        if isinstance(getattr(value, "result_id", None), str)
    }
    return replace(
        outcome,
        grounded_response=ground_answer(outcome.answer, deps, by_id),
    )


def terminal_status(outcome: AgentRunOutcomeV1) -> str:
    if outcome.status == "completed" and outcome.grounded_response is None:
        return "agent_failed"
    return {
        "completed": "agent_completed",
        "timed_out": "agent_timed_out",
        "failed": "agent_failed",
        # Approval execution is deliberately owned by Story 2.9. Until then a
        # suspension cannot be resumed through this request path.
        "suspended": "agent_failed",
    }[outcome.status]


def visible_response(outcome: AgentRunOutcomeV1, deps: AgentDepsV1) -> GroundedResponseV1:
    return outcome.grounded_response or GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=(),
    )


def _response_visible_text(response: GroundedResponseV1) -> str:
    parts: list[str] = []
    for segment in response.segments:
        if isinstance(segment, GroundedProseSegmentV1):
            parts.append(segment.text)
        elif isinstance(segment, GroundedClaimV1) and segment.verdict == "supported":
            parts.append(f"{segment.value} {segment.unit}")
        elif isinstance(segment, GroundedClaimV1):
            parts.append(f"Claim unavailable: {segment.failure}")
    return " ".join(part.strip() for part in parts if part.strip())


def rehydrate_history(activities: tuple[ActivityItemV1, ...]) -> AgentTurnV1:
    """Rebuild bounded owned history from visible persisted activities only.

    Raw framework transcripts and ``AgentTurnV1`` itself remain unpersisted;
    their provenance envelope belongs to Epic 4 (AD-12).
    """
    messages: list[AgentMessageV1] = []
    for activity in activities[-100:]:
        if isinstance(activity, PlannerMessageActivityV1):
            role, text = "user", activity.text
        elif isinstance(activity, AgentResponseActivityV1):
            # A failed or timed-out turn persists a response with no segments,
            # which is truthful -- it produced no visible content. Dropping it
            # here would leave two adjacent user turns in the rehydrated
            # history, which several providers reject outright. This is
            # application-owned text standing in for a turn that produced none;
            # it is never presented as model output.
            role = "assistant"
            text = _response_visible_text(activity.response) or (
                "The previous turn did not complete."
            )
        else:  # defensive for future ActivityItemV1 variants
            raise ValueError(f"unsupported history activity {type(activity).__name__}")
        if text:
            messages.append(
                AgentMessageV1(
                    role=role,
                    parts=(AgentPartV1(kind="text", text=text),),
                )
            )
    return AgentTurnV1(messages=tuple(messages))


__all__ = ["execute_turn", "rehydrate_history", "terminal_status", "visible_response"]
