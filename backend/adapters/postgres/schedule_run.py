"""SQLAlchemy Core adapter for the governed schedule-run aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Connection, exists, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from adapters.postgres.schema import (
    command_idempotency,
    job_queue,
    run_snapshot,
    schedule_assignment,
    schedule_run,
    schedule_version,
)
from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.canonical import contract_digest
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import ScheduleRunStatusV1, ScheduleVersionV1
from application.contracts.scenario_projection import QualificationRefV1
from application.ports.schedule_run import (
    IdempotentScheduleRunResultV1,
    RunNotCancellableError,
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


class PostgresScheduleRunRepository:
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
        result = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status == expected_status,
                schedule_run.c.resource_version == expected_resource_version,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", 1) != 1:
            raise RunNotCancellableError(
                f"schedule run is no longer {expected_status} at resource version "
                f"{expected_resource_version}"
            )

    def cancel_queued_run(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        expected_resource_version: int,
    ) -> None:
        self._cancel_transition(
            connection,
            run_id=run_id,
            site_id=site_id,
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
        expected_resource_version: int,
    ) -> None:
        self._cancel_transition(
            connection,
            run_id=run_id,
            site_id=site_id,
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
        raise ValueError(f"schedule run is no longer {expected_status}")

    def mark_running(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        fencing_epoch: int,
    ) -> None:
        result = connection.execute(
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
        )
        if getattr(result, "rowcount", 1) != 1:
            self._raise_transition_failure(
                connection,
                run_id=run_id,
                site_id=site_id,
                fencing_epoch=fencing_epoch,
                expected_status="solver_queued",
            )

    def create_queued_run(
        self,
        connection: Connection,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
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
        connection.execute(
            insert(schedule_run).values(
                id=snapshot.schedule_run_id,
                site_id=site_id,
                run_snapshot_id=snapshot.snapshot_id,
                status="solver_queued",
            )
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
    ) -> None:
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
        result = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status.in_(("solver_running", "cancellation_requested")),
                self._has_current_epoch(run_id, site_id, fencing_epoch),
            )
            .values(
                status=status,
                reason=reason,
                candidate_schedule_version_id=candidate_id,
                resource_version=schedule_run.c.resource_version + 1,
                finished_at=candidate.created_at if candidate else (finished_at or datetime.now(timezone.utc)),
            )
        )
        if getattr(result, "rowcount", 1) != 1:
            self._raise_transition_failure(
                connection,
                run_id=run_id,
                site_id=site_id,
                fencing_epoch=fencing_epoch,
                expected_status="solver_running or cancellation_requested",
            )


__all__ = ["PostgresScheduleRunRepository"]
