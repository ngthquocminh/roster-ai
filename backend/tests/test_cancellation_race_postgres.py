from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from sqlalchemy import func, select, text, update

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.schema import (
    command_idempotency,
    job_queue,
    run_snapshot,
    schedule_run,
    schedule_version,
)
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
from application.use_cases.cancel_schedule_run import (
    IdempotencyKeyConflictError,
    StaleResourceVersionError,
    cancel_schedule_run,
)
from application.use_cases.lease_and_execute_schedule_run import (
    lease_and_execute_schedule_run,
)
from tests.test_job_leasing_postgres import (
    _candidate,
    _lease,
    _only_leasable,
    _queue_jobs,
    _runtime,
    lease_ids,
)


pytestmark = pytest.mark.postgres


def _key(prefix: str, run_id) -> str:
    return f"{prefix}-{run_id.hex}"[:40]


def _cancel(engine, ids, run_id, expected_version, key):
    repository = PostgresScheduleRunRepository()
    with engine.begin() as connection:
        _runtime(connection, ids["site"])
        return cancel_schedule_run(
            repository,
            connection,
            run_id=run_id,
            site_id=ids["site"],
            actor_id=ids["actor"],
            expected_resource_version=expected_version,
            idempotency_key=key,
        )


def _seed_valid_snapshot(engine, ids, run_id) -> None:
    with engine.begin() as connection:
        snapshot_id = connection.scalar(
            select(schedule_run.c.run_snapshot_id).where(schedule_run.c.id == run_id)
        )
        snapshot = RunSnapshotV1(
            snapshot_id=snapshot_id,
            schedule_run_id=run_id,
            scenario_id=ids["scenario"],
            scenario_version_id=ids["scenario_version"],
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            proposal_id=ids["proposal"],
            proposal_version_id=ids["proposal_version"],
            proposal_resource_version=1,
            solver_config=GovernedSolverConfigV1(),
            component_versions=(("application", "1"),),
            accepted_at=datetime.now(timezone.utc),
        )
        connection.execute(
            update(run_snapshot)
            .where(run_snapshot.c.id == snapshot_id)
            .values(payload=TypeAdapter(RunSnapshotV1).dump_python(snapshot, mode="json"))
        )


@contextmanager
def _runtime_connection(engine, site_id):
    with engine.begin() as connection:
        _runtime(connection, site_id)
        yield connection


def _run_worker(engine, repository, scheduler):
    with engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as lease_connection:
        lease_connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            return lease_and_execute_schedule_run(
                lease_connection,
                lambda site_id: _runtime_connection(engine, site_id),
                repository,
                scheduler,
                lease_owner=f"worker-{uuid4()}",
                lease_seconds=30,
            )
        finally:
            lease_connection.exec_driver_sql("RESET ROLE")


class _ForbiddenScheduler:
    def __init__(self) -> None:
        self.calls = 0

    def solve(self, _snapshot):
        self.calls += 1
        raise AssertionError("cancelled work reached the solver")


def test_cancel_bundle_replay_conflict_and_rollback_cover_all_three_writes(
    governed_postgres_engine, lease_ids
) -> None:
    repository = PostgresScheduleRunRepository()
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    key = _key("once", run_id)
    arguments = dict(
        run_id=run_id,
        site_id=lease_ids["site"],
        actor_id=lease_ids["actor"],
        expected_resource_version=1,
        idempotency_key=key,
    )
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        first = cancel_schedule_run(repository, connection, **arguments)
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        replay = cancel_schedule_run(repository, connection, **arguments)
    assert replay == first

    with governed_postgres_engine.connect() as connection:
        row = connection.execute(
            select(
                schedule_run.c.status,
                schedule_run.c.resource_version,
                schedule_run.c.candidate_schedule_version_id,
            ).where(schedule_run.c.id == run_id)
        ).one()
        assert row == ("solver_cancelled", 2, None)
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.id == job_id,
                job_queue.c.cancellation_requested.is_(True),
            )
        ) == 1
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == key
            )
        ) == 1

    with pytest.raises(IdempotencyKeyConflictError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        cancel_schedule_run(
            repository,
            connection,
            **{**arguments, "expected_resource_version": 2},
        )

    rollback_job, rollback_run = _queue_jobs(
        governed_postgres_engine, lease_ids, 1
    )[0]
    rollback_key = _key("rollback", rollback_run)
    with pytest.raises(RuntimeError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        cancel_schedule_run(
            repository,
            connection,
            run_id=rollback_run,
            site_id=lease_ids["site"],
            actor_id=lease_ids["actor"],
            expected_resource_version=1,
            idempotency_key=rollback_key,
        )
        raise RuntimeError("force rollback")
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(schedule_run.c.status, schedule_run.c.resource_version).where(
                schedule_run.c.id == rollback_run
            )
        ).one() == ("solver_queued", 1)
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.id == rollback_job,
                job_queue.c.cancellation_requested.is_(True),
            )
        ) == 0
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == rollback_key
            )
        ) == 0


