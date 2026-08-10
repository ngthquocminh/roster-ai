from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from typing import get_args
from uuid import uuid4

import pytest

from application.contracts.activity import ActivityItemV1, ActivityTypeV1
from application.contracts.persisted_event import PersistedEventV1
from api.main import app
from api.schemas import AcceptedTurnOut, ActivityItemOut


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
    activity = ActivityItemV1(
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
    activity = ActivityItemOut(
        schema_version="1", activity_id=uuid4(), activity_type="planner_message",
        conversation_id=uuid4(), conversation_resource_version=2,
        scenario_id=uuid4(), scenario_version_id=uuid4(), occurred_at=now,
        message_id=uuid4(), text="Inspect",
    )
    body = AcceptedTurnOut(activity=activity, resource_version=2, agent_run_status="agent_queued", sequence="9007199254740993").model_dump_json()
    assert '"sequence":"9007199254740993"' in body
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/conversations"]) >= {"get", "post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/messages"]) >= {"post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/timeline"]) >= {"get"}
    assert not any(path.startswith("/api/v1/scenarios") and "post" in methods for path, methods in paths.items())
