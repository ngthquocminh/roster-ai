from __future__ import annotations

import threading
import time
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


# ---------------------------------------------------------------------------
# Genuinely concurrent races.
#
# Every test above this line runs its transactions strictly one after another:
# each `engine.begin()` block closes before the next opens, so no two sessions
# ever contend for a row. That proves the state machine and nothing about
# concurrency -- which is why a lock-ordering deadlock between the cancel
# command and `finalize_run` survived a green suite. The tests below hold two
# transactions open at once and are the only ones that can see it.
# ---------------------------------------------------------------------------


def _wait_for_blocked_backend(engine, *, timeout=15.0) -> bool:
    """Block until some backend is waiting on a lock, so the interleaving is real."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as probe:
            waiting = probe.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND state = 'active'"
                )
            ).scalar_one()
        if waiting:
            return True
        time.sleep(0.05)
    return False


def _running_run(engine, ids):
    """Seed a leased, solver_running run with a valid snapshot."""
    job_id, run_id = _queue_jobs(engine, ids, 1)[0]
    _seed_valid_snapshot(engine, ids, run_id)
    _only_leasable(engine, job_id)
    lease = _lease(engine, f"worker-{uuid4()}")
    with engine.begin() as connection:
        _runtime(connection, ids["site"])
        PostgresScheduleRunRepository().mark_running(
            connection,
            run_id=run_id,
            site_id=ids["site"],
            fencing_epoch=lease["fencing_epoch"],
        )
    return job_id, run_id, lease


def test_cancel_racing_an_open_finalize_does_not_deadlock(
    governed_postgres_engine, lease_ids
) -> None:
    """The cancel command and `finalize_run` must take the two row locks in one order.

    `finalize_run` claims `workflow.job_queue` (`_claim_epoch`) and only then
    writes `schedule_run`; its window between the two spans one INSERT per
    assignment. Taking them in the opposite order deadlocks these two sessions
    (40P01) -- discarding a completed solve on one side, or turning a 409 into
    a bare 500 on the other.
    """
    _, run_id, lease = _running_run(governed_postgres_engine, lease_ids)
    repository = PostgresScheduleRunRepository()
    candidate = _candidate(run_id, lease_ids)
    claimed = threading.Event()
    failures = {}
    refusals = {}

    def finalizing_worker():
        try:
            with governed_postgres_engine.begin() as connection:
                _runtime(connection, lease_ids["site"])
                connection.exec_driver_sql("SET lock_timeout = '15s'")
                # Hold the job row exactly as finalize_run does, then pause in
                # the window before the schedule_run write.
                repository._claim_epoch(
                    connection,
                    run_id=run_id,
                    site_id=lease_ids["site"],
                    fencing_epoch=lease["fencing_epoch"],
                )
                claimed.set()
                _wait_for_blocked_backend(governed_postgres_engine)
                repository.finalize_run(
                    connection,
                    run_id=run_id,
                    site_id=lease_ids["site"],
                    fencing_epoch=lease["fencing_epoch"],
                    status="solver_completed",
                    reason=None,
                    candidate=candidate,
                )
        except Exception as exc:  # noqa: BLE001 - surfaced as a failure below
            failures["worker"] = exc

    def cancelling_planner():
        assert claimed.wait(15), "worker never claimed the job row"
        try:
            with governed_postgres_engine.begin() as connection:
                _runtime(connection, lease_ids["site"])
                connection.exec_driver_sql("SET lock_timeout = '15s'")
                cancel_schedule_run(
                    repository,
                    connection,
                    run_id=run_id,
                    site_id=lease_ids["site"],
                    actor_id=lease_ids["actor"],
                    expected_resource_version=2,
                    idempotency_key=_key("deadlock", run_id),
                )
        except StaleResourceVersionError as exc:
            # Losing to a completed solve is correct; a deadlock is not.
            refusals["cancel"] = exc
        except Exception as exc:  # noqa: BLE001
            failures["cancel"] = exc

    threads = [
        threading.Thread(target=finalizing_worker),
        threading.Thread(target=cancelling_planner),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=45)
        assert not thread.is_alive(), "a session hung -- lock ordering regressed"

    assert not failures, f"unexpected failure: {failures}"
    assert "cancel" in refusals
    with governed_postgres_engine.connect() as connection:
        # The completed solve survived: no deadlock rolled it back.
        assert connection.execute(
            select(schedule_run.c.status).where(schedule_run.c.id == run_id)
        ).scalar_one() == "solver_completed"
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 1


def test_concurrent_replay_of_one_idempotency_key_returns_the_stored_result(
    governed_postgres_engine, lease_ids
) -> None:
    """AD-8: a replay returns the ORIGINAL semantic result, including under contention.

    Two in-flight requests carrying the same key both read
    `get_idempotent_result -> None`. The loser's compare-and-set then matches
    zero rows, which used to surface as `409 run_not_cancellable` while the
    cancel was in fact succeeding -- exactly the double-click / timeout-retry
    case idempotency keys exist for.
    """
    _, run_id, _lease_row = _running_run(governed_postgres_engine, lease_ids)
    repository = PostgresScheduleRunRepository()
    key = _key("concurrent", run_id)
    ready = threading.Barrier(2)
    results = {}
    failures = {}

    def cancel(name):
        try:
            with governed_postgres_engine.begin() as connection:
                _runtime(connection, lease_ids["site"])
                connection.exec_driver_sql("SET lock_timeout = '15s'")
                ready.wait(timeout=15)
                results[name] = cancel_schedule_run(
                    repository,
                    connection,
                    run_id=run_id,
                    site_id=lease_ids["site"],
                    actor_id=lease_ids["actor"],
                    expected_resource_version=2,
                    idempotency_key=key,
                )
        except Exception as exc:  # noqa: BLE001
            failures[name] = exc

    threads = [
        threading.Thread(target=cancel, args=(name,)) for name in ("first", "second")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=45)
        assert not thread.is_alive()

    assert not failures, f"a replay was refused instead of replayed: {failures}"
    assert results["first"] == results["second"]
    assert results["first"].status == "cancellation_requested"
    assert results["first"].resource_version == 3
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == key
            )
        ) == 1
        assert connection.execute(
            select(schedule_run.c.status, schedule_run.c.resource_version).where(
                schedule_run.c.id == run_id
            )
        ).one() == ("cancellation_requested", 3)


def test_cancel_committing_between_the_state_read_and_mark_running_is_recovered(
    governed_postgres_engine, lease_ids
) -> None:
    """Checkpoint 1's read is unlocked, so its compare-and-set can lose.

    The dangerous ordering is not "cancel commits, then the worker reads" -- it
    is "worker reads solver_queued, cancel commits, the worker's WHERE
    re-evaluates and matches zero rows". That used to raise a bare ValueError
    out of `run_once`, leaving the job `leased` with no terminal status.
    """
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)
    _only_leasable(governed_postgres_engine, job_id)
    scheduler = _ForbiddenScheduler()

    class _CancelDuringStateRead:
        """Commit a cancellation on another connection, once, mid-Transaction A."""

        def __init__(self, inner) -> None:
            self._inner = inner
            self.fired = False

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def get_run_state(self, connection, **kwargs):
            state = self._inner.get_run_state(connection, **kwargs)
            if not self.fired:
                self.fired = True
                _cancel(
                    governed_postgres_engine,
                    lease_ids,
                    run_id,
                    1,
                    _key("cp1race", run_id),
                )
            return state

    outcome = _run_worker(
        governed_postgres_engine,
        _CancelDuringStateRead(PostgresScheduleRunRepository()),
        scheduler,
    )

    assert outcome.status == "solver_cancelled"
    assert scheduler.calls == 0
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(schedule_run.c.status).where(schedule_run.c.id == run_id)
        ).scalar_one() == "solver_cancelled"
        # The job reached a terminal state instead of being stranded `leased`.
        assert connection.execute(
            select(job_queue.c.status).where(job_queue.c.id == job_id)
        ).scalar_one() == "completed"
