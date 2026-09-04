"""HTTP contracts for the durable-conversation write surface.

The repository is substituted through `dependency_overrides` so these tests
exercise the transport — routing, session, CSRF, status codes, and the RFC 7807
shapes — rather than PostgreSQL. `test_conversations_postgres.py` owns the
governed-storage side.
"""
from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_agent_runtime_factory,
    get_capability_registry,
    get_conversation_repository,
    get_identity_store,
    get_settings,
    get_site_context,
    get_site_context_opener,
    get_projection_reader,
    get_telemetry_sink,
)
from api.main import app
from application.contracts.activity import (
    AgentResponseActivityV1,
    ClarificationActivityV1,
    PlannerMessageActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.dialogue import ClarificationV1, RefusalV1
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1, GroundedResponseV1
from application.contracts.persisted_event import PersistedEventV1
from application.ports.conversation import (
    AcceptedTurnV1,
    ClaimedAgentRunV1,
    ConversationPageV1,
    ConversationTimelineV1,
    ConversationV1,
    ExecutedAgentRunV1,
)
from application.ports.conversation import AgentRunNotQueuedError
from application.ports.session import ResolvedSession
from application.ports.agent_runtime import AgentRuntimeError
from settings import default_settings

_CSRF_TOKEN = "csrf-token-value"
_SESSION_TOKEN = "opaque-session"
_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

_NOT_FOUND_BODY = {
    "type": "https://shiftmind.app/problems/resource_not_found",
    "title": "Resource not found",
    "status": 404,
    "detail": "The requested resource was not found.",
    "code": "resource_not_found",
}


class _IdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self.session = session

    def resolve_session(self, _token_hash: str) -> ResolvedSession:
        return self.session


def _event(conversation_id: UUID, scenario_id: UUID, version_id: UUID, sequence: str) -> PersistedEventV1:
    activity_id = uuid4()
    return PersistedEventV1(
        stream_id=conversation_id,
        sequence=Decimal(sequence),
        event_type="planner_message_accepted",
        occurred_at=_NOW,
        resource_version=2,
        request_id=uuid4(),
        conversation_id=conversation_id,
        agent_run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        payload=PlannerMessageActivityV1(
            activity_id=activity_id,
            activity_type="planner_message",
            conversation_id=conversation_id,
            conversation_resource_version=2,
            scenario_id=scenario_id,
            scenario_version_id=version_id,
            occurred_at=_NOW,
            message_id=uuid4(),
            text="Check Tuesday night coverage",
        ),
    )


class _Repository:
    """Accepts exactly one known (scenario, version, conversation) triple.

    Everything else returns None, which is how the router is told to produce the
    single non-disclosing 404 — an unknown id and a foreign site are the same
    answer here by construction.
    """

    def __init__(self, scenario_id: UUID, version_id: UUID, conversation_id: UUID) -> None:
        self.scenario_id = scenario_id
        self.version_id = version_id
        self.conversation_id = conversation_id
        self.accepted: list[str] = []
        self.timeline_has_more = False
        self.claimed_statuses: list[str] = []
        self.finished_events: list[PersistedEventV1] = []
        self.raise_not_queued_on_claim = False

    def _conversation(self) -> ConversationV1:
        return ConversationV1(self.conversation_id, self.scenario_id, self.version_id, 2)

    def create(self, _connection, *, scenario_id, scenario_version_id, site_id, actor_id):
        if scenario_id != self.scenario_id or scenario_version_id != self.version_id:
            return None
        return self._conversation()

    def list_for_scenario(self, _connection, *, scenario_id, limit=100):
        if scenario_id != self.scenario_id:
            return ConversationPageV1((), limit, False)
        return ConversationPageV1((self._conversation(),), limit, False)

    def timeline(self, _connection, *, conversation_id, limit=200):
        if conversation_id != self.conversation_id:
            return None
        return ConversationTimelineV1(
            conversation_id,
            2,
            "agent_queued",
            (
                _event(conversation_id, self.scenario_id, self.version_id, "1"),
                *self.finished_events,
            ),
            limit,
            self.timeline_has_more,
        )

    def accept_turn(self, _connection, *, conversation_id, site_id, actor_id, text, request_id):
        if conversation_id != self.conversation_id:
            return None
        self.accepted.append(text)
        return AcceptedTurnV1(
            _event(conversation_id, self.scenario_id, self.version_id, "9007199254740993"),
            2,
            "agent_queued",
        )

    def claim_queued_run(self, _connection, *, conversation_id, agent_run_id):
        if conversation_id != self.conversation_id:
            return None
        if self.raise_not_queued_on_claim:
            raise AgentRunNotQueuedError("agent run is not queued")
        self._run_id = agent_run_id
        return ClaimedAgentRunV1(
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            scenario_id=self.scenario_id,
            scenario_version_id=self.version_id,
            site_id=self.site_id,
            actor_id=self.actor_id,
            membership_id=uuid4(),
            prompt="Check coverage",
        )

    def finish_agent_run(self, _connection, *, claimed, status, payload, request_id):
        self.claimed_statuses.append(status)
        activity_id = uuid4()
        common = dict(
            activity_id=activity_id,
            conversation_id=claimed.conversation_id,
            conversation_resource_version=3,
            scenario_id=claimed.scenario_id,
            scenario_version_id=claimed.scenario_version_id,
            occurred_at=_NOW,
        )
        if isinstance(payload, GroundedResponseV1):
            activity = AgentResponseActivityV1(
                activity_type="agent_response", response=payload, **common
            )
        elif isinstance(payload, ResolvedClarificationV1):
            activity = ClarificationActivityV1(
                activity_type="clarification", clarification=payload, **common
            )
        elif isinstance(payload, TerminalOutcomeV1):
            activity = TerminalOutcomeActivityV1(
                activity_type="terminal_outcome", outcome=payload, **common
            )
        else:
            raise AssertionError(type(payload))
        event = PersistedEventV1(
            stream_id=claimed.conversation_id,
            sequence=Decimal(2),
            event_type=activity.activity_type,
            occurred_at=_NOW,
            resource_version=3,
            request_id=request_id,
            conversation_id=claimed.conversation_id,
            agent_run_id=claimed.agent_run_id,
            site_id=claimed.site_id,
            actor_id=claimed.actor_id,
            payload=activity,
        )
        self.finished_events.append(event)
        return ExecutedAgentRunV1(event, 3, status)


class _Runtime:
    name = "test"

    def run_turn(self, request):
        return AgentRunOutcomeV1(
            status="completed",
            answer=GroundedAnswerV1(
                segments=(GroundedProseSegmentV1(text="Coverage checked."),)
            ),
        )


class _ClarifyingRuntime:
    name = "test-clarification"

    def run_turn(self, _request):
        return AgentRunOutcomeV1(
            clarification=ClarificationV1(question="Which time window?")
        )


class _RefusingRuntime:
    name = "test-refusal"

    def run_turn(self, _request):
        return AgentRunOutcomeV1(
            refusal=RefusalV1(
                reason="capability_unavailable",
                detail="That capability is unavailable.",
                next_step="Review Scenario Data.",
            )
        )


class _FailingRuntime:
    name = "test"

    def run_turn(self, request):
        raise AgentRuntimeError("provider unavailable")


class _NumericProseRuntime:
    """Answers with a bare numeral in prose, which the gate refuses."""

    name = "test"

    def run_turn(self, request):
        return AgentRunOutcomeV1(
            status="completed",
            answer=GroundedAnswerV1(
                segments=(GroundedProseSegmentV1(text="You are short by 2 hours."),)
            ),
        )


@contextmanager
def _open_context(_site_id):
    yield object()


@pytest.fixture()
def conversation_client(tmp_path):
    scenario_id, version_id, conversation_id = uuid4(), uuid4(), uuid4()
    repository = _Repository(scenario_id, version_id, conversation_id)
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repository.site_id = resolved.site_id
    repository.actor_id = resolved.app_user_id
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(resolved)
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_conversation_repository] = lambda: repository
    app.dependency_overrides[get_site_context_opener] = lambda: _open_context
    app.dependency_overrides[get_capability_registry] = lambda: (lambda _context: ())
    app.dependency_overrides[get_projection_reader] = lambda: object()
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: _Runtime()
    )
    try:
        with TestClient(app) as client:
            yield client, repository, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _headers(settings, *, csrf: bool = True) -> dict[str, str]:
    headers = {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
    }
    if csrf:
        headers["X-CSRF-Token"] = _CSRF_TOKEN
    return headers


