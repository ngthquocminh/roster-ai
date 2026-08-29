"""SQLAlchemy Core adapter for the governed schedule-run aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import Connection, exists, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from adapters.postgres.schema import (
    command_idempotency,
    job_queue,
    persisted_event,
    proposal_version,
    run_snapshot,
    schedule_assignment,
    schedule_run,
    schedule_version,
    proposal,
)
from adapters.postgres.conversation import UnsupportedActivityPayloadError
from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.activity import RunProgressActivityV1
from application.contracts.canonical import contract_digest
from application.contracts.persisted_event import PersistedEventV1
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import (
    RUN_EVENT_TYPES,
    ScheduleRunStatusV1,
    ScheduleVersionV1,
)
from application.contracts.scenario_projection import QualificationRefV1
from application.ports.schedule_run import (
    IdempotentScheduleRunResultV1,
    IllegalTransitionError,
    RunNotCancellableError,
    RunTransitionConflictError,
    ScheduleRunEventHeadV1,
    ScheduleRunPageV1,
    ScheduleRunSummaryV1,
    ScheduleRunViewV1,
    ScheduleRunStateV1,
    StaleLeaseError,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a `timestamptz` decoded in the session timezone to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_FINALIZE_STATUSES = frozenset(
    (
        "solver_completed",
        "solver_infeasible",
        "solver_timed_out",
        "solver_cancelled",
        "solver_failed",
    )
)

_FINALIZE_EXPECTED_STATUSES = {
    "solver_completed": ("solver_running", "cancellation_requested"),
    "solver_infeasible": ("solver_running", "cancellation_requested"),
    "solver_timed_out": (
        "solver_queued",
        "solver_running",
        "cancellation_requested",
    ),
    "solver_cancelled": ("cancellation_requested",),
    "solver_failed": (
        "solver_queued",
        "solver_running",
        "cancellation_requested",
    ),
}


class PostgresScheduleRunRepository:
    def get_conversation_for_run(self, connection: Connection, *, run_id: UUID, site_id: UUID) -> UUID | None:
        return connection.execute(
            select(proposal.c.conversation_id)
            .select_from(schedule_run.join(run_snapshot, (run_snapshot.c.id == schedule_run.c.run_snapshot_id) & (run_snapshot.c.site_id == schedule_run.c.site_id)).join(proposal, (proposal.c.id == run_snapshot.c.proposal_id) & (proposal.c.site_id == run_snapshot.c.site_id)))
            .where(schedule_run.c.id == run_id, schedule_run.c.site_id == site_id)
        ).scalar_one_or_none()
    def get_candidate(
        self,
        connection: Connection,
        *,
        schedule_run_id: UUID,
        site_id: UUID,
    ) -> ScheduleVersionV1 | None:
        row = connection.execute(
            select(schedule_version.c.payload).where(
                schedule_version.c.schedule_run_id == schedule_run_id,
                schedule_version.c.site_id == site_id,
            )
        ).one_or_none()
        if row is None:
            return None
        return TypeAdapter(ScheduleVersionV1).validate_python(row.payload)

    def get_run(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunViewV1 | None:
        row = connection.execute(
            select(
                schedule_run.c.id,
                schedule_run.c.status,
                schedule_run.c.reason,
                schedule_run.c.resource_version,
                schedule_run.c.created_at,
                schedule_run.c.finished_at,
                job_queue.c.cancellation_requested,
            )
            .select_from(
                schedule_run.outerjoin(
                    job_queue,
                    (job_queue.c.schedule_run_id == schedule_run.c.id)
                    & (job_queue.c.site_id == schedule_run.c.site_id),
                )
            )
            .where(schedule_run.c.id == run_id, schedule_run.c.site_id == site_id)
        ).one_or_none()
        if row is None:
            return None
        return ScheduleRunViewV1(
            schedule_run_id=row.id,
            status=row.status,
            reason=row.reason,
            resource_version=row.resource_version,
            cancellation_requested=bool(row.cancellation_requested),
            created_at=_as_utc(row.created_at),
            finished_at=_as_utc(row.finished_at),
        )

    def list_runs(
        self,
        connection: Connection,
        *,
        scenario_id: UUID,
        site_id: UUID,
        cursor: int,
        limit: int,
    ) -> ScheduleRunPageV1:
        # Newest-first (AC1). `run_snapshot.scenario_id` -- not `schedule_run` --
        # carries the scenario this run belongs to; `proposal_version` supplies
        # the immutable ordinal a planner can cite (distinct from the mutable
        # `proposal.resource_version` Retry needs, which this row deliberately
        # does not carry -- see `ScheduleRunSummaryV1`'s docstring).
        #
        # AC1's "updated time". `schedule_run` has no `updated_at` column and
        # `finished_at` is NULL for every non-terminal run, so the newest event
        # on the run's stream is the only source. Correlated MAX rather than a
        # join so a run with several events still yields one row;
        # `ix_persisted_event_schedule_run_id` covers the lookup. COALESCE keeps
        # the field non-nullable for a run whose stream is still empty.
        last_event_at = (
            select(func.max(persisted_event.c.occurred_at))
            .where(
                persisted_event.c.schedule_run_id == schedule_run.c.id,
                persisted_event.c.site_id == schedule_run.c.site_id,
            )
            .correlate(schedule_run)
            .scalar_subquery()
        )
        query = (
            select(
                schedule_run.c.id,
                schedule_run.c.status,
                schedule_run.c.reason,
                schedule_run.c.resource_version,
                schedule_run.c.created_at,
                func.coalesce(last_event_at, schedule_run.c.created_at).label(
                    "updated_at"
                ),
                schedule_run.c.finished_at,
                run_snapshot.c.scenario_version_id,
                run_snapshot.c.proposal_id,
                proposal_version.c.version_ordinal,
                run_snapshot.c.baseline_schedule_version,
            )
            .select_from(
                schedule_run.join(
                    run_snapshot,
                    (run_snapshot.c.id == schedule_run.c.run_snapshot_id)
                    & (run_snapshot.c.site_id == schedule_run.c.site_id),
                ).join(
                    proposal_version,
                    (proposal_version.c.id == run_snapshot.c.proposal_version_id)
                    & (proposal_version.c.site_id == run_snapshot.c.site_id),
                )
            )
            .where(
                run_snapshot.c.scenario_id == scenario_id,
                schedule_run.c.site_id == site_id,
            )
            .order_by(schedule_run.c.created_at.desc(), schedule_run.c.id.desc())
            .offset(cursor)
            # One extra row answers "is there a next page?" in the same round
            # trip. (`scenario_projection` pages differently -- `_slice_window`
            # slices an already-materialised in-memory sequence and reads
            # `len(items)`, so it has no SQL over-fetch to mirror.)
            .limit(limit + 1)
        )
        rows = connection.execute(query).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        # Same FROM and WHERE as the page query, so the count can never
        # disagree with what the pages actually yield. This route publishes no
        # filters, so matching == total; both are reported to match the shape
        # of the API's other paged reads.
        total_count = connection.execute(
            select(func.count())
            .select_from(
                schedule_run.join(
                    run_snapshot,
                    (run_snapshot.c.id == schedule_run.c.run_snapshot_id)
                    & (run_snapshot.c.site_id == schedule_run.c.site_id),
                ).join(
                    proposal_version,
                    (proposal_version.c.id == run_snapshot.c.proposal_version_id)
                    & (proposal_version.c.site_id == run_snapshot.c.site_id),
                )
            )
            .where(
                run_snapshot.c.scenario_id == scenario_id,
                schedule_run.c.site_id == site_id,
            )
        ).scalar_one()
        items = tuple(
            ScheduleRunSummaryV1(
                schedule_run_id=row.id,
                status=row.status,
                reason=row.reason,
                resource_version=row.resource_version,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                finished_at=_as_utc(row.finished_at),
                scenario_version_id=row.scenario_version_id,
                proposal_id=row.proposal_id,
                proposal_version=row.version_ordinal,
                baseline_schedule_version=row.baseline_schedule_version,
            )
            for row in rows
        )
        return ScheduleRunPageV1(
            items=items,
            next_cursor=(cursor + limit) if has_more else None,
            total_count=total_count,
            matching_count=total_count,
        )

    def event_head(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunEventHeadV1 | None:
        row = connection.execute(
            select(
                schedule_run.c.id,
                func.max(persisted_event.c.sequence).label("max_sequence"),
            )
            .select_from(
                schedule_run.outerjoin(
                    persisted_event,
                    (persisted_event.c.schedule_run_id == schedule_run.c.id)
                    & (persisted_event.c.site_id == schedule_run.c.site_id)
                    & (persisted_event.c.stream_id == schedule_run.c.id),
                )
            )
            .where(schedule_run.c.id == run_id, schedule_run.c.site_id == site_id)
            .group_by(schedule_run.c.id)
        ).one_or_none()
        if row is None:
            return None
        return ScheduleRunEventHeadV1(row.max_sequence or 0)

    def events_after(
        self,
        connection: Connection,
        *,
        stream_id: UUID,
        after,
        limit: int,
    ):
        visible = connection.execute(
            select(schedule_run.c.id).where(schedule_run.c.id == stream_id)
        ).scalar_one_or_none()
        if visible is None:
            return None
        rows = connection.execute(
            select(persisted_event)
            .where(
                persisted_event.c.stream_id == stream_id,
                persisted_event.c.schedule_run_id == stream_id,
                persisted_event.c.sequence > after,
            )
            .order_by(persisted_event.c.sequence)
            .limit(limit)
        ).all()
        return tuple(self._progress_event_from_row(row) for row in rows)

    @staticmethod
    def _progress_event_from_row(row) -> PersistedEventV1:
        # Mirror the conversation reader's allow-list. `_event_frames` catches
        # only `UnsupportedActivityPayloadError`; a raw `ValidationError` from
        # `validate_python` would escape an async generator whose 200 has
        # already been sent, tearing the body mid-frame and leaving the
        # client's `EventSource` to reconnect onto the same unreadable row
        # forever. An event this reader predates must close the stream
        # cleanly, not crash it.
        activity_type = (row.payload or {}).get("activity_type")
        if activity_type != "run_progress":
            raise UnsupportedActivityPayloadError(
                f"activity_type {activity_type!r} has no payload shape in this reader"
            )
        activity = TypeAdapter(RunProgressActivityV1).validate_python(row.payload)
        return PersistedEventV1(
            stream_id=row.stream_id,
            sequence=row.sequence,
            event_type=row.event_type,
            occurred_at=_as_utc(row.occurred_at),
            resource_version=row.resource_version,
            request_id=row.request_id,
            conversation_id=row.conversation_id,
            agent_run_id=row.agent_run_id,
            schedule_run_id=row.schedule_run_id,
            site_id=row.site_id,
            actor_id=row.actor_id,
            payload=activity,
        )

    @staticmethod
    def _write_progress_event(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        status: ScheduleRunStatusV1,
        reason: str | None,
        resource_version: int,
        request_id: UUID,
        occurred_at: datetime | None = None,
    ) -> None:
        # One clock per stream. Callers used to supply three different ones --
        # `snapshot.accepted_at` (upstream Python), the adapter's own `now()`,
        # and `row.finished_at` (database, itself `candidate.created_at` for a
        # completed run) -- so a single run's events were not comparable to
        # each other and a terminal event carried the candidate's creation time
        # rather than the transition's. `occurred_at` stays overridable for a
        # caller that genuinely owns the instant, but no transition writer
        # passes one now. `schedule_run.finished_at` keeps its own clock; that
        # divergence is pre-existing and tracked in deferred-work.
        when = occurred_at or datetime.now(timezone.utc)
        activity = RunProgressActivityV1(
            activity_id=uuid4(),
            activity_type="run_progress",
            schedule_run_id=run_id,
            status=status,
            reason=reason,
            resource_version=resource_version,
            occurred_at=when,
        )
        next_sequence = (
            select(func.coalesce(func.max(persisted_event.c.sequence), 0) + 1)
            .where(persisted_event.c.stream_id == run_id)
            .scalar_subquery()
        )
        connection.execute(
            insert(persisted_event).values(
                site_id=site_id,
                stream_id=run_id,
                sequence=next_sequence,
                event_type=RUN_EVENT_TYPES[status],
                occurred_at=when,
                resource_version=resource_version,
                request_id=request_id,
                conversation_id=None,
                agent_run_id=None,
                schedule_run_id=run_id,
                actor_id=actor_id,
                payload=TypeAdapter(RunProgressActivityV1).dump_python(
                    activity, mode="json"
                ),
            )
        )

    @staticmethod
    def _actor_for_run(
        connection: Connection, *, run_id: UUID, site_id: UUID
    ) -> UUID:
        # `scalar_one_or_none` with a `limit(1)`, not `scalar_one`: a run can
        # legitimately exist with no job row (`create_run_snapshot` writes the
        # run; only `enqueue_compute` bundles the job alongside it), and Story
        # 3.9's manual flow will produce that shape deliberately. A
        # `NoResultFound` here would abort an otherwise valid terminal
        # transition and strand the run non-terminal, and a duplicate job row
        # would raise `MultipleResultsFound` for a value either row could
        # supply.
        actor_id = connection.execute(
            select(job_queue.c.actor_id)
            .where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if actor_id is not None:
            return actor_id
        # Fall back to the actor who opened this stream. `create_queued_run`
        # always writes `run.queued.v1` with a caller-supplied actor, so any
        # run reaching a later transition has one, and `persisted_event.actor_id`
        # is NOT NULL.
        return connection.execute(
            select(persisted_event.c.actor_id)
            .where(
                persisted_event.c.stream_id == run_id,
                persisted_event.c.schedule_run_id == run_id,
            )
            .order_by(persisted_event.c.sequence)
            .limit(1)
        ).scalar_one()

    def get_run_state(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> ScheduleRunStateV1 | None:
        row = connection.execute(
            select(schedule_run.c.status, schedule_run.c.resource_version).where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
            )
        ).one_or_none()
        if row is None:
            return None
        return ScheduleRunStateV1(row.status, row.resource_version)

    @staticmethod
    def _cancel_transition(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        expected_resource_version: int,
        expected_status: str,
        status: str,
        reason: str,
        terminal: bool,
    ) -> None:
        values = {
            "status": status,
            "reason": reason,
            "resource_version": schedule_run.c.resource_version + 1,
        }
        if terminal:
            values["finished_at"] = func.now()
        row = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status == expected_status,
                schedule_run.c.resource_version == expected_resource_version,
            )
            .values(**values)
            .returning(schedule_run.c.resource_version)
        ).one_or_none()
        if row is None:
            raise RunNotCancellableError(
                f"schedule run is no longer {expected_status} at resource version "
                f"{expected_resource_version}"
            )
        PostgresScheduleRunRepository._write_progress_event(
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=actor_id,
            status=status,
            reason=reason,
            resource_version=row.resource_version,
            # Minted once per cancellation command rather than once per event,
            # so every event this command writes shares one correlation id --
            # the property AD-21 needs and a per-event `uuid4()` cannot give.
            request_id=uuid4(),
        )

    def cancel_queued_run(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        expected_resource_version: int,
    ) -> None:
        self._cancel_transition(
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=actor_id,
            expected_resource_version=expected_resource_version,
            expected_status="solver_queued",
            status="solver_cancelled",
            reason="cancelled",
            terminal=True,
        )

    def request_cancellation(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        expected_resource_version: int,
    ) -> None:
        self._cancel_transition(
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=actor_id,
            expected_resource_version=expected_resource_version,
            expected_status="solver_running",
            status="cancellation_requested",
            reason="cancellation_requested",
            terminal=False,
        )

    @staticmethod
    def set_job_cancellation_requested(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> None:
        connection.execute(
            update(job_queue)
            .where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
            )
            .values(cancellation_requested=True)
        )

    @staticmethod
    def get_job_cancellation_requested(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> bool:
        """Read the job's carrier flag. A run with no job row carries no request."""
        value = connection.execute(
            select(job_queue.c.cancellation_requested).where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
            )
        ).scalar_one_or_none()
        return bool(value)

    @staticmethod
    def _has_current_epoch(run_id: UUID, site_id: UUID, fencing_epoch: int):
        # `status == 'leased'` and a positive epoch are load-bearing, not
        # decoration: a job is enqueued at fencing_epoch=0, so without them a
        # caller passing 0 would satisfy the fence for a job that was never
        # leased and could drive a run terminal outside any lease at all.
        return exists(
            select(1).select_from(job_queue).where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
                job_queue.c.status == "leased",
                job_queue.c.fencing_epoch == fencing_epoch,
                job_queue.c.fencing_epoch > 0,
            )
        )

    @staticmethod
    def _claim_epoch(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None:
        """Take a real row lock on the job before writing any effect.

        The `EXISTS` predicate inside the compare-and-set is an unlocked read:
        under READ COMMITTED it can pass against an epoch that a concurrent
        `lease_next_job` is in the middle of superseding, letting an expired
        worker commit. This touch UPDATE takes a row-exclusive lock that
        conflicts with that function's `FOR UPDATE`, so the two serialise, and
        it runs BEFORE the candidate rows are written rather than after.

        It uses only the `heartbeat_at` column the runtime role is granted
        (`GRANT UPDATE (status, heartbeat_at)`), and writes the clock from the
        database so the column has one time source.
        """
        result = connection.execute(
            update(job_queue)
            .where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
                job_queue.c.status == "leased",
                job_queue.c.fencing_epoch == fencing_epoch,
                job_queue.c.fencing_epoch > 0,
            )
            .values(heartbeat_at=func.now())
        )
        if getattr(result, "rowcount", 1) != 1:
            current_epoch = connection.execute(
                select(job_queue.c.fencing_epoch).where(
                    job_queue.c.schedule_run_id == run_id,
                    job_queue.c.site_id == site_id,
                )
            ).scalar_one_or_none()
            raise StaleLeaseError(
                f"schedule run lease epoch {fencing_epoch} is stale; "
                f"current is {current_epoch}"
            )

    @staticmethod
    def _raise_transition_failure(
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
        expected_status: str,
        target_status: str | None = None,
    ) -> None:
        current_epoch = connection.execute(
            select(job_queue.c.fencing_epoch).where(
                job_queue.c.schedule_run_id == run_id,
                job_queue.c.site_id == site_id,
            )
        ).scalar_one_or_none()
        if current_epoch != fencing_epoch:
            raise StaleLeaseError(
                f"schedule run lease epoch {fencing_epoch} is stale; current is {current_epoch}"
            )
        # Both reads below run only on the failure path, so the happy path pays
        # nothing. Naming the ACTUAL current status matters: the old message
        # said "no longer <expected>" for a run that was never <expected>.
        current_status = connection.execute(
            select(schedule_run.c.status).where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
            )
        ).scalar_one_or_none()
        if (current_status, target_status) == ("solver_running", "solver_cancelled"):
            raise IllegalTransitionError(
                "solver_running -> solver_cancelled is not an AD-7 ScheduleRun edge. "
                "Cancelling running work must pass through cancellation_requested "
                "(AD-6: cancellation is cooperative). A solver-reported 'cancelled' "
                "outcome on a run nobody cancelled has no legal terminal edge -- see "
                "finalize_schedule_run._terminal, which maps it without knowing the "
                "current status. Story 3.5 shipped persistence and replay, not this "
                "root cause; it stays owned by the first story that raises the "
                "wall-time limit (deferred-work)."
            )
        raise RunTransitionConflictError(
            f"schedule run is {current_status}, expected {expected_status}"
        )

    def mark_running(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
        request_id: UUID | None = None,
    ) -> None:
        # Transaction A now COMMITS this edge, so the fence must be claimed
        # under a real row lock exactly as `finalize_run` does. The unlocked
        # `_has_current_epoch` EXISTS can pass against an epoch a concurrent
        # `lease_next_job` is superseding; before the split a later rollback
        # suppressed the write, but a committed `solver_running` from a
        # fenced-out worker is durable AND bumps `resource_version`, which
        # silently invalidates an in-flight cancel holding the right version.
        # Claiming job_queue BEFORE schedule_run also fixes the lock order.
        self._claim_epoch(
            connection, run_id=run_id, site_id=site_id, fencing_epoch=fencing_epoch
        )
        row = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status == "solver_queued",
                self._has_current_epoch(run_id, site_id, fencing_epoch),
            )
            .values(
                status="solver_running",
                resource_version=schedule_run.c.resource_version + 1,
            )
            .returning(schedule_run.c.resource_version)
        ).one_or_none()
        if row is None:
            self._raise_transition_failure(
                connection,
                run_id=run_id,
                site_id=site_id,
                fencing_epoch=fencing_epoch,
                expected_status="solver_queued",
                target_status="solver_running",
            )
        self._write_progress_event(
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=self._actor_for_run(
                connection, run_id=run_id, site_id=site_id
            ),
            status="solver_running",
            reason=None,
            resource_version=row.resource_version,
            # The worker passes `lease.attempt_id`, which correlates this edge
            # to the attempt that produced it. `uuid4()` is only the fallback
            # for callers with no attempt in hand.
            request_id=request_id or uuid4(),
        )

    def create_queued_run(
        self,
        connection: Connection,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
        actor_id: UUID,
    ) -> None:
        assert snapshot.snapshot_id is not None
        assert snapshot.schedule_run_id is not None
        assert snapshot.scenario_id is not None
        assert snapshot.scenario_version_id is not None
        assert snapshot.proposal_id is not None
        assert snapshot.proposal_version_id is not None
        payload = TypeAdapter(RunSnapshotV1).dump_python(snapshot, mode="json")
        connection.execute(
            insert(run_snapshot).values(
                id=snapshot.snapshot_id,
                site_id=site_id,
                scenario_id=snapshot.scenario_id,
                scenario_version_id=snapshot.scenario_version_id,
                proposal_id=snapshot.proposal_id,
                proposal_version_id=snapshot.proposal_version_id,
                baseline_schedule_version=snapshot.baseline_schedule_version,
                payload=payload,
                canonical_hash=snapshot.canonical_hash,
                checksum_algorithm=snapshot.canonical_hash_algorithm,
                checksum_schema_version=snapshot.canonical_hash_schema_version,
                accepted_at=snapshot.accepted_at,
            )
        )
        # Read the version back like every other writer instead of asserting
        # `1`: the literal coupled the opening event to a `server_default` two
        # files away (`schema.py`), and would have lied silently if that
        # default or this insert path ever changed.
        queued = connection.execute(
            insert(schedule_run)
            .values(
                id=snapshot.schedule_run_id,
                site_id=site_id,
                run_snapshot_id=snapshot.snapshot_id,
                status="solver_queued",
            )
            .returning(schedule_run.c.resource_version)
        ).one()
        self._write_progress_event(
            connection,
            run_id=snapshot.schedule_run_id,
            site_id=site_id,
            actor_id=actor_id,
            status="solver_queued",
            reason=None,
            resource_version=queued.resource_version,
            request_id=uuid4(),
        )

    def enqueue_job(
        self,
        connection: Connection,
        *,
        job: JobLeaseV1,
        site_id: UUID,
    ) -> None:
        if job.site_id != site_id:
            raise ValueError("job site does not match the transaction site")
        connection.execute(
            insert(job_queue).values(
                id=job.job_id,
                site_id=site_id,
                job_type=job.job_type,
                status=job.status,
                schedule_run_id=job.schedule_run_id,
                actor_id=job.actor_id,
                attempt_id=job.attempt_id,
                contract_version=job.contract_version,
                capability_version=job.capability_version,
                idempotency_key=job.idempotency_key,
                lease_owner=job.lease_owner,
                lease_expires_at=job.lease_expires_at,
                heartbeat_at=job.heartbeat_at,
                fencing_epoch=job.fencing_epoch,
                cancellation_requested=job.cancellation_requested,
                created_at=job.created_at,
            )
        )

    def lease_next_job(
        self,
        connection: Connection,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> JobLeaseV1 | None:
        row = connection.execute(
            text(
                "SELECT * FROM workflow.lease_next_job("
                ":lease_owner, :lease_seconds)"
            ),
            {"lease_owner": lease_owner, "lease_seconds": lease_seconds},
        ).mappings().one_or_none()
        if row is None or row["id"] is None:
            return None
        # psycopg decodes `timestamptz` using the SESSION TimeZone, which
        # nothing pins to UTC. `JobLeaseV1` requires a zero utcoffset, so
        # without this every lease would raise on a non-UTC server. Same
        # normalisation `adapters/postgres/conversation.py` already applies.
        return JobLeaseV1(
            job_id=row["id"],
            job_type=row["job_type"],
            status=row["status"],
            site_id=row["site_id"],
            actor_id=row["actor_id"],
            attempt_id=row["attempt_id"],
            contract_version=row["contract_version"],
            capability_version=row["capability_version"],
            schedule_run_id=row["schedule_run_id"],
            idempotency_key=row["idempotency_key"],
            lease_owner=row["lease_owner"],
            lease_expires_at=_as_utc(row["lease_expires_at"]),
            heartbeat_at=_as_utc(row["heartbeat_at"]),
            fencing_epoch=row["fencing_epoch"],
            cancellation_requested=row["cancellation_requested"],
            created_at=_as_utc(row["created_at"]),
        )

    def renew_job_lease(
        self,
        connection: Connection,
        *,
        job_id: UUID,
        fencing_epoch: int,
        extension_seconds: int,
    ) -> LeaseRenewalV1:
        row = connection.execute(
            text(
                "SELECT renewed, cancellation_requested "
                "FROM workflow.renew_job_lease("
                ":job_id, :fencing_epoch, :extension_seconds)"
            ),
            {
                "job_id": job_id,
                "fencing_epoch": fencing_epoch,
                "extension_seconds": extension_seconds,
            },
        ).mappings().one()
        return LeaseRenewalV1(
            renewed=bool(row["renewed"]),
            cancellation_requested=bool(row["cancellation_requested"]),
        )

    def load_snapshot(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
    ) -> RunSnapshotV1 | None:
        payload = connection.execute(
            select(run_snapshot.c.payload)
            .select_from(
                schedule_run.join(
                    run_snapshot,
                    (run_snapshot.c.id == schedule_run.c.run_snapshot_id)
                    & (run_snapshot.c.site_id == schedule_run.c.site_id),
                )
            )
            .where(schedule_run.c.id == run_id, schedule_run.c.site_id == site_id)
        ).scalar_one_or_none()
        return None if payload is None else TypeAdapter(RunSnapshotV1).validate_python(payload)

    def complete_job(
        self,
        connection: Connection,
        *,
        job_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None:
        result = connection.execute(
            update(job_queue)
            .where(
                job_queue.c.id == job_id,
                job_queue.c.site_id == site_id,
                job_queue.c.status == "leased",
                job_queue.c.fencing_epoch == fencing_epoch,
            )
            .values(status="completed", heartbeat_at=func.now())
        )
        if getattr(result, "rowcount", 1) != 1:
            current_epoch = connection.execute(
                select(job_queue.c.fencing_epoch).where(
                    job_queue.c.id == job_id,
                    job_queue.c.site_id == site_id,
                )
            ).scalar_one_or_none()
            if current_epoch != fencing_epoch:
                raise StaleLeaseError(
                    f"job lease epoch {fencing_epoch} is stale; current is {current_epoch}"
                )
            raise ValueError("job is no longer leased")

    def fail_job(
        self,
        connection: Connection,
        *,
        job_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None:
        result = connection.execute(
            update(job_queue)
            .where(
                job_queue.c.id == job_id,
                job_queue.c.site_id == site_id,
                job_queue.c.status == "leased",
                job_queue.c.fencing_epoch == fencing_epoch,
            )
            .values(status="failed", heartbeat_at=func.now())
        )
        if getattr(result, "rowcount", 1) != 1:
            current_epoch = connection.execute(
                select(job_queue.c.fencing_epoch).where(
                    job_queue.c.id == job_id,
                    job_queue.c.site_id == site_id,
                )
            ).scalar_one_or_none()
            if current_epoch != fencing_epoch:
                raise StaleLeaseError(
                    f"job lease epoch {fencing_epoch} is stale; current is {current_epoch}"
                )
            raise ValueError("job is no longer leased")

    def get_idempotent_result(
        self,
        connection: Connection,
        *,
        site_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> IdempotentScheduleRunResultV1 | None:
        row = connection.execute(
            select(
                command_idempotency.c.body_hash,
                command_idempotency.c.response_payload,
            ).where(
                command_idempotency.c.site_id == site_id,
                command_idempotency.c.actor_id == actor_id,
                command_idempotency.c.operation == operation,
                command_idempotency.c.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        return (
            None
            if row is None
            else IdempotentScheduleRunResultV1(row.body_hash, row.response_payload)
        )

    @staticmethod
    def acquire_site_enqueue_lock(
        connection: Connection,
        *,
        site_id: UUID,
    ) -> None:
        connection.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(CAST(:site_id AS text), 0))"
            ),
            {"site_id": str(site_id)},
        )

    @staticmethod
    def count_runs_with_statuses(
        connection: Connection,
        *,
        site_id: UUID,
        statuses: tuple[ScheduleRunStatusV1, ...],
    ) -> int:
        return int(
            connection.scalar(
                select(func.count())
                .select_from(schedule_run)
                .where(
                    schedule_run.c.site_id == site_id,
                    schedule_run.c.status.in_(statuses),
                )
            )
            or 0
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
            postgres_insert(command_idempotency)
            .values(
                site_id=site_id,
                actor_id=actor_id,
                operation=operation,
                idempotency_key=idempotency_key,
                body_hash=body_hash,
                response_payload=response_payload,
            )
            .on_conflict_do_nothing(constraint="uq_command_idempotency_request")
        )

    def finalize_run(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
        status: ScheduleRunStatusV1,
        reason: str | None,
        candidate: ScheduleVersionV1 | None,
        finished_at: datetime | None = None,
        request_id: UUID | None = None,
    ) -> None:
        if status not in _FINALIZE_STATUSES:
            raise ValueError(f"{status} is not a terminal schedule-run status")
        expected_statuses = _FINALIZE_EXPECTED_STATUSES[status]
        # AC3 is about the EFFECT commit, so the fence is claimed under a real
        # row lock before any candidate row is written. Without this the guard
        # rejected nothing on its own — the inserts had already happened and
        # only the caller's rollback suppressed them.
        self._claim_epoch(
            connection, run_id=run_id, site_id=site_id, fencing_epoch=fencing_epoch
        )
        candidate_id = None
        if candidate is not None:
            assert candidate.schedule_version_id is not None
            payload = TypeAdapter(ScheduleVersionV1).dump_python(candidate, mode="json")
            algorithm, digest_schema, digest = contract_digest(payload)
            connection.execute(insert(schedule_version).values(
                id=candidate.schedule_version_id,
                site_id=site_id,
                schedule_run_id=run_id,
                scenario_id=candidate.scenario_id,
                scenario_version_id=candidate.scenario_version_id,
                proposal_id=candidate.proposal_id,
                proposal_version_id=candidate.proposal_version_id,
                solver_status=candidate.feasible_solver_status,
                payload=payload,
                canonical_hash=digest,
                checksum_algorithm=algorithm,
                checksum_schema_version=digest_schema,
                created_at=candidate.created_at,
            ))
            for assignment in candidate.assignments:
                connection.execute(insert(schedule_assignment).values(
                    site_id=site_id,
                    schedule_version_id=candidate.schedule_version_id,
                    assignment_record_id=assignment.record_id,
                    worker_id=assignment.worker_id,
                    task_id=assignment.task_id,
                    shift_id=assignment.shift_id,
                    start_minute=assignment.start_minute,
                    end_minute=assignment.end_minute,
                    qualification_refs=TypeAdapter(tuple[QualificationRefV1, ...]).dump_python(
                        assignment.qualification_refs, mode="json"
                    ),
                    source=assignment.source,
                    lock_ref=assignment.lock_ref,
                ))
            candidate_id = candidate.schedule_version_id
        row = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status.in_(expected_statuses),
                self._has_current_epoch(run_id, site_id, fencing_epoch),
            )
            .values(
                status=status,
                reason=reason,
                candidate_schedule_version_id=candidate_id,
                resource_version=schedule_run.c.resource_version + 1,
                finished_at=candidate.created_at if candidate else (finished_at or datetime.now(timezone.utc)),
            )
            .returning(schedule_run.c.resource_version, schedule_run.c.finished_at)
        ).one_or_none()
        if row is None:
            self._raise_transition_failure(
                connection,
                run_id=run_id,
                site_id=site_id,
                fencing_epoch=fencing_epoch,
                expected_status=" or ".join(expected_statuses),
                target_status=status,
            )
        self._write_progress_event(
            connection,
            run_id=run_id,
            site_id=site_id,
            actor_id=self._actor_for_run(
                connection, run_id=run_id, site_id=site_id
            ),
            status=status,
            reason=reason,
            resource_version=row.resource_version,
            request_id=request_id or uuid4(),
        )


__all__ = ["PostgresScheduleRunRepository"]
