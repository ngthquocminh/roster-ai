from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest

from agent.translate import to_framework_messages
from application.capabilities.deps import AgentDepsV1
from application.contracts.activity import AgentResponseActivityV1, PlannerMessageActivityV1
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
from application.use_cases.execute_turn import execute_turn

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
