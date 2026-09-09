from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic_ai import models

from agent.runtime import AgentRuntimeConfig, PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_inspect import scheduling_inspect_module
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.grounding import GroundedAnswerV1
from application.contracts.scenario_projection import ScenarioOverviewV1
from settings import default_settings


models.ALLOW_MODEL_REQUESTS = False


class _ProjectionReader:
    def get_overview(self, _connection, scenario_id):
        return ScenarioOverviewV1(
            scenario_id=scenario_id,
            scenario_version_id=UUID(int=8),
            site_id=UUID(int=2),
            fixture_id="sample_tiny_input",
            scenario_name="tiny",
            fixture_version="v1",
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="abc",
            horizon_start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            site_timezone="UTC",
            horizon_minutes=10080,
            baseline_schedule_version=None,
            projection_generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            work_area_count=2,
            task_count=3,
            worker_count=4,
            demand_interval_count=5,
            baseline_assignment_count=0,
            lock_count=0,
            constraint_count=0,
        )


def test_configured_deterministic_model_executes_a_real_tool_then_answers() -> None:
    assert default_settings().agent_runtime_model == "deterministic"
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "AGENT_RUNTIME_MODEL: ${AGENT_RUNTIME_MODEL:-deterministic}" in compose

    deps = AgentDepsV1(
        actor_id=UUID(int=1), site_id=UUID(int=2), membership_id=UUID(int=3),
        request_id=UUID(int=4), agent_run_id=UUID(int=5), conversation_id=UUID(int=6),
        scenario_id=UUID(int=7), scenario_version_id=UUID(int=8),
        policy_version="one-user-mvp-v1", clock=lambda: datetime.now(timezone.utc),
        projection_reader=_ProjectionReader(), connection=object(),
        remaining_budget=AgentBudgetV1(),
    )
    runtime = PydanticAIAgentRuntime(
        config=AgentRuntimeConfig(model="deterministic"),
        capabilities=(scheduling_inspect_module(),),
        deps=deps,
        answer_type=GroundedAnswerV1,
    )

    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="Inspect this scenario"))

    assert outcome.status == "completed"
    assert outcome.answer is not None
    assert outcome.answer.segments
    assert all(not char.isnumeric() for segment in outcome.answer.segments for char in segment.text)
    assert [result.tool_name for result in outcome.tool_results] == ["scheduling_inspect"]
