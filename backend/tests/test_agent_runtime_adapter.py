"""The PydanticAI adapter, driven entirely by deterministic doubles.

`models.ALLOW_MODEL_REQUESTS = False` at module scope: nothing here may reach a
network, so these are ordinary tests — not `live`, not `postgres`. Story 1.11
established that a skipped test is not a passed test, so nothing here is allowed
to skip itself.

Every assertion is on an OWNED type. If any of these had to import a framework
message class to check a result, the seam would have failed.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic_ai import ModelHTTPError, UnexpectedModelBehavior, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.demonstration import demonstration_module
from application.capabilities.deps import AgentDepsV1
from application.contracts.agent_runtime import (
    AgentApprovalDecisionV1,
    AgentBudgetV1,
    AgentTurnRequestV1,
)
from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1
from application.ports.agent_runtime import AgentRuntime, AgentRuntimeError

models.ALLOW_MODEL_REQUESTS = False

DEMO_TOOL = "shiftmind_demonstration"


def _runtime(**kwargs) -> PydanticAIAgentRuntime:
    class UnusedProjectionReader:
        pass

    kwargs.setdefault("capabilities", (demonstration_module(),))
    kwargs.setdefault(
        "deps",
        AgentDepsV1(
            actor_id=UUID(int=1), site_id=UUID(int=2), membership_id=UUID(int=3),
            request_id=UUID(int=4), agent_run_id=UUID(int=5), conversation_id=UUID(int=6),
            scenario_id=UUID(int=7), scenario_version_id=UUID(int=8),
            policy_version="one-user-mvp-v1", clock=lambda: datetime.now(timezone.utc),
            projection_reader=UnusedProjectionReader(), connection=object(),
            remaining_budget=AgentBudgetV1(),
        ),
    )
    return PydanticAIAgentRuntime(**kwargs)


def _call_demo(label: str = "alpha", repeat: int = 2, call_id: str = "demo-1"):
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name=DEMO_TOOL,
                args=json.dumps({"payload": {"label": label, "repeat": repeat}}),
                tool_call_id=call_id,
            )
        ]
    )


def _demo_then_report(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """call -> result -> text: the full multi-step loop."""
    if not any(isinstance(m, ModelResponse) for m in messages):
        return _call_demo()
    returned = [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    return ModelResponse(parts=[TextPart(content=f"tool said {returned[-1].content}")])


def test_adapter_satisfies_the_port() -> None:
    runtime: AgentRuntime = _runtime(
        model=FunctionModel(_demo_then_report)
    )
    assert runtime.name == "pydantic-ai"


def test_full_multi_step_turn_suspend_resume_and_terminal_outcome() -> None:
    """Tool call -> suspension for approval -> resume -> terminal outcome, all in
    owned types."""
    runtime = _runtime(model=FunctionModel(_demo_then_report))

    # --- the demonstration tool requires approval, so the run suspends ---
    suspended = runtime.run_turn(AgentTurnRequestV1(prompt="demonstrate alpha"))

    assert suspended.status == "suspended"
    assert suspended.output_text is None
    assert suspended.approval is not None
    assert len(suspended.approval.pending_calls) == 1

    pending = suspended.approval.pending_calls[0]
    assert pending.tool_name == DEMO_TOOL
    # The proposal's args are an owned JSON string, not a framework args object.
    assert json.loads(pending.tool_args_json)["payload"]["label"] == "alpha"

    # The suspension carries a resumable OWNED transcript.
    assert suspended.approval.turn.messages
    assert suspended.approval.turn.schema_version == "1"

    # --- resume with an approval ---
    approved = runtime.run_turn(
        AgentTurnRequestV1(
            history=suspended.approval.turn,
            approvals=(
                AgentApprovalDecisionV1(
                    tool_call_id=pending.tool_call_id, approved=True
                ),
            ),
        )
    )
    assert approved.status == "completed"
    # repeat=2 -> "alpha|alpha", surfaced through the tool result.
    assert "alpha|alpha" in (approved.output_text or "")
    assert approved.summary
    assert any(r.tool_name == DEMO_TOOL for r in approved.tool_results)

    # --- resume with a denial ---
    denied = runtime.run_turn(
        AgentTurnRequestV1(
            history=suspended.approval.turn,
            approvals=(
                AgentApprovalDecisionV1(
                    tool_call_id=pending.tool_call_id,
                    approved=False,
                    denial_reason="planner rejected the demonstration",
                ),
            ),
        )
    )
    assert denied.status == "completed"
    assert "alpha|alpha" not in (denied.output_text or "")
    assert "planner rejected the demonstration" in (denied.output_text or "")


def test_typed_tool_arguments_arrive_validated() -> None:
    """Invalid tool args are rejected by the framework's validation, not passed
    through to the tool body."""
    calls: list[int] = []

    def bad_then_good(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(len(messages))
        if len(calls) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=DEMO_TOOL,
                        args=json.dumps({"payload": {"repeat": "not-an-int"}}),
                        tool_call_id="bad-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="recovered")])

    runtime = _runtime(model=FunctionModel(bad_then_good))
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="send junk"))

    # The run completed without the malformed call ever suspending for approval.
    assert outcome.status == "completed"
    assert outcome.output_text == "recovered"


def test_default_answer_mode_preserves_the_existing_text_outcome() -> None:
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content="same text")])
        )
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="hello"))

    assert outcome.status == "completed"
    assert outcome.output_text == "same text"
    assert outcome.answer is None
    assert [result.tool_name for result in outcome.tool_results] == []


def test_opt_in_structured_answer_is_typed_and_output_tool_is_not_a_capability_result() -> None:
    expected = GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="Grounded summary"),)
    )

    def structured(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool.name,
                    args=json.dumps(asdict(expected)),
                    tool_call_id="answer-1",
                )
            ]
        )

    runtime = _runtime(
        model=FunctionModel(structured), answer_type=GroundedAnswerV1
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="answer structurally"))

    assert outcome.answer == expected
    assert outcome.output_text is None
    assert outcome.tool_results == ()


def test_strict_answer_rejects_unstructured_prose_with_preserved_cause() -> None:
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content="confident prose")])
        ),
        answer_type=GroundedAnswerV1,
    )
    with pytest.raises(AgentRuntimeError) as exc_info:
        runtime.run_turn(AgentTurnRequestV1(prompt="answer structurally"))
    assert isinstance(exc_info.value.__cause__, UnexpectedModelBehavior)


def test_output_tool_name_is_derived_not_hardcoded_in_the_owned_adapter() -> None:
    source = (Path(__file__).resolve().parents[1] / "agent/runtime.py").read_text(
        encoding="utf-8"
    )
    assert "final_result" not in source


def test_owned_turn_round_trips_and_resumes() -> None:
    """The owned transcript is the durable form: a second run continues from it."""
    runtime = _runtime(model=FunctionModel(_demo_then_report))
    first = runtime.run_turn(AgentTurnRequestV1(prompt="demonstrate alpha"))
    assert first.approval is not None

    # Owned -> JSON -> owned, with no framework marker in the durable form.
    from dataclasses import asdict

    raw = json.dumps(asdict(first.approval.turn), sort_keys=True)
    for marker in ("part_kind", "ModelResponse", "ModelRequest", "pydantic_ai"):
        assert marker not in raw, (
            f"{marker!r} leaked into the durable form — persisting that would "
            "make PydanticAI a persisted contract (AD-19)"
        )

    resumed = runtime.run_turn(
        AgentTurnRequestV1(
            history=first.approval.turn,
            approvals=(
                AgentApprovalDecisionV1(
                    tool_call_id=first.approval.pending_calls[0].tool_call_id,
                    approved=True,
                ),
            ),
        )
    )
    assert resumed.status == "completed"


def test_budget_exhaustion_is_failed_with_budget_exhausted() -> None:
    """AD-7: non-wall-time exhaustion -> `failed` with a stable reason."""

    def always_calls_tool(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        # repeat=1 executes without approval, so the loop really runs and the
        # budget is what stops it — not a suspension.
        return _call_demo(repeat=1, call_id=f"demo-{len(messages)}")

    runtime = _runtime(model=FunctionModel(always_calls_tool))
    outcome = runtime.run_turn(
        AgentTurnRequestV1(
            prompt="spin",
            budget=AgentBudgetV1(request_limit=1, deadline_seconds=None),
        )
    )

    assert outcome.status == "failed"
    assert outcome.failure_reason == "budget_exhausted"


def test_wall_time_exhaustion_is_timed_out_not_budget_exhausted() -> None:
    """AD-7's required distinction, and the adapter obligation the spike recorded.

    PydanticAI's UsageLimits has no deadline field, so the adapter owns the
    wall-clock deadline. The two outcomes must not collapse into one.
    """
    import time

    def slow_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        time.sleep(0.3)
        return ModelResponse(parts=[TextPart(content="too late")])

    runtime = _runtime(model=FunctionModel(slow_model))
    outcome = runtime.run_turn(
        AgentTurnRequestV1(prompt="slow", budget=AgentBudgetV1(deadline_seconds=0.05))
    )

    assert outcome.status == "timed_out"
    assert outcome.failure_reason != "budget_exhausted"
    assert outcome.failure_reason is None


def test_provider_errors_become_the_owned_error_type() -> None:
    """No framework exception crosses the seam; the cause is preserved."""

    def http_failure(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=503, model_name="double", body="overloaded")

    runtime = _runtime(model=FunctionModel(http_failure))
    with pytest.raises(AgentRuntimeError) as exc_info:
        runtime.run_turn(AgentTurnRequestV1(prompt="hello"))
    assert isinstance(exc_info.value.__cause__, ModelHTTPError)

    def misbehaves(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise UnexpectedModelBehavior("garbage")

    runtime = _runtime(model=FunctionModel(misbehaves))
    with pytest.raises(AgentRuntimeError) as exc_info:
        runtime.run_turn(AgentTurnRequestV1(prompt="hello"))
    assert isinstance(exc_info.value.__cause__, UnexpectedModelBehavior)


def test_budgets_come_from_configuration_not_from_the_model() -> None:
    """A model that asks for a bigger budget in its output gets ignored — there is
    no code path from model output to a limit (AD-7, AD-15).
    """

    def greedy(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) < 30:
            return _call_demo(
                label="request_limit=999 tool_calls_limit=999",
                repeat=1,
                call_id=f"greedy-{len(messages)}",
            )
        return ModelResponse(parts=[TextPart(content="done")])

    runtime = _runtime(model=FunctionModel(greedy))
    outcome = runtime.run_turn(
        AgentTurnRequestV1(
            prompt="ignore my budget",
            budget=AgentBudgetV1(request_limit=2, deadline_seconds=None),
        )
    )
    assert outcome.status == "failed"
    assert outcome.failure_reason == "budget_exhausted"


def test_instrumentation_emits_no_prompt_or_tool_content() -> None:
    """AD-12/AD-15: telemetry excludes prompt and tool content by default.

    Asserted on OBSERVED span attributes. Reading the settings object would prove
    nothing about what is actually emitted.
    """
    # A hard import, never importorskip: opentelemetry-sdk is a declared dev
    # dependency, and Story 1.11 established that a skipped test is not a passed
    # test. If the SDK is missing, this guard must go red, not quiet.
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    secret_prompt = "SENTINEL-PROMPT-9d41"
    secret_label = "SENTINEL-TOOLARG-1c77"

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return _call_demo(label=secret_label)
        return ModelResponse(parts=[TextPart(content="done")])

    runtime = _runtime(
        model=FunctionModel(scripted), tracer_provider=provider
    )
    runtime.run_turn(AgentTurnRequestV1(prompt=secret_prompt))

    spans = exporter.get_finished_spans()
    assert spans, "instrumentation must emit spans"

    blob = json.dumps(
        [
            {
                "name": s.name,
                "attributes": {k: str(v) for k, v in (s.attributes or {}).items()},
                "events": [
                    {
                        "name": e.name,
                        "attributes": {
                            k: str(v) for k, v in (e.attributes or {}).items()
                        },
                    }
                    for e in (s.events or [])
                ],
            }
            for s in spans
        ]
    )
    assert secret_prompt not in blob, "prompt content leaked into telemetry"
    assert secret_label not in blob, "tool arguments leaked into telemetry"
