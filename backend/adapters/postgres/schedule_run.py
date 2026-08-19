"""SQLAlchemy Core adapter for the governed schedule-run aggregate."""
from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Connection, insert

from adapters.postgres.schema import run_snapshot, schedule_run
from application.contracts.run_snapshot import RunSnapshotV1


class PostgresScheduleRunRepository:
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


__all__ = ["PostgresScheduleRunRepository"]