def test_checkpoint_1_completes_a_cancelled_queued_job_without_solving(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)
    _cancel(governed_postgres_engine, lease_ids, run_id, 1, _key("cp1", run_id))
    _only_leasable(governed_postgres_engine, job_id)
    scheduler = _ForbiddenScheduler()

    outcome = _run_worker(
        governed_postgres_engine, PostgresScheduleRunRepository(), scheduler
    )

    assert outcome.status == "solver_cancelled"
    assert scheduler.calls == 0
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(job_queue.c.status).where(job_queue.c.id == job_id)
        ) == "completed"


def test_checkpoint_2_observes_a_cancel_after_running_commit(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)
    _only_leasable(governed_postgres_engine, job_id)
    repository = PostgresScheduleRunRepository()
    scheduler = _ForbiddenScheduler()
    opened = 0

    @contextmanager
    def injecting_factory(site_id):
        nonlocal opened
        opened += 1
        if opened == 2:
            _cancel(
                governed_postgres_engine,
                lease_ids,
                run_id,
                2,
                _key("cp2", run_id),
            )
        with governed_postgres_engine.begin() as connection:
            _runtime(connection, site_id)
            yield connection

    with governed_postgres_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as lease_connection:
        lease_connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            outcome = lease_and_execute_schedule_run(
                lease_connection,
                injecting_factory,
                repository,
                scheduler,
                lease_owner=f"worker-{uuid4()}",
                lease_seconds=30,
            )
        finally:
            lease_connection.exec_driver_sql("RESET ROLE")

    assert opened == 2
    assert outcome.status == "solver_cancelled"
    assert scheduler.calls == 0
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(schedule_run.c.status, schedule_run.c.reason).where(
                schedule_run.c.id == run_id
            )
        ).one() == ("solver_cancelled", "cancelled")
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 0


def test_cancellation_then_completion_uses_the_legal_requested_edge(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, f"worker-{uuid4()}")
    repository = PostgresScheduleRunRepository()
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=lease["fencing_epoch"],
        )
    _cancel(governed_postgres_engine, lease_ids, run_id, 2, _key("race-a", run_id))
    candidate = _candidate(run_id, lease_ids)
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=lease["fencing_epoch"],
            status="solver_completed",
            reason=None,
            candidate=candidate,
        )
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(schedule_run.c.status, schedule_run.c.resource_version).where(
                schedule_run.c.id == run_id
            )
        ).one() == ("solver_completed", 4)
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 1


def test_completion_then_cancellation_is_stale_and_writes_no_replay_row(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, f"worker-{uuid4()}")
    repository = PostgresScheduleRunRepository()
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=lease["fencing_epoch"],
        )
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=lease["fencing_epoch"],
            status="solver_completed",
            reason=None,
            candidate=_candidate(run_id, lease_ids),
        )
    key = _key("race-b", run_id)
    with pytest.raises(StaleResourceVersionError):
        _cancel(governed_postgres_engine, lease_ids, run_id, 2, key)
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(schedule_run.c.status, schedule_run.c.resource_version).where(
                schedule_run.c.id == run_id
            )
        ).one() == ("solver_completed", 3)
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == key
            )
        ) == 0


def test_runtime_grant_cannot_write_lease_or_fencing_columns(
    governed_postgres_engine,
) -> None:
    with governed_postgres_engine.connect() as connection:
        update_columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE grantee = 'shiftmind_runtime' "
                    "AND table_schema = 'workflow' AND table_name = 'job_queue' "
                    "AND privilege_type = 'UPDATE'"
                )
            ).scalars()
        )
    assert update_columns == {"status", "heartbeat_at", "cancellation_requested"}
    assert update_columns.isdisjoint(
        {"lease_owner", "lease_expires_at", "fencing_epoch"}
    )
