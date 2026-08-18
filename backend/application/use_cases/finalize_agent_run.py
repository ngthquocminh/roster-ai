"""Atomically persist a trusted draft and finalize its conversation run."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.contracts.activity import DraftReferenceV1
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
    """Compose the create-draft bundle inside the caller's one transaction.

    This function is the only place the Scheduling and Conversation aggregates
    meet (AD-22): it translates `ProposalV1` into the Conversation-owned
    `DraftReferenceV1` so neither repository has to read the other's contract.

    Ordering is deliberate. `finish_agent_run` holds the run's still-claimable
    guard, so it runs *first*: writing the proposal ahead of it would let a
    duplicate finalisation fail on a proposal-side constraint and mask the
    `AgentRunNotQueuedError` that correctly describes what happened. Both writes
    share the caller's transaction, so the bundle stays atomic either way.
    """
    if isinstance(payload, ProposalV1):
        if payload.proposal_id is None or payload.proposal_version_id is None:
            raise ValueError("a trusted proposal must carry durable identifiers")
        executed = conversation_repository.finish_agent_run(
            connection,
            claimed=claimed,
            status=status,
            payload=DraftReferenceV1(
                proposal_id=payload.proposal_id,
                proposal_version_id=payload.proposal_version_id,
                consequence_summary=payload.consequence_summary,
            ),
            request_id=request_id,
        )
        proposal_repository.create_draft(
            connection,
            proposal=payload,
            site_id=claimed.site_id,
            conversation_id=claimed.conversation_id,
            actor_id=claimed.actor_id,
        )
        return executed
    return conversation_repository.finish_agent_run(
        connection,
        claimed=claimed,
        status=status,
        payload=payload,
        request_id=request_id,
    )


__all__ = ["finalize_agent_run"]
