from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import TypeAdapter

from application.clarification.resolve import planner_label
from application.contracts.proposal import (
    DraftConstraintKindV1,
    DraftConstraintProposalV1,
    DraftConstraintV1,
    DraftProposalV1,
    ProposalStateV1,
    ProposalV1,
    ResolvedEntityV1,
)
from application.contracts.scenario_projection import TaskV1
from application.contracts.agent_runtime import AgentRunOutcomeV1


FIXTURE = Path(__file__).parent / "fixtures" / "proposal-v1.json"


def test_proposal_contracts_have_the_normative_frozen_transport_free_shape() -> None:
    assert [field.name for field in fields(DraftConstraintProposalV1)] == [
        "kind", "group", "record_id", "related_group", "related_record_id",
        "n", "factor", "max_hours", "start_minute", "end_minute", "schema_version",
    ]
    assert [field.name for field in fields(ResolvedEntityV1)] == [
        "group", "record_id", "label", "scenario_version_id", "schema_version",
    ]
    assert [field.name for field in fields(DraftConstraintV1)] == [
        "kind", "resolved_entities", "n", "factor", "max_hours", "start_minute",
        "end_minute", "description", "schema_version",
    ]
    assert [field.name for field in fields(ProposalV1)] == [
        "proposal_id", "proposal_version_id", "scenario_id", "scenario_version_id",
        "expected_baseline_schedule_version", "resolved_entities", "constraints",
        "preserved_locks", "consequence_summary", "canonical_hash",
        "canonical_hash_algorithm", "canonical_hash_schema_version", "state",
        "resource_version", "schema_version",
    ]
    assert [field.name for field in fields(DraftProposalV1)] == [
        "draft_id", "schema_version",
    ]
    assert get_args(DraftConstraintKindV1) == (
        "set_min_workers_per_task", "scale_demand", "lock_worker_shift",
        "exclude_worker_from_task", "set_max_hours",
    )
    assert get_args(ProposalStateV1) == ("active", "rejected")

    module_names = set(vars(__import__(ProposalV1.__module__, fromlist=["*"])))
    assert not {"fastapi", "pydantic", "sqlalchemy"}.intersection(module_names)


def test_proposal_contract_fixture_round_trips_and_is_frozen() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    adapter = TypeAdapter(ProposalV1)
    proposal = adapter.validate_python(payload)

    assert adapter.dump_python(proposal, mode="json") == payload
    assert proposal.schema_version == "1"
    assert all(entity.schema_version == "1" for entity in proposal.resolved_entities)
    assert all(constraint.schema_version == "1" for constraint in proposal.constraints)
    with pytest.raises(FrozenInstanceError):
        proposal.state = "rejected"  # type: ignore[misc]


def test_shared_planner_label_matches_the_scenario_data_identity_shape() -> None:
    task = TaskV1("task-1", "task-1", "Picking", "Pick", "area-1", "Area 1", None)
    assert planner_label(task) == "Picking (task-1)"


def test_agent_outcome_keeps_untrusted_and_resolved_drafts_separate() -> None:
    citation = DraftProposalV1(draft_id="draft-123")
    trusted = TypeAdapter(ProposalV1).validate_json(FIXTURE.read_text(encoding="utf-8"))

    model_side = AgentRunOutcomeV1(draft=citation)
    resolved = AgentRunOutcomeV1(draft=citation, resolved_draft=trusted)

    assert model_side.draft is citation
    assert model_side.resolved_draft is None
    assert resolved.draft is citation
    assert resolved.resolved_draft is trusted
