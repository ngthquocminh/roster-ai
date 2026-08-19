"""SQLAlchemy Core adapter for the governed schedule-run aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Connection, insert, update

from adapters.postgres.schema import (
    run_snapshot,
    schedule_assignment,
    schedule_run,
    schedule_version,
)
from application.contracts.canonical import contract_digest
from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import ScheduleRunStatusV1, ScheduleVersionV1
from application.contracts.scenario_projection import QualificationRefV1


class PostgresScheduleRunRepository:
    def mark_running(
        self, connection: Connection, *, run_id: UUID, site_id: UUID
    ) -> None:
        result = connection.execute(
            update(schedule_run)
            .where(
                schedule_run.c.id == run_id,
                schedule_run.c.site_id == site_id,
                schedule_run.c.status == "solver_queued",
            )
            .values(status="solver_running")
        )
        if getattr(result, "rowcount", 1) != 1:
            raise ValueError("schedule run is no longer solver_queued")

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

    def finalize_run(
        self,
        connection: Connection,
        *,
        run_id: UUID,
        site_id: UUID,
        status: ScheduleRunStatusV1,
        reason: str | None,
        candidate: ScheduleVersionV1 | None,
    ) -> None:
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
                schedule_run.c.status == "solver_running",
            )
            .values(
                status=status,
                reason=reason,
                candidate_schedule_version_id=candidate_id,
                finished_at=candidate.created_at if candidate else datetime.now(timezone.utc),
            )
        )
        if getattr(result, "rowcount", 1) != 1:
            raise ValueError("schedule run is no longer solver_running")


__all__ = ["PostgresScheduleRunRepository"]
