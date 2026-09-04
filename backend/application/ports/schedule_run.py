"""Application port for immutable snapshots and schedule-run persistence."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.persisted_event import PersistedEventV1
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import ScheduleRunStatusV1, ScheduleVersionV1


@dataclass(frozen=True)
class IdempotentScheduleRunResultV1:
    body_hash: str
    response_payload: dict


@dataclass(frozen=True)
class ScheduleRunStateV1:
    status: ScheduleRunStatusV1
    resource_version: int


@dataclass(frozen=True)
class ScheduleRunEventHeadV1:
    max_sequence: Decimal


@dataclass(frozen=True)
class ScheduleRunViewV1:
    schedule_run_id: UUID
    status: ScheduleRunStatusV1
    reason: str | None
    resource_version: int
    cancellation_requested: bool
    #: The polling fallback is the degraded path for clients that cannot hold
    #: an SSE connection, so it must answer "when did this run finish?" --
    #: `finalize_run` populates `finished_at` on the very row this view joins.
    #: `ScheduleRunOut` has carried both fields since the cancellation replay
    #: payload; only this read left them permanently null.
    created_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True)
class ScheduleRunSummaryV1:
    """One row of the planner-visible Runs list (Story 3.7 AC1).

    Every field here already lives on `schedule_run`, `run_snapshot`, or
    `proposal_version` -- no new column, no migration. `proposal_version` is
    the immutable ordinal (`proposal_version.version_ordinal`), not the live,
    mutable `proposal.resource_version` a Retry command needs; Retry re-reads
    the current resource version through the existing proposal read (see
    `RunsTable.tsx`), not from this row.
    """

    schedule_run_id: UUID
    status: ScheduleRunStatusV1
    reason: str | None
    resource_version: int
    created_at: datetime
    #: When this run last changed -- the newest `persisted_event.occurred_at`
    #: on its stream, falling back to `created_at` for a run whose stream is
    #: still empty. AC1 asks for an "updated time"; `finished_at` cannot serve
    #: because it is NULL for every non-terminal run, which is exactly the set
    #: a planner monitors. `schedule_run` carries no `updated_at` column, so
    #: the event stream is the only source.
    updated_at: datetime
    finished_at: datetime | None
    scenario_version_id: UUID
    proposal_id: UUID
    proposal_version: int
    baseline_schedule_version: str | None


@dataclass(frozen=True)
class ScheduleRunPageV1:
    items: tuple[ScheduleRunSummaryV1, ...]
    next_cursor: int | None
    #: Every run visible for the scenario, not just this page -- the shared
    #: `PaginationControls` primitive needs it to offer Previous/Last and a
    #: "showing X-Y of N" line. This route publishes no filters yet, so
    #: `matching_count` equals `total_count`; it is carried anyway so the shape
    #: matches the API's other paged reads (`TaskPageOut` and siblings) and a
    #: future filter does not become a breaking response change.
    total_count: int
    matching_count: int


class StaleLeaseError(ValueError):
    """The caller's fencing epoch is no longer current for this run."""


class RunNotCancellableError(ValueError):
    """The schedule run no longer permits the requested cancellation edge."""


class RunTransitionConflictError(ValueError):
    """A compare-and-set lost: the row moved between the read and the UPDATE.

    Distinct from `StaleLeaseError` (the fencing epoch moved) because the
    caller's recourse differs: a lost transition is recoverable by re-reading
    and re-dispatching, whereas a stale lease means this worker must stop.
    """


class IllegalTransitionError(ValueError):
    """The attempted (from_status, to_status) pair is not an AD-7 edge."""


class ScheduleRunRepository(Protocol):
    def get_conversation_for_run(self, connection: Any, *, run_id: UUID, site_id: UUID) -> UUID | None: ...
    def get_candidate(
        self,
        connection: Any,
        *,
        schedule_run_id: UUID,
        site_id: UUID,
    ) -> ScheduleVersionV1 | None: ...

    def get_version(
        self,
        connection: Any,
        *,
        schedule_version_id: UUID,
        site_id: UUID,
    ) -> ScheduleVersionV1 | None: ...

    def get_run(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunViewV1 | None: ...

    def list_runs(
        self,
        connection: Any,
        *,
        scenario_id: UUID,
        site_id: UUID,
        cursor: int,
        limit: int,
    ) -> ScheduleRunPageV1: ...

    def event_head(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunEventHeadV1 | None: ...

    def events_after(
        self,
        connection: Any,
        *,
        stream_id: UUID,
        after: Decimal,
        limit: int,
    ) -> tuple[PersistedEventV1, ...] | None: ...

    def get_run_state(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunStateV1 | None: ...

    def cancel_queued_run(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        expected_resource_version: int,
    ) -> None: ...

    def request_cancellation(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        expected_resource_version: int,
    ) -> None: ...

    def set_job_cancellation_requested(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> None: ...

    def get_job_cancellation_requested(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> bool: ...

    def mark_running(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
        request_id: UUID | None = None,
    ) -> datetime | None: ...

    def create_queued_run(
        self,
        connection: Any,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
        actor_id: UUID,
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

    def fail_job(
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

    def acquire_site_enqueue_lock(
        self,
        connection: Any,
        *,
        site_id: UUID,
    ) -> None: ...

    def count_runs_with_statuses(
        self,
        connection: Any,
        *,
        site_id: UUID,
        statuses: tuple[ScheduleRunStatusV1, ...],
    ) -> int: ...

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
        request_id: UUID | None = None,
    ) -> None: ...


__all__ = [
    "IdempotentScheduleRunResultV1",
    "IllegalTransitionError",
    "RunNotCancellableError",
    "RunTransitionConflictError",
    "ScheduleRunRepository",
    "ScheduleRunEventHeadV1",
    "ScheduleRunPageV1",
    "ScheduleRunSummaryV1",
    "ScheduleRunViewV1",
    "ScheduleRunStateV1",
    "StaleLeaseError",
]
