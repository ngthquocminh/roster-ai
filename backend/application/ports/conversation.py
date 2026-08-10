"""Application port for durable conversations; transport and SQL-free by design."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
from uuid import UUID

from application.contracts.activity import ActivityItemV1


@dataclass(frozen=True)
class ConversationV1:
    id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    resource_version: int


@dataclass(frozen=True)
class ConversationTimelineV1:
    conversation_id: UUID
    resource_version: int
    latest_agent_run_status: str | None
    items: tuple[ActivityItemV1, ...]
    limit: int


@dataclass(frozen=True)
class AcceptedTurnV1:
    activity: ActivityItemV1
    resource_version: int
    agent_run_status: str
    sequence: str


class ConversationRepository(Protocol):
    def create(self, connection: Any, *, scenario_id: UUID, site_id: UUID, actor_id: UUID) -> ConversationV1 | None: ...
    def list_for_scenario(self, connection: Any, *, scenario_id: UUID, limit: int = 100) -> tuple[ConversationV1, ...]: ...
    def timeline(self, connection: Any, *, conversation_id: UUID, limit: int = 200) -> ConversationTimelineV1 | None: ...
    def accept_turn(self, connection: Any, *, conversation_id: UUID, site_id: UUID, actor_id: UUID, text: str, request_id: UUID, after_message: Callable[[], None] | None = None) -> AcceptedTurnV1 | None: ...
