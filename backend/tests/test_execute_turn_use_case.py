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
from application.use_cases.execute_turn import (
    execute_turn,
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
    assert outcome.resolved_clarification.candidates[0].label == "CONTACT-9"


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
            AgentRunOutcomeV1(status="failed", failure_reason="cancelled"),
            "agent_cancelled",
            "cancelled",
        ),
        (
            AgentRunOutcomeV1(status="failed", failure_reason="tool_declared_error"),
            "agent_failed",
            "capability_error",
        ),
        (
            AgentRunOutcomeV1(status="suspended"),
            "approval_required",
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

    history = rehydrate_history((clarification, terminal))

    assert [message.parts[0].text for message in history.messages] == [
        "Which worker?",
        "The previous turn did not complete: provider_error.",
    ]


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
