from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest

from agent.translate import to_framework_messages
from application.capabilities.deps import AgentDepsV1
from application.contracts.activity import (
    AgentResponseActivityV1,
    ClarificationActivityV1,
    DraftActivityV1,
    PlannerMessageActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.agent_runtime import (
    AgentBudgetV1,
    AgentMessageRoleV1,
    AgentMessageV1,
    AgentPartKindV1,
    AgentPartV1,
    AgentRunOutcomeV1,
    AgentTurnV1,
)
from application.contracts.grounding import (
    GroundedAnswerV1,
    GroundedClaimV1,
    GroundedProseSegmentV1,
    GroundedResponseV1,
)
from application.contracts.dialogue import ClarificationV1, EntityCandidateProposalV1
from application.contracts.dialogue import RefusalV1, ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.scenario_projection import WorkerV1
from application.capabilities.scheduling_draft import SchedulingDraftResultV1
from application.contracts.proposal import DraftProposalV1, ProposalV1
from application.use_cases.execute_turn import (
    activity_payload,
    execute_turn,
    outcome_visible_text,
    rehydrate_history,
    terminal_outcome,
    terminal_status,
)

NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


class _Runtime:
    name = "capture"

    def run_turn(self, request):
        self.request = request
        return AgentRunOutcomeV1(
            status="completed",
            answer=GroundedAnswerV1(
                segments=(GroundedProseSegmentV1(text="Current answer."),)
            ),
        )


def _deps() -> AgentDepsV1:
    ids = [UUID(int=value) for value in range(1, 9)]
    return AgentDepsV1(
        actor_id=ids[0], site_id=ids[1], membership_id=ids[2], request_id=ids[3],
        agent_run_id=ids[4], conversation_id=ids[5], scenario_id=ids[6],
        scenario_version_id=ids[7], policy_version="v1", clock=lambda: NOW,
        projection_reader=object(), connection=None, remaining_budget=AgentBudgetV1(),
    )


def test_execute_turn_rehydrates_visible_bounded_owned_history() -> None:
    deps = _deps()
    common = dict(
        conversation_id=deps.conversation_id,
        conversation_resource_version=2,
        scenario_id=deps.scenario_id,
        scenario_version_id=deps.scenario_version_id,
        occurred_at=NOW,
    )
    prior_user = PlannerMessageActivityV1(
        activity_id=UUID(int=20), activity_type="planner_message",
        message_id=UUID(int=21), text="Earlier question", **common,
    )
    prior_agent = AgentResponseActivityV1(
        activity_id=UUID(int=22), activity_type="agent_response",
        response=GroundedResponseV1(
            scenario_version_id=deps.scenario_version_id,
            segments=(
                GroundedProseSegmentV1(text="Earlier answer."),
                GroundedClaimV1(value=45, unit="minutes", verdict="supported"),
            ),
        ),
        **common,
    )
    runtime = _Runtime()

    execute_turn(
        runtime,
        deps,
        prompt="Follow-up question",
        calculation_results=[],
        history=(prior_user, prior_agent),
    )

    messages = runtime.request.history.messages
    assert [(message.role, message.parts[0].text) for message in messages] == [
        ("user", "Earlier question"),
        ("assistant", "Earlier answer. 45 minutes"),
    ]
    assert all("Follow-up question" not in (part.text or "") for message in messages for part in message.parts)


def test_rehydrated_history_is_capped_at_one_hundred_activities() -> None:
    deps = _deps()
    activities = tuple(
        PlannerMessageActivityV1(
            activity_id=UUID(int=1000 + index), activity_type="planner_message",
            conversation_id=deps.conversation_id, conversation_resource_version=index + 1,
            scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
            occurred_at=NOW, message_id=UUID(int=2000 + index), text=f"m{index}",
        )
        for index in range(120)
    )
    runtime = _Runtime()
    execute_turn(runtime, deps, prompt="now", calculation_results=[], history=activities)
    assert len(runtime.request.history.messages) == 100
    assert runtime.request.history.messages[0].parts[0].text == "m20"


def test_execute_turn_resolves_clarification_at_the_use_case_boundary() -> None:
    deps = _deps()
    worker = WorkerV1(
        "worker-record", "CONTACT-9", "Taylor", "casual", "1", "EBA", 8.0, (), ()
    )

    class Reader:
        def resolve_worker(self, _connection, scenario_id, version_id, record_id):
            assert (scenario_id, version_id, record_id) == (
                deps.scenario_id,
                deps.scenario_version_id,
                "worker-record",
            )
            return type(
                "Resolution",
                (),
                {
                    "outcome": "resolved",
                    "current_scenario_version_id": deps.scenario_version_id,
                    "item": worker,
                },
            )()

    deps = AgentDepsV1(**{**deps.__dict__, "projection_reader": Reader()})

    class ClarifyingRuntime:
        name = "clarifying"

        def run_turn(self, _request):
            return AgentRunOutcomeV1(
                clarification=ClarificationV1(
                    question="Which worker?",
                    candidates=(
                        EntityCandidateProposalV1(
                            group="workers", record_id="worker-record"
                        ),
                    ),
                )
            )

    outcome = execute_turn(
        ClarifyingRuntime(), deps, prompt="Move Taylor", calculation_results=[]
    )

    assert outcome.clarification is not None
    assert outcome.resolved_clarification is not None
    assert outcome.resolved_clarification.candidates[0].label == "Taylor (CONTACT-9)"


def _proposal(deps: AgentDepsV1) -> ProposalV1:
    return ProposalV1(
        proposal_id=UUID(int=40), proposal_version_id=UUID(int=41),
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
        consequence_summary="Two reversible constraints; no baseline change.",
        canonical_hash="draft-123",
    )


def test_execute_turn_binds_a_model_draft_citation_to_this_turns_trusted_result() -> None:
    deps = _deps()
    proposal = _proposal(deps)

    class DraftRuntime:
        name = "draft"

        def run_turn(self, _request):
            return AgentRunOutcomeV1(draft=DraftProposalV1(draft_id="draft-123"))

    outcome = execute_turn(
        DraftRuntime(), deps, prompt="Draft it",
        calculation_results=(SchedulingDraftResultV1("draft-123", proposal),),
    )

    assert outcome.resolved_draft is proposal
    assert terminal_status(outcome) == "agent_completed"
    assert terminal_outcome(outcome) is None
    assert activity_payload(outcome, deps) is proposal
    assert outcome_visible_text(outcome) == proposal.consequence_summary


def test_a_draft_citation_without_a_trusted_result_fails_closed() -> None:
    deps = _deps()

    class DraftRuntime:
        name = "draft"

        def run_turn(self, _request):
            return AgentRunOutcomeV1(draft=DraftProposalV1(draft_id="missing"))

    outcome = execute_turn(
        DraftRuntime(), deps, prompt="Draft it", calculation_results=(),
    )

    assert outcome.status == "failed"
    assert outcome.failure_reason == "invalid_output"
    assert outcome.resolved_draft is None


@pytest.mark.parametrize(
    ("outcome", "status", "reason"),
    [
        (AgentRunOutcomeV1(status="timed_out"), "agent_timed_out", "deadline_exceeded"),
        (
            AgentRunOutcomeV1(status="failed", failure_reason="budget_exhausted"),
            "agent_failed",
            "budget_exhausted",
        ),
        (
            AgentRunOutcomeV1(status="failed", failure_reason="provider_error"),
            "agent_failed",
            "provider_error",
        ),
        (
            AgentRunOutcomeV1(status="failed", failure_reason="invalid_output"),
            "agent_failed",
            "invalid_output",
        ),
        (
            AgentRunOutcomeV1(
                status="failed",
                failure_reason="tool_declared_error",
                failure_source="capability",
            ),
            "agent_failed",
            "capability_error",
        ),
        # A manifest code spelled exactly like an agent-level reason. The
        # source tag -- not the string -- decides, so this must NOT render as
        # "The configured agent budget was exhausted".
        (
            AgentRunOutcomeV1(
                status="failed",
                failure_reason="budget_exhausted",
                failure_source="capability",
            ),
            "agent_failed",
            "capability_error",
        ),
        # A suspension is terminal here: it lands on AD-7's own
        # `approval_required --> agent_cancelled: rejected or expired` edge
        # rather than parking the row in a waiting state nothing can leave.
        (
            AgentRunOutcomeV1(status="suspended"),
            "agent_cancelled",
            "approval_unsupported",
        ),
        (
            AgentRunOutcomeV1(
                refusal=RefusalV1(
                    reason="unsupported_request",
                    detail="That request is not supported.",
                    next_step="Review Scenario Data.",
                )
            ),
            "agent_completed",
            "refused",
        ),
    ],
)
def test_terminal_taxonomy_keeps_every_reachable_reason_distinct(
    outcome: AgentRunOutcomeV1, status: str, reason: str
) -> None:
    assert terminal_status(outcome) == status
    terminal = terminal_outcome(outcome)
    assert terminal is not None
    assert terminal.reason == reason
    assert terminal.detail
    assert len(terminal.detail) <= 200


# Values `AgentFailureReasonV1` declares that NO branch in `backend/agent/`
# emits today. Each needs an owner, not merely a mention: a declared-but-
# unemittable reason is the "declared and entirely unimplemented" shape
# `deferred-work.md:7` records.
UNEMITTED_AGENT_FAILURE_REASONS = {
    "cancelled": (
        "AgentRun cancellation has AD-7 edges (`agent_queued`/`agent_running` "
        "--> `agent_cancelled`) but no assigned story. Story 3.4 is ScheduleRun "
        "cancellation, not AgentRun. Whoever makes the adapter emit this must "
        "add the TerminalReasonV1 value and its named branch in the same change."
    ),
}


def test_every_emittable_failure_reason_has_a_terminal_mapping() -> None:
    """The executable form of Task 4's "each value must be reachable" rule.

    Bidirectional on purpose. If a reason becomes emittable it must gain a
    terminal mapping in the same change, or it silently renders as
    `capability_error`. If a reason stops being emittable, the exemption
    registry must say so with an owner rather than leaving dead vocabulary.
    """
    from pathlib import Path
    from typing import get_args

    from application.contracts.agent_runtime import AgentFailureReasonV1
    from application.contracts.dialogue import TerminalReasonV1
    from application.use_cases.execute_turn import _AGENT_TERMINAL_COPY

    # Both producers: the adapter sets some reasons directly, and the use case
    # sets others when translating a typed exception from the request path.
    # Scanning only one of the two would report a live reason as unemittable.
    backend = Path(__file__).resolve().parents[1]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            *sorted((backend / "agent").glob("*.py")),
            backend / "application" / "use_cases" / "execute_turn.py",
        )
    )

    emittable = {
        reason
        for reason in get_args(AgentFailureReasonV1)
        if f'failure_reason="{reason}"' in source
    }
    unemitted = set(get_args(AgentFailureReasonV1)) - emittable

    assert unemitted == set(UNEMITTED_AGENT_FAILURE_REASONS), (
        "A failure reason changed emittability. Update the exemption registry "
        "and the terminal taxonomy together — an unmapped emittable reason "
        "renders as `capability_error` and misreports the cause to the planner."
    )
    unmapped = emittable - set(_AGENT_TERMINAL_COPY)
    assert not unmapped, f"emittable with no terminal mapping: {sorted(unmapped)}"
    # Nothing exempted may still be in the rendered vocabulary.
    assert not set(UNEMITTED_AGENT_FAILURE_REASONS) & set(get_args(TerminalReasonV1))


