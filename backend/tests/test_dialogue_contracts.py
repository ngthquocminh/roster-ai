from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.dialogue import (
    ClarificationV1,
    EntityCandidateProposalV1,
    EntityCandidateV1,
    RefusalReasonV1,
    RefusalV1,
    ResolvedClarificationV1,
    TerminalOutcomeV1,
    TerminalReasonV1,
)


def test_dialogue_contracts_have_pinned_fields_and_closed_vocabularies() -> None:
    assert [field.name for field in fields(EntityCandidateProposalV1)] == [
        "group",
        "record_id",
        "schema_version",
    ]
    assert [field.name for field in fields(EntityCandidateV1)] == [
        "group",
        "record_id",
        "label",
        "scenario_version_id",
        "schema_version",
    ]
    assert [field.name for field in fields(ClarificationV1)] == [
        "question",
        "candidates",
        "schema_version",
    ]
    assert [field.name for field in fields(ResolvedClarificationV1)] == [
        "question",
        "candidates",
        "scenario_version_id",
        "dropped_candidate_count",
        "schema_version",
    ]
    assert [field.name for field in fields(RefusalV1)] == [
        "reason",
        "detail",
        "next_step",
        "schema_version",
    ]
    assert [field.name for field in fields(TerminalOutcomeV1)] == [
        "status",
        "reason",
        "detail",
        "next_step",
        "schema_version",
    ]
    assert get_args(RefusalReasonV1) == (
        "unsupported_request",
        "capability_unavailable",
        "out_of_scope",
    )
    assert get_args(TerminalReasonV1) == (
        "provider_error",
        "invalid_output",
        "budget_exhausted",
        "deadline_exceeded",
        "cancelled",
        "capability_error",
        "refused",
        "approval_unsupported",
    )


def test_dialogue_contracts_round_trip_as_frozen_owned_json() -> None:
    scenario_version_id = uuid4()
    proposal = EntityCandidateProposalV1(
        group="workers",
        record_id="worker-1",
    )
    clarification = ClarificationV1(
        question="Which worker?",
        candidates=(proposal,),
    )
    resolved = ResolvedClarificationV1(
        question=clarification.question,
        candidates=(
            EntityCandidateV1(
                group="workers",
                record_id="worker-1",
                label="C-100",
                scenario_version_id=scenario_version_id,
            ),
        ),
        scenario_version_id=scenario_version_id,
        dropped_candidate_count=0,
    )
    refusal = RefusalV1(
        reason="capability_unavailable",
        detail="That capability is not available.",
        next_step="Review Scenario Data.",
    )
    terminal = TerminalOutcomeV1(
        status="completed",
        reason="refused",
        detail=refusal.detail,
        next_step=refusal.next_step,
    )

    for value in (proposal, clarification, resolved, refusal, terminal):
        adapter = TypeAdapter(type(value))
        payload = adapter.dump_python(value, mode="json")
        assert adapter.validate_python(payload) == value
        assert payload["schema_version"] == "1"

    with pytest.raises(FrozenInstanceError):
        proposal.record_id = "changed"  # type: ignore[misc]


def test_agent_run_outcome_keeps_model_dialogue_outputs_untrusted_and_separate() -> None:
    clarification = ClarificationV1(question="Which worker?")
    refusal = RefusalV1(reason="unsupported_request", detail="I cannot do that.")

    clarification_outcome = AgentRunOutcomeV1(clarification=clarification)
    refusal_outcome = AgentRunOutcomeV1(refusal=refusal)

    assert clarification_outcome.clarification is clarification
    assert clarification_outcome.resolved_clarification is None
    assert clarification_outcome.refusal is None
    assert refusal_outcome.refusal is refusal
    assert refusal_outcome.clarification is None
