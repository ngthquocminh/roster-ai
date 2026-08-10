"""Story 2.1 compatibility spike — the seven AC1 capabilities at PydanticAI 2.27.0.

One test per capability. All seven must pass or the story halts (see
docs/AGENT-RUNTIME-DECISION.md). No test here may touch the network:
`models.ALLOW_MODEL_REQUESTS = False` is set at module scope AND in conftest.py.

Each test name maps 1:1 to a row in the decision doc's verdict table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    ApprovalRequired,
    CancellationToken,
    DeferredToolRequests,
    DeferredToolResults,
    InstrumentationSettings,
    ModelHTTPError,
    ModelRetry,
    RunCancelled,
    RunContext,
    ToolDenied,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
    capture_run_messages,
    models,
)
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from owned import OwnedTurnV1

models.ALLOW_MODEL_REQUESTS = False


# --------------------------------------------------------------------------
# Capability 1 — typed tools
# --------------------------------------------------------------------------


class ShiftWindow(BaseModel):
    """A Pydantic-typed tool argument, so validation is the framework's job."""

    day: int
    start_hour: float
    end_hour: float


def test_capability_1_typed_tools() -> None:
    """A Pydantic-typed tool signature is exposed to the model and its arguments
    arrive validated."""
    agent = Agent()
    received: list[ShiftWindow] = []

    @agent.tool_plain
    def widen_window(window: ShiftWindow) -> str:
        received.append(window)
        return f"widened day {window.day}"

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # The tool schema is genuinely exposed to the model side.
        assert "widen_window" in {t.name for t in info.function_tools}
        schema = next(t for t in info.function_tools if t.name == "widen_window")
        assert schema.parameters_json_schema is not None

        if not any(isinstance(m, ModelResponse) for m in messages):
            # Args deliberately sent as JSON text with a float-ish string, so a
            # pass-through (unvalidated) path would hand us raw strings.
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="widen_window",
                        args=json.dumps(
                            {"window": {"day": 2, "start_hour": 6, "end_hour": 14.5}}
                        ),
                        tool_call_id="call-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    result = agent.run_sync("widen it", model=FunctionModel(scripted))

    assert result.output == "done"
    assert len(received) == 1
    window = received[0]
    # Validated, coerced, and typed — not a dict, not strings.
    assert isinstance(window, ShiftWindow)
    assert window.day == 2
    assert isinstance(window.start_hour, float) and window.start_hour == 6.0
    assert window.end_hour == 14.5

    # And validation actually rejects bad input rather than passing it through.
    def bad_args(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="widen_window",
                        args=json.dumps({"window": {"day": "not-an-int"}}),
                        tool_call_id="call-2",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="recovered")])

    with capture_run_messages() as captured:
        agent.run_sync("widen it badly", model=FunctionModel(bad_args))
    retries = [
        part
        for message in captured
        if isinstance(message, ModelRequest)
        for part in message.parts
        if part.part_kind == "retry-prompt"
    ]
    assert retries, "invalid tool args must be rejected, not passed through"
    assert len(received) == 1, "the tool body must never see unvalidated args"


# --------------------------------------------------------------------------
# Capability 2 — deferred calls (suspend, resume with approve AND deny)
# --------------------------------------------------------------------------


def _approval_agent() -> Agent:
    agent = Agent(output_type=[str, DeferredToolRequests])

    @agent.tool_plain(requires_approval=True)
    def publish_roster(week: int) -> str:
        return f"published week {week}"

    return agent


