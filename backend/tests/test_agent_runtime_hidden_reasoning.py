"""Hidden reasoning is discarded — AC4, AD-15, FR20 precursor.

AD-15: prompts, model output, and tool output are untrusted; adapters discard
provider hidden-reasoning parts and persist only visible messages, owned
summaries, typed recovery data, and evidence links.

Two halves are asserted, and BOTH matter:

  * the negative — a sentinel planted in a `ThinkingPart` reaches no owned or
    emitted surface;
  * the positive — planner-visible content, typed recovery data, and the
    application-owned summary DO survive translation.

A test that only proved absence would also pass if the adapter discarded
everything, which would be a different bug wearing the same green tick.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import models
from pydantic_ai.messages import (
    CompactionPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent.runtime import PydanticAIAgentRuntime
from agent.translate import to_owned_turn
from application.contracts.agent_runtime import AgentTurnRequestV1

models.ALLOW_MODEL_REQUESTS = False

# If any of these strings escapes, the story's central invariant is broken.
THINKING_SENTINEL = "SENTINEL-THINKING-do-not-persist-4e81"
COMPACTION_SENTINEL = "SENTINEL-COMPACTION-do-not-persist-6b23"

VISIBLE_TEXT = "Coverage on day 3 is 92 percent."
TOOL_LABEL = "day3"


def _thinking_then_visible(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    """A response carrying hidden reasoning alongside legitimate content."""
    if not any(isinstance(m, ModelResponse) for m in messages):
        return ModelResponse(
            parts=[
                # Hidden reasoning — must never survive.
                ThinkingPart(content=THINKING_SENTINEL),
                # A DIFFERENT non-whitelisted kind, deliberately not named
                # anywhere in agent/translate.py — see the whitelist test below.
                CompactionPart(content=COMPACTION_SENTINEL),
                # Legitimate typed recovery data — must survive.
                ToolCallPart(
                    tool_name="shiftmind_demonstration",
                    args=json.dumps({"payload": {"label": TOOL_LABEL, "repeat": 1}}),
                    tool_call_id="think-1",
                ),
            ]
        )
    return ModelResponse(
        parts=[
            ThinkingPart(content=THINKING_SENTINEL),
            TextPart(content=VISIBLE_TEXT),
        ]
    )


def _run_with_spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    runtime = PydanticAIAgentRuntime(
        model=FunctionModel(_thinking_then_visible), tracer_provider=provider
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="how is day 3 coverage?"))
    return outcome, exporter.get_finished_spans()


def test_sentinel_reaches_no_owned_or_emitted_surface() -> None:
    """The negative half — every surface the story enumerates."""
    outcome, spans = _run_with_spans()
    assert outcome.status == "completed"

    # 1. planner-visible content
    assert THINKING_SENTINEL not in (outcome.output_text or "")

    # 2. the owned message record
    owned_blob = json.dumps(asdict(outcome.turn))
    assert THINKING_SENTINEL not in owned_blob

    # 3. the application-owned summary
    assert THINKING_SENTINEL not in (outcome.summary or "")

    # 4. typed recovery data
    for result in outcome.tool_results:
        assert THINKING_SENTINEL not in result.content
        assert THINKING_SENTINEL not in result.tool_name

    # 5. the JSON round-trip of the whole outcome contract
    outcome_blob = json.dumps(asdict(outcome))
    assert THINKING_SENTINEL not in outcome_blob

    # 6. emitted span attributes
    assert spans, "instrumentation must emit spans, or surface 6 is untested"
    span_blob = json.dumps(
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
    assert THINKING_SENTINEL not in span_blob


def test_legitimate_content_survives_translation() -> None:
    """The positive half — without this, discarding everything would pass."""
    outcome, _ = _run_with_spans()

    # planner-visible content survived
    assert outcome.output_text == VISIBLE_TEXT
    assert VISIBLE_TEXT in outcome.turn.visible_text()

    # the application-owned summary was produced and is meaningful
    assert outcome.summary
    assert VISIBLE_TEXT in outcome.summary

    # typed recovery data survived: the tool ran and its result was recorded
    assert outcome.tool_results
    assert any(TOOL_LABEL in r.content for r in outcome.tool_results)

    # the owned transcript kept the tool call as a typed part, not as prose
    tool_calls = [
        part
        for message in outcome.turn.messages
        for part in message.parts
        if part.kind == "tool_call"
    ]
    assert tool_calls
    assert tool_calls[0].tool_name == "shiftmind_demonstration"


def test_translation_is_a_whitelist_not_a_thinkingpart_blacklist() -> None:
    """The discard must not depend on naming `ThinkingPart`.

    `CompactionPart` is a real 2.27.0 response part that carries model-generated
    content and is named NOWHERE in agent/translate.py. It is dropped anyway,
    because translation enumerates what it keeps rather than what it rejects.
    That is the property that survives the framework adding a new
    reasoning-bearing part kind next release.
    """
    response = ModelResponse(
        parts=[
            ThinkingPart(content=THINKING_SENTINEL),
            CompactionPart(content=COMPACTION_SENTINEL),
            TextPart(content=VISIBLE_TEXT),
        ]
    )
    turn = to_owned_turn([ModelRequest(parts=[]), response])
    blob = json.dumps(asdict(turn))

    assert THINKING_SENTINEL not in blob
    assert COMPACTION_SENTINEL not in blob, (
        "a part kind the translator never names was still admitted — that is a "
        "blacklist, and it will leak the next reasoning part the framework adds"
    )
    assert VISIBLE_TEXT in blob

    # Only whitelisted kinds exist in the owned record.
    kinds = {part.kind for message in turn.messages for part in message.parts}
    assert kinds <= {"text", "tool_call", "tool_result"}


def test_hidden_reasoning_is_dropped_from_rehydrated_history_too() -> None:
    """Resuming from an owned transcript cannot reintroduce the sentinel."""
    outcome, _ = _run_with_spans()

    replayed = PydanticAIAgentRuntime(
        model=FunctionModel(_thinking_then_visible)
    ).run_turn(AgentTurnRequestV1(prompt="again", history=outcome.turn))

    assert THINKING_SENTINEL not in json.dumps(asdict(replayed))


def test_sentinel_would_be_caught_if_it_leaked() -> None:
    """The guard's own smoke test: prove the assertion can fail.

    Translating a response whose VISIBLE text contains the sentinel must produce
    an owned record that contains it. If this test passed while the sentinel was
    absent, the assertions above would be vacuous — they would pass against an
    adapter that discarded all content.
    """
    leaked = ModelResponse(parts=[TextPart(content=f"oops {THINKING_SENTINEL}")])
    turn = to_owned_turn([leaked])
    assert THINKING_SENTINEL in json.dumps(asdict(turn))
