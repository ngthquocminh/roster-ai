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
from dataclasses import asdict, dataclass, replace
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

from agent.runtime import AgentRuntimeConfig, PydanticAIAgentRuntime, create_agent_runtime
from evals.doubles import build_model_double
from application.capabilities.demonstration import demonstration_module
from application.capabilities.deps import AgentDepsV1
from application.contracts.agent_runtime import (
    AgentApprovalDecisionV1,
    AgentBudgetV1,
    AgentTurnRequestV1,
)
from application.contracts.dialogue import ClarificationV1, RefusalV1
from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1
from application.contracts.proposal import DraftProposalV1
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


def test_factory_wires_configured_model_but_injected_model_wins() -> None:
    injected = FunctionModel(_demo_then_report)
    configured = create_agent_runtime(
        settings=type(
            "SettingsStub",
            (),
            {
                "agent_runtime_model": "test",
                "agent_runtime_api_key": None,
                "agent_runtime_request_limit": 1,
                "agent_runtime_tool_calls_limit": 1,
                "agent_runtime_deadline_seconds": 1.0,
                "agent_runtime_retries_limit": 2,
                "agent_runtime_total_tokens_limit": 100,
            },
        )()
    )
    assert configured._model.__class__.__name__ == "TestModel"

    overridden = create_agent_runtime(
        settings=type(
            "SettingsStub",
            (),
            {
                "agent_runtime_model": "test",
                "agent_runtime_api_key": None,
                "agent_runtime_request_limit": 1,
                "agent_runtime_tool_calls_limit": 1,
                "agent_runtime_deadline_seconds": 1.0,
                "agent_runtime_retries_limit": 2,
                "agent_runtime_total_tokens_limit": 100,
            },
        )(),
        model=injected,
    )
    assert overridden._model is injected


def test_openrouter_model_uses_the_explicit_agent_runtime_key() -> None:
    runtime = PydanticAIAgentRuntime(
        config=AgentRuntimeConfig(
            model="openrouter:openai/gpt-oss-20b:free", api_key="test-key"
        )
    )
    assert runtime._model.__class__.__name__ == "OpenAIChatModel"


def test_configured_retry_ceiling_bounds_tool_and_output_model_retries() -> None:
    settings = type(
        "SettingsStub",
        (),
        {
            "agent_runtime_model": "test",
            "agent_runtime_api_key": None,
            "agent_runtime_request_limit": 8,
            "agent_runtime_tool_calls_limit": 8,
            "agent_runtime_deadline_seconds": 60.0,
            "agent_runtime_retries_limit": 3,
            "agent_runtime_total_tokens_limit": 2_000,
        },
    )()

    runtime = create_agent_runtime(settings=settings)

    assert runtime._agent._max_tool_retries == 3
    assert runtime._agent._max_output_retries == 3
    assert runtime._config.default_budget.total_tokens_limit == 2_000


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


