"""Agent turn routing: prompt split, route decision, Jev router, runtime paths."""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adapters.grounding import factory
from adapters.grounding.factory import create_turn_router
from adapters.grounding.jev_checker import OPENROUTER_DECISIONS_ENDPOINT, TYPESAFE_ENDPOINT
from adapters.grounding.jev_router import JevTurnRouter
from adapters.telemetry import span_policy
from agent import scheduling_instructions as prompts
from api.deps import get_agent_runtime_factory, get_settings
from api.main import app
from agent.runtime import (
    ANSWER_OUTPUT_TOOL, OUT_OF_SCOPE_REFUSAL, REFUSAL_OUTPUT_TOOL, PydanticAIAgentRuntime,
    create_agent_runtime,
)
from application.contracts.activity import (
    AgentResponseActivityV1, DraftActivityV1, PlannerMessageActivityV1,
)
from application.contracts.agent_runtime import AgentRunOutcomeV1, AgentTurnRequestV1
from application.contracts.dialogue import RefusalV1
from application.contracts.grounding import (
    GroundedAnswerV2, GroundedProseSegmentV1, GroundedResponseV1,
)
from application.ports.turn_router import TURN_ROUTES, TurnRouteResultV1, TurnRouteStateV1
from application.use_cases.route_turn import (
    LATEST_MESSAGE_CHAR_LIMIT, MESSAGE_CHAR_LIMIT, TurnRouteDecisionV1, decide_route,
    route_state,
)
from settings import InvalidFlagError, default_settings
from tests.test_conversations_api import (  # noqa: F401  (conversation_client is a fixture)
    _Runtime, _headers, _with_workflow_context_reader, conversation_client,
)

#: sha256 of `SCHEDULING_ASSISTANT_INSTRUCTIONS` minus Scope. Pinned before routing
#: (commit f44d122) to prove the split changed nothing; re-pinned when the
#: "Saying what the baseline is now, or where its decision record is" workflow was
#: added, and again when summaries were kept to the subject the planner named (live run
#: ad89854, A:6), when a named family was required in metric arguments (9b8dad2, C:3), and
#: for Story 5.11's one-working-draft rewrite (Revising a draft, the discard section, the
#: Tool routing line, "Saying what the baseline is now" step 2), and for Story 5.12's undo
#: rule (reverse the previous change; live smoke E:4 read "undo" as removing another constraint).
#: Any other prompt edit must re-pin here, deliberately.
TODAYS_PROMPT_SHA256 = "3cd0a0dc53123fa6e49158ae2f2100e6c2eef2bd539e7fda872b5256de2b6c14"


# --- prompt split ------------------------------------------------------------

def test_the_full_path_prompt_minus_scope_is_todays_prompt() -> None:
    full = prompts.SCHEDULING_ASSISTANT_INSTRUCTIONS
    assert full.count(prompts.SCOPE) == 1
    without_scope = full.replace(prompts.SCOPE + "\n\n", "", 1)
    assert hashlib.sha256(without_scope.encode()).hexdigest() == TODAYS_PROMPT_SHA256
    assert prompts.instructions_for("scheduling") == full


def test_the_scheduling_prompt_says_where_a_baseline_decision_record_is() -> None:
    # Live B:10 answered with a bare version id and "if available in the
    # application": the agent knew the approval id and the run, but not the path.
    full = prompts.SCHEDULING_ASSISTANT_INSTRUCTIONS
    workflow = full.split("**Saying what the baseline is now", 1)[1].split("\n\n", 1)[0]
    for needed in ("baseline_schedule_version", "proposal_id", "approval_id", "Runs tab",
                   "Debug details", "Decision provenance", "the baseline it replaced"):
        assert needed.casefold() in workflow.casefold(), needed
    # A direct (no-data) reply never gets it: it has no snapshot to follow.
    assert "Decision provenance" not in prompts.DIRECT_INSTRUCTIONS