def test_creating_a_conversation_pins_the_version_the_client_selected(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        "/api/v1/conversations",
        headers=_headers(settings),
        json={
            "scenario_id": str(repository.scenario_id),
            "scenario_version_id": str(repository.version_id),
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(repository.conversation_id),
        "scenario_id": str(repository.scenario_id),
        "scenario_version_id": str(repository.version_id),
        "resource_version": 2,
    }


def test_a_version_that_is_not_the_scenarios_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    """A foreign or unknown version must not be distinguishable from a foreign
    or unknown scenario — the whole point of resolving by identity is that the
    server never silently substitutes a different one."""
    client, repository, settings = conversation_client

    response = client.post(
        "/api/v1/conversations",
        headers=_headers(settings),
        json={
            "scenario_id": str(repository.scenario_id),
            "scenario_version_id": str(uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_post_without_a_csrf_header_is_rejected_before_the_repository(
    conversation_client,
) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings, csrf=False),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_validation_failed"
    assert repository.accepted == []


def test_post_without_a_session_is_rejected_before_the_repository(
    conversation_client,
) -> None:
    client, repository, _ = conversation_client

    response = client.post(
        "/api/v1/conversations",
        json={"scenario_id": str(repository.scenario_id), "scenario_version_id": str(repository.version_id)},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_accepted_turn_serializes_sequence_as_a_lossless_string(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 201
    body = response.json()
    # Beyond float precision: a JSON number here would round-trip wrong in the
    # browser and break AD-21's `<stream_uuid>:<sequence>` SSE id.
    assert '"sequence":"9007199254740993"' in response.text
    assert body["sequence"] == "9007199254740993"
    assert UUID(body["agent_run_id"])
    assert body["activity"]["sequence"] == "9007199254740993"
    assert body["agent_run_status"] == "agent_queued"


def test_execute_turn_is_conversation_scoped_and_persists_terminal_response(
    conversation_client,
) -> None:
    client, repository, settings = conversation_client
    run_id = uuid4()

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{run_id}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["agent_run_id"] == str(run_id)
    assert response.json()["activity"]["activity_type"] == "agent_response"
    assert repository.claimed_statuses == ["agent_completed"]


def test_execute_turn_emits_claim_to_finalize_telemetry(conversation_client) -> None:
    client, repository, settings = conversation_client
    records = []

    class Sink:
        def emit(self, record) -> None:
            records.append(record)

    app.dependency_overrides[get_telemetry_sink] = Sink
    run_id = uuid4()
    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{run_id}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    completed = [record for record in records if record.event == "agent.run.completed"]
    assert len(completed) == 1
    assert completed[0].correlation.agent_run_id == run_id
    assert completed[0].labels["agent_run_status"] == "agent_completed"
    assert completed[0].labels["model"] == "test"
    assert completed[0].estimated_cost_usd is None
    assert completed[0].labels["cost_basis"] == "usage_unavailable"


@pytest.mark.parametrize(
    ("runtime", "activity_type"),
    [(_ClarifyingRuntime(), "clarification"), (_RefusingRuntime(), "terminal_outcome")],
)
def test_execute_turn_persists_each_new_visible_activity_type(
    conversation_client, runtime, activity_type: str
) -> None:
    client, repository, settings = conversation_client
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: runtime
    )

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["activity"]["activity_type"] == activity_type
    assert response.json()["agent_run_status"] == "agent_completed"
    # Decision 4 item 1: a clarification turn writes EXACTLY ONE persisted
    # event. Asserting the activity type alone left the count unchecked, and a
    # turn that finalised twice would have looked identical in the response.
    assert len(repository.claimed_statuses) == 1


def test_execute_turn_foreign_conversation_is_non_disclosing_404(
    conversation_client,
) -> None:
    client, _repository, settings = conversation_client
    response = client.post(
        f"/api/v1/conversations/{uuid4()}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )
    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_execute_turn_requires_an_authenticated_session(conversation_client) -> None:
    client, repository, _settings = conversation_client
    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute"
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_runtime_failure_still_finalizes_the_claimed_run(conversation_client) -> None:
    client, repository, settings = conversation_client
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: _FailingRuntime()
    )

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["agent_run_status"] == "agent_failed"
    assert repository.claimed_statuses == ["agent_failed"]


def test_telemetry_export_failure_and_disabled_export_preserve_owned_activity(
    conversation_client,
) -> None:
    """NFR10 at the injectable OTel seam: telemetry cannot change product work."""
    import json
    from dataclasses import asdict

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from agent.runtime import PydanticAIAgentRuntime

    client, repository, settings = conversation_client
    answer = GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="Coverage remains available."),)
    )

    def scripted(_messages, info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool.name,
                    args=json.dumps(asdict(answer)),
                    tool_call_id="answer-1",
                )
            ]
        )

    class _RaisingExporter(SpanExporter):
        def export(self, _spans):
            raise RuntimeError("simulated exporter failure")

        def shutdown(self) -> None:
            return None

    def provider(exporter) -> TracerProvider:
        value = TracerProvider()
        value.add_span_processor(SimpleSpanProcessor(exporter))
        return value

    def semantic_activity(item: dict) -> dict:
        return {
            key: value
            for key, value in item.items()
            if key
            not in {
                "activity_id",
                "message_id",
                "occurred_at",
                "sequence",
            }
        }

    def execute_with(tracer_provider) -> tuple[dict, list[dict], str]:
        repository.claimed_statuses.clear()
        repository.finished_events.clear()

        def factory(**kwargs):
            return PydanticAIAgentRuntime(
                model=FunctionModel(scripted),
                tracer_provider=tracer_provider,
                capabilities=kwargs["capabilities"],
                deps=kwargs["deps"],
                answer_type=kwargs["answer_type"],
            )

        app.dependency_overrides[get_agent_runtime_factory] = lambda: factory
        response = client.post(
            f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
            headers=_headers(settings),
        )
        assert response.status_code == 200
        timeline = client.get(
            f"/api/v1/conversations/{repository.conversation_id}/timeline",
            headers=_headers(settings),
        )
        assert timeline.status_code == 200
        return (
            semantic_activity(response.json()["activity"]),
            [semantic_activity(item) for item in timeline.json()["items"]],
            response.json()["agent_run_status"],
        )

    control_exporter = InMemorySpanExporter()
    working_provider = provider(control_exporter)
    failing_provider = provider(_RaisingExporter())
    try:
        working = execute_with(working_provider)
        export_failed = execute_with(failing_provider)
        export_disabled = execute_with(None)
    finally:
        working_provider.shutdown()
        failing_provider.shutdown()

    # Without this the proof is only as strong as the instrumentation: if the
    # adapter ever stops emitting spans, all three runs become trivially
    # identical and this NFR10 case goes vacuously green (Story 3.9 review).
    assert control_exporter.get_finished_spans(), (
        "no span was exported -- the telemetry seam was never exercised"
    )

    assert export_failed == working
    assert export_disabled == working
    assert working[2] == "agent_completed"


