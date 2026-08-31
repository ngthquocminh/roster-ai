"""Execute and ground one already-claimed planner turn."""
from __future__ import annotations

from dataclasses import replace

from application.contracts.agent_runtime import (
    AgentMessageV1,
    AgentApprovalDecisionV1,
    AgentPartV1,
    AgentRunOutcomeV1,
    AgentTurnRequestV1,
    AgentTurnV1,
)
from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    ClarificationActivityV1,
    DraftActivityV1,
    PlannerMessageActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.grounding import GroundedClaimV1, GroundedProseSegmentV1, GroundedResponseV1
from application.grounding.gate import UncitedNumericProseError, ground_answer
from application.clarification.resolve import resolve_clarification
from application.ports.agent_runtime import AgentRuntime
from application.ports.agent_runtime import AgentProviderError, AgentRuntimeError
from application.capabilities.deps import AgentDepsV1
from application.contracts.capability_manifest import IncompleteManifestError
from application.capabilities.scheduling_draft import SchedulingDraftResultV1
from application.contracts.proposal import ProposalV1


def resolve_draft_citation(
    outcome: AgentRunOutcomeV1, trusted_by_id: dict[str, object]
) -> AgentRunOutcomeV1:
    """Bind the model's `draft_id` citation to a trusted capability result.

    The model never authors a proposal; it cites one. Everything downstream
    renders from `resolved_draft`, which comes from the tool-result sink, so a
    citation naming no captured result is invalid output rather than a draft.

    Extracted from `execute_turn` so the golden dataset can drive this exact
    binding instead of a copy of it -- `evals/report.py` calls it for any case
    whose run produced a draft citation.
    """
    if outcome.draft is None:
        return outcome
    trusted = trusted_by_id.get(outcome.draft.draft_id)
    if not isinstance(trusted, SchedulingDraftResultV1):
        return replace(
            outcome,
            status="failed",
            failure_reason="invalid_output",
            failure_source="agent",
        )
    return replace(outcome, resolved_draft=trusted.proposal)


def execute_turn(
    runtime: AgentRuntime,
    deps: AgentDepsV1,
    *,
    prompt: str,
    calculation_results: list[object],
    history: tuple[ActivityItemV1, ...] | AgentTurnV1 = (),
    approvals: tuple[AgentApprovalDecisionV1, ...] = (),
) -> AgentRunOutcomeV1:
    """Run outside a database transaction, then bind claims to raw tool results."""
    outcome = runtime.run_turn(
        AgentTurnRequestV1(
            prompt=prompt,
            history=history if isinstance(history, AgentTurnV1) else rehydrate_history(history),
            approvals=approvals,
        )
    )
    if outcome.status != "completed":
        return outcome
    if outcome.clarification is not None:
        return replace(
            outcome,
            resolved_clarification=resolve_clarification(outcome.clarification, deps),
        )
    by_id = {
        value.result_id: value
        for value in calculation_results
        if isinstance(getattr(value, "result_id", None), str)
    }
    if outcome.draft is not None:
        return resolve_draft_citation(outcome, by_id)
    if outcome.answer is None:
        return outcome
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
                outcome.resolved_draft,
            )
        ):
            return "agent_completed"
        return "agent_failed"
    return {
        "timed_out": "agent_timed_out",
        "failed": "agent_failed",
        "suspended": "approval_required",
    }[outcome.status]


# Agent-level failure reasons this use case can render as literal planner copy.
# `cancelled` is deliberately ABSENT: no branch in `backend/agent/` emits it, and
# Story 3.4 owns `ScheduleRun` cancellation, not `AgentRun` -- so it had no
# producer and no owner. `test_every_emittable_failure_reason_has_a_terminal_
# mapping` fails if one ever appears, forcing the reason and its branch to land
# together rather than silently rendering as `capability_error`.
_AGENT_TERMINAL_COPY: dict[str, str] = {
    "provider_error": "The provider failed before the turn completed.",
    "invalid_output": "The model returned an invalid response.",
    "budget_exhausted": "The configured agent budget was exhausted.",
}
_CAPABILITY_TERMINAL_COPY = (
    "A governed capability failed without executing an unsupported action."
)

# Bound on untrusted model copy crossing into a persisted payload. Applied to
# BOTH `detail` and `next_step`: bounding one and not the other left arbitrary
# model prose unbounded on the refusal path, which is the only path whose copy
# is model-authored at all.
_MODEL_COPY_LIMIT = 200


def _bounded(text: str | None) -> str | None:
    return text if text is None else text[:_MODEL_COPY_LIMIT]


