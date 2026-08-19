"""Read, revise, and reject reversible proposals with transactional idempotency."""
from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import TypeAdapter

from application.contracts.canonical import contract_digest
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    ProposalV1,
    ProposalViewV1,
)
from application.drafting.resolve import (
    DraftConstraintError,
    DraftResolutionContextV1,
    consequence_summary,
    derive_draft_id,
    resolve_constraints,
    unique_entities,
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


class ProjectionUnavailableError(ProposalCommandError):
    """The proposal row is readable but its scenario projection is not.

    Distinct from "no such proposal": the planner should be told the scenario
    could not be read, not that their draft has ceased to exist.
    """


def _view(proposal: ProposalV1, current_version_id: UUID) -> ProposalViewV1:
    return ProposalViewV1(
        proposal=proposal,
        current_scenario_version_id=current_version_id,
        stale=proposal.scenario_version_id != current_version_id,
    )


def _max_constraints() -> int:
    from settings import default_settings

    return default_settings().scheduling_draft_max_constraints


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
        raise ProjectionUnavailableError(
            "the proposal's scenario projection could not be read"
        )
    return _view(record.proposal, overview.scenario_version_id)


def _operation(proposal_id: UUID, command: str) -> str:
    """The operation is what the command *does* — never who asked for it.

    Folding the idempotency key in here would make `command_idempotency.operation`
    unique per request, so the table's `(site_id, actor_id, operation,
    idempotency_key)` constraint could never fire on the case it exists for: one
    key reused with a different body.
    """
    return f"{command}:{proposal_id}"


def _body_hash(expected_resource_version: int, value: object | None = None) -> str:
    """AD-8: actor, site, operation, canonical body hash **plus expected version**.

    Resolved at review 2026-08-18. The expected version is part of the command's
    identity, not merely a concurrency guard: replaying one key against a
    different expected version is a semantically different command and must
    conflict rather than return the first command's stored result.
    """
    payload: dict[str, object] = {"expected_resource_version": expected_resource_version}
    if value is not None:
        payload["constraints"] = TypeAdapter(tuple[DraftConstraintProposalV1, ...]).dump_python(
            tuple(value), mode="json"
        )
    return contract_digest(payload)[2]


def _replay_or_conflict(
    repository,
    connection,
    *,
    site_id,
    actor_id,
    operation,
    idempotency_key,
    body_hash,
    current_version_id: UUID,
):
    stored = repository.get_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    if stored is None:
        return None
    if stored.body_hash != body_hash:
        raise IdempotencyKeyConflictError("idempotency key was already used with another body")
    replayed = TypeAdapter(ProposalViewV1).validate_python(stored.response_payload)
    # Recompute drift against the CURRENT projection rather than replaying the
    # `stale` flag captured at first execution (AD-14: cached data is never
    # authority). A replay after a scenario reimport must still read as stale.
    return _view(replayed.proposal, current_version_id)


def _current_for_command(repository, projection_reader, connection, proposal_id):
    record = repository.get_current(connection, proposal_id=proposal_id, for_update=True)
    if record is None or record.proposal.scenario_id is None:
        return None, None
    overview = projection_reader.get_overview(connection, record.proposal.scenario_id)
    if overview is None:
        raise ProjectionUnavailableError(
            "the proposal's scenario projection could not be read"
        )
    return record, overview


def revise_proposal(
    repository: ProposalRepository,
    projection_reader: ScenarioProjectionReader,
    connection,
    *,
    proposal_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    constraints: tuple[DraftConstraintProposalV1, ...],
    expected_resource_version: int,
    idempotency_key: str,
) -> ProposalViewV1 | None:
    """Resolve an UNTRUSTED revision and append an immutable version.

    `constraints` arrives from a browser and is exactly as untrusted as a model
    tool call, so it goes through the same resolver the draft capability uses
    (`application/drafting/resolve.py`). Nothing the client sends — labels,
    descriptions, resolved entities — is persisted; all of it is recomposed
    from the pinned projection.
    """
    limit = _max_constraints()
    if not 1 <= len(constraints) <= limit:
        raise ProposalCommandError(
            f"a revision requires between one and {limit} constraints"
        )
    operation = _operation(proposal_id, "revision")
    body_hash = _body_hash(expected_resource_version, constraints)
    record, overview = _current_for_command(
        repository, projection_reader, connection, proposal_id
    )
    if record is None or overview is None:
        return None
    replay = _replay_or_conflict(
        repository, connection, site_id=site_id, actor_id=actor_id,
        operation=operation, idempotency_key=idempotency_key, body_hash=body_hash,
        current_version_id=overview.scenario_version_id,
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

    context = DraftResolutionContextV1(
        projection_reader=projection_reader,
        connection=connection,
        scenario_id=current.scenario_id,
        scenario_version_id=current.scenario_version_id,
    )
    try:
        resolved = resolve_constraints(context, constraints, overview.horizon_minutes)
    except DraftConstraintError as exc:
        raise ProposalCommandError(str(exc)) from exc

    revised = ProposalV1(
        **{
            **current.__dict__,
            "proposal_version_id": uuid4(),
            "resolved_entities": unique_entities(resolved),
            "constraints": resolved,
            "consequence_summary": consequence_summary(resolved, current.preserved_locks),
            "canonical_hash": derive_draft_id(
                current.scenario_version_id, resolved, current.preserved_locks
            ),
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
        idempotency_key=idempotency_key,
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
    """Close a proposal out. Permitted while stale, deliberately.

    Rejection is not a rebase and changes no baseline — it is the one action
    that is unconditionally safe on a stale draft. Refusing it would leave a
    scenario reimport able to strand a proposal `active` with no terminal path,
    which is the opposite of what AC3's "terminal rejection" asks for.
    """
    operation = _operation(proposal_id, "rejection")
    body_hash = _body_hash(expected_resource_version)
    record, overview = _current_for_command(
        repository, projection_reader, connection, proposal_id
    )
    if record is None or overview is None:
        return None
    replay = _replay_or_conflict(
        repository, connection, site_id=site_id, actor_id=actor_id,
        operation=operation, idempotency_key=idempotency_key, body_hash=body_hash,
        current_version_id=overview.scenario_version_id,
    )
    if replay is not None:
        return replay
    current = record.proposal
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
        idempotency_key=idempotency_key,
        body_hash=body_hash,
        actor_id=actor_id,
        response_payload=TypeAdapter(ProposalViewV1).dump_python(result, mode="json"),
    )
    return result


__all__ = [
    "IdempotencyKeyConflictError", "ProjectionUnavailableError", "ProposalCommandError",
    "RejectedProposalError", "StaleProposalError", "StaleResourceVersionError",
    "get_proposal", "reject_proposal", "revise_proposal",
]