def test_special_paths_compose_only_their_sections() -> None:
    headings = lambda text: [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings(prompts.DIRECT_INSTRUCTIONS) == [
        "Scope", "Business context", "ShiftMind workflow",
        "Greetings and capability questions", "Tool routing", "Direct rule",
    ]
    assert headings(prompts.OUT_OF_SCOPE_INSTRUCTIONS) == ["Scope", "Refusal rule"]
    for text in (prompts.DIRECT_INSTRUCTIONS, prompts.OUT_OF_SCOPE_INSTRUCTIONS):
        assert text.startswith("You are ShiftMind's scheduling assistant.")


# --- route decision ------------------------------------------------------------

class _Router:
    name, provider = "scripted", "stub"

    def __init__(self, result: TurnRouteResultV1 | Exception) -> None:
        self.result = result
        self.states: list[TurnRouteStateV1] = []

    def route(self, state: TurnRouteStateV1) -> TurnRouteResultV1:
        self.states.append(state)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _p(scheduling: float, direct: float, out_of_scope: float) -> TurnRouteResultV1:
    return TurnRouteResultV1(probabilities={
        "scheduling": scheduling, "direct": direct, "out_of_scope": out_of_scope})


@pytest.mark.parametrize(("result", "expected"), [
    (_p(0.02, 0.01, 0.97), TurnRouteDecisionV1("out_of_scope", 0.97)),
    (_p(0.04, 0.95, 0.01), TurnRouteDecisionV1("direct", 0.95)),
    (_p(0.9, 0.05, 0.05), TurnRouteDecisionV1("scheduling", 0.9)),
    (_p(0.3, 0.6, 0.1), TurnRouteDecisionV1("scheduling", 0.3)),
    (_p(0.15, 0.0, 0.85), TurnRouteDecisionV1("out_of_scope", 0.85)),
    (_p(0.0, 0.5, 0.5), TurnRouteDecisionV1("scheduling", 0.0)),
    (TurnRouteResultV1(error="timeout"), TurnRouteDecisionV1(error="timeout")),
    (TurnRouteResultV1(error="http_503"), TurnRouteDecisionV1(error="http_503")),
    (TurnRouteResultV1(), TurnRouteDecisionV1(error="bad_response")),
    (RuntimeError("boom"), TurnRouteDecisionV1(error="router_exception")),
])
def test_only_a_confident_special_route_leaves_scheduling(result, expected) -> None:
    decision = decide_route(_Router(result), prompt="x", history=(), threshold=0.85)
    assert decision == expected


def test_no_router_is_scheduling_without_an_error() -> None:
    assert decide_route(None, prompt="sing a song", history=(), threshold=0.85) == (
        TurnRouteDecisionV1())


def _planner(text: str) -> PlannerMessageActivityV1:
    return PlannerMessageActivityV1(
        activity_id=uuid4(), activity_type="planner_message", conversation_id=uuid4(),
        conversation_resource_version=1, scenario_id=uuid4(), scenario_version_id=uuid4(),
        occurred_at=datetime.now(timezone.utc), message_id=uuid4(), text=text)


def _reply(text: str) -> AgentResponseActivityV1:
    return AgentResponseActivityV1(
        activity_id=uuid4(), activity_type="agent_response", conversation_id=uuid4(),
        conversation_resource_version=1, scenario_id=uuid4(), scenario_version_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        response=GroundedResponseV1(segments=(GroundedProseSegmentV1(text=text),)))


def test_the_router_state_is_the_last_exchange_as_truncated_text() -> None:
    history = (_planner("p1"), _reply("r1"), _planner("p2"), _reply("r2"),
               _planner("p3"), _reply("r3" * 400), _planner("   "))
    state = route_state("  hi  " + "x" * 5000, history)
    assert state.message.startswith("hi") and len(state.message) == LATEST_MESSAGE_CHAR_LIMIT
    assert state.previous_planner_messages == ("p2", "p3")
    assert state.previous_agent_replies[0] == "r2"
    assert len(state.previous_agent_replies[1]) == MESSAGE_CHAR_LIMIT


def test_a_draft_counts_as_the_agents_last_reply() -> None:
    draft = DraftActivityV1(
        activity_id=uuid4(), activity_type="draft", conversation_id=uuid4(),
        conversation_resource_version=1, scenario_id=uuid4(), scenario_version_id=uuid4(),
        occurred_at=datetime.now(timezone.utc), proposal_id=uuid4(),
        proposal_version_id=uuid4(), consequence_summary="Caps Ana at 40 hours.")
    state = route_state("yes, do that", (_planner("cap Ana at 40h"), _reply("ok"), draft))
    assert state.previous_agent_replies == ("ok", "Caps Ana at 40 hours.")


# --- factory -------------------------------------------------------------------

def _settings(**overrides):
    base = {"agent_router_mode": "on", "typesafe_api_key": None, "openrouter_api_key": None,
            "agent_runtime_model": "deterministic"}
    return replace(default_settings(), **{**base, **overrides})


def test_the_keyless_suite_pins_the_router_off() -> None:
    assert default_settings().agent_router_mode == "off"
    assert create_turn_router(default_settings()) is None


def test_off_makes_no_router_even_with_a_key() -> None:
    assert create_turn_router(_settings(agent_router_mode="off", typesafe_api_key="k")) is None


def test_a_missing_key_disables_the_router_with_one_warning(caplog) -> None:
    factory._warned.clear()
    with caplog.at_level(logging.WARNING):
        assert create_turn_router(_settings()) is None
        assert create_turn_router(_settings()) is None
    warnings = [r.getMessage() for r in caplog.records if "agent turn router" in r.getMessage()]
    assert warnings == ["agent turn router disabled: no API key for provider openrouter"]


@pytest.mark.parametrize(("overrides", "endpoint", "provider"), [
    ({"typesafe_api_key": "ts"}, TYPESAFE_ENDPOINT, "typesafe"),
    ({"openrouter_api_key": "or"}, OPENROUTER_DECISIONS_ENDPOINT, "openrouter"),
    ({"agent_runtime_model": "openrouter:openai/x", "agent_runtime_api_key": "agent"},
     OPENROUTER_DECISIONS_ENDPOINT, "openrouter"),
])
def test_the_router_reuses_the_tier1_provider_resolution(overrides, endpoint, provider) -> None:
    router = create_turn_router(_settings(**overrides))
    assert isinstance(router, JevTurnRouter)
    assert (router._endpoint, router.provider, router._timeout) == (endpoint, provider, 2.0)


def test_router_settings_fail_closed_at_start(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_ROUTER_MODE", "shadow")
    with pytest.raises(InvalidFlagError):
        default_settings()
    monkeypatch.setenv("AGENT_ROUTER_MODE", "on")
    monkeypatch.setenv("AGENT_ROUTER_THRESHOLD", "1.5")
    with pytest.raises(InvalidFlagError):
        default_settings()


# --- Jev adapter ---------------------------------------------------------------

def _jev(handler) -> JevTurnRouter:
    return JevTurnRouter(
        endpoint=TYPESAFE_ENDPOINT, api_key="k", model="jev-latest", timeout_seconds=2.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_one_choice_question_over_message_text_only() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"answers": {"route": {
            "type": "choice", "choice": "direct",
            "probabilities": {"scheduling": 0.05, "direct": 0.9, "out_of_scope": 0.05}}}})

    result = _jev(handler).route(TurnRouteStateV1("hi", ("p",), ("r",)))

    assert result == TurnRouteResultV1(
        probabilities={"scheduling": 0.05, "direct": 0.9, "out_of_scope": 0.05})
    auth, body = seen[0]
    assert auth == "Bearer k"
    assert body["state"] == {
        "message": "hi", "previous_planner_messages": ["p"], "previous_agent_replies": ["r"]}
    question = body["questions"]["route"]
    assert question["type"] == "choice"
    assert tuple(question["criteria"]) == TURN_ROUTES


@pytest.mark.parametrize(("handler", "code"), [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
    (lambda r: httpx.Response(429), "http_429"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "transport_error"),
    (lambda r: httpx.Response(200, json={"answers": {}}), "bad_response"),
    (lambda r: httpx.Response(200, text="not json"), "bad_response"),
    (lambda r: httpx.Response(200, json={"answers": {"route": {"probabilities": {
        "scheduling": 0.0, "direct": 1.4, "out_of_scope": 0.0}}}}), "bad_response"),
    (lambda r: httpx.Response(200, json={"answers": {"route": {"probabilities": {
        "direct": 0.9}}}}), "bad_response"),
    (lambda r: httpx.Response(200, json={"answers": {"route": {"probabilities": {
        "scheduling": 0.86, "direct": 0.0, "out_of_scope": 0.87}}}}), "bad_response"),
])
def test_every_router_failure_is_a_closed_code(handler, code) -> None:
    assert _jev(handler).route(TurnRouteStateV1("hi")) == TurnRouteResultV1(error=code)


def test_the_span_policy_vocabularies_match_their_sources() -> None:
    assert span_policy.TURN_ROUTES == frozenset(TURN_ROUTES)
    validate = span_policy.POLICIES[span_policy.HTTP_SERVER].validated
    assert validate["shiftmind.turn.route"]("direct") == "direct"
    assert validate["shiftmind.turn.route"]("sing a song") is None
    for code in ("timeout", "http_503", "transport_error", "bad_response", "router_exception"):
        assert validate["shiftmind.turn.route_error"](code) == code
    assert validate["shiftmind.turn.route_error"]("provider said: no") is None


# --- runtime paths -------------------------------------------------------------

def _scripted(*responses):
    """A model that records what it was offered and replies in order."""
    offered: list[AgentInfo] = []
    queue = list(responses)

    def respond(_messages, info: AgentInfo) -> ModelResponse:
        offered.append(info)
        return queue.pop(0)

    return FunctionModel(respond), offered


def _text(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)], finish_reason="stop")


