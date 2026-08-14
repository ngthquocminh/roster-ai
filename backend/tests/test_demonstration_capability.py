"""The governed demonstration module's own declared behaviour.

Story 2.6 promoted `shiftmind_demonstration` out of the runtime constructor into
a governed module. Every code in its declared `ERROR_CODES` is exercised here --
a manifest that advertises a failure no test can produce is a claim, not a
contract.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic_ai import models

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.demonstration import (
    ERROR_CODES,
    MAX_REPEAT,
    SCOPE_CONTROLS,
    DemonstrationApprovalRequired,
    DemonstrationBudgetExhausted,
    DemonstrationError,
    DemonstrationInvalidRepeat,
    DemonstrationRequestV1,
    DemonstrationResultV1,
    demonstrate,
    demonstration_manifest,
    demonstration_module,
)


def test_generic_demonstration_failure_is_not_a_retryable_argument_code() -> None:
    module = demonstration_module()
    assert DemonstrationError.code not in module.retryable_error_codes
    assert DemonstrationInvalidRepeat.code in module.retryable_error_codes
from application.capabilities.deps import AgentDepsV1
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.capability_manifest import CapabilityApprovalRequired
from evals.cases import case_from_mapping
from evals.doubles import build_model_double

models.ALLOW_MODEL_REQUESTS = False

# Distinct UUIDs per identity field: sharing one made every scope assertion
# vacuous (Story 2.5 review finding 8).
ACTOR, SITE, MEMBERSHIP = UUID(int=11), UUID(int=12), UUID(int=13)
REQUEST, AGENT_RUN, CONVERSATION = UUID(int=14), UUID(int=15), UUID(int=16)
SCENARIO, VERSION = UUID(int=17), UUID(int=18)


def _deps(*, approved: bool = False, tool_calls_limit: int | None = 3) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=ACTOR, site_id=SITE, membership_id=MEMBERSHIP,
        request_id=REQUEST, agent_run_id=AGENT_RUN, conversation_id=CONVERSATION,
        scenario_id=SCENARIO, scenario_version_id=VERSION,
        policy_version="one-user-mvp-v1",
        clock=lambda: datetime(2026, 8, 12, tzinfo=timezone.utc),
        projection_reader=object(), connection=object(),
        remaining_budget=AgentBudgetV1(tool_calls_limit=tool_calls_limit),
        tool_call_approved=approved,
    )


def _manifest():
    return demonstration_manifest()


def test_a_single_repetition_executes_without_approval() -> None:
    result = demonstrate(_deps(), DemonstrationRequestV1(label="alpha"), _manifest())

    assert result == DemonstrationResultV1(text="alpha")


def test_repetition_refuses_before_computing_when_unapproved() -> None:
    """Authority BEFORE effect. The signal must carry no precomputed result:
    an unapproved call performs no work at all."""
    with pytest.raises(DemonstrationApprovalRequired) as raised:
        demonstrate(_deps(), DemonstrationRequestV1(label="alpha", repeat=2), _manifest())

    assert raised.value.code == "approval_required"
    assert isinstance(raised.value, CapabilityApprovalRequired)
    assert not hasattr(raised.value, "approved_result")


def test_repetition_executes_exactly_once_when_approved() -> None:
    result = demonstrate(
        _deps(approved=True), DemonstrationRequestV1(label="alpha", repeat=2), _manifest()
    )

    assert result.text == "alpha|alpha"


def test_an_exhausted_tool_call_budget_is_a_declared_failure() -> None:
    with pytest.raises(DemonstrationBudgetExhausted) as raised:
        demonstrate(
            _deps(tool_calls_limit=0), DemonstrationRequestV1(label="alpha"), _manifest()
        )

    assert raised.value.code == "budget_exhausted"


@pytest.mark.parametrize("repeat", [0, -1])
def test_a_repeat_below_one_is_a_declared_failure(repeat) -> None:
    with pytest.raises(DemonstrationError) as raised:
        demonstrate(_deps(), DemonstrationRequestV1(label="alpha", repeat=repeat), _manifest())

    assert raised.value.code == "invalid_repeat"


def test_repeat_is_bounded_before_any_allocation_happens() -> None:
    """A model-supplied repetition count must not be able to allocate without
    bound -- even on an approved call."""
    with pytest.raises(DemonstrationError, match="must not exceed"):
        demonstrate(
            _deps(approved=True),
            DemonstrationRequestV1(label="alpha", repeat=MAX_REPEAT + 1),
            _manifest(),
        )


def test_every_declared_error_code_is_produced_by_a_real_class() -> None:
    produced = {
        DemonstrationError.code,
        DemonstrationInvalidRepeat.code,
        DemonstrationApprovalRequired.code,
        DemonstrationBudgetExhausted.code,
    }
    assert produced == set(ERROR_CODES)


def test_scope_controls_record_what_is_not_covered() -> None:
    assert set(SCOPE_CONTROLS) == {"budget", "audit", "evidence", "approval"}
    assert all("NOT COVERED" in value for value in SCOPE_CONTROLS.values())


def _demo_case(repeat: int, *, state: str = "completed"):
    arguments = {"payload": {"label": "alpha", "repeat": repeat}}
    return case_from_mapping({
        "case_id": f"demo-repeat-{repeat}", "case_version": "1",
        "capability": "demonstration", "risk_class": "consequential",
        "prompt": f"Demonstrate alpha {repeat} times.",
        "scripted_turns": [
            {"tool_name": "shiftmind_demonstration", "arguments": arguments,
             "tool_call_id": "demo-1"},
            {"response_text": "tool said alpha"},
        ],
        "expected_outcome": "allow",
        "expected_tool_calls": [
            {"tool_name": "shiftmind_demonstration", "arguments": arguments}
        ],
        "expected_evidence_refs": [], "expected_visible_state": state,
        "expected_visible_text": "tool said alpha", "scenario_fixtures": [],
    })


def test_an_unapproved_repetition_suspends_the_run_through_the_real_runtime() -> None:
    case = _demo_case(2, state="suspended")
    runtime = PydanticAIAgentRuntime(
        model=build_model_double(case),
        capabilities=(demonstration_module(),),
        deps=_deps(),
    )

    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))

    assert outcome.status == "suspended"


def test_a_single_repetition_completes_through_the_real_runtime() -> None:
    case = _demo_case(1)
    runtime = PydanticAIAgentRuntime(
        model=build_model_double(case),
        capabilities=(demonstration_module(),),
        deps=_deps(),
    )

    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))

    assert outcome.status == "completed"
    assert outcome.tool_results[0].tool_name == "shiftmind_demonstration"


def test_the_module_declares_its_model_facing_rendering() -> None:
    """The adapter must not have to guess the result shape."""
    module = demonstration_module()

    assert module.request_argument == "payload"
    # Projecting the bare string keeps Story 2.2's seven frozen golden cases
    # byte-identical; rendering the whole record would change the transcript.
    assert module.model_facing_view(DemonstrationResultV1(text="a|a")) == "a|a"
    assert replace(module).manifest.approval_policy == "exact_action"
