from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from typing import get_args
from uuid import uuid4

import pytest

from application.contracts.activity import (
    ActivityTypeV1,
    AgentResponseActivityV1,
    PlannerMessageActivityV1,
)
from application.contracts.grounding import (
    ClaimArgumentsV1,
    GroundedClaimV1,
    GroundedResponseV1,
)
from application.contracts.persisted_event import PersistedEventV1
from api.main import app
from api.schemas import AcceptedTurnOut, PlannerMessageActivityOut
from adapters.postgres.conversation import _activity_from_payload, _payload_to_json
from api.routers.conversations import _activity


def test_activity_discriminant_is_the_closed_eight_value_vocabulary() -> None:
    assert get_args(ActivityTypeV1) == (
        "planner_message",
        "agent_response",
        "clarification",
        "draft",
        "run_progress",
        "comparison",
        "approval_request",
        "terminal_outcome",
    )


def test_persisted_event_requires_one_typed_frozen_payload() -> None:
    now = datetime.now(timezone.utc)
    activity = PlannerMessageActivityV1(
        activity_id=uuid4(),
        activity_type="planner_message",
        conversation_id=uuid4(),
        conversation_resource_version=2,
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        occurred_at=now,
        message_id=uuid4(),
        text="Investigate this fixture",
    )
    event = PersistedEventV1(
        stream_id=activity.conversation_id,
        sequence=Decimal("1"),
        event_type="planner_message_accepted",
        occurred_at=now,
        resource_version=2,
        request_id=uuid4(),
        conversation_id=activity.conversation_id,
        agent_run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=activity,
    )

    assert event.schema_version == "1"
    assert event.payload is activity
    with pytest.raises(FrozenInstanceError):
        event.sequence = Decimal("2")  # type: ignore[misc]
    with pytest.raises(TypeError):
        PersistedEventV1(  # type: ignore[call-arg]
            stream_id=uuid4(),
            sequence=Decimal("1"),
            event_type="planner_message_accepted",
            occurred_at=now,
            resource_version=2,
            request_id=uuid4(),
            conversation_id=uuid4(),
            agent_run_id=uuid4(),
            site_id=uuid4(),
            actor_id=uuid4(),
        )


def test_sequence_is_serialized_as_a_json_string_and_routes_are_peer_resources() -> None:
    now = datetime.now(timezone.utc)
    activity = PlannerMessageActivityOut(
        schema_version="1", activity_id=uuid4(), activity_type="planner_message",
        conversation_id=uuid4(), conversation_resource_version=2,
        scenario_id=uuid4(), scenario_version_id=uuid4(), occurred_at=now,
        message_id=uuid4(), text="Inspect", sequence="9007199254740993",
    )
    body = AcceptedTurnOut(
        activity=activity,
        resource_version=2,
        agent_run_status="agent_queued",
        sequence="9007199254740993",
        agent_run_id=uuid4(),
    ).model_dump_json()
    assert '"sequence":"9007199254740993"' in body
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/conversations"]) >= {"get", "post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/messages"]) >= {"post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/timeline"]) >= {"get"}
    assert not any(path.startswith("/api/v1/scenarios") and "post" in methods for path, methods in paths.items())


def test_agent_response_activity_carries_a_discriminated_grounded_response() -> None:
    response = GroundedResponseV1(
        scenario_version_id=uuid4(),
        segments=(
            GroundedClaimV1(
                metric="staffed_minutes",
                arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
                result_id="result-1", value=60, unit="minutes",
                verdict="supported", evidence_refs=(),
            ),
        ),
    )
    activity = AgentResponseActivityV1(
        activity_id=uuid4(), activity_type="agent_response",
        conversation_id=uuid4(), conversation_resource_version=3,
        scenario_id=uuid4(), scenario_version_id=response.scenario_version_id,
        occurred_at=datetime.now(timezone.utc), response=response,
    )
    assert activity.response.claims[0].value == 60
    assert activity.activity_type == "agent_response"

    raw = _payload_to_json(activity)
    restored = _activity_from_payload(raw)
    event = PersistedEventV1(
        stream_id=activity.conversation_id, sequence=Decimal("2"),
        event_type="agent_response", occurred_at=activity.occurred_at,
        resource_version=3, request_id=uuid4(),
        conversation_id=activity.conversation_id, agent_run_id=uuid4(),
        site_id=uuid4(), actor_id=uuid4(), payload=restored,
    )
    transport = _activity(event)
    assert transport.activity_type == "agent_response"
    assert transport.sequence == "2"
    assert transport.response.claims[0].value == 60
