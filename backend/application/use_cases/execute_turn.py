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
from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    ClarificationActivityV1,
    PlannerMessageActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.grounding import GroundedClaimV1, GroundedProseSegmentV1, GroundedResponseV1
from application.grounding.gate import UncitedNumericProseError, ground_answer
from application.clarification.resolve import resolve_clarification
from application.ports.agent_runtime import AgentRuntime
from application.ports.agent_runtime import AgentRuntimeError
from application.capabilities.deps import AgentDepsV1
from application.contracts.capability_manifest import IncompleteManifestError


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
    if outcome.status != "completed":
        return outcome
    if outcome.clarification is not None:
        return replace(
            outcome,
            resolved_clarification=resolve_clarification(outcome.clarification, deps),
        )
    if outcome.answer is None:
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
    if outcome.status == "completed":
        if any(
            value is not None
            for value in (
                outcome.grounded_response,
                outcome.clarification,
                outcome.resolved_clarification,
                outcome.refusal,
            )
        ):
            return "agent_completed"
        return "agent_failed"
    if outcome.status == "failed" and outcome.failure_reason == "cancelled":
        return "agent_cancelled"
    return {
        "timed_out": "agent_timed_out",
        "failed": "agent_failed",
        # Epic 4 (AD-10, Stories 4.1-4.3) owns approval resumption. A suspension
        # is still distinct and must never be collapsed into agent_failed.
        "suspended": "approval_required",
    }[outcome.status]


def terminal_outcome(outcome: AgentRunOutcomeV1) -> TerminalOutcomeV1 | None:
    """Map every non-answer terminal path to literal bounded planner copy."""
    if outcome.status == "completed":
        if outcome.refusal is not None:
            return TerminalOutcomeV1(
                status="completed",
                reason="refused",
                detail=outcome.refusal.detail[:200],
                next_step=outcome.refusal.next_step,
            )
        if outcome.clarification is not None or outcome.resolved_clarification is not None:
            return None
        if outcome.grounded_response is not None:
            return None
        return TerminalOutcomeV1(
            status="completed",
            reason="invalid_output",
            detail="The turn completed without a usable response.",
            next_step="Retry the request or review Scenario Data.",
        )
    if outcome.status == "timed_out":
        return TerminalOutcomeV1(
            status="timed_out",
            reason="deadline_exceeded",
            detail="The turn timed out before it completed.",
            next_step="Retry the request or review Scenario Data.",
        )
    if outcome.status == "suspended":
        return TerminalOutcomeV1(
            status="suspended",
            reason="approval_unsupported",
            detail="The turn requires approval that this workflow cannot resume yet.",
            next_step="Review the requested action; approval execution arrives in Epic 4.",
        )

    reason = outcome.failure_reason or "invalid_output"
    terminal_reason = (
        reason
        if reason in {"provider_error", "invalid_output", "budget_exhausted", "cancelled"}
        else "capability_error"
    )
    copy = {
        "provider_error": "The provider failed before the turn completed.",
        "invalid_output": "The model returned an invalid response.",
        "budget_exhausted": "The configured agent budget was exhausted.",
        "cancelled": "The turn was cancelled before it completed.",
        "capability_error": "A governed capability failed without executing an unsupported action.",
    }
    return TerminalOutcomeV1(
        status="failed",
        reason=terminal_reason,
        detail=copy[terminal_reason],
        next_step="Retry the request or review Scenario Data.",
    )


def failed_outcome_for_exception(exc: Exception) -> AgentRunOutcomeV1:
    """Map known request-path failures without importing framework exceptions."""
    if isinstance(exc, IncompleteManifestError):
        reason = "capability_error"
    elif isinstance(exc, AgentRuntimeError) and "provider call failed" in str(exc):
        reason = "provider_error"
    elif isinstance(exc, (AgentRuntimeError, UncitedNumericProseError, ValueError)):
        reason = "invalid_output"
    else:
        reason = "invalid_output"
    return AgentRunOutcomeV1(status="failed", failure_reason=reason)


def visible_response(outcome: AgentRunOutcomeV1, deps: AgentDepsV1) -> GroundedResponseV1:
    return outcome.grounded_response or GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=(),
    )


def activity_payload(
    outcome: AgentRunOutcomeV1, deps: AgentDepsV1
) -> GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1:
    if outcome.resolved_clarification is not None:
        return outcome.resolved_clarification
    terminal = terminal_outcome(outcome)
    if terminal is not None:
        return terminal
    return visible_response(outcome, deps)


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


def outcome_visible_text(outcome: AgentRunOutcomeV1) -> str:
    """Single planner-visible text projection shared by runtime and evaluation."""
    if outcome.grounded_response is not None:
        return _response_visible_text(outcome.grounded_response)
    if outcome.resolved_clarification is not None:
        return outcome.resolved_clarification.question
    if outcome.clarification is not None:
        return outcome.clarification.question
    if outcome.refusal is not None:
        return outcome.refusal.detail
    return outcome.output_text or ""


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
        elif isinstance(activity, ClarificationActivityV1):
            role, text = "assistant", activity.clarification.question
        elif isinstance(activity, TerminalOutcomeActivityV1):
            role = "assistant"
            text = f"The previous turn did not complete: {activity.outcome.reason}."
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


__all__ = [
    "execute_turn",
    "failed_outcome_for_exception",
    "activity_payload",
    "rehydrate_history",
    "outcome_visible_text",
    "terminal_outcome",
    "terminal_status",
    "visible_response",
]
