"""Application port for durable conversations; transport and SQL-free by design."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.persisted_event import PersistedEventV1


@dataclass(frozen=True)
class ConversationV1:
    id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    resource_version: int


@dataclass(frozen=True)
class ConversationPageV1:
    """A bounded window over a scenario's conversations.

    ``has_more`` exists because a bare capped list is indistinguishable from a
    list that happens to be exactly ``limit`` long, which leaves a client no
    way to know older conversations were silently dropped.
    """

    items: tuple[ConversationV1, ...]
    limit: int
    has_more: bool


@dataclass(frozen=True)
class ConversationTimelineV1:
    """A bounded window over the *most recent* events on a conversation stream.

    The window is anchored at the tail, not the head: a head-anchored window
    stops showing the planner their own new messages once the stream passes
    ``limit``, which breaks timeline reconstruction outright.

    Events cross this boundary as full ``PersistedEventV1`` envelopes rather
    than bare activity payloads so the read side exercises the same AD-21
    contract the write side commits, and so a caller can read ``sequence``
    without a second query.
    """

    conversation_id: UUID
    resource_version: int
    latest_agent_run_status: str | None
    events: tuple[PersistedEventV1, ...]
    limit: int
    has_more: bool


@dataclass(frozen=True)
class AcceptedTurnV1:
    event: PersistedEventV1
    resource_version: int
    agent_run_status: str


class ConversationRepository(Protocol):
    def create(
        self,
        connection: Any,
        *,
        scenario_id: UUID,
        scenario_version_id: UUID,
        site_id: UUID,
        actor_id: UUID,
    ) -> ConversationV1 | None: ...

    def list_for_scenario(
        self,
        connection: Any,
        *,
        scenario_id: UUID,
        limit: int = 100,
    ) -> ConversationPageV1: ...

    def timeline(
        self,
        connection: Any,
        *,
        conversation_id: UUID,
        limit: int = 200,
    ) -> ConversationTimelineV1 | None: ...

    def accept_turn(
        self,
        connection: Any,
        *,
        conversation_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        text: str,
        request_id: UUID,
    ) -> AcceptedTurnV1 | None: ...
