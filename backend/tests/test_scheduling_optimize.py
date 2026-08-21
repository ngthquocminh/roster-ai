from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_optimize import (
    BudgetExhaustedError,
    InvalidRunRequestError,
    SchedulingOptimizeRequestV1,
    scheduling_optimize,
    scheduling_optimize_manifest,
    scheduling_optimize_module,
)
from application.contracts.agent_runtime import AgentBudgetV1


def _deps(*, tool_calls_limit: int = 1) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=UUID(int=1),
        site_id=UUID(int=2),
        membership_id=UUID(int=3),
        request_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        conversation_id=UUID(int=6),
        scenario_id=UUID(int=7),
        scenario_version_id=UUID(int=8),
        policy_version="one-user-mvp-v1",
        clock=lambda: datetime.now(timezone.utc),
        projection_reader=object(),
        connection=None,
        remaining_budget=AgentBudgetV1(tool_calls_limit=tool_calls_limit),
    )


def test_manifest_declares_compute_risk_and_real_evaluation_files() -> None:
    manifest = scheduling_optimize_manifest()
    backend = Path(__file__).resolve().parents[1]

    assert manifest.capability_name == "scheduling_optimize"
    assert manifest.risk_class == "compute"
    assert manifest.approval_policy == "none"
    assert len(manifest.evaluation_fixtures) == 4
    assert all((backend / path).is_file() for path in manifest.evaluation_fixtures)


def test_handler_validates_and_returns_trusted_transport_identity() -> None:
    request = SchedulingOptimizeRequestV1(
        proposal_id=UUID(int=9),
        expected_resource_version=2,
        idempotency_key="run-key",
    )

    result = scheduling_optimize(_deps(), request)

    assert result.proposal_id == UUID(int=9)
    assert result.expected_resource_version == 2
    assert result.idempotency_key == "run-key"
    assert result.actor_id == UUID(int=1)
    assert result.site_id == UUID(int=2)
    assert result.capability_version == scheduling_optimize_manifest().capability_version


@pytest.mark.parametrize(
    "run_request",
    (
        SchedulingOptimizeRequestV1(
            proposal_id=UUID(int=0), expected_resource_version=1, idempotency_key="key"
        ),
        SchedulingOptimizeRequestV1(
            proposal_id=UUID(int=9), expected_resource_version=0, idempotency_key="key"
        ),
        SchedulingOptimizeRequestV1(
            proposal_id=UUID(int=9), expected_resource_version=1, idempotency_key=""
        ),
        SchedulingOptimizeRequestV1(
            proposal_id=UUID(int=9), expected_resource_version=1, idempotency_key="x" * 41
        ),
    ),
)
def test_handler_rejects_invalid_run_requests(run_request) -> None:
    with pytest.raises(InvalidRunRequestError):
        scheduling_optimize(_deps(), run_request)


def test_handler_fails_when_no_tool_call_budget_remains() -> None:
    request = SchedulingOptimizeRequestV1(
        proposal_id=UUID(int=9), expected_resource_version=1, idempotency_key="key"
    )

    with pytest.raises(BudgetExhaustedError):
        scheduling_optimize(_deps(tool_calls_limit=0), request)


def test_model_view_exposes_only_the_validated_command_reference() -> None:
    request = SchedulingOptimizeRequestV1(
        proposal_id=UUID(int=9), expected_resource_version=1, idempotency_key="key"
    )
    result = scheduling_optimize(_deps(), request)

    view = scheduling_optimize_module().model_facing_view(result)

    assert view.proposal_id == UUID(int=9)
    assert view.expected_resource_version == 1
    assert not hasattr(view, "actor_id")
    assert not hasattr(view, "site_id")
    assert not hasattr(view, "idempotency_key")
