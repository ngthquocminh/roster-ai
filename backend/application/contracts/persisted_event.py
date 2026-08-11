"""Versioned durable event envelope owned by the conversation aggregate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from application.contracts.activity import ActivityItemV1

SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class PersistedEventV1:
    stream_id: UUID
    sequence: Decimal
    event_type: str
    occurred_at: datetime
    resource_version: int
    request_id: UUID
    conversation_id: UUID
    agent_run_id: UUID
    site_id: UUID
    actor_id: UUID
    payload: ActivityItemV1
    schema_version: str = SCHEMA_VERSION
