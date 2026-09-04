"""Real PostgreSQL lineage proof for one agent-backed approval run."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import insert, select

from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.schema import (
    app_user,
    audit_event,
    membership,
    organization,
    persisted_event,
    site,
)
from api.deps import site_context
from application.app_version import APP_VERSION
from application.capabilities.deps import AgentDepsV1
from application.capabilities.registry import POLICY_GENERATION
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.use_cases.accept_turn import accept_turn
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval
from application.use_cases.request_approval import RequestApprovalCommandV1, request_approval
from tests.test_agent_runtime_adapter import _call_demo, _runtime
from tests.test_approval_governance_postgres import (
    NOW,
    _decision_dependencies,
    _seed_candidate_run,
    _use_case_dependencies,
)

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def telemetry_ids(governed_postgres_engine):
    ids = {name: uuid4() for name in ("org", "site", "actor")}
    with governed_postgres_engine.begin() as connection:
        connection.execute(insert(organization).values(id=ids["org"], name="Telemetry Org"))
        connection.execute(
            insert(site).values(
                id=ids["site"], organization_id=ids["org"], name="Telemetry Site"
            )
        )
        connection.execute(
            insert(app_user).values(
                id=ids["actor"],
                idp_subject="telemetry-planner",
                email="telemetry-planner@example.test",
            )
        )
        connection.execute(
            insert(membership).values(
                id=uuid4(), app_user_id=ids["actor"], site_id=ids["site"]
            )
        )
    return ids


def test_agent_run_is_correlated_across_product_audit_and_telemetry(
    governed_postgres_engine, telemetry_ids
) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(
        engine,
        site_id=telemetry_ids["site"],
        actor_id=telemetry_ids["actor"],
        resource_version=2,
    )
    conversations = PostgresConversationRepository()
    planner_text = "PLANNER_SECRET_5_1"
    model_text = "MODEL_SECRET_5_1"
    tool_argument = "TOOL_ARGUMENT_SECRET_5_1"
    tool_result = "TOOL_RESULT_SECRET_5_1"

    with site_context(engine, telemetry_ids["site"]) as connection:
        accepted = accept_turn(
            conversations,
            connection,
            conversation_id=ids["conversation"],
            site_id=telemetry_ids["site"],
            actor_id=telemetry_ids["actor"],
            text=planner_text,
        )
    assert accepted is not None and accepted.event.agent_run_id is not None
    agent_run_id = accepted.event.agent_run_id
    with site_context(engine, telemetry_ids["site"]) as connection:
        claimed = conversations.claim_queued_run(
            connection,
            conversation_id=ids["conversation"],
            agent_run_id=agent_run_id,
        )
    assert claimed is not None

    records = []

    class RecordingSink:
        def emit(self, record) -> None:
            records.append(record)

    sink = RecordingSink()

    # Drive one REAL agent run end to end through the real `AgentRuntime` and
    # a real registered capability tool (Task 12's acceptance boundary,
    # code review of story-5.1: the version of this test that only
    # constructed `pending_payload` by hand never exercised any code that
    # actually saw `planner_text`/`model_text`/`tool_argument`, so the
    # "no leaked secret" assertion below passed trivially). The demo
    # capability's handler echoes its `label` argument back verbatim
    # (`repeat=1` => the result IS the label), so `tool_argument` doubles as
    # both the real tool argument and the real tool result here.
    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return _call_demo(label=tool_argument, repeat=1, call_id="correlation-demo")
        return ModelResponse(parts=[TextPart(content=model_text)])

    real_run_deps = AgentDepsV1(
        actor_id=telemetry_ids["actor"], site_id=telemetry_ids["site"],
        membership_id=claimed.membership_id, request_id=uuid4(),
        agent_run_id=agent_run_id, conversation_id=ids["conversation"],
        scenario_id=claimed.scenario_id, scenario_version_id=claimed.scenario_version_id,
        policy_version=POLICY_GENERATION, clock=lambda: datetime.now(timezone.utc),
        projection_reader=object(), connection=None,
        remaining_budget=AgentBudgetV1(), telemetry=sink,
    )
    real_outcome = _runtime(model=FunctionModel(scripted), deps=real_run_deps).run_turn(
        AgentTurnRequestV1(prompt=planner_text)
    )
    assert real_outcome.status == "completed"

    pending_payload = {
        "pending_calls": [
            {
                "tool_call_id": "correlation-call",
                "tool_name": "scheduling_baseline",
                "tool_args_json": json.dumps({"secret": tool_argument}),
            }
        ],
        "turn": {
            "messages": [
                {"role": "assistant", "parts": [{"kind": "text", "text": model_text}]},
                {"role": "tool_result", "parts": [{"kind": "tool_result", "text": tool_result}]},
            ]
        },
    }
    with site_context(engine, telemetry_ids["site"]) as connection:
        binding = request_approval(
            connection,
            command=RequestApprovalCommandV1(
                site_id=telemetry_ids["site"],
                actor_id=telemetry_ids["actor"],
                schedule_run_id=ids["schedule_run"],
                expected_resource_version=2,
                expected_baseline_schedule_version=None,
                request_effect_key=f"command:{uuid4()}",
                request_id=uuid4(),
                conversation_id=ids["conversation"],
                agent_run_id=agent_run_id,
                pending_payload=pending_payload,
            ),
            **_use_case_dependencies(),
        ).binding

    with site_context(engine, telemetry_ids["site"]) as connection:
        decision = decide_approval(
            connection,
            command=DecideApprovalCommandV1(
                site_id=telemetry_ids["site"],
                actor_id=telemetry_ids["actor"],
                approval_id=binding.approval_id,
                decision="reject",
                expected_resource_version=binding.resource_version,
                request_id=uuid4(),
            ),
            telemetry=sink,
            **_decision_dependencies(),
        )
    assert decision.outcome == "rejected"

    with engine.connect() as connection:
        product_rows = connection.execute(
            select(persisted_event.c.agent_run_id).where(
                persisted_event.c.agent_run_id == agent_run_id
            )
        ).all()
        audit_rows = connection.execute(
            select(audit_event.c.agent_run_id, audit_event.c.app_version).where(
                audit_event.c.agent_run_id == agent_run_id
            )
        ).all()

    assert product_rows and {row.agent_run_id for row in product_rows} == {agent_run_id}
    assert len(audit_rows) == 2
    assert {row.agent_run_id for row in audit_rows} == {agent_run_id}
    assert records and {record.correlation.agent_run_id for record in records} == {agent_run_id}
    assert {record.app_version for record in records} == {APP_VERSION}
    assert {row.app_version for row in audit_rows} == {APP_VERSION}

    # Proves the recording sink actually captured records from the code that
    # had access to the secrets below -- not just the one `approval.decided`
    # record the pre-review version of this test produced (code review of
    # story-5.1).
    # `agent.run.completed` is emitted by the router layer (conversations.py /
    # approvals.py), not by `AgentRuntime.run_turn` itself -- this test drives
    # the runtime directly (no HTTP context here), so it is not asserted.
    events = {record.event for record in records}
    assert "agent.model.calls.completed" in events
    assert "agent.tool.call.completed" in events
    assert "approval.decided" in events

    serialized = json.dumps([asdict(record) for record in records], default=str)
    for secret in (planner_text, model_text, tool_argument, tool_result):
        assert secret not in serialized

