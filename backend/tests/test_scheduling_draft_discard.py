"""Story 5.11 Task 6: the `scheduling_draft_discard` capability's unit proofs."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft_discard import (
    BudgetExhaustedError,
    DraftChangedThisTurnError,
    NoWorkingDraftError,
    SCOPE_CONTROLS,
    SchedulingDraftDiscardRequestV1,
    scheduling_draft_discard,
    scheduling_draft_discard_manifest,
    scheduling_draft_discard_module,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.proposal import WorkingDraftObservationV1
from application.drafting.turn_state import DraftTurnState
from evals.fixture_projection import FixtureProjectionReader

PROPOSAL = UUID(int=900)


def _deps(state: DraftTurnState, *, tool_calls_limit: int | None = 2) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=UUID(int=4), site_id=UUID(int=1), membership_id=UUID(int=5),
        request_id=UUID(int=6), agent_run_id=UUID(int=7), conversation_id=UUID(int=8),
        scenario_id=UUID(int=2), scenario_version_id=UUID(int=3), policy_version="v1",
        clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc),
        projection_reader=FixtureProjectionReader(), connection=object(),
        remaining_budget=AgentBudgetV1(tool_calls_limit=tool_calls_limit),
        draft_turn=state,
    )


def _state(observation=WorkingDraftObservationV1(PROPOSAL, 4, 3)) -> DraftTurnState:
    return DraftTurnState(lambda: observation)


def _discard(state: DraftTurnState, **kw):
    return scheduling_draft_discard(_deps(state, **kw), SchedulingDraftDiscardRequestV1())


def test_it_refuses_when_there_is_no_working_draft() -> None:
    state = _state(None)
    with pytest.raises(NoWorkingDraftError) as raised:
        _discard(state)
    assert raised.value.code == "no_working_draft"
    assert state.discarded is None


def test_it_refuses_after_a_same_turn_draft() -> None:
    """Mutation: allow discard after a draft => this and the golden case redden."""
    state = _state()
    state.note_drafted()
    with pytest.raises(DraftChangedThisTurnError) as raised:
        _discard(state)
    assert raised.value.code == "draft_changed_this_turn"
    assert state.discarded is None


def test_it_refuses_a_second_discard_in_one_turn() -> None:
    state = _state()
    _discard(state)
    with pytest.raises(NoWorkingDraftError):
        _discard(state)


def test_it_records_exactly_the_observation_it_discarded() -> None:
    state = _state()
    result = _discard(state)
    assert state.discarded == WorkingDraftObservationV1(PROPOSAL, 4, 3)
    assert (result.proposal_id, result.observed_resource_version, result.version_ordinal) == (
        PROPOSAL, 4, 3,
    )


def test_it_spends_no_tool_call_budget_it_does_not_have() -> None:
    with pytest.raises(BudgetExhaustedError):
        _discard(_state(), tool_calls_limit=0)


def test_the_model_view_carries_no_proposal_id() -> None:
    result = _discard(_state())
    view = scheduling_draft_discard_module().model_facing_view(result)
    assert asdict(view) == {"outcome": "discarded", "version_ordinal": 3, "schema_version": "1"}
    assert str(PROPOSAL) not in str(asdict(view))


def test_the_manifest_is_a_draft_risk_capability_with_no_approval_and_four_fixtures() -> None:
    manifest = scheduling_draft_discard_manifest()
    assert (manifest.risk_class, manifest.approval_policy, manifest.budget_limit) == ("draft", "none", 1)
    assert manifest.scope == "current_site/current_conversation"
    assert manifest.citable_result_id is False
    assert len(manifest.evaluation_fixtures) == 4
    assert {"no_working_draft", "draft_changed_this_turn", "budget_exhausted"} <= set(manifest.errors)


def test_the_two_refusals_are_retryable_so_the_model_can_tell_the_planner() -> None:
    module = scheduling_draft_discard_module()
    assert module.retryable_error_codes == frozenset({"no_working_draft", "draft_changed_this_turn"})
    assert module.required_feature_policy == "scheduling_draft_discard_enabled"


def test_the_description_routes_start_over_to_scheduling_draft() -> None:
    description = scheduling_draft_discard_module().model_description
    assert "explicitly asks to discard, delete, or throw away" in description
    assert "scheduling_draft with only X, never discard" in description
    assert all("NOT COVERED" in text for key, text in SCOPE_CONTROLS.items() if key.startswith("lifecycle"))
