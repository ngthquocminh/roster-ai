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
class ActivityItemV1:
    """One stable timeline item.

    Only ``planner_message`` is constructible as a complete payload in Story 2.3;
    the remaining discriminants reserve the closed cross-story vocabulary.
    """

    activity_id: UUID
    activity_type: ActivityTypeV1
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    message_id: UUID
    text: str
    schema_version: str = SCHEMA_VERSION