def test_clarification_is_completed_without_becoming_a_terminal_failure() -> None:
    outcome = AgentRunOutcomeV1(
        clarification=ClarificationV1(question="Which worker?")
    )
    assert terminal_status(outcome) == "agent_completed"
    assert terminal_outcome(outcome) is None


def test_new_activity_variants_rehydrate_as_application_owned_assistant_text() -> None:
    deps = _deps()
    common = dict(
        conversation_id=deps.conversation_id,
        conversation_resource_version=2,
        scenario_id=deps.scenario_id,
        scenario_version_id=deps.scenario_version_id,
        occurred_at=NOW,
    )
    clarification = ClarificationActivityV1(
        activity_id=UUID(int=30),
        activity_type="clarification",
        clarification=ResolvedClarificationV1(
            question="Which worker?", scenario_version_id=deps.scenario_version_id
        ),
        **common,
    )
    terminal = TerminalOutcomeActivityV1(
        activity_id=UUID(int=31),
        activity_type="terminal_outcome",
        outcome=TerminalOutcomeV1(
            status="failed",
            reason="provider_error",
            detail="The provider failed.",
        ),
        **common,
    )
    draft = DraftActivityV1(
        activity_id=UUID(int=32), activity_type="draft",
        proposal_id=UUID(int=40), proposal_version_id=UUID(int=41),
        consequence_summary="Two reversible constraints; no baseline change.",
        **common,
    )

    history = rehydrate_history((clarification, draft, terminal))

    assert [message.parts[0].text for message in history.messages] == [
        "Which worker?",
        "Two reversible constraints; no baseline change.",
        "The previous turn did not complete: provider_error.",
    ]


def test_a_second_turn_after_a_draft_rehydrates_without_losing_the_conversation() -> None:
    deps = _deps()
    draft = DraftActivityV1(
        activity_id=UUID(int=50), activity_type="draft",
        conversation_id=deps.conversation_id, conversation_resource_version=3,
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
        occurred_at=NOW, proposal_id=UUID(int=51), proposal_version_id=UUID(int=52),
        consequence_summary="One reversible constraint; no baseline change.",
    )
    runtime = _Runtime()

    execute_turn(
        runtime, deps, prompt="Now revise it", calculation_results=[], history=(draft,),
    )

    assert runtime.request.history.messages[0].parts[0].text == (
        "One reversible constraint; no baseline change."
    )


@pytest.mark.parametrize(
    "turn",
    [
        AgentTurnV1(messages=(AgentMessageV1(role=cast(AgentMessageRoleV1, "future")),)),
        AgentTurnV1(messages=(AgentMessageV1(role="assistant", parts=(AgentPartV1(kind=cast(AgentPartKindV1, "future")),)),)),
    ],
)
def test_framework_rehydration_rejects_unknown_owned_discriminants(turn) -> None:
    with pytest.raises(ValueError):
        to_framework_messages(turn)