def test_a_run_that_is_not_queued_is_refused_with_a_stable_problem(
    conversation_client,
) -> None:
    """Decision 1 makes the agent_run state machine the double-submit guard, so
    the refusal is the guard's only visible behaviour. It was implemented but
    never driven: the repository double never raised.
    """
    client, repository, settings = conversation_client
    repository.raise_not_queued_on_claim = True

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "agent_run_not_queued"
    assert repository.claimed_statuses == []


def test_a_gate_failure_still_reaches_a_terminal_status(conversation_client) -> None:
    """The claim already committed `agent_running`, and only `agent_queued` can
    be claimed -- so an exception escaping the turn leaves a run no request can
    ever execute again. `UncitedNumericProseError` is the likeliest source
    because it is the gate's own fail-closed rule, and it is a ValueError, not
    an AgentRuntimeError.
    """
    client, repository, settings = conversation_client
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: _NumericProseRuntime()
    )

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert repository.claimed_statuses == ["agent_failed"]


def test_actual_exception_classes_map_to_stable_owned_failure_reasons() -> None:
    from application.use_cases.execute_turn import failed_outcome_for_exception
    from application.contracts.capability_manifest import IncompleteManifestError
    from application.grounding.gate import UncitedNumericProseError
    from application.ports.agent_runtime import (
        AgentInvalidOutputError,
        AgentProviderError,
        AgentRuntimeError,
    )

    cases = (
        (AgentProviderError("anything at all"), "provider_error", "agent"),
        (AgentInvalidOutputError("anything at all"), "invalid_output", "agent"),
        (AgentRuntimeError("framework catch-all"), "invalid_output", "agent"),
        (UncitedNumericProseError("uncited"), "invalid_output", "agent"),
        (IncompleteManifestError("missing feature policy"), "capability_error", "capability"),
        (ValueError("invalid runtime model"), "invalid_output", "agent"),
    )
    for exception, expected, source in cases:
        outcome = failed_outcome_for_exception(exception)
        assert outcome.status == "failed"
        assert outcome.failure_reason == expected
        assert outcome.failure_source == source

    # Classification is by TYPE. The previous form matched
    # `"provider call failed" in str(exc)` and built that string itself, so
    # rewording the adapter's message would have downgraded every provider
    # outage to `invalid_output` while this test stayed green.
    assert (
        failed_outcome_for_exception(AgentProviderError("")).failure_reason
        == "provider_error"
    )
    assert (
        failed_outcome_for_exception(
            AgentRuntimeError("agent runtime provider call failed")
        ).failure_reason
        == "invalid_output"
    )


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        ("provider", "provider_error"),
        ("invalid_output", "invalid_output"),
        ("capability", "capability_error"),
        ("unclassified", "invalid_output"),
    ],
)
def test_every_mapped_failure_cause_keeps_the_planner_message_durable(
    conversation_client, exception: str, reason: str
) -> None:
    """AC3: "accepted conversation history remains durable" -- per cause.

    Task 4 asked for a test proving each mapped cause reaches its own reason
    AND that the accepted planner message survives it. The reason half was
    covered by a pure function-level mapping test with no timeline in it; this
    is the durability half, driven through the real route.
    """
    from application.contracts.capability_manifest import IncompleteManifestError
    from application.ports.agent_runtime import (
        AgentInvalidOutputError,
        AgentProviderError,
        AgentRuntimeError,
    )

    raised = {
        "provider": AgentProviderError("provider down"),
        "invalid_output": AgentInvalidOutputError("unusable"),
        "capability": IncompleteManifestError("missing feature policy"),
        "unclassified": AgentRuntimeError("something else"),
    }[exception]

    client, repository, settings = conversation_client

    class _RaisingRuntime:
        def run_turn(self, _request):
            raise raised

        @property
        def name(self) -> str:
            return "raising"

    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **_kwargs: _RaisingRuntime()
    )

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["activity"]["outcome"]["reason"] == reason
    # The run reached a terminal status rather than being stranded, and the
    # planner's accepted message is still in the timeline afterwards.
    assert repository.claimed_statuses == ["agent_failed"]
    timeline = client.get(
        f"/api/v1/conversations/{repository.conversation_id}/timeline",
        headers=_headers(settings),
    )
    assert timeline.status_code == 200
    assert any(
        activity["activity_type"] == "planner_message"
        for activity in timeline.json()["items"]
    )


