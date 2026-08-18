"""Read, revise, and reject reversible proposals with transactional idempotency."""
from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import TypeAdapter

from application.contracts.canonical import contract_digest
from application.contracts.proposal import (
    DraftConstraintV1,
    ProposalV1,
    ProposalViewV1,
    ResolvedEntityV1,
)
from application.ports.proposal import ProposalRepository
from application.ports.scenario_projection import ScenarioProjectionReader


class ProposalCommandError(ValueError):
    pass


class IdempotencyKeyConflictError(ProposalCommandError):
    pass


class StaleResourceVersionError(ProposalCommandError):
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"expected resource version {expected}; current is {current}")


class StaleProposalError(ProposalCommandError):
    pass


class RejectedProposalError(ProposalCommandError):
    pass


def _view(proposal: ProposalV1, current_version_id: UUID) -> ProposalViewV1:
    return ProposalViewV1(
        proposal=proposal,
        current_scenario_version_id=current_version_id,
        stale=proposal.scenario_version_id != current_version_id,
    )


def get_proposal(
    repository: ProposalRepository,
    projection_reader: ScenarioProjectionReader,
    connection,
    *,
    proposal_id: UUID,
) -> ProposalViewV1 | None:
    record = repository.get_current(connection, proposal_id=proposal_id)
    if record is None or record.proposal.scenario_id is None:
        return None
    overview = projection_reader.get_overview(connection, record.proposal.scenario_id)
    if overview is None:
        return None
    return _view(record.proposal, overview.scenario_version_id)


def _operation(proposal_id: UUID, command: str, idempotency_key: str) -> str:
    return f"{command}:{proposal_id}:{idempotency_key}"


def _body_hash(expected_resource_version: int, value: object | None = None) -> str:
    # The expected version is the concurrency guard, not the semantic command
    # body. A retry may refresh that guard while retaining the same effect key.
    payload: dict[str, object] = {}
    if value is not None:
        payload["constraints"] = TypeAdapter(type(value)).dump_python(value, mode="json")
    return contract_digest(payload)[2]


def _replay_or_conflict(repository, connection, *, site_id, actor_id, operation, body_hash):
    stored = repository.get_idempotent_result(
        connection, site_id=site_id, actor_id=actor_id, operation=operation
    )
    if stored is None:
        return None
    if stored.body_hash != body_hash:
        raise IdempotencyKeyConflictError("idempotency key was already used with another body")
    return TypeAdapter(ProposalViewV1).validate_python(stored.response_payload)


def _current_for_command(repository, projection_reader, connection, proposal_id):
    record = repository.get_current(connection, proposal_id=proposal_id, for_update=True)
    if record is None or record.proposal.scenario_id is None:
        return None, None
    overview = projection_reader.get_overview(connection, record.proposal.scenario_id)
    return record, overview


def revise_proposal(
    repository: ProposalRepository,
    projection_reader: ScenarioProjectionReader,
    connection,
    *,
    proposal_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    constraints: tuple[DraftConstraintV1, ...],
    expected_resource_version: int,
    idempotency_key: str,
) -> ProposalViewV1 | None:
    if not 1 <= len(constraints) <= 10:
        raise ProposalCommandError("a revision requires between one and ten constraints")
    operation = _operation(proposal_id, "revision", idempotency_key)
    body_hash = _body_hash(expected_resource_version, constraints)
    record, overview = _current_for_command(
        repository, projection_reader, connection, proposal_id
    )
    if record is None or overview is None:
        return None
    replay = _replay_or_conflict(
        repository, connection, site_id=site_id, actor_id=actor_id,
        operation=operation, body_hash=body_hash,
    )
    if replay is not None:
        return replay
    current = record.proposal
    if current.scenario_version_id != overview.scenario_version_id:
        raise StaleProposalError("proposal is stale against the governed scenario version")
    if current.state == "rejected":
        raise RejectedProposalError("a rejected proposal cannot be revised")
    if expected_resource_version != current.resource_version:
        raise StaleResourceVersionError(expected_resource_version, current.resource_version)
    for constraint in constraints:
        if any(
            entity.scenario_version_id != current.scenario_version_id
            for entity in constraint.resolved_entities
        ):
            raise ProposalCommandError("revision entities must match the proposal scenario version")
    entities: list[ResolvedEntityV1] = []
    seen: set[tuple[str, str]] = set()
    for constraint in constraints:
        for entity in constraint.resolved_entities:
            key = (entity.group, entity.record_id)
            if key not in seen:
                seen.add(key)
                entities.append(entity)
    digest = contract_digest(
        {
            "scenario_version_id": str(current.scenario_version_id),
            "constraints": TypeAdapter(type(constraints)).dump_python(constraints, mode="json"),
            "preserved_locks": TypeAdapter(type(current.preserved_locks)).dump_python(
                current.preserved_locks, mode="json"
            ),
        }
    )[2]
    revised = ProposalV1(
        **{
            **current.__dict__,
            "proposal_version_id": uuid4(),
            "resolved_entities": tuple(entities),
            "constraints": constraints,
            "consequence_summary": (
                f"{len(constraints)} reversible constraint"
                f"{'s' if len(constraints) != 1 else ''}; preserved "
                f"{len(current.preserved_locks)} existing lock"
                f"{'s' if len(current.preserved_locks) != 1 else ''}; no baseline change."
            ),
            "canonical_hash": digest,
            "resource_version": current.resource_version + 1,
        }
    )
    result = _view(revised, overview.scenario_version_id)
    repository.append_revision(
        connection,
        proposal=revised,
        site_id=site_id,
        version_ordinal=record.version_ordinal + 1,
        operation=operation,
        body_hash=body_hash,
        actor_id=actor_id,
        response_payload=TypeAdapter(ProposalViewV1).dump_python(result, mode="json"),
    )
    return result


def reject_proposal(
    repository: ProposalRepository,
    projection_reader: ScenarioProjectionReader,
    connection,
    *,
    proposal_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    expected_resource_version: int,
    idempotency_key: str,
) -> ProposalViewV1 | None:
    operation = _operation(proposal_id, "rejection", idempotency_key)
    body_hash = _body_hash(expected_resource_version)
    record, overview = _current_for_command(
        repository, projection_reader, connection, proposal_id
    )
    if record is None or overview is None:
        return None
    replay = _replay_or_conflict(
        repository, connection, site_id=site_id, actor_id=actor_id,
        operation=operation, body_hash=body_hash,
    )
    if replay is not None:
        return replay
    current = record.proposal
    if current.scenario_version_id != overview.scenario_version_id:
        raise StaleProposalError("proposal is stale against the governed scenario version")
    if current.state == "rejected":
        raise RejectedProposalError("proposal is already rejected")
    if expected_resource_version != current.resource_version:
        raise StaleResourceVersionError(expected_resource_version, current.resource_version)
    rejected = ProposalV1(
        **{**current.__dict__, "state": "rejected", "resource_version": current.resource_version + 1}
    )
    result = _view(rejected, overview.scenario_version_id)
    repository.reject(
        connection,
        proposal=rejected,
        site_id=site_id,
        operation=operation,
        body_hash=body_hash,
        actor_id=actor_id,
        response_payload=TypeAdapter(ProposalViewV1).dump_python(result, mode="json"),
    )
    return result


__all__ = [
    "IdempotencyKeyConflictError", "ProposalCommandError", "RejectedProposalError",
    "StaleProposalError", "StaleResourceVersionError", "get_proposal",
    "reject_proposal", "revise_proposal",
]
