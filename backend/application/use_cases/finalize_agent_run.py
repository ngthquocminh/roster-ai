"""Atomically persist a trusted draft (or discard) and finalize its conversation run."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.contracts.activity import DraftReferenceV1
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.proposal import AgentDraftDiscardV1, AgentDraftWriteV1
from application.ports.conversation import (
    ClaimedAgentRunV1,
    ConversationRepository,
    ExecutedAgentRunV1,
)
from application.ports.proposal import ProposalRepository

# AC2's visible outcome when the conversation moved under an in-flight turn
# (spec 2.2, D8). Literal: the tests pin it.
DRAFT_CHANGED_DETAIL = "Your draft changed while I was working, so I didn't apply this change."
DRAFT_CHANGED_NEXT_STEP = "Ask again to apply it to the current draft."


def _draft_changed() -> TerminalOutcomeV1:
    return TerminalOutcomeV1(
        status="failed",
        reason="capability_error",
        detail=DRAFT_CHANGED_DETAIL,
        next_step=DRAFT_CHANGED_NEXT_STEP,
    )


def finalize_agent_run(
    conversation_repository: ConversationRepository,
    proposal_repository: ProposalRepository,
    connection: Any,
    *,
    claimed: ClaimedAgentRunV1,
    status: str,
    payload: GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1 | AgentDraftWriteV1,
    discard: AgentDraftDiscardV1 | None = None,
    request_id: UUID,
) -> ExecutedAgentRunV1:
    """Compose the draft/discard bundle inside the caller's one transaction.

    This function is the only place the Scheduling and Conversation aggregates
    meet (AD-22): it translates `AgentDraftWriteV1` into the Conversation-owned
    `DraftReferenceV1` so neither repository has to read the other's contract.

    THE GUARD (Story 5.11 Decision 8). It runs only when this turn carries a
    draft write or a discard; every other turn finalizes exactly as before, with
    no new lock. It takes the conversation lock FIRST, then the working-draft
    row: one lock order everywhere (conversation, then proposal), which is also
    why TX2 writes `mark_applied` last. A write is applied only if the
    conversation still looks exactly as the turn observed it; otherwise the turn
    ends with a `capability_error` and NOTHING is written to `proposal` or
    `proposal_version` (AC2). The unique index is a backstop that should never
    fire.

    Ordering is otherwise deliberate. `finish_agent_run` holds the run's
    still-claimable guard, so it runs *before* any proposal write: writing the
    proposal ahead of it would let a duplicate finalisation fail on a
    proposal-side constraint and mask the `AgentRunNotQueuedError` that
    correctly describes what happened. All writes share the caller's
    transaction, so the bundle stays atomic either way.
    """
    draft = payload if isinstance(payload, AgentDraftWriteV1) else None
    if draft is None and discard is None:
        return conversation_repository.finish_agent_run(
            connection,
            claimed=claimed,
            status=status,
            payload=payload,
            request_id=request_id,
        )
    if draft is not None:
        proposal = draft.proposal
        if proposal.proposal_id is None or proposal.proposal_version_id is None:
            raise ValueError("a trusted proposal must carry durable identifiers")
        if discard is not None and draft.outcome == "updated":
            # The tools make this unreachable (discard-then-draft is `created`,
            # draft-then-discard is refused): reaching it is a programming error.
            raise ValueError("a turn cannot both update and discard the working draft")

    conversation_repository.lock_conversation(connection, conversation_id=claimed.conversation_id)
    working = proposal_repository.get_working(
        connection, conversation_id=claimed.conversation_id, for_update=True
    )

    def _working_matches(proposal_id: UUID | None, resource_version: int | None) -> bool:
        return (
            working is not None
            and working.proposal.proposal_id == proposal_id
            and working.proposal.resource_version == resource_version
        )

    if discard is not None:
        applies = _working_matches(discard.proposal_id, discard.observed_resource_version)
    elif draft is not None and draft.outcome == "updated":
        applies = _working_matches(draft.observed_working_id, draft.observed_resource_version)
    else:  # draft `created`, no discard
        applies = working is None
    # discard + `created` draft: the draft replaces the discarded one, so the
    # check is the discard's (the first branch above already made it).

    if not applies:
        return conversation_repository.finish_agent_run(
            connection,
            claimed=claimed,
            status="agent_failed",
            payload=_draft_changed(),
            request_id=request_id,
        )

    if draft is not None:
        proposal = draft.proposal
        executed = conversation_repository.finish_agent_run(
            connection,
            claimed=claimed,
            status=status,
            payload=DraftReferenceV1(
                proposal_id=proposal.proposal_id,
                proposal_version_id=proposal.proposal_version_id,
                consequence_summary=proposal.consequence_summary,
            ),
            request_id=request_id,
        )
    else:
        executed = conversation_repository.finish_agent_run(
            connection,
            claimed=claimed,
            status=status,
            payload=payload,
            request_id=request_id,
        )
    if discard is not None:
        # Index order: the old draft leaves `active` before a new one is created.
        proposal_repository.end_by_assistant(
            connection,
            proposal_id=discard.proposal_id,
            resource_version=discard.observed_resource_version + 1,
        )
    if draft is not None:
        if draft.outcome == "created":
            proposal_repository.create_draft(
                connection,
                proposal=draft.proposal,
                site_id=claimed.site_id,
                conversation_id=claimed.conversation_id,
                actor_id=claimed.actor_id,
            )
        else:
            proposal_repository.append_agent_version(
                connection,
                proposal=draft.proposal,
                site_id=claimed.site_id,
                version_ordinal=draft.version_ordinal,
            )
    return executed


__all__ = ["DRAFT_CHANGED_DETAIL", "DRAFT_CHANGED_NEXT_STEP", "finalize_agent_run"]
