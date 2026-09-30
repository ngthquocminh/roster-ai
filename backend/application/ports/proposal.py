"""Application port for durable reversible proposals; framework-free by design."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.proposal import ProposalEndedByV1, ProposalV1


@dataclass(frozen=True)
class ProposalRecordV1:
    proposal: ProposalV1
    version_ordinal: int
    created_by_actor_id: UUID
    ended_by: ProposalEndedByV1 | None = None
    applied_version_id: UUID | None = None
    applied_version_ordinal: int | None = None


@dataclass(frozen=True)
class IdempotentResultV1:
    body_hash: str
    response_payload: dict


class ProposalRepository(Protocol):
    def create_draft(
        self,
        connection: Any,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        conversation_id: UUID,
        actor_id: UUID,
    ) -> ProposalV1: ...

    def get_current(
        self, connection: Any, *, proposal_id: UUID, for_update: bool = False
    ) -> ProposalRecordV1 | None: ...

    def get_working(
        self, connection: Any, *, conversation_id: UUID, for_update: bool
    ) -> ProposalRecordV1 | None:
        """The conversation's `active` proposal (at most one, by the unique index)."""
        ...

    def append_agent_version(
        self,
        connection: Any,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        version_ordinal: int,
    ) -> None:
        """Append a version by the agent: no idempotency row (finalize is exactly-once)."""
        ...

    def end_by_assistant(
        self, connection: Any, *, proposal_id: UUID, resource_version: int
    ) -> None: ...

    def mark_applied(
        self, connection: Any, *, site_id: UUID, schedule_version_id: UUID
    ) -> bool:
        """Mark the draft a promoted schedule version pinned as `applied`.

        Zero rows changed is normal (no proposal, or already ended) and returns
        ``False``; it is not an error.
        """
        ...

    def get_version(
        self, connection: Any, *, proposal_version_id: UUID
    ) -> tuple[int, ProposalV1] | None: ...

    def get_idempotent_result(
        self,
        connection: Any,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> IdempotentResultV1 | None: ...

    def append_revision(
        self,
        connection: Any,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        version_ordinal: int,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        actor_id: UUID,
        response_payload: dict,
    ) -> None: ...

    def reject(
        self,
        connection: Any,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        actor_id: UUID,
        response_payload: dict,
    ) -> None: ...


__all__ = ["IdempotentResultV1", "ProposalRecordV1", "ProposalRepository"]