def test_a_committed_golden_case_outcome_is_unchanged_by_the_answer_type_seam() -> None:
    """Decision 3's regression fence, as specified: a REAL committed golden case
    producing a byte-identical `AgentRunOutcomeV1`.

    Asserting four fields against a one-line FunctionModel -- which is what this
    replaces -- could not detect the three consequences Decision 3 named: a
    `final_result` entry appearing in `tool_results`, `output_text` degrading to
    a dataclass repr, or the framework output tool being counted as a routed
    capability. Only the whole serialized outcome catches those.
    """
    from pathlib import Path

    from application.capabilities.installed import installed_modules
    from evals.cases import load_case
    from evals.report import _runtime_for_case

    golden = Path(__file__).resolve().parents[1] / "evals/golden/demonstration/repeat-once.json"
    case = load_case(golden)
    modules = installed_modules()

    outcome = _runtime_for_case(case, modules).run_turn(
        AgentTurnRequestV1(prompt=case.prompt)
    )

    # json round-trip so tuple-vs-list is not the thing under test.
    assert json.loads(json.dumps(asdict(outcome))) == {
        "schema_version": "1",
        "status": "completed",
        "failure_reason": None,
        # None on every success path; set at the raise site so the request path
        # can tell an agent-level reason from an identically-spelled manifest code.
        "failure_source": None,
        "output_text": "tool said alpha",
        # Structured model-side variants stay absent on the default text path.
        "answer": None,
        "grounded_response": None,
        "clarification": None,
        "resolved_clarification": None,
        "refusal": None,
        "draft": None,
        "resolved_draft": None,
        "turn": {
            "schema_version": "1",
            "messages": [
                {
                    "schema_version": "1",
                    "role": "user",
                    "parts": [{
                        "schema_version": "1", "kind": "text",
                        "text": "Demonstrate alpha once.", "tool_name": None,
                        "tool_call_id": None, "tool_args_json": None,
                    }],
                },
                {
                    "schema_version": "1",
                    "role": "assistant",
                    "parts": [{
                        "schema_version": "1", "kind": "tool_call", "text": None,
                        "tool_name": "shiftmind_demonstration",
                        "tool_call_id": "demo-repeat-once",
                        "tool_args_json": '{"payload": {"label": "alpha", "repeat": 1}}',
                    }],
                },
                {
                    "schema_version": "1",
                    "role": "tool_result",
                    "parts": [{
                        "schema_version": "1", "kind": "tool_result", "text": "alpha",
                        "tool_name": "shiftmind_demonstration",
                        "tool_call_id": "demo-repeat-once", "tool_args_json": None,
                    }],
                },
                {
                    "schema_version": "1",
                    "role": "assistant",
                    "parts": [{
                        "schema_version": "1", "kind": "text", "text": "tool said alpha",
                        "tool_name": None, "tool_call_id": None, "tool_args_json": None,
                    }],
                },
            ],
        },
        "summary": "tool said alpha",
        "approval": None,
        "tool_results": [{
            "schema_version": "1",
            "tool_call_id": "demo-repeat-once",
            "tool_name": "shiftmind_demonstration",
            "content": "alpha",
        }],
        "usage": {
            "requests": 2,
            "tool_calls": 1,
            "input_tokens": 109,
            "output_tokens": 19,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
        "budget_outcome": "within_budget",
    }
    # Omitting the parameter and passing it as None must be the same path.
    explicit = PydanticAIAgentRuntime(
        model=build_model_double(case),
        capabilities=modules,
        deps=_runtime_for_case(case, modules)._deps,
        answer_type=None,
    ).run_turn(AgentTurnRequestV1(prompt=case.prompt))
    assert asdict(explicit) == asdict(outcome)


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


def test_structured_output_tools_keep_the_four_exact_stable_names() -> None:
    runtime = _runtime(model=FunctionModel(lambda _messages, _info: ModelResponse()), answer_type=GroundedAnswerV1)
    assert runtime._agent._output_toolset is not None
    assert {
        definition.name
        for definition in runtime._agent._output_toolset._tool_defs
    } == {"final_result", "clarification", "refusal", "draft"}


@pytest.mark.parametrize(
    ("tool_name", "payload", "field"),
    [
        (
            "clarification",
            ClarificationV1(question="Which worker?"),
            "clarification",
        ),
        (
            "refusal",
            RefusalV1(
                reason="capability_unavailable",
                detail="The 60-second budget is unavailable.",
                next_step="Review Scenario Data.",
            ),
            "refusal",
        ),
        (
            "draft",
            DraftProposalV1(draft_id="draft-123"),
            "draft",
        ),
    ],
)
def test_dialogue_outputs_dispatch_without_leaking_output_tools_as_results(
    tool_name: str,
    payload: ClarificationV1 | RefusalV1 | DraftProposalV1,
    field: str,
) -> None:
    def structured(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert tool_name in {tool.name for tool in info.output_tools}
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool_name,
                    args=json.dumps(asdict(payload)),
                    tool_call_id=f"{tool_name}-1",
                )
            ]
        )

    outcome = _runtime(
        model=FunctionModel(structured), answer_type=GroundedAnswerV1
    ).run_turn(AgentTurnRequestV1(prompt="respond structurally"))

    assert getattr(outcome, field) == payload
    assert outcome.answer is None
    assert outcome.tool_results == ()