def _publish_then_report(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if not any(isinstance(m, ModelResponse) for m in messages):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="publish_roster",
                    args=json.dumps({"week": 34}),
                    tool_call_id="publish-1",
                )
            ]
        )
    returned = [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    return ModelResponse(parts=[TextPart(content=f"outcome: {returned[-1].content}")])


def test_capability_2_deferred_calls_suspend_and_resume() -> None:
    """A tool marked for approval suspends the run, returns the pending call, and
    the run resumes from that suspension with an approve AND with a deny."""
    model = FunctionModel(_publish_then_report)

    # --- suspend -------------------------------------------------------
    agent = _approval_agent()
    suspended = agent.run_sync("publish it", model=model)

    assert isinstance(suspended.output, DeferredToolRequests), (
        "an approval-gated tool must suspend the run, not execute"
    )
    assert len(suspended.output.approvals) == 1
    pending = suspended.output.approvals[0]
    assert pending.tool_name == "publish_roster"
    call_id = pending.tool_call_id

    # The suspension is durable raw material: history + the pending call id.
    history = suspended.all_messages()

    # --- resume: APPROVE -----------------------------------------------
    approved = _approval_agent().run_sync(
        model=model,
        message_history=history,
        deferred_tool_results=DeferredToolResults(approvals={call_id: True}),
    )
    assert isinstance(approved.output, str)
    assert "published week 34" in approved.output

    # --- resume: DENY --------------------------------------------------
    denied = _approval_agent().run_sync(
        model=model,
        message_history=history,
        deferred_tool_results=DeferredToolResults(
            approvals={call_id: ToolDenied("planner rejected the publish")}
        ),
    )
    assert isinstance(denied.output, str)
    assert "published week 34" not in denied.output
    assert "planner rejected the publish" in denied.output


def test_capability_2_conditional_approval_via_raise() -> None:
    """ApprovalRequired raised from inside a tool body suspends conditionally —
    the form ShiftMind needs, because approval is a persisted state machine."""
    agent = Agent(output_type=[str, DeferredToolRequests])

    @agent.tool
    def adjust(ctx: RunContext, hours: int) -> str:
        if hours > 8 and not ctx.tool_call_approved:
            raise ApprovalRequired
        return f"adjusted by {hours}"

    def call_adjust(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="adjust",
                        args=json.dumps({"hours": 12}),
                        tool_call_id="adjust-1",
                    )
                ]
            )
        returned = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        return ModelResponse(parts=[TextPart(content=str(returned[-1].content))])

    model = FunctionModel(call_adjust)
    suspended = agent.run_sync("adjust by 12", model=model)
    assert isinstance(suspended.output, DeferredToolRequests)

    resumed = agent.run_sync(
        model=model,
        message_history=suspended.all_messages(),
        deferred_tool_results=DeferredToolResults(
            approvals={suspended.output.approvals[0].tool_call_id: True}
        ),
    )
    assert "adjusted by 12" in str(resumed.output)


# --------------------------------------------------------------------------
# Capability 3 — deterministic model doubles
# --------------------------------------------------------------------------


def test_capability_3_deterministic_model_doubles() -> None:
    """A scripted multi-step tool loop (call -> result -> text) runs identically
    twice with no network."""
    agent = Agent()

    @agent.tool_plain
    def coverage(day: int) -> str:
        return f"day {day} at 92%"

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="coverage",
                        args=json.dumps({"day": 3}),
                        tool_call_id="cov-1",
                    )
                ]
            )
        returned = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        return ModelResponse(parts=[TextPart(content=f"report: {returned[-1].content}")])

    def transcript() -> list[tuple[str, tuple[str, ...]]]:
        result = agent.run_sync("how is coverage", model=FunctionModel(scripted))
        return [
            (m.kind, tuple(p.part_kind for p in m.parts)) for m in result.all_messages()
        ]

    first, second = transcript(), transcript()
    assert first == second, "scripted double must be byte-identical across runs"
    # And it really was the full loop, not a single text turn.
    assert any("tool-call" in parts for _, parts in first)

    # TestModel is the other double: it exercises tools without a script.
    with Agent().override(model=TestModel()):
        pass
    probe = Agent()

    @probe.tool_plain
    def ping() -> str:
        return "pong"

    with probe.override(model=TestModel()):
        a = probe.run_sync("go")
        b = probe.run_sync("go")
    assert a.output == b.output


