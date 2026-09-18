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

from agent.runtime import (
    AgentRuntimeConfig, PydanticAIAgentRuntime, _openrouter_model_settings, create_agent_runtime,
)


def test_default_instructions_bound_broad_orientation_inspection():
    instructions = AgentRuntimeConfig().instructions
    # Normalized so incidental source line-wraps inside a sentence never
    # break a substring check -- the prompt's own line breaks (markdown
    # headers/bullets) still matter to the model, but not to this test.
    flat = ' '.join(instructions.split())
    assert flat.index('A greeting alone') < flat.index('Call a tool when you already have')
    assert 'Broad orientation requests' in flat
    assert 'scenario overview' in flat
    assert 'scoped to a family' in flat
    assert 'successful scheduling_draft call' in flat
    assert 'workflow snapshot' in flat
    assert 'copy its worker_id or task_id' in flat
    assert 'current_scenario_version_id' in flat
    assert 'How can you help' in flat
    assert 'placeholder result_id' in flat
    assert 'present a failed claim' in flat
    assert 'Tool routing' in flat
    assert 'scheduling_inspect(group="overview")' in flat


def test_openrouter_settings_omit_reasoning_for_none_and_unset():
    # A model that doesn't support the "reasoning" parameter (e.g.
    # qwen/qwen3-235b-a22b-2507) rejects the whole call if it's sent anyway --
    # "none" must omit the key entirely, not send effort="none".
    assert _openrouter_model_settings(None) is None
    assert _openrouter_model_settings('none') is None


def test_openrouter_settings_include_reasoning_for_a_real_effort_value():
    assert _openrouter_model_settings('low') == {'extra_body': {'reasoning': {'effort': 'low'}}}
    assert _openrouter_model_settings('medium') == {
        'extra_body': {'reasoning': {'effort': 'medium'}}}
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
    model = runtime._model
    assert model.__class__.__name__ == "FallbackModel"
    assert [m.__class__.__name__ for m in model.models] == ["OpenRouterModel"] * 3
    from agent.runtime import _is_transient_openrouter_error, _is_upstream_error_response

    assert model._response_handlers == [_is_upstream_error_response]
    assert model._exception_handlers == [_is_transient_openrouter_error]


def test_openrouter_retries_only_transient_failures() -> None:
    from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
    from pydantic_ai.messages import ModelResponse, TextPart

    from agent.runtime import _is_transient_openrouter_error, _is_upstream_error_response

    assert _is_transient_openrouter_error(ModelHTTPError(502, "m"))
    assert _is_transient_openrouter_error(ModelHTTPError(429, "m"))
    assert not _is_transient_openrouter_error(ModelHTTPError(400, "m"))
    assert not _is_transient_openrouter_error(ModelHTTPError(402, "m"))
    assert _is_transient_openrouter_error(ModelAPIError("m", "no completion"))
    assert not _is_transient_openrouter_error(ValueError("bad"))
    assert _is_upstream_error_response(ModelResponse(parts=[TextPart("")], finish_reason="error"))
    assert not _is_upstream_error_response(ModelResponse(parts=[TextPart("hi")], finish_reason="stop"))


def _upstream_error(_messages, _info):
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart("")], finish_reason="error")


def _hello(_messages, _info):
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart("hello")], finish_reason="stop")


def _retrying(*functions):
    from pydantic_ai.models.fallback import FallbackModel

    from agent.runtime import _is_transient_openrouter_error, _is_upstream_error_response

    return FallbackModel(
        *(FunctionModel(function) for function in functions),
        fallback_on=[_is_transient_openrouter_error, _is_upstream_error_response],
    )


def test_an_upstream_error_response_is_retried_instead_of_failing_the_turn() -> None:
    runtime = PydanticAIAgentRuntime(model=_retrying(_upstream_error, _hello))
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="HI my name is Minh"))
    assert outcome.status == "completed"


def test_exhausted_upstream_retries_are_a_provider_error_not_invalid_output() -> None:
    from application.ports.agent_runtime import AgentProviderError

    runtime = PydanticAIAgentRuntime(
        model=_retrying(_upstream_error, _upstream_error, _upstream_error))
    with pytest.raises(AgentProviderError):
        runtime.run_turn(AgentTurnRequestV1(prompt="HI my name is Minh"))


