from dataclasses import fields
from typing import get_args

from application.contracts.telemetry import (
    AgentUsageV1,
    BudgetOutcomeV1,
    CorrelationV1,
    TELEMETRY_LABEL_KEYS,
    TelemetryEventV1,
    TelemetryRecordV1,
)
from application.ports.telemetry import NullTelemetrySink


def test_telemetry_contract_has_exact_closed_vocabularies() -> None:
    assert set(get_args(TelemetryEventV1)) == {
        "api.request.completed",
        "agent.run.completed",
        "agent.model.calls.completed",
        "agent.tool.call.completed",
        "solver.run.completed",
        "job.leased",
        "run.first_event.persisted",
        "approval.decided",
    }
    assert TELEMETRY_LABEL_KEYS == frozenset(
        {
            "route_template",
            "method",
            "status_class",
            "agent_run_status",
            "failure_reason",
            "capability_name",
            "budget_outcome",
            "solver_status",
            "job_type",
            "approval_outcome",
            "model",
            "cost_basis",
        }
    )
    assert set(get_args(BudgetOutcomeV1)) == {
        "within_budget",
        "budget_exhausted",
        "deadline_expired",
        "unknown",
    }


def test_telemetry_contract_field_sets_are_owned_and_content_free() -> None:
    assert {field.name for field in fields(CorrelationV1)} == {
        "request_id",
        "site_id",
        "actor_id",
        "conversation_id",
        "agent_run_id",
        "tool_call_id",
        "approval_id",
        "job_id",
        "schedule_run_id",
        "schedule_version_id",
    }
    assert {field.name for field in fields(AgentUsageV1)} == {
        "requests",
        "tool_calls",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    }
    assert {field.name for field in fields(TelemetryRecordV1)} == {
        "schema_version",
        "event",
        "occurred_at",
        "app_version",
        "correlation",
        "labels",
        "duration_ms",
        "queue_age_s",
        "approval_age_s",
        "estimated_cost_usd",
        "usage",
        "budget_outcome",
    }


def test_null_telemetry_sink_accepts_records() -> None:
    assert NullTelemetrySink().emit(TelemetryRecordV1()) is None