def _tool(name: str, args: dict) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(name, args)])


def _runtime(route, model) -> PydanticAIAgentRuntime:
    return create_agent_runtime(model=model, answer_type=GroundedAnswerV2, route=route)


def test_off_topic_text_becomes_the_fixed_refusal() -> None:
    model, offered = _scripted(_text("Twinkle twinkle little star..."))
    outcome = _runtime("out_of_scope", model).run_turn(AgentTurnRequestV1(prompt="sing a song"))
    assert outcome.refusal == OUT_OF_SCOPE_REFUSAL
    assert outcome.answer is None
    assert offered[0].function_tools == []
    assert [t.name for t in offered[0].output_tools] == [REFUSAL_OUTPUT_TOOL]
    assert offered[0].instructions == prompts.OUT_OF_SCOPE_INSTRUCTIONS.strip()


def test_an_off_topic_refusal_is_always_the_fixed_one() -> None:
    """The model's own detail could carry the off-topic answer itself."""
    model, _ = _scripted(_tool(REFUSAL_OUTPUT_TOOL, {
        "reason": "unsupported_request", "detail": "def solve(a, b, c): ...",
        "next_step": "Ask who works Wednesday."}))
    outcome = _runtime("out_of_scope", model).run_turn(
        AgentTurnRequestV1(prompt="write Python for a quadratic"))
    assert outcome.refusal == OUT_OF_SCOPE_REFUSAL