def test_anthropic_model_uses_the_explicit_agent_runtime_key() -> None:
    runtime = PydanticAIAgentRuntime(
        config=AgentRuntimeConfig(
            model="anthropic:claude-haiku-4-5-20251001", api_key="test-key"
        )
    )

    assert runtime._model.__class__.__name__ == "AnthropicModel"


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


def test_plain_text_becomes_a_prose_only_grounded_answer() -> None:
    """Story 5.7: text is accepted so the provider is not forced into
    tool_choice="required", under which a model answering in text looped until
    the upstream stream broke."""
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content=" Hi Minh, how can I help? ")])
        ),
        answer_type=GroundedAnswerV1,
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="HI my name is Minh"))
    assert outcome.status == "completed"
    assert outcome.answer == GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="Hi Minh, how can I help?"),))


def test_plain_text_with_an_uncited_numeral_is_still_rejected_with_preserved_cause() -> None:
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content="There are 24 workers.")])
        ),
        answer_type=GroundedAnswerV1,
    )
    with pytest.raises(AgentRuntimeError) as exc_info:
        runtime.run_turn(AgentTurnRequestV1(prompt="how many workers?"))
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
    assert outcome.usage is not None
    assert outcome.usage.requests == 1
    assert outcome.usage.input_tokens > 0


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


def _stub_draft_module():
    from types import SimpleNamespace

    from application.capabilities.scheduling_draft import scheduling_draft_module

    return replace(scheduling_draft_module(),
                   handler=lambda deps, request, manifest: SimpleNamespace(result_id="draft-abc"))


def _draft_call():
    return ModelResponse(parts=[ToolCallPart(
        tool_name="scheduling_draft",
        args=json.dumps({"request": {"constraints": []}}),
        tool_call_id="draft-call-1",
    )])


def test_a_draft_created_this_turn_must_be_returned_as_the_draft_output() -> None:
    """Story 5.7 lesson 14: prose "Created a draft" after scheduling_draft saved nothing."""
    seen_retry = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        responses = [m for m in messages if isinstance(m, ModelResponse)]
        if not responses:
            return _draft_call()
        if len(responses) == 1:
            return ModelResponse(parts=[TextPart(content="Created a reversible draft.")])
        seen_retry.append(True)
        return ModelResponse(parts=[ToolCallPart(
            tool_name="draft", args=json.dumps({"draft_id": "draft-abc"}), tool_call_id="out-1")])

    runtime = _runtime(model=FunctionModel(model), capabilities=(_stub_draft_module(),),
                       answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="Keep that worker off that task in a draft"))
    assert seen_retry == [True]
    assert outcome.draft == DraftProposalV1(draft_id="draft-abc")


def test_prose_never_stands_in_for_a_draft_the_model_did_not_create() -> None:
    """The prose claim alone must not become a success. (A draft that WAS
    created is recovered instead -- see the unusable-final-message test below.)"""
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="Created a reversible draft.")])

    runtime = _runtime(model=FunctionModel(model), capabilities=(_stub_draft_module(),),
                       answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="Keep that worker off that task in a draft"))
    assert outcome.draft is None
    assert outcome.answer == GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="Created a reversible draft."),))


def test_only_a_draft_from_the_current_prompt_requires_the_draft_output() -> None:
    from pydantic_ai.messages import UserPromptPart

    from agent.runtime import _latest_draft_id_this_run

    earlier_turn = [
        ModelRequest(parts=[UserPromptPart(content="make a draft")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="scheduling_draft",
                                           content={"draft_id": "old"}, tool_call_id="a")]),
    ]
    current = [ModelRequest(parts=[UserPromptPart(content="show me the draft")])]
    assert _latest_draft_id_this_run(earlier_turn) == "old"
    assert _latest_draft_id_this_run(earlier_turn + current) is None
    created_now = current + [ModelRequest(parts=[ToolReturnPart(
        tool_name="scheduling_draft", content={"draft_id": "new"}, tool_call_id="b")])]
    assert _latest_draft_id_this_run(earlier_turn + created_now) == "new"


def test_plain_text_may_copy_a_numeral_from_the_planners_message() -> None:
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content="Capped at 40 hours.")])),
        answer_type=GroundedAnswerV1,
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="cap that worker at 40 hours"))
    assert outcome.answer == GroundedAnswerV1(segments=(GroundedProseSegmentV1(text="Capped at 40 hours."),))


