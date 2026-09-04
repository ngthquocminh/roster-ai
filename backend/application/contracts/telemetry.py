"""Owned operational telemetry records for ShiftMind.

Budget outcomes are intentionally coarse. The AgentRuntime boundary maps
framework failures by exception type and never by parsing provider text, so it
can distinguish deadline expiry from aggregate budget exhaustion but cannot
honestly identify which individual ceiling was hit.

The contract contains identifiers, closed labels, and measurements only. It has
no free-text field and therefore cannot carry prompts, results, exceptions, or
planner content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Mapping
from uuid import UUID

SCHEMA_VERSION = "1"

TelemetryEventV1 = Literal[
    "api.request.completed",
    "agent.run.completed",
    # Named "calls" (plural), not "call": this fires once per agent run, from
    # a `finally` wrapping the whole framework `run_sync`, which can itself
    # issue several model requests. Its `duration_ms`/`usage` are a run-level
    # sum, not a single model call's latency, and overlap the time separately
    # reported by `agent.tool.call.completed`. Accepted for this MVP; true
    # per-request timing needs a framework hook this story does not add
    # (review of story-5.1, Decision-needed #2).
    "agent.model.calls.completed",
    "agent.tool.call.completed",
    "solver.run.completed",
    "job.leased",
    "run.first_event.persisted",
    "approval.decided",
]

TELEMETRY_LABEL_KEYS = frozenset(
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

BudgetOutcomeV1 = Literal[
    "within_budget", "budget_exhausted", "deadline_expired", "unknown"
]


@dataclass(frozen=True)
class CorrelationV1:
    request_id: UUID | None = None
    site_id: UUID | None = None
    actor_id: UUID | None = None
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    tool_call_id: str | None = None
    approval_id: UUID | None = None
    job_id: UUID | None = None
    schedule_run_id: UUID | None = None
    schedule_version_id: UUID | None = None


@dataclass(frozen=True)
class AgentUsageV1:
    requests: int | None = None
    tool_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


@dataclass(frozen=True)
class TelemetryRecordV1:
    schema_version: str = SCHEMA_VERSION
    event: TelemetryEventV1 = "api.request.completed"
    occurred_at: datetime | None = None
    app_version: str | None = None
    correlation: CorrelationV1 = field(default_factory=CorrelationV1)
    labels: Mapping[str, str] = field(default_factory=dict)
    duration_ms: float | None = None
    queue_age_s: float | None = None
    approval_age_s: float | None = None
    estimated_cost_usd: float | None = None
    usage: AgentUsageV1 | None = None
    budget_outcome: BudgetOutcomeV1 | None = None


__all__ = [
    "AgentUsageV1",
    "BudgetOutcomeV1",
    "CorrelationV1",
    "SCHEMA_VERSION",
    "TELEMETRY_LABEL_KEYS",
    "TelemetryEventV1",
    "TelemetryRecordV1",
]
