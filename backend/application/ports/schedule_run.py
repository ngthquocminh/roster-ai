"""Application port for immutable snapshots and schedule-run persistence."""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import ScheduleRunStatusV1, ScheduleVersionV1


@dataclass(frozen=True)
class IdempotentScheduleRunResultV1:
    body_hash: str
    response_payload: dict


class StaleLeaseError(ValueError):
    """The caller's fencing epoch is no longer current for this run."""


class ScheduleRunRepository(Protocol):
    def mark_running(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None: ...

    def create_queued_run(
        self,
        connection: Any,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
    ) -> None: ...

    def enqueue_job(
        self,
        connection: Any,
        *,
        job: JobLeaseV1,
        site_id: UUID,
    ) -> None: ...

    def lease_next_job(
        self,
        connection: Any,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> JobLeaseV1 | None: ...

    def renew_job_lease(
        self,
        connection: Any,
        *,
        job_id: UUID,
        fencing_epoch: int,
        extension_seconds: int,
    ) -> LeaseRenewalV1: ...

    def load_snapshot(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> RunSnapshotV1 | None: ...

    def complete_job(
        self,
        connection: Any,
        *,
        job_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None: ...

    def get_idempotent_result(
        self,
        connection: Any,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> IdempotentScheduleRunResultV1 | None: ...

    def _store_idempotent_result(
        self,
        connection: Any,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
        body_hash: str,
        response_payload: dict,
    ) -> None: ...

    def finalize_run(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
        status: ScheduleRunStatusV1,
        reason: str | None,
        candidate: ScheduleVersionV1 | None,
        finished_at: datetime | None = None,
    ) -> None: ...


__all__ = [
    "IdempotentScheduleRunResultV1",
    "ScheduleRunRepository",
    "StaleLeaseError",
]
