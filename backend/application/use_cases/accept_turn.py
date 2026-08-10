"""Accept a planner turn without executing the agent (AD-22)."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from application.ports.conversation import AcceptedTurnV1, ConversationRepository


def accept_turn(
    repository: ConversationRepository,
    connection: Any,
    *,
    conversation_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    text: str,
) -> AcceptedTurnV1 | None:
    # Defence in depth only: `MessageCreateIn` strips and enforces a non-empty
    # length, so the transport never reaches this branch. It stays for direct
    # callers, and deliberately raises rather than silently persisting blank
    # text.
    normalized = text.strip()
    if not normalized:
        raise ValueError("message text must not be empty")
    return repository.accept_turn(
        connection,
        conversation_id=conversation_id,
        site_id=site_id,
        actor_id=actor_id,
        text=normalized,
        # Server-generated correlation identity (spine, *Correlation*). The
        # wider AD-13 problem-details correlation gap stays open and is
        # recorded in this story's completion notes.
        request_id=uuid4(),
    )
