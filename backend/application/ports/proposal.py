"""Application port for durable reversible proposals; framework-free by design."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.proposal import ProposalV1


@dataclass(frozen=True)
class ProposalRecordV1:
    proposal: ProposalV1
    version_ordinal: int
    created_by_actor_id: UUID


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
