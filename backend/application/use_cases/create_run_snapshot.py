"""Freeze one accepted proposal into an immutable governed run snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable
from uuid import UUID, uuid4

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.proposal import ProposalV1
from application.contracts.run_snapshot import (
    SCHEMA_VERSION,
    GovernedSolverConfigV1,
    RunSnapshotV1,
)
from application.ports.proposal import ProposalRepository
from application.ports.scenario_catalogue import ScenarioCatalogueReader
from application.ports.schedule_run import ScheduleRunRepository


class SnapshotCreationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def _input_evidence(proposal: ProposalV1, context) -> tuple[EvidenceRefV1, ...]:
    common = dict(
        scenario_version_id=context.scenario_version_id,
        checksum_algorithm=context.checksum_algorithm,
        checksum_schema_version=context.checksum_schema_version,
        checksum_digest=context.checksum_digest,
        producing_run_version=None,
        baseline_schedule_version=context.baseline_schedule_version,
    )
    references = [
        EvidenceRefV1(
            **common,
            group=entity.group,
            record_id=entity.record_id,
        )
        for entity in proposal.resolved_entities
    ]
    references.extend(
        EvidenceRefV1(**common, group="locks", record_id=lock.record_id)
        for lock in proposal.preserved_locks
    )
    return tuple(references)


def create_run_snapshot(
    proposal_repository: ProposalRepository,
    scenario_catalogue: ScenarioCatalogueReader,
    run_repository: ScheduleRunRepository,
    connection: Any,
    *,
    proposal_id: UUID,
    settings: Any,
    actor_id: UUID | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RunSnapshotV1:
    """Validate persisted authority and insert snapshot + queued run together."""
    record = proposal_repository.get_current(
        connection, proposal_id=proposal_id, for_update=True
    )
    if record is None:
        raise SnapshotCreationError("proposal_not_found", "proposal was not found")
    proposal = record.proposal
    if proposal.state == "rejected":
        raise SnapshotCreationError(
            "rejected_proposal", "a rejected proposal cannot be scheduled"
        )
    if proposal.scenario_id is None:
        raise SnapshotCreationError(
            "invalid_proposal", "proposal does not carry a governed scenario"
        )
    context = scenario_catalogue.get_scenario_context(connection, proposal.scenario_id)
    if context is None:
        raise SnapshotCreationError(
            "scenario_unavailable", "the governed scenario could not be read"
        )
    if (
        proposal.scenario_version_id != context.scenario_version_id
        or proposal.expected_baseline_schedule_version
        != context.baseline_schedule_version
    ):
        raise SnapshotCreationError(
            "stale_proposal", "proposal is stale; silent rebasing is forbidden"
        )
    if proposal.proposal_id is None or proposal.proposal_version_id is None:
        raise SnapshotCreationError(
            "invalid_proposal", "proposal does not carry durable version identifiers"
        )

    snapshot = RunSnapshotV1(
        snapshot_id=uuid4(),
        schedule_run_id=uuid4(),
        scenario_id=proposal.scenario_id,
        scenario_version_id=context.scenario_version_id,
        checksum_algorithm=context.checksum_algorithm,
        checksum_schema_version=context.checksum_schema_version,
        checksum_digest=context.checksum_digest,
        baseline_schedule_version=context.baseline_schedule_version,
        proposal_id=proposal.proposal_id,
        proposal_version_id=proposal.proposal_version_id,
        proposal_resource_version=proposal.resource_version,
        preserved_locks=proposal.preserved_locks,
        constraints=proposal.constraints,
        objectives=(),
        solver_config=GovernedSolverConfigV1(
            engine_name=settings.solver_engine_name,
            seed=settings.solver_seed,
            num_search_workers=settings.solver_num_search_workers,
            max_deterministic_time=settings.solver_max_deterministic_time,
            wall_time_limit_seconds=settings.solver_wall_time_limit_seconds,
        ),
        component_versions=(
            ("application", "1"),
            ("contract", SCHEMA_VERSION),
            ("ortools", _package_version("ortools")),
        ),
        accepted_at=clock(),
        input_evidence_refs=_input_evidence(proposal, context),
    )
    # One repository call on the caller-owned transaction makes it impossible
    # for an adapter to commit the immutable snapshot without its queued run.
    run_repository.create_queued_run(
        connection,
        snapshot=snapshot,
        site_id=context.site_id,
        actor_id=actor_id or record.created_by_actor_id,
    )
    return snapshot


__all__ = ["SnapshotCreationError", "create_run_snapshot"]
