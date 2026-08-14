from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import get_args
from uuid import uuid4

import pytest

from application.contracts.grounding import (
    ClaimArgumentsV1,
    ClaimProposalV1,
    GroundedAnswerV1,
    GroundedClaimV1,
    GroundedProseSegmentV1,
    GroundedResponseV1,
    FAMILY_AWARE_METRICS,
    GroundingFailureV1,
    MetricV1,
)


def test_grounding_contracts_are_closed_versioned_and_frozen() -> None:
    # Demand splits by dimension because `DemandIntervalV1.unit` is
    # volume|headcount and the only rate in the projection is per WORKER per
    # task, so volume -> minutes needs an assignment and belongs to Epic 3.
    assert set(get_args(MetricV1)) == {
        "required_headcount_minutes",
        "required_demand_volume",
        "staffed_minutes",
        "shortfall_minutes",
        "qualified_worker_count",
    }
    # family lives only on demand rows and is not a function of task_id, so
    # only demand-reading metrics may accept it.
    assert FAMILY_AWARE_METRICS == {
        "required_headcount_minutes",
        "required_demand_volume",
    }
    assert set(get_args(GroundingFailureV1)) == {
        "missing_evidence",
        "unauthorized_evidence",
        "version_mismatch",
        "calculation_failed",
        "uncited_claim",
    }

    arguments = ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60)
    proposal = ClaimProposalV1(
        metric="staffed_minutes", arguments=arguments, result_id="result-1"
    )
    assert "value" not in {field.name for field in fields(proposal)}
    assert proposal.schema_version == "1"
    with pytest.raises(FrozenInstanceError):
        proposal.result_id = "changed"  # type: ignore[misc]


def test_grounded_answer_preserves_segment_order_and_response_keeps_claim_state() -> None:
    arguments = ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60)
    proposal = ClaimProposalV1(
        metric="staffed_minutes", arguments=arguments, result_id="result-1"
    )
    answer = GroundedAnswerV1(
        segments=(GroundedProseSegmentV1(text="Staffing is"), proposal)
    )
    claim = GroundedClaimV1(
        metric=proposal.metric,
        arguments=arguments,
        result_id=proposal.result_id,
        value=60,
        unit="minutes",
        evidence_refs=(),
        verdict="supported",
    )
    response = GroundedResponseV1(
        scenario_version_id=uuid4(),
        segments=(answer.segments[0], claim),
    )

    assert response.segments == (answer.segments[0], claim)
    assert response.claims == (claim,)
    assert response.schema_version == "1"


def test_grounding_contract_module_is_transport_and_framework_free() -> None:
    module = __import__(GroundedAnswerV1.__module__, fromlist=["*"])
    source_names = set(vars(module))
    assert "fastapi" not in source_names
    assert "pydantic_ai" not in source_names
    assert "sqlalchemy" not in source_names