@pytest.mark.parametrize("answer_type", [None, RefusalV1])
def test_a_special_route_needs_the_grounded_answer_type(answer_type) -> None:
    with pytest.raises(ValueError):
        create_agent_runtime(model=_scripted()[0], answer_type=answer_type, route="direct")


def test_a_direct_turn_gets_no_tools_and_answers_only() -> None:
    model, offered = _scripted(_text("Hi! Ask me about your schedule."))
    outcome = _runtime("direct", model).run_turn(AgentTurnRequestV1(prompt="hi"))
    assert outcome.answer is not None and outcome.answer.text == "Hi! Ask me about your schedule."
    assert offered[0].function_tools == []
    assert [t.name for t in offered[0].output_tools] == [ANSWER_OUTPUT_TOOL]
    assert offered[0].instructions == prompts.DIRECT_INSTRUCTIONS.strip()


def test_the_scheduling_route_keeps_todays_output_set() -> None:
    model, offered = _scripted(_text("Coverage checked."))
    _runtime("scheduling", model).run_turn(AgentTurnRequestV1(prompt="who works Wed?"))
    assert {t.name for t in offered[0].output_tools} == {
        "final_result", "clarification", "refusal", "draft"}
    assert offered[0].instructions == prompts.SCHEDULING_ASSISTANT_INSTRUCTIONS.strip()


def test_approval_resume_never_routes() -> None:
    from api.routers import approvals

    assert "create_turn_router" not in inspect.getsource(approvals)
    assert "route=" not in inspect.getsource(approvals._drive_resumed_turn)


# --- the execute route ---------------------------------------------------------

#: The small-talk and off-topic messages of conversation f0cdeca6.
F0CDECA6 = [
    ("hi", "direct"), ("hello", "direct"), ("yo", "direct"),
    ("nice to meet you", "direct"), ("how are you", "direct"),
    ("sing a song", "out_of_scope"), ("write python to solve a quadratic", "out_of_scope"),
]


class _OffTopicRuntime:
    name = "test-out-of-scope"

    def run_turn(self, _request):
        return AgentRunOutcomeV1(refusal=OUT_OF_SCOPE_REFUSAL)


def _execute(client, repository, settings, *, route, runtime, monkeypatch):
    calls: list[dict] = []
    annotations: list[tuple] = []
    router = _Router(_p(*[0.9 if r == route else 0.05 for r in TURN_ROUTES]))
    monkeypatch.setattr("api.routers.conversations.create_turn_router", lambda _s: router)
    monkeypatch.setattr("api.routers.conversations.annotate_turn_route",
                        lambda *args: annotations.append(args))

    def factory_(**kwargs):
        calls.append(kwargs)
        return runtime

    app.dependency_overrides[get_agent_runtime_factory] = lambda: factory_
    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(settings))
    assert response.status_code == 200
    return response.json(), calls, annotations, router


