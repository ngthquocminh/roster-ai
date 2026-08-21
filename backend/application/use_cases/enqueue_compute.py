"""Atomically enqueue one immutable governed schedule-run computation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from application.contracts.canonical import contract_digest
from application.contracts.job_lease import MAX_IDEMPOTENCY_KEY_LENGTH, JobLeaseV1
from application.contracts.run_snapshot import SCHEMA_VERSION
from application.contracts.schedule_version import ScheduleRunStatusV1
from application.capabilities.scheduling_optimize import scheduling_optimize_manifest
from application.ports.proposal import ProposalRepository
from application.ports.scenario_catalogue import ScenarioCatalogueReader
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.create_run_snapshot import create_run_snapshot


SCOPE_CONTROLS = (
    "COVERS: roles:worker_reuses_shiftmind_runtime; "
    "COVERS: events:queued_run_progress_v1; "
    # This module creates the job and the run; it neither writes nor observes
    # a cancellation. The command lives in `cancel_schedule_run`, the
    # observation in `lease_and_execute_schedule_run`.
    "NOT COVERED: cancellation:command_owned_by_cancel_schedule_run; "
    "NOT COVERED: cancellation:mid_solve_preemption_owned_by_first_story_raising_wall_time_limit; "
    "COVERS: contracts:capability_version_from_scheduling_optimize_manifest; "
    # AC1 names "actor/site/attempt IDs" in the bundle, but `attempt_id` is
    # NULL on every job this use case creates. That is Decision 5 working as
    # intended — an attempt is per LEASE ACQUISITION, and nothing has leased
    # this job yet — not an omission. Recorded here because Decisions 6 and 7
    # both got an entry for their equivalent gaps and this one did not.
    "NOT COVERED: contracts:attempt_id_unset_until_first_lease"
)

NON_TERMINAL_RUN_STATUSES: tuple[ScheduleRunStatusV1, ...] = (
    "solver_queued",
    "solver_running",
    "cancellation_requested",
)


class EnqueueComputeError(ValueError):
    pass


class IdempotencyKeyConflictError(EnqueueComputeError):
    pass


class SiteConcurrencyExhaustedError(EnqueueComputeError):
    code = "site_concurrency_exhausted"


class StaleProposalResourceVersionError(EnqueueComputeError):
    code = "stale_resource_version"

    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(
            f"expected proposal resource version {expected}; current is {current}"
        )


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
    actor_id: UUID,
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
    if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        # Both tables are written in this one transaction; an over-long key
        # would insert into job_queue and then abort the whole transaction on
        # command_idempotency with a driver-level truncation error.
        raise EnqueueComputeError(
            f"idempotency_key must be 1..{MAX_IDEMPOTENCY_KEY_LENGTH} characters"
        )
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
    run_repository.acquire_site_enqueue_lock(connection, site_id=site_id)
    active_runs = run_repository.count_runs_with_statuses(
        connection,
        site_id=site_id,
        statuses=NON_TERMINAL_RUN_STATUSES,
    )
    if active_runs >= settings.site_max_concurrent_runs:
        raise SiteConcurrencyExhaustedError(
            f"site has reached its limit of {settings.site_max_concurrent_runs} active runs"
        )
    if record.proposal.resource_version != expected_proposal_resource_version:
        raise StaleProposalResourceVersionError(
            expected_proposal_resource_version,
            record.proposal.resource_version,
        )

    accepted_at = clock()
    snapshot = create_run_snapshot(
        proposal_repository,
        scenario_catalogue,
        run_repository,
        connection,
        proposal_id=proposal_id,
        settings=settings,
        actor_id=actor_id,
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
        capability_version=scheduling_optimize_manifest().capability_version,
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
    "NON_TERMINAL_RUN_STATUSES",
    "SiteConcurrencyExhaustedError",
    "StaleProposalResourceVersionError",
    "SCOPE_CONTROLS",
    "enqueue_compute",
]
