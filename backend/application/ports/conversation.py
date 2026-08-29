"""Application port for durable conversations; transport and SQL-free by design."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from application.contracts.persisted_event import PersistedEventV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.activity import ActivityItemV1, DraftReferenceV1
from application.contracts.approval_binding import ApprovalBindingV1


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
    latest_agent_run_status_reason: str | None = None


@dataclass(frozen=True)
class AcceptedTurnV1:
    event: PersistedEventV1
    resource_version: int
    # `None` when the activity was appended OUTSIDE any agent run -- the
    # planner-initiated approval path has no agent run in scope, and naming a
    # status there would be a fabricated value inside a typed contract.
    agent_run_status: str | None


@dataclass(frozen=True)
class ClaimedAgentRunV1:
    agent_run_id: UUID
    conversation_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    actor_id: UUID
    membership_id: UUID
    prompt: str
    history: tuple[ActivityItemV1, ...] = ()


@dataclass(frozen=True)
class ExecutedAgentRunV1:
    event: PersistedEventV1
    resource_version: int
    # `None` when the activity was appended OUTSIDE any agent run -- the
    # planner-initiated approval path has no agent run in scope, and naming a
    # status there would be a fabricated value inside a typed contract.
    agent_run_status: str | None


class AgentRunNotQueuedError(ValueError):
    """A visible run exists but cannot be claimed from its current state."""


class ConversationRepository(Protocol):
    def latest_terminal_outcome_for_site(
        self,
        connection: Any,
        *,
        site_id: UUID,
    ) -> PersistedEventV1 | None: ...

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

    def events_after(
        self,
        connection: Any,
        *,
        stream_id: UUID,
        after: Decimal,
        limit: int,
    ) -> tuple[PersistedEventV1, ...] | None:
        """Events on one stream with sequence strictly greater than ``after``.

        Oldest first, at most ``limit`` of them — this is SSE replay draining
        forward from a client's cursor, not a timeline window.

        ``after`` is a ``Decimal`` because the column is ``Numeric(38, 0)``:
        compared as text, ``"10" < "9"`` and a client resuming at 9 would
        silently lose everything from 10 on.

        ``None`` means the conversation is not visible to this site — the same
        absence-equals-denial answer :meth:`timeline` gives (AD-3). An empty
        tuple is the *different*, legitimate answer "nothing outstanding".
        """
        ...

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

    def claim_queued_run(
        self,
        connection: Any,
        *,
        conversation_id: UUID,
        agent_run_id: UUID,
    ) -> ClaimedAgentRunV1 | None: ...

    def finish_agent_run(
        self,
        connection: Any,
        *,
        claimed: ClaimedAgentRunV1,
        status: str,
        payload: GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1 | DraftReferenceV1,
        request_id: UUID,
    ) -> ExecutedAgentRunV1: ...

    def pause_agent_run_for_approval(self, connection: Any, *, claimed_agent_run_id: UUID, binding: ApprovalBindingV1, request_id: UUID) -> ExecutedAgentRunV1: ...

    def append_approval_request_activity(self, connection: Any, *, binding: ApprovalBindingV1, actor_id: UUID, request_id: UUID, agent_run_id: UUID | None = None, occurred_at: Any = None) -> ExecutedAgentRunV1: ...
    def cancel_agent_run_for_approval(self, connection: Any, *, agent_run_id: UUID, binding: ApprovalBindingV1, reason: str) -> None: ...
