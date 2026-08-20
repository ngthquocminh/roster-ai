"""Versioned planner-visible conversation activity contracts (AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

SCHEMA_VERSION = "1"

ActivityTypeV1 = Literal[
    "planner_message",
    "agent_response",
    "clarification",
    "draft",
    "run_progress",
    "comparison",
    "approval_request",
    "terminal_outcome",
]


@dataclass(frozen=True)
class PlannerMessageActivityV1:
    """The byte-compatible planner-message timeline payload from Story 2.3."""

    activity_id: UUID
    activity_type: Literal["planner_message"]
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    message_id: UUID
    text: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AgentResponseActivityV1:
    """A persisted visible response whose claims already passed grounding."""

    activity_id: UUID
    activity_type: Literal["agent_response"]
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    response: "GroundedResponseV1"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ClarificationActivityV1:
    """Application-resolved clarification persisted as its reserved AD-20 type."""

    activity_id: UUID
    activity_type: Literal["clarification"]
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    clarification: "ResolvedClarificationV1"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DraftReferenceV1:
    """A Conversation-owned pointer at a Scheduling-owned proposal.

    AD-22 permits only an application orchestrator to cross aggregate owners, so
    the conversation adapter must not read `ProposalV1` to decide what a draft
    activity contains. `finalize_agent_run` performs that translation and hands
    the repository this reference instead — the same three fields
    `DraftActivityV1` persists, in a contract the Conversation side owns.
    """

    proposal_id: UUID
    proposal_version_id: UUID
    consequence_summary: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DraftActivityV1:
    """Reference to the current proposal plus application-composed summary."""

    activity_id: UUID
    activity_type: Literal["draft"]
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    proposal_id: UUID
    proposal_version_id: UUID
    consequence_summary: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class RunProgressActivityV1:
    """Literal persisted state for one schedule-run transition."""

    activity_id: UUID
    activity_type: Literal["run_progress"]
    schedule_run_id: UUID
    status: "ScheduleRunStatusV1"
    reason: str | None
    resource_version: int
    occurred_at: datetime
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class TerminalOutcomeActivityV1:
    """Literal non-answer state, including reason-discriminated refusal."""

    activity_id: UUID
    activity_type: Literal["terminal_outcome"]
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    outcome: "TerminalOutcomeV1"
    schema_version: str = SCHEMA_VERSION


from application.contracts.grounding import GroundedResponseV1
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.schedule_version import ScheduleRunStatusV1

ActivityItemV1 = (
    PlannerMessageActivityV1
    | AgentResponseActivityV1
    | ClarificationActivityV1
    | DraftActivityV1
    | RunProgressActivityV1
    | TerminalOutcomeActivityV1
)

__all__ = [
    "ActivityItemV1", "ActivityTypeV1", "AgentResponseActivityV1",
    "ClarificationActivityV1", "DraftActivityV1", "PlannerMessageActivityV1", "RunProgressActivityV1", "SCHEMA_VERSION",
    "TerminalOutcomeActivityV1",
]