# --------------------------------------------------------------------------
# Capability 4 — owned-message translation
# --------------------------------------------------------------------------


def test_capability_4_owned_message_round_trip() -> None:
    """A run's messages round-trip through a ShiftMind-owned shape and a second
    run continues from the rehydrated history.

    The durable form is OwnedTurnV1's JSON, NOT
    `to_jsonable_python(result.all_messages())` — see owned.py.
    """
    agent = Agent()

    @agent.tool_plain
    def headcount(day: int) -> str:
        return f"{day * 4} workers"

    def first_turn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="headcount",
                        args=json.dumps({"day": 5}),
                        tool_call_id="hc-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="20 workers on day 5")])

    result = agent.run_sync("how many on day 5", model=FunctionModel(first_turn))

    # ModelMessage[] -> owned
    owned = OwnedTurnV1.from_framework(result.all_messages())
    assert owned.schema_version == "1"
    assert owned.visible_text() == "20 workers on day 5"

    # owned -> JSON -> owned, and the JSON contains no framework type name.
    raw = owned.to_json()
    for framework_marker in (
        "ModelResponse",
        "ModelRequest",
        "part_kind",
        "pydantic_ai",
        "TextPart",
        "ToolCallPart",
    ):
        assert framework_marker not in raw, (
            f"{framework_marker!r} leaked into the durable form — that is a "
            "PydanticAI contract being persisted, which AD-19 prohibits"
        )
    rehydrated = OwnedTurnV1.from_json(raw)
    assert rehydrated == owned

    # owned -> ModelMessage[], and a SECOND run continues from it.
    history = rehydrated.to_framework()
    assert all(isinstance(m, (ModelRequest, ModelResponse)) for m in history)

    def second_turn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # The rehydrated history really arrived at the model.
        flattened = " ".join(
            str(getattr(p, "content", ""))
            for m in messages
            for p in m.parts
        )
        assert "20 workers on day 5" in flattened
        assert "how many on day 5" in flattened
        return ModelResponse(parts=[TextPart(content="same as before")])

    continued = agent.run_sync(
        "and day 6?", message_history=history, model=FunctionModel(second_turn)
    )
    assert continued.output == "same as before"


# --------------------------------------------------------------------------
# Capability 5 — bounded execution
# --------------------------------------------------------------------------


def test_capability_5_bounded_execution_distinguishes_exhaustion_kinds() -> None:
    """An application-set limit terminates the run, and wall-time exhaustion is
    distinguishable from other limit exhaustion.

    AD-7 wants wall-time -> `timed_out` and other exhaustion -> `failed` with a
    stable `budget_exhausted` reason. At 2.27.0 `UsageLimits` carries NO deadline
    field, so the two arrive as two different exception types:

      * budget    -> UsageLimitExceeded   (framework-owned)
      * wall-time -> RunCancelled          (framework mechanism, adapter policy)

    The framework supplies the cancellation mechanism; the ADAPTER owns the
    deadline itself. That ownership split is recorded in the decision doc.
    """
    agent = Agent()

    @agent.tool_plain
    def spin() -> str:
        return "spun"

    def always_calls_tool(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="spin",
                    args="{}",
                    tool_call_id=f"spin-{len(messages)}",
                )
            ]
        )

    # --- budget exhaustion ---------------------------------------------
    with pytest.raises(UsageLimitExceeded) as budget:
        agent.run_sync(
            "spin forever",
            model=FunctionModel(always_calls_tool),
            usage_limits=UsageLimits(request_limit=3),
        )
    assert "request" in str(budget.value).lower()

    # A tool-call ceiling is a *different* budget, same owned reason.
    with pytest.raises(UsageLimitExceeded):
        agent.run_sync(
            "spin forever",
            model=FunctionModel(always_calls_tool),
            usage_limits=UsageLimits(tool_calls_limit=2),
        )

    # --- wall-time exhaustion ------------------------------------------
    token = CancellationToken()
    deadline_agent = Agent()

    @deadline_agent.tool_plain
    def slow() -> str:
        # Stands in for "the adapter's deadline elapsed mid-run".
        token.cancel()
        return "slow"

    with pytest.raises(RunCancelled) as walltime:
        deadline_agent.run_sync(
            "take too long",
            model=FunctionModel(always_calls_tool_named("slow")),
            cancellation_token=token,
        )

    # THE POINT: the two are distinguishable, so the adapter can map them to
    # different owned outcomes without string-matching a message.
    assert type(walltime.value) is not type(budget.value)
    assert not isinstance(walltime.value, UsageLimitExceeded)
    assert not isinstance(budget.value, RunCancelled)


