"""Atomically persist a trusted draft and finalize its conversation run."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.proposal import ProposalV1
from application.ports.conversation import (
    ClaimedAgentRunV1,
    ConversationRepository,
    ExecutedAgentRunV1,
)
from application.ports.proposal import ProposalRepository


def finalize_agent_run(
    conversation_repository: ConversationRepository,
    proposal_repository: ProposalRepository,
    connection: Any,
    *,
    claimed: ClaimedAgentRunV1,
    status: str,
    payload: GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1 | ProposalV1,
    request_id: UUID,
) -> ExecutedAgentRunV1:
    """Compose the create-draft bundle inside the caller's one transaction."""
    if isinstance(payload, ProposalV1):
        proposal_repository.create_draft(
            connection,
            proposal=payload,
            site_id=claimed.site_id,
            conversation_id=claimed.conversation_id,
            actor_id=claimed.actor_id,
        )
    return conversation_repository.finish_agent_run(
        connection,
        claimed=claimed,
        status=status,
        payload=payload,
        request_id=request_id,
    )


__all__ = ["finalize_agent_run"]