@pytest.mark.parametrize(("message", "route"), F0CDECA6)
def test_small_talk_and_off_topic_turns_get_no_tools(
    conversation_client, monkeypatch, message, route
) -> None:
    client, repository, settings = conversation_client
    loaded = []
    _with_workflow_context_reader(lambda *a, **k: loaded.append(1), monkeypatch)
    monkeypatch.setattr(repository, "claim_queued_run", _claiming(repository, message))
    runtime = _OffTopicRuntime() if route == "out_of_scope" else _Runtime()

    body, calls, annotations, router = _execute(
        client, repository, settings, route=route, runtime=runtime, monkeypatch=monkeypatch)

    assert router.states[0].message == message
    assert calls[0]["capabilities"] == () and calls[0]["route"] == route
    assert loaded == []
    assert annotations == [(route, 0.9, None)]
    if route == "out_of_scope":
        assert body["activity"]["activity_type"] == "terminal_outcome"
        assert body["activity"]["outcome"]["reason"] == "refused"
        assert body["activity"]["outcome"]["refusal_reason"] == "out_of_scope"
    else:
        assert body["activity"]["activity_type"] == "agent_response"


def test_a_scheduling_turn_builds_todays_runtime(conversation_client, monkeypatch) -> None:
    client, repository, settings = conversation_client
    body, calls, annotations, _ = _execute(
        client, repository, settings, route="scheduling", runtime=_Runtime(),
        monkeypatch=monkeypatch)
    assert set(calls[0]) == {"settings", "capabilities", "deps", "answer_type"}
    assert annotations == [("scheduling", 0.9, None)]
    assert body["activity"]["activity_type"] == "agent_response"


def test_router_off_makes_no_request_and_takes_the_full_path(
    conversation_client, monkeypatch
) -> None:
    client, repository, settings = conversation_client
    keyed = replace(settings, agent_router_mode="off", typesafe_api_key="k")
    app.dependency_overrides[get_settings] = lambda: keyed
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("router request made"))
    calls: list[dict] = []
    app.dependency_overrides[get_agent_runtime_factory] = lambda: (
        lambda **kwargs: calls.append(kwargs) or _Runtime())

    response = client.post(
        f"/api/v1/conversations/{repository.conversation_id}/agent-runs/{uuid4()}/execute",
        headers=_headers(keyed))

    assert response.status_code == 200
    assert "route" not in calls[0]


def _claiming(repository, message):
    original = repository.claim_queued_run

    def claim(connection, **kwargs):
        claimed = original(connection, **kwargs)
        return None if claimed is None else replace(claimed, prompt=message)

    return claim


def test_the_scheduling_prompt_teaches_the_one_working_draft_lifecycle() -> None:
    """Story 5.11 Decision 12: the rules the model needs, in the sections it reads."""
    full = prompts.SCHEDULING_ASSISTANT_INSTRUCTIONS
    revising = full.split("**Revising a draft.**", 1)[1].split("\n\n", 1)[0]
    for needed in ("at most one working draft", "working_draft", "next version",
                   "omit a constraint to remove it"):
        assert needed in revising, needed
    # The draft output stays the reply (C6): the prompt must not ask the model to
    # word a draft turn's reply, and the citation rule survives verbatim.
    assert ("After a successful scheduling_draft call, return the draft output citing the "
            "exact draft_id\nthat call returned. Never claim draft success in prose alone.") in full
    discard = " ".join(
        full.split("## Discarding a draft (scheduling_draft_discard)", 1)[1].split("\n## ", 1)[0].split()
    )
    assert "explicitly asks to discard, delete, or throw away" in discard
    assert "Start over with just X" in discard and "never discard" in discard
    # Undo reverses the planner's previous change (live smoke E:4 read "undo" as
    # "remove another constraint" under the old wording), and never claims a revert.
    assert "There is no undo tool" in discard
    assert ("every constraint the draft holds now, plus the one that change removed"
            in discard)
    assert "Never claim the draft was reverted or restored to an earlier version" in discard
    assert ("- Discarding the working draft on explicit request: scheduling_draft_discard, only."
            in full)
    # Both the full and the direct prompt compose Tool routing from one section.
    assert ("- Discarding the working draft on explicit request: scheduling_draft_discard, only."
            in prompts.DIRECT_INSTRUCTIONS)
    baseline = full.split("**Saying what the baseline is now", 1)[1].split("\n\n", 1)[0]
    assert "applied_version" in baseline and "proposal_version" in baseline
