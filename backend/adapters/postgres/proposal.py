"""SQLAlchemy Core adapter for governed reversible scheduling proposals."""
from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from adapters.postgres.schema import proposal as proposal_table
from adapters.postgres.schema import proposal_version
from adapters.postgres.schema import command_idempotency
from application.contracts.proposal import ProposalV1
from application.ports.proposal import IdempotentResultV1, ProposalRecordV1


class PostgresProposalRepository:
    def create_draft(
        self,
        connection: Connection,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        conversation_id: UUID,
        actor_id: UUID,
    ) -> ProposalV1:
        if proposal.proposal_id is None or proposal.proposal_version_id is None:
            raise ValueError("a trusted proposal must carry durable identifiers")
        if proposal.scenario_id is None or proposal.scenario_version_id is None:
            raise ValueError("a trusted proposal must carry governed scenario identifiers")

        connection.execute(
            insert(proposal_table).values(
                id=proposal.proposal_id,
                site_id=site_id,
                scenario_id=proposal.scenario_id,
                scenario_version_id=proposal.scenario_version_id,
                conversation_id=conversation_id,
                created_by_actor_id=actor_id,
                state=proposal.state,
                current_version_id=None,
                resource_version=proposal.resource_version,
            )
        )
        connection.execute(
            insert(proposal_version).values(
                id=proposal.proposal_version_id,
                site_id=site_id,
                proposal_id=proposal.proposal_id,
                version_ordinal=1,
                payload=TypeAdapter(ProposalV1).dump_python(proposal, mode="json"),
                canonical_hash=proposal.canonical_hash,
                checksum_algorithm=proposal.canonical_hash_algorithm,
                checksum_schema_version=proposal.canonical_hash_schema_version,
            )
        )
        connection.execute(
            update(proposal_table)
            .where(proposal_table.c.id == proposal.proposal_id)
            .values(current_version_id=proposal.proposal_version_id)
        )
        return proposal

    def get_current(
        self, connection: Connection, *, proposal_id: UUID, for_update: bool = False
    ) -> ProposalRecordV1 | None:
        # OUTER join: an inner join folds "no such proposal" together with
        # "this proposal has no current version", and the second is a broken
        # invariant the caller must be able to tell apart from a 404.
        statement = (
            select(proposal_table, proposal_version.c.version_ordinal, proposal_version.c.payload)
            .outerjoin(
                proposal_version,
                (proposal_version.c.id == proposal_table.c.current_version_id)
                & (proposal_version.c.site_id == proposal_table.c.site_id),
            )
            .where(proposal_table.c.id == proposal_id)
        )
        if for_update:
            statement = statement.with_for_update(of=proposal_table)
        row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        if row.payload is None:
            raise RuntimeError(
                f"proposal {proposal_id} has no current version row; the aggregate is inconsistent"
            )
        value = TypeAdapter(ProposalV1).validate_python(row.payload)
        value = ProposalV1(
            **{
                **value.__dict__,
                "state": row.state,
                "resource_version": row.resource_version,
            }
        )
        return ProposalRecordV1(
            proposal=value,
            version_ordinal=row.version_ordinal,
            created_by_actor_id=row.created_by_actor_id,
        )

    def get_idempotent_result(
        self,
        connection: Connection,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> IdempotentResultV1 | None:
        # Matches uq_command_idempotency_request exactly, so at most one row can
        # satisfy it and the read needs no ordering to be deterministic.
        row = connection.execute(
            select(command_idempotency.c.body_hash, command_idempotency.c.response_payload)
            .where(
                command_idempotency.c.site_id == site_id,
                command_idempotency.c.actor_id == actor_id,
                command_idempotency.c.operation == operation,
                command_idempotency.c.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        return None if row is None else IdempotentResultV1(row.body_hash, row.response_payload)

    def append_revision(
        self,
        connection: Connection,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        version_ordinal: int,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        actor_id: UUID,
        response_payload: dict,
    ) -> None:
        assert proposal.proposal_id is not None and proposal.proposal_version_id is not None
        connection.execute(
            insert(proposal_version).values(
                id=proposal.proposal_version_id,
                site_id=site_id,
                proposal_id=proposal.proposal_id,
                version_ordinal=version_ordinal,
                payload=TypeAdapter(ProposalV1).dump_python(proposal, mode="json"),
                canonical_hash=proposal.canonical_hash,
                checksum_algorithm=proposal.canonical_hash_algorithm,
                checksum_schema_version=proposal.canonical_hash_schema_version,
            )
        )
        connection.execute(
            update(proposal_table)
            .where(proposal_table.c.id == proposal.proposal_id)
            .values(
                current_version_id=proposal.proposal_version_id,
                resource_version=proposal.resource_version,
            )
        )
        self._store_idempotent_result(
            connection, site_id=site_id, actor_id=actor_id, operation=operation,
            idempotency_key=idempotency_key, body_hash=body_hash,
            response_payload=response_payload,
        )

    def reject(
        self,
        connection: Connection,
        *,
        proposal: ProposalV1,
        site_id: UUID,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        actor_id: UUID,
        response_payload: dict,
    ) -> None:
        assert proposal.proposal_id is not None
        connection.execute(
            update(proposal_table)
            .where(proposal_table.c.id == proposal.proposal_id)
            .values(state="rejected", resource_version=proposal.resource_version)
        )
        self._store_idempotent_result(
            connection, site_id=site_id, actor_id=actor_id, operation=operation,
            idempotency_key=idempotency_key, body_hash=body_hash,
            response_payload=response_payload,
        )

    @staticmethod
    def _store_idempotent_result(
        connection: Connection,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        response_payload: dict,
    ) -> None:
        connection.execute(
            postgres_insert(command_idempotency).values(
                site_id=site_id,
                actor_id=actor_id,
                operation=operation,
                idempotency_key=idempotency_key,
                body_hash=body_hash,
                response_payload=response_payload,
            ).on_conflict_do_nothing(constraint="uq_command_idempotency_request")
        )


__all__ = ["PostgresProposalRepository"]