@pytest.mark.parametrize("text", ["   ", "\t\n", "　"])
def test_whitespace_only_text_is_a_422_not_a_500(conversation_client, text: str) -> None:
    client, repository, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": text},
    )

    assert response.status_code == 422
    assert repository.accepted == []


def test_submitted_text_reaches_the_repository_stripped(conversation_client) -> None:
    client, repository, settings = conversation_client

    client.post(
        f"/api/v1/conversations/{repository.conversation_id}/messages",
        headers=_headers(settings),
        json={"text": "  Check Tuesday night coverage  "},
    )

    assert repository.accepted == ["Check Tuesday night coverage"]


def test_message_to_an_unknown_conversation_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    client, _, settings = conversation_client

    response = client.post(
        f"/api/v1/conversations/{uuid4()}/messages",
        headers=_headers(settings),
        json={"text": "Check Tuesday night coverage"},
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_timeline_reports_its_window_and_carries_sequence_on_every_item(
    conversation_client,
) -> None:
    client, repository, settings = conversation_client
    repository.timeline_has_more = True

    response = client.get(
        f"/api/v1/conversations/{repository.conversation_id}/timeline",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is True
    assert body["limit"] == 200
    assert body["latest_agent_run_status"] == "agent_queued"
    # A read that omitted `sequence` would leave a reconnecting client with no
    # resume point, which is the whole reason the window is bounded.
    assert [item["sequence"] for item in body["items"]] == ["1"]


def test_timeline_for_an_unknown_conversation_is_the_standard_non_disclosing_404(
    conversation_client,
) -> None:
    client, _, settings = conversation_client

    response = client.get(
        f"/api/v1/conversations/{uuid4()}/timeline",
        headers=_headers(settings),
    )

    assert response.status_code == 404
    assert response.json() == _NOT_FOUND_BODY


def test_conversation_list_reports_truncation(conversation_client) -> None:
    client, repository, settings = conversation_client

    response = client.get(
        f"/api/v1/conversations?scenario_id={repository.scenario_id}",
        headers=_headers(settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is False
    assert body["limit"] == 100
    assert [item["id"] for item in body["items"]] == [str(repository.conversation_id)]
