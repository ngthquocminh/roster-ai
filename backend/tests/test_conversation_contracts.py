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
    ApprovalRequestActivityV1,
    ClarificationActivityV1,
    DraftActivityV1,
    PlannerMessageActivityV1,
    RunProgressActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.dialogue import (
    EntityCandidateV1,
    ResolvedClarificationV1,
    TerminalOutcomeV1,
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


def test_persisted_event_supports_a_schedule_run_owned_stream() -> None:
    now = datetime.now(timezone.utc)
    schedule_run_id = uuid4()
    event = PersistedEventV1(
        stream_id=schedule_run_id,
        sequence=Decimal("1"),
        event_type="run.queued.v1",
        occurred_at=now,
        resource_version=1,
        request_id=uuid4(),
        conversation_id=None,
        agent_run_id=None,
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=PlannerMessageActivityV1(
            activity_id=uuid4(),
            activity_type="planner_message",
            conversation_id=uuid4(),
            conversation_resource_version=1,
            scenario_id=uuid4(),
            scenario_version_id=uuid4(),
            occurred_at=now,
            message_id=uuid4(),
            text="placeholder until Task 2 adds run_progress",
        ),
        schedule_run_id=schedule_run_id,
    )

    assert event.conversation_id is None
    assert event.agent_run_id is None
    assert event.schedule_run_id == schedule_run_id


def test_run_progress_activity_round_trips_to_the_discriminated_api_shape() -> None:
    now = datetime.now(timezone.utc)
    schedule_run_id = uuid4()
    activity = RunProgressActivityV1(
        activity_id=uuid4(),
        activity_type="run_progress",
        schedule_run_id=schedule_run_id,
        status="solver_running",
        reason=None,
        resource_version=2,
        occurred_at=now,
    )
    event = PersistedEventV1(
        stream_id=schedule_run_id,
        sequence=Decimal("2"),
        event_type="run.running.v1",
        occurred_at=now,
        resource_version=2,
        request_id=uuid4(),
        conversation_id=None,
        agent_run_id=None,
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=activity,
        schedule_run_id=schedule_run_id,
    )

    transport = _activity(event)
    assert transport.activity_type == "run_progress"
    assert transport.schedule_run_id == schedule_run_id
    assert transport.status == "solver_running"
    assert transport.resource_version == 2
    assert transport.sequence == "2"
    with pytest.raises(FrozenInstanceError):
        activity.status = "solver_completed"  # type: ignore[misc]


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


@pytest.mark.parametrize("kind", ["clarification", "terminal_outcome"])
def test_new_activity_payloads_round_trip_through_storage_and_transport(kind: str) -> None:
    now = datetime.now(timezone.utc)
    version_id = uuid4()
    common = dict(
        activity_id=uuid4(),
        conversation_id=uuid4(),
        conversation_resource_version=3,
        scenario_id=uuid4(),
        scenario_version_id=version_id,
        occurred_at=now,
    )
    if kind == "clarification":
        activity = ClarificationActivityV1(
            activity_type="clarification",
            clarification=ResolvedClarificationV1(
                question="Which worker?",
                candidates=(
                    EntityCandidateV1(
                        group="workers",
                        record_id="worker-1",
                        label="CONTACT-9",
                        scenario_version_id=version_id,
                    ),
                ),
                scenario_version_id=version_id,
            ),
            **common,
        )
    else:
        activity = TerminalOutcomeActivityV1(
            activity_type="terminal_outcome",
            outcome=TerminalOutcomeV1(
                status="failed",
                reason="provider_error",
                detail="The provider failed before the turn completed.",
                next_step="Retry the request.",
            ),
            **common,
        )

    restored = _activity_from_payload(_payload_to_json(activity))
    event = PersistedEventV1(
        stream_id=activity.conversation_id,
        sequence=Decimal("3"),
        event_type=kind,
        occurred_at=now,
        resource_version=3,
        request_id=uuid4(),
        conversation_id=activity.conversation_id,
        agent_run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=restored,
    )

    transport = _activity(event)
    assert transport.activity_type == kind
    assert transport.sequence == "3"
    if kind == "clarification":
        assert transport.clarification.candidates[0].label == "CONTACT-9"
    else:
        assert transport.outcome.reason == "provider_error"


def test_draft_activity_round_trips_through_storage_without_embedding_proposal() -> None:
    activity = DraftActivityV1(
        activity_id=uuid4(),
        activity_type="draft",
        conversation_id=uuid4(),
        conversation_resource_version=4,
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        consequence_summary="Adds one worker to task PICK during the outbound window.",
    )

    raw = _payload_to_json(activity)
    restored = _activity_from_payload(raw)

    assert restored == activity
    assert raw["activity_type"] == "draft"
    assert raw["proposal_id"] == str(activity.proposal_id)
    assert raw["proposal_version_id"] == str(activity.proposal_version_id)
    assert "constraints" not in raw


def test_approval_request_activity_round_trips_through_storage() -> None:
    activity = ApprovalRequestActivityV1(
        activity_id=uuid4(), activity_type="approval_request", conversation_id=uuid4(),
        conversation_resource_version=4, scenario_id=uuid4(), scenario_version_id=uuid4(),
        occurred_at=datetime.now(timezone.utc), approval_id=uuid4(), approval_state="pending",
        agent_run_id=uuid4(), schedule_run_id=uuid4(), candidate_schedule_version_id=uuid4(),
        baseline_schedule_version=None, consequence_summary="Candidate version is ready for approval.",
        parameter_hash="a" * 64, consequence_hash="b" * 64, policy_version="one-user-mvp-v1+0123456789ab",
        expires_at=datetime.now(timezone.utc),
    )
    assert _activity_from_payload(_payload_to_json(activity)) == activity