def test_unrecognized_structured_output_fails_owned_instead_of_returning_empty() -> None:
    @dataclass(frozen=True)
    class OtherOutput:
        value: str = ""

    def structured(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args="{}",
                    tool_call_id="other-1",
                )
            ]
        )

    runtime = _runtime(model=FunctionModel(structured), answer_type=OtherOutput)
    with pytest.raises(AgentRuntimeError, match="unrecognized structured output"):
        runtime.run_turn(AgentTurnRequestV1(prompt="respond structurally"))


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
    assert outcome.budget_outcome == "budget_exhausted"
    assert outcome.usage is None


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
    assert outcome.budget_outcome == "deadline_expired"
    assert outcome.usage is None


def test_success_carries_owned_usage_and_emits_model_latency() -> None:
    records = []

    class RecordingSink:
        def emit(self, record) -> None:
            records.append(record)

    base = _runtime()
    deps = base._deps
    object.__setattr__(deps, "telemetry", RecordingSink())
    runtime = _runtime(
        model=FunctionModel(
            lambda _messages, _info: ModelResponse(parts=[TextPart(content="done")])
        ),
        deps=deps,
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="hello"))

    assert outcome.status == "completed"
    assert outcome.budget_outcome == "within_budget"
    assert outcome.usage is not None
    assert outcome.usage.requests is not None
    assert [record.event for record in records] == ["agent.model.calls.completed"]
    assert records[0].duration_ms is not None and records[0].duration_ms >= 0
    assert records[0].correlation.agent_run_id == deps.agent_run_id


def test_capability_call_emits_tool_latency_and_correlation() -> None:
    records = []

    class RecordingSink:
        def emit(self, record) -> None:
            records.append(record)

    base = _runtime()
    deps = base._deps
    object.__setattr__(deps, "telemetry", RecordingSink())

    def execute_once(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(repeat=1)
        return ModelResponse(parts=[TextPart(content="done")])

    outcome = _runtime(model=FunctionModel(execute_once), deps=deps).run_turn(
        AgentTurnRequestV1(prompt="run tool")
    )
    assert outcome.status == "completed"
    tool_records = [r for r in records if r.event == "agent.tool.call.completed"]
    assert len(tool_records) == 1
    assert tool_records[0].labels == {"capability_name": DEMO_TOOL}
    assert tool_records[0].correlation.agent_run_id == deps.agent_run_id
    assert tool_records[0].correlation.tool_call_id == "demo-1"
    assert tool_records[0].duration_ms is not None


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


def test_numeral_in_prose_is_corrected_in_loop_instead_of_killing_the_turn() -> None:
    """The D2 remediation, asserted as behaviour.

    The gate's prose rule runs after the turn, so a violation used to reach the
    route as an exception and persist an empty response the planner saw as a
    blank bubble. As an output validator it becomes a `ModelRetry` the model can
    act on -- the same mechanism the framework already uses for unusable output.
    """
    attempts: list[str] = []
    clean = GroundedAnswerV1(segments=(GroundedProseSegmentV1(text="Coverage is short"),))
    dirty = GroundedAnswerV1(segments=(GroundedProseSegmentV1(text="Short by 90 minutes"),))

    def echoes_a_number_then_corrects(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        output_tool = info.output_tools[0]
        payload = dirty if not attempts else clean
        attempts.append("call")
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool.name,
                    args=json.dumps(asdict(payload)),
                    tool_call_id=f"answer-{len(attempts)}",
                )
            ]
        )

    runtime = _runtime(
        model=FunctionModel(echoes_a_number_then_corrects), answer_type=GroundedAnswerV1
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="how short are we"))

    assert len(attempts) == 2, "the validator must have forced exactly one retry"
    assert outcome.answer == clean
    assert outcome.status == "completed"


def test_the_prose_rule_has_one_implementation_shared_with_the_gate() -> None:
    """A second copy in the adapter is the drift this arrangement prevents.

    The adapter may WIRE the rule to the framework, but the rule itself lives in
    `application/grounding/gate.py`, which cannot import pydantic_ai (AD-19).
    """
    source = (Path(__file__).resolve().parents[1] / "agent/runtime.py").read_text(
        encoding="utf-8"
    )
    assert "numeric_prose_violation" in source
    assert "isnumeric" not in source, "the adapter must call the rule, not restate it"
