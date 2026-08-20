"""Atomically enqueue one immutable governed schedule-run computation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from application.contracts.canonical import contract_digest
from application.contracts.job_lease import JobLeaseV1
from application.contracts.run_snapshot import SCHEMA_VERSION
from application.ports.proposal import ProposalRepository
from application.ports.scenario_catalogue import ScenarioCatalogueReader
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.create_run_snapshot import create_run_snapshot


SCOPE_CONTROLS = (
    "COVERS: roles:worker_reuses_shiftmind_runtime; "
    "NOT COVERED: events:owned_by_story_3_5; "
    "NOT COVERED: cancellation:owned_by_story_3_4; "
    "NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6"
)


class EnqueueComputeError(ValueError):
    pass


class IdempotencyKeyConflictError(EnqueueComputeError):
    pass


@dataclass(frozen=True)
class EnqueueComputeResultV1:
    schedule_run_id: UUID
    job_id: UUID


def _body_hash(proposal_id: UUID, expected_resource_version: int) -> str:
    return contract_digest(
        {
            "proposal_id": str(proposal_id),
            "expected_proposal_resource_version": expected_resource_version,
        }
    )[2]


def enqueue_compute(
    proposal_repository: ProposalRepository,
    scenario_catalogue: ScenarioCatalogueReader,
    run_repository: ScheduleRunRepository,
    connection: Any,
    *,
    proposal_id: UUID,
    site_id: UUID,
    expected_proposal_resource_version: int,
    idempotency_key: str,
    settings: Any,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> EnqueueComputeResultV1:
    """Create snapshot, queued run, job, and replay record on one transaction."""
    record = proposal_repository.get_current(
        connection, proposal_id=proposal_id, for_update=True
    )
    if record is None:
        raise EnqueueComputeError("proposal was not found")
    actor_id = record.created_by_actor_id
    operation = f"enqueue_compute:{proposal_id}"
    body_hash = _body_hash(proposal_id, expected_proposal_resource_version)
    stored = run_repository.get_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    if stored is not None:
        if stored.body_hash != body_hash:
            raise IdempotencyKeyConflictError(
                "idempotency key was already used with another body"
            )
        return EnqueueComputeResultV1(
            schedule_run_id=UUID(stored.response_payload["schedule_run_id"]),
            job_id=UUID(stored.response_payload["job_id"]),
        )
    if record.proposal.resource_version != expected_proposal_resource_version:
        raise EnqueueComputeError(
            f"expected proposal resource version {expected_proposal_resource_version}; "
            f"current is {record.proposal.resource_version}"
        )

    accepted_at = clock()
    snapshot = create_run_snapshot(
        proposal_repository,
        scenario_catalogue,
        run_repository,
        connection,
        proposal_id=proposal_id,
        settings=settings,
        clock=lambda: accepted_at,
    )
    assert snapshot.schedule_run_id is not None
    job = JobLeaseV1(
        job_id=uuid4(),
        job_type="schedule_run_execute",
        status="queued",
        site_id=site_id,
        actor_id=actor_id,
        contract_version=SCHEMA_VERSION,
        capability_version=None,
        schedule_run_id=snapshot.schedule_run_id,
        idempotency_key=idempotency_key,
        created_at=accepted_at,
    )
    run_repository.enqueue_job(connection, job=job, site_id=site_id)
    assert job.job_id is not None
    result = EnqueueComputeResultV1(snapshot.schedule_run_id, job.job_id)
    run_repository._store_idempotent_result(
        connection,
        site_id=site_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
        body_hash=body_hash,
        response_payload={
            "schedule_run_id": str(result.schedule_run_id),
            "job_id": str(result.job_id),
        },
    )
    return result


__all__ = [
    "EnqueueComputeError",
    "EnqueueComputeResultV1",
    "IdempotencyKeyConflictError",
    "SCOPE_CONTROLS",
    "enqueue_compute",
]