def test_a_rejected_reply_cannot_vouch_for_its_own_numeral_on_retry() -> None:
    """The retry prompt quotes the offending numeral; it must not become trusted."""
    runtime = _runtime(
        model=FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content="There are 24 workers.")])),
        answer_type=GroundedAnswerV1,
    )
    with pytest.raises(AgentRuntimeError):
        runtime.run_turn(AgentTurnRequestV1(prompt="cap that worker at 40 hours"))


def test_a_claim_citing_no_calculation_from_this_turn_is_corrected_in_loop() -> None:
    from application.contracts.grounding import ClaimArgumentsV1, ClaimProposalV1

    attempts = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        attempts.append(len(attempts))
        answer = GroundedAnswerV1(segments=(
            GroundedProseSegmentV1(text="The draft keeps that worker off that task."),
            *((ClaimProposalV1(metric="worker_count", arguments=ClaimArgumentsV1(), result_id=""),)
              if len(attempts) == 1 else ()),
        ))
        return ModelResponse(parts=[ToolCallPart(
            tool_name="final_result", args=answer.__class__.__name__ and _answer_json(answer),
            tool_call_id=f"out-{len(attempts)}")])

    runtime = _runtime(model=FunctionModel(model), answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="show me what you put in the draft"))
    assert len(attempts) == 2, "the uncited claim must be corrected inside the run"
    assert outcome.answer == GroundedAnswerV1(segments=(
        GroundedProseSegmentV1(text="The draft keeps that worker off that task."),))


def _answer_json(answer) -> str:
    return json.dumps(asdict(answer))


def test_a_draft_created_this_turn_survives_an_unusable_final_message() -> None:
    """live-suite-v2-acceptance-b C8/C9: the draft was saved, then discarded
    because the model never produced a usable final message."""
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return _draft_call()
        return ModelResponse(parts=[TextPart(content="Created a reversible draft.")])

    runtime = _runtime(model=FunctionModel(model), capabilities=(_stub_draft_module(),),
                       answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="cap that worker at 40 hours in a draft"))
    assert outcome.status == "completed"
    assert outcome.draft == DraftProposalV1(draft_id="draft-abc")


@pytest.mark.parametrize("text", [
    "**A Pick | Picking Ambient** has <claim> staffed minutes over the horizon.",
    "There are  workers in the scenario.",
])
def test_prose_left_with_a_gap_where_a_claim_belongs_is_corrected_in_loop(text) -> None:
    """live-suite-v2-acceptance-c: the model wrote the sentence around a claim
    it never emitted, so the planner saw no number at all."""
    attempts = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        attempts.append(len(attempts))
        answer = GroundedAnswerV1(segments=(GroundedProseSegmentV1(
            text=text if len(attempts) == 1 else "That task has staffed time recorded."),))
        return ModelResponse(parts=[ToolCallPart(
            tool_name="final_result", args=_answer_json(answer), tool_call_id=f"o{len(attempts)}")])

    runtime = _runtime(model=FunctionModel(model), answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="how many minutes are staffed?"))
    assert len(attempts) == 2
    assert outcome.answer == GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="That task has staffed time recorded."),))


def test_a_claim_bearing_answer_may_still_space_its_prose_normally() -> None:
    from application.contracts.grounding import ClaimArgumentsV1, ClaimProposalV1

    answer = GroundedAnswerV1(segments=(
        GroundedProseSegmentV1(text="There are "),
        ClaimProposalV1(metric="worker_count", arguments=ClaimArgumentsV1(), result_id="r1"),
        GroundedProseSegmentV1(text=" workers."),
    ))
    runtime = _runtime(
        model=FunctionModel(lambda messages, info: ModelResponse(parts=[ToolCallPart(
            tool_name="final_result", args=_answer_json(answer), tool_call_id="o1")])),
        answer_type=GroundedAnswerV1)
    assert runtime.run_turn(AgentTurnRequestV1(prompt="how many workers?")).answer == answer


@pytest.mark.parametrize("text", [
    "Hello.  How can I help with your schedule?",   # ordinary sentence spacing
    "The draft keeps that worker off that task.",
])
def test_ordinary_prose_is_not_mistaken_for_a_dropped_claim(text) -> None:
    runtime = _runtime(
        model=FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(content=text)])),
        answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="hi"))
    assert outcome.answer == GroundedAnswerV1(segments=(GroundedProseSegmentV1(text=text),))