def terminal_outcome(outcome: AgentRunOutcomeV1) -> TerminalOutcomeV1 | None:
    """Map every non-answer terminal path to literal bounded planner copy."""
    if outcome.status == "completed":
        if outcome.refusal is not None:
            return TerminalOutcomeV1(
                status="completed",
                reason="refused",
                # The model's own closed-vocabulary reason is carried through so
                # the three values are observable. Without this the planner saw
                # one "Refusal" label for all three, which is exactly the
                # "collapse distinct outcomes" EXPERIENCE.md forbids, and made
                # Task 1's AD-3 argument for excluding "unauthorized" moot --
                # there is nothing to leak if nothing is rendered.
                refusal_reason=outcome.refusal.reason,
                detail=_bounded(outcome.refusal.detail) or "",
                next_step=_bounded(outcome.refusal.next_step),
            )
        if outcome.clarification is not None or outcome.resolved_clarification is not None:
            return None
        if outcome.grounded_response is not None:
            return None
        if outcome.resolved_draft is not None:
            return None
        return TerminalOutcomeV1(
            # `terminal_status()` finalises this same outcome as `agent_failed`
            # -- a completed adapter call that produced nothing usable is a
            # failure to the planner. Reporting "completed" here contradicted
            # the row written in the same transaction.
            status="failed",
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
            reason="approval_not_grantable",
            detail="The requested action cannot be approved from this workflow.",
            next_step="Review the candidate and request approval from Results.",
        )

    # Discriminate by SOURCE, never by matching the reason string.
    # `CapabilityFailureReasonV1` is an open `str` and each module declares its
    # own codes, so a manifest code can be spelled identically to an agent-level
    # reason -- `demonstration.py` already declares `budget_exhausted` and
    # `approval_required`. A string test therefore reported "The configured
    # agent budget was exhausted" when a capability had merely hit its own
    # internal limit. `failure_source` is set by whichever layer raised.
    if outcome.failure_source == "capability":
        return TerminalOutcomeV1(
            status="failed",
            reason="capability_error",
            detail=_CAPABILITY_TERMINAL_COPY,
            next_step="Retry the request or review Scenario Data.",
        )
    reason = outcome.failure_reason or "invalid_output"
    terminal_reason = reason if reason in _AGENT_TERMINAL_COPY else "invalid_output"
    return TerminalOutcomeV1(
        status="failed",
        reason=terminal_reason,
        detail=_AGENT_TERMINAL_COPY[terminal_reason],
        next_step="Retry the request or review Scenario Data.",
    )


def failed_outcome_for_exception(exc: Exception) -> AgentRunOutcomeV1:
    """Map known request-path failures by TYPE, never by error-message text.

    `contracts/agent_runtime.py` states the rule for this exact distinction:
    "the adapter maps them by type, never by string-matching an error message."
    An earlier revision tested `"provider call failed" in str(exc)`, so renaming
    that literal in `agent/runtime.py` would have silently reclassified every
    provider outage as `invalid_output` while its test -- which built the string
    itself -- stayed green.
    """
    if isinstance(exc, IncompleteManifestError):
        return AgentRunOutcomeV1(
            status="failed", failure_reason="capability_error", failure_source="capability"
        )
    if isinstance(exc, AgentProviderError):
        return AgentRunOutcomeV1(
            status="failed", failure_reason="provider_error", failure_source="agent"
        )
    # `UncitedNumericProseError` is a `ValueError` subclass, and an unclassified
    # exception is no better understood than a malformed output, so both land on
    # the same honest reason rather than on separate branches that pretend to
    # distinguish them.
    return AgentRunOutcomeV1(
        status="failed", failure_reason="invalid_output", failure_source="agent"
    )


def visible_response(outcome: AgentRunOutcomeV1, deps: AgentDepsV1) -> GroundedResponseV1:
    return outcome.grounded_response or GroundedResponseV1(
        scenario_version_id=deps.scenario_version_id,
        segments=(),
    )


def activity_payload(
    outcome: AgentRunOutcomeV1, deps: AgentDepsV1
) -> GroundedResponseV1 | ResolvedClarificationV1 | ProposalV1 | TerminalOutcomeV1:
    if outcome.resolved_clarification is not None:
        return outcome.resolved_clarification
    if outcome.resolved_draft is not None:
        return outcome.resolved_draft
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
    if outcome.resolved_draft is not None:
        return outcome.resolved_draft.consequence_summary
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
        elif isinstance(activity, DraftActivityV1):
            role, text = "assistant", activity.consequence_summary
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
    "resolve_draft_citation",
    "execute_turn",
    "failed_outcome_for_exception",
    "activity_payload",
    "rehydrate_history",
    "outcome_visible_text",
    "terminal_outcome",
    "terminal_status",
    "visible_response",
]