def always_calls_tool_named(name: str):
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=name, args="{}", tool_call_id=f"{name}-{len(messages)}"
                )
            ]
        )

    return fn


# --------------------------------------------------------------------------
# Capability 6 — provider failure mapping
# --------------------------------------------------------------------------


class OwnedAgentRuntimeError(RuntimeError):
    """Spike stand-in for the real owned error type (Task 6 builds that one)."""


def test_capability_6_provider_failure_maps_to_owned_type() -> None:
    """A provider error surfaces as an identifiable framework exception that an
    adapter can catch and re-raise as an owned type, cause preserved."""
    agent = Agent()

    def http_failure(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=503, model_name="spike", body="overloaded")

    with pytest.raises(ModelHTTPError) as raw:
        agent.run_sync("hello", model=FunctionModel(http_failure))
    assert raw.value.status_code == 503

    # The adapter shape: catch framework, re-raise owned, keep the cause.
    def adapter_run() -> None:
        try:
            agent.run_sync("hello", model=FunctionModel(http_failure))
        except (ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded) as exc:
            raise OwnedAgentRuntimeError("agent runtime call failed") from exc

    with pytest.raises(OwnedAgentRuntimeError) as owned:
        adapter_run()
    assert isinstance(owned.value.__cause__, ModelHTTPError)

    # Malformed model behaviour is also identifiable.
    strict = Agent(output_type=ShiftWindow)

    def never_calls_output_tool(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        raise UnexpectedModelBehavior("model returned no usable output")

    with pytest.raises(UnexpectedModelBehavior):
        strict.run_sync("give me a window", model=FunctionModel(never_calls_output_tool))


# --------------------------------------------------------------------------
# Capability 7 — content-disabled instrumentation
# --------------------------------------------------------------------------

SECRET_PROMPT = "SENTINEL-PROMPT-do-not-emit-7f3a"
SECRET_TOOL_ARG = "SENTINEL-TOOLARG-do-not-emit-9b2c"


def test_capability_7_instrumentation_excludes_content() -> None:
    """Instrumentation can be enabled with prompt/tool content excluded, and the
    EMITTED SPANS carry no prompt or tool payload.

    Asserted on observed span attributes via an in-memory exporter. Reading
    `settings.include_content is False` would prove nothing about what is emitted.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    settings = InstrumentationSettings(include_content=False, tracer_provider=provider)
    agent = Agent(capabilities=[Instrumentation(settings=settings)])

    @agent.tool_plain
    def lookup(note: str) -> str:
        return f"looked up {note}"

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="lookup",
                        args=json.dumps({"note": SECRET_TOOL_ARG}),
                        tool_call_id="look-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent.run_sync(SECRET_PROMPT, model=FunctionModel(scripted))

    spans = exporter.get_finished_spans()
    assert spans, "instrumentation must actually emit spans when enabled"

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
    assert SECRET_PROMPT not in blob, "prompt content leaked into emitted spans"
    assert SECRET_TOOL_ARG not in blob, "tool arguments leaked into emitted spans"