def _claim_answer(result_id: str) -> GroundedAnswerV1:
    from application.contracts.grounding import ClaimArgumentsV1, ClaimProposalV1

    return GroundedAnswerV1(segments=(
        GroundedProseSegmentV1(text="There are "),
        ClaimProposalV1(metric="worker_count", arguments=ClaimArgumentsV1(), result_id=result_id),
        GroundedProseSegmentV1(text=" workers."),
    ))


REAL_RESULT_ID = "d7481a87240baee0bdf74d774a2f092090eb5a947670bbee08960b45f34c819a"


def _compute_stub_module():
    from types import SimpleNamespace

    from application.capabilities.scheduling_compute import scheduling_compute_module

    return replace(
        scheduling_compute_module(),
        handler=lambda deps, request, manifest: SimpleNamespace(
            result_id=REAL_RESULT_ID, metric="worker_count", unit="workers",
            consumed_row_count=1, value=10, arguments=request.arguments,
            evidence_refs=(), scenario_version_id=None),
        model_facing_view=lambda result: {"result_id": result.result_id, "metric": "worker_count",
                                          "unit": "workers", "matched": "some"},
    )


def _compute_then(answers):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        responses = [m for m in messages if isinstance(m, ModelResponse)]
        if not responses:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="scheduling_compute",
                args=json.dumps({"request": {"metric": "worker_count", "arguments": {}}}),
                tool_call_id="c1")])
        answer = answers[min(len(responses) - 1, len(answers) - 1)]
        return ModelResponse(parts=[ToolCallPart(
            tool_name="final_result", args=_answer_json(answer), tool_call_id=f"o{len(responses)}")])
    return model


def test_a_mistyped_result_id_is_corrected_in_loop() -> None:
    """live-suite-v2-acceptance-f: the model copied a 64-character hash as 63
    and as 68 characters, and the gate could only report missing_evidence."""
    runtime = _runtime(
        model=FunctionModel(_compute_then([_claim_answer(REAL_RESULT_ID[:-1]),
                                           _claim_answer(REAL_RESULT_ID)])),
        capabilities=(_compute_stub_module(),), answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="how many workers?"))
    assert outcome.answer == _claim_answer(REAL_RESULT_ID)


def test_an_unrelated_result_id_still_reaches_the_gate_as_missing_evidence() -> None:
    """golden case grounding-missing-evidence depends on this path staying open."""
    invented = _claim_answer("f" * 64)
    runtime = _runtime(model=FunctionModel(_compute_then([invented])),
                       capabilities=(_compute_stub_module(),), answer_type=GroundedAnswerV1)
    assert runtime.run_turn(AgentTurnRequestV1(prompt="how many workers?")).answer == invented


def test_a_sentence_that_announces_a_number_and_stops_is_corrected_in_loop() -> None:
    """live-suite-v2-measurement-final C5: 'Staffed minutes for <task>:' with no claim."""
    attempts = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        attempts.append(len(attempts))
        text = ("Staffed minutes for C Fork | Grid P 8GR:" if len(attempts) == 1
                else "That task has staffed time recorded.")
        return ModelResponse(parts=[TextPart(content=text)])

    runtime = _runtime(model=FunctionModel(model), answer_type=GroundedAnswerV1)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="how many minutes are staffed?"))
    assert len(attempts) == 2
    assert outcome.answer == GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="That task has staffed time recorded."),))


def test_a_lead_in_followed_by_more_prose_is_not_a_dropped_claim() -> None:
    """live-suite-final-measurement C7: 'Active constraints:' followed by the
    list was rejected until the turn ran out of retries."""
    answer = GroundedAnswerV1(segments=(
        GroundedProseSegmentV1(text="Locks: none are active. Active constraints:"),
        GroundedProseSegmentV1(text="- Maximum agency shifts: 6 weekly."),
    ))
    runtime = _runtime(
        model=FunctionModel(lambda messages, info: ModelResponse(parts=[ToolCallPart(
            tool_name="final_result", args=_answer_json(answer), tool_call_id="o1")])),
        answer_type=GroundedAnswerV1)
    assert runtime.run_turn(
        AgentTurnRequestV1(prompt="what locks and constraints are active? 6 56")).answer == answer


def test_every_in_loop_correction_asks_for_a_complete_answer() -> None:
    """live-suite-final-measurement C2 answered a retry with 'Correction: ...',
    so the planner received a delta instead of the answer."""
    from agent import runtime as runtime_module

    source = Path(runtime_module.__file__).read_text(encoding="utf-8")
    assert source.count("+ _COMPLETE_ANSWER") == source.count("raise ModelRetry(")
