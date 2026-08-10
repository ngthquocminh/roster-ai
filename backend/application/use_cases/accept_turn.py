"""Accept a planner turn without executing the agent (AD-22)."""
from __future__ import annotations

from typing import Any, Callable
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
    after_message: Callable[[], None] | None = None,
) -> AcceptedTurnV1 | None:
    normalized = text.strip()
    if not normalized:
        raise ValueError("message text must not be empty")
    return repository.accept_turn(
        connection, conversation_id=conversation_id, site_id=site_id,
        actor_id=actor_id, text=normalized, request_id=uuid4(),
        after_message=after_message,
    )
