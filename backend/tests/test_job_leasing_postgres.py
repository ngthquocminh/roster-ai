from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.schema import (
    app_user,
    command_idempotency,
    conversation,
    job_queue,
    organization,
    persisted_event,
    proposal,
    proposal_version,
    run_snapshot,
    scenario,
    scenario_version,
    schedule_run,
    schedule_version,
    site,
)
from application.contracts.job_lease import LeaseRenewalV1
from application.contracts.proposal import ProposalV1
from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.proposal import ProposalRecordV1
from application.ports.scenario_catalogue import ScenarioContext
from application.ports.schedule_run import RunTransitionConflictError, StaleLeaseError
from application.use_cases.enqueue_compute import (
    IdempotencyKeyConflictError,
    SiteConcurrencyExhaustedError,
    enqueue_compute,
)
from application.use_cases.lease_and_execute_schedule_run import (
    FatalJobError,
    lease_and_execute_schedule_run,
)


pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def lease_ids(governed_postgres_engine):
    ids = {
        name: uuid4()
        for name in (
            "org",
            "site",
            "actor",
            "scenario",
            "scenario_version",
            "conversation",
            "proposal",
            "proposal_version",
        )
    }
    with governed_postgres_engine.begin() as connection:
        connection.execute(insert(organization).values(id=ids["org"], name="Lease Org"))
        connection.execute(
            insert(site).values(
                id=ids["site"], organization_id=ids["org"], name="Lease Site"
            )
        )
        connection.execute(
            insert(app_user).values(
                id=ids["actor"],
                idp_subject="lease-planner",
                email="lease-planner@example.test",
            )
        )
        connection.execute(
            insert(scenario).values(
                id=ids["scenario"],
                site_id=ids["site"],
                fixture_id="lease-fixture",
                name="Lease Fixture",
            )
        )
        connection.execute(
            insert(scenario_version).values(
                id=ids["scenario_version"],
                site_id=ids["site"],
                scenario_id=ids["scenario"],
                fixture_id="lease-fixture",
                version="v1",
                payload={},
                checksum_digest="a" * 64,
            )
        )
        connection.execute(
            insert(conversation).values(
                id=ids["conversation"],
                site_id=ids["site"],
                scenario_id=ids["scenario"],
                scenario_version_id=ids["scenario_version"],
                created_by_actor_id=ids["actor"],
            )
        )
        connection.execute(
            insert(proposal).values(
                id=ids["proposal"],
                site_id=ids["site"],
                scenario_id=ids["scenario"],
                scenario_version_id=ids["scenario_version"],
                conversation_id=ids["conversation"],
                created_by_actor_id=ids["actor"],
                state="active",
                current_version_id=None,
                resource_version=1,
            )
        )
        connection.execute(
            insert(proposal_version).values(
                id=ids["proposal_version"],
                site_id=ids["site"],
                proposal_id=ids["proposal"],
                version_ordinal=1,
                payload={},
                canonical_hash="b" * 64,
                checksum_algorithm="sha256",
                checksum_schema_version="rfc8785-v1",
            )
        )
        connection.execute(
            update(proposal)
            .where(proposal.c.id == ids["proposal"])
            .values(current_version_id=ids["proposal_version"])
        )
    return ids


def _queue_jobs(engine, ids, count):
    job_ids = []
    with engine.begin() as connection:
        for index in range(count):
            snapshot_id = uuid4()
            run_id = uuid4()
            job_id = uuid4()
            connection.execute(
                insert(run_snapshot).values(
                    id=snapshot_id,
                    site_id=ids["site"],
                    scenario_id=ids["scenario"],
                    scenario_version_id=ids["scenario_version"],
                    proposal_id=ids["proposal"],
                    proposal_version_id=ids["proposal_version"],
                    payload={},
                    canonical_hash=f"{index + 1:064x}",
                    checksum_algorithm="sha256",
                    checksum_schema_version="rfc8785-v1",
                    accepted_at=datetime.now(timezone.utc),
                )
            )
            connection.execute(
                insert(schedule_run).values(
                    id=run_id,
                    site_id=ids["site"],
                    run_snapshot_id=snapshot_id,
                    status="solver_queued",
                )
            )
            connection.execute(
                insert(job_queue).values(
                    id=job_id,
                    site_id=ids["site"],
                    schedule_run_id=run_id,
                    actor_id=ids["actor"],
                    contract_version="1",
                    # `.hex` not `str()`: the column is varchar(40), matching
                    # command_idempotency, and "seed-" + a dashed UUID is 41.
                    idempotency_key=f"seed-{job_id.hex}",
                )
            )
            job_ids.append((job_id, run_id))
    return job_ids


def _lease(engine, owner):
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_lease")
        row = connection.execute(
            text("SELECT * FROM workflow.lease_next_job(:owner, 30)"),
            {"owner": owner},
        ).mappings().one()
        return dict(row)


def test_skip_locked_leases_four_jobs_across_two_sessions_without_duplicates(
    governed_postgres_engine, lease_ids
) -> None:
    expected = {job_id for job_id, _ in _queue_jobs(governed_postgres_engine, lease_ids, 4)}

    def lease_two(owner):
        with governed_postgres_engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL ROLE shiftmind_lease")
            return [
                connection.execute(
                    text("SELECT * FROM workflow.lease_next_job(:owner, 30)"),
                    {"owner": owner},
                ).mappings().one()["id"]
                for _ in range(2)
            ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        leased = pool.map(lease_two, ("worker-a", "worker-b"))
    actual = [job_id for pair in leased for job_id in pair]
    assert set(actual) == expected
    assert len(actual) == len(set(actual)) == 4


def test_expired_worker_is_fenced_and_recovered_worker_finishes_once(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    first = _lease(governed_postgres_engine, "worker-old")
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id == job_id)
            .values(lease_expires_at=func.now() - text("interval '1 second'"))
        )
    second = _lease(governed_postgres_engine, "worker-new")
    assert first["id"] == second["id"] == job_id
    assert second["attempt_id"] != first["attempt_id"]
    assert second["fencing_epoch"] == first["fencing_epoch"] + 1

    repository = PostgresScheduleRunRepository()
    with pytest.raises(StaleLeaseError), governed_postgres_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(lease_ids["site"])},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=first["fencing_epoch"],
        )

    with governed_postgres_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(lease_ids["site"])},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=second["fencing_epoch"],
        )
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=second["fencing_epoch"],
            status="solver_failed",
            reason="seeded_terminal",
            candidate=None,
        )
        repository.complete_job(
            connection,
            job_id=job_id,
            site_id=lease_ids["site"],
            fencing_epoch=second["fencing_epoch"],
        )

    with pytest.raises(StaleLeaseError), governed_postgres_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(lease_ids["site"])},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=first["fencing_epoch"],
            status="solver_failed",
            reason="late_stale_terminal",
            candidate=None,
        )
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(schedule_run).where(schedule_run.c.id == run_id)
        ) == 1
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 0
        assert connection.scalar(select(schedule_run.c.reason).where(schedule_run.c.id == run_id)) == "seeded_terminal"


def test_mark_running_cannot_create_a_jobless_solver_running_orphan(
    governed_postgres_engine, lease_ids
) -> None:
    """A running row cannot be created without the leased job that fences it."""
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    with governed_postgres_engine.begin() as connection:
        connection.execute(job_queue.delete().where(job_queue.c.id == job_id))

    repository = PostgresScheduleRunRepository()
    with pytest.raises(StaleLeaseError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=1,
        )

    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(schedule_run.c.status).where(schedule_run.c.id == run_id)
        ) == "solver_queued"
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.schedule_run_id == run_id
            )
        ) == 0
        assert connection.scalar(
            select(func.count()).select_from(persisted_event).where(
                persisted_event.c.stream_id == run_id
            )
        ) == 0


def test_lease_role_cannot_query_the_queue_directly(governed_postgres_engine) -> None:
    with pytest.raises(DBAPIError), governed_postgres_engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_lease")
        connection.execute(text("SELECT * FROM workflow.job_queue"))


def test_live_role_and_routine_grants_are_narrow(governed_postgres_engine) -> None:
    with governed_postgres_engine.connect() as connection:
        lease_table_grants = connection.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee='shiftmind_lease'"
            )
        ).scalars().all()
        routines = set(
            connection.execute(
                text(
                    "SELECT grantee, routine_name FROM information_schema.role_routine_grants "
                    "WHERE routine_schema='workflow' AND grantee IN "
                    "('shiftmind_lease','shiftmind_runtime')"
                )
            ).all()
        )
    assert lease_table_grants == []
    assert routines == {
        ("shiftmind_lease", "lease_next_job"),
        ("shiftmind_runtime", "renew_job_lease"),
    }


class _ProposalRepository:
    def __init__(self, value, actor_id):
        self.value = value
        self.actor_id = actor_id

    def get_current(self, _connection, *, proposal_id, for_update=False):
        assert proposal_id == self.value.proposal_id
        return ProposalRecordV1(self.value, 1, self.actor_id)


class _Catalogue:
    def __init__(self, value):
        self.value = value

    def get_scenario_context(self, _connection, _scenario_id):
        return self.value


def _runtime(connection, site_id):
    connection.execute(
        text("SELECT set_config('app.site_id', :site_id, true)"),
        {"site_id": str(site_id)},
    )
    connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")


def test_enqueue_replay_and_rollback_have_exact_row_counts(
    governed_postgres_engine, lease_ids
) -> None:
    proposal_value = ProposalV1(
        proposal_id=lease_ids["proposal"],
        proposal_version_id=lease_ids["proposal_version"],
        scenario_id=lease_ids["scenario"],
        scenario_version_id=lease_ids["scenario_version"],
        canonical_hash="b" * 64,
        resource_version=1,
    )
    context = ScenarioContext(
        scenario_name="Lease Fixture",
        scenario_id=lease_ids["scenario"],
        scenario_version_id=lease_ids["scenario_version"],
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        site_id=lease_ids["site"],
        baseline_schedule_version=None,
    )
    settings = SimpleNamespace(
        solver_engine_name="cpsat",
        solver_seed=42,
        solver_num_search_workers=1,
        solver_max_deterministic_time=30.0,
        solver_wall_time_limit_seconds=30.0,
        site_max_concurrent_runs=1000,
    )
    repository = PostgresScheduleRunRepository()
    arguments = dict(
        proposal_id=lease_ids["proposal"],
        site_id=lease_ids["site"],
        actor_id=lease_ids["actor"],
        expected_proposal_resource_version=1,
        idempotency_key="live-enqueue",
        capability_version="1",
        settings=settings,
    )
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        first = enqueue_compute(
            _ProposalRepository(proposal_value, lease_ids["actor"]),
            _Catalogue(context),
            repository,
            connection,
            **arguments,
        )
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        replay = enqueue_compute(
            _ProposalRepository(proposal_value, lease_ids["actor"]),
            _Catalogue(context),
            repository,
            connection,
            **arguments,
        )
    assert replay == first

    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.id == first.job_id
            )
        ) == 1
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == "live-enqueue"
            )
        ) == 1
        events = connection.execute(
            select(
                persisted_event.c.event_type,
                persisted_event.c.resource_version,
                persisted_event.c.schedule_run_id,
                persisted_event.c.conversation_id,
                persisted_event.c.payload,
            ).where(persisted_event.c.stream_id == first.schedule_run_id)
        ).all()
        assert len(events) == 1
        assert events[0].event_type == "run.queued.v1"
        assert events[0].resource_version == 1
        assert events[0].schedule_run_id == first.schedule_run_id
        assert events[0].conversation_id is None
        assert events[0].payload["status"] == "solver_queued"

    with pytest.raises(IdempotencyKeyConflictError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        enqueue_compute(
            _ProposalRepository(proposal_value, lease_ids["actor"]),
            _Catalogue(context),
            repository,
            connection,
            **{**arguments, "expected_proposal_resource_version": 2},
        )

    def _site_counts():
        with governed_postgres_engine.connect() as connection:
            return {
                table.name: connection.scalar(
                    select(func.count()).select_from(table).where(
                        table.c.site_id == lease_ids["site"]
                    )
                )
                for table in (
                    run_snapshot,
                    schedule_run,
                    job_queue,
                    command_idempotency,
                    # AD-22 puts the event IN the enqueue bundle, so a
                    # leak here must fail the rollback proof too.
                    persisted_event,
                )
            }

    before_rollback = _site_counts()
    with pytest.raises(RuntimeError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        enqueue_compute(
            _ProposalRepository(proposal_value, lease_ids["actor"]),
            _Catalogue(context),
            repository,
            connection,
            **{**arguments, "idempotency_key": "rolled-back-enqueue"},
        )
        raise RuntimeError("force rollback")
    # AC1 says the bundle commits as one unit, so the rollback must be proven
    # across EVERY table it names — asserting only command_idempotency would
    # pass even if the snapshot, run, and job had leaked.
    assert _site_counts() == before_rollback
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.idempotency_key == "rolled-back-enqueue"
            )
        ) == 0


def test_site_advisory_lock_serializes_concurrent_enqueues_at_limit_one(
    governed_postgres_engine, lease_ids
) -> None:
    ids = {
        name: uuid4()
        for name in (
            "site", "scenario", "scenario_version", "conversation", "proposal",
            "proposal_version",
        )
    }
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            insert(site).values(
                id=ids["site"], organization_id=lease_ids["org"], name=f"Concurrency {ids['site']}"
            )
        )
        connection.execute(
            insert(scenario).values(
                id=ids["scenario"], site_id=ids["site"], fixture_id="concurrency-fixture",
                name="Concurrency Fixture",
            )
        )
        connection.execute(
            insert(scenario_version).values(
                id=ids["scenario_version"], site_id=ids["site"],
                scenario_id=ids["scenario"], fixture_id="concurrency-fixture", version="v1",
                payload={}, checksum_digest="c" * 64,
            )
        )
        connection.execute(
            insert(conversation).values(
                id=ids["conversation"], site_id=ids["site"], scenario_id=ids["scenario"],
                scenario_version_id=ids["scenario_version"],
                created_by_actor_id=lease_ids["actor"],
            )
        )
        connection.execute(
            insert(proposal).values(
                id=ids["proposal"], site_id=ids["site"], scenario_id=ids["scenario"],
                scenario_version_id=ids["scenario_version"], conversation_id=ids["conversation"],
                created_by_actor_id=lease_ids["actor"], state="active",
                current_version_id=None, resource_version=1,
            )
        )
        connection.execute(
            insert(proposal_version).values(
                id=ids["proposal_version"], site_id=ids["site"],
                proposal_id=ids["proposal"], version_ordinal=1, payload={},
                canonical_hash="d" * 64, checksum_algorithm="sha256",
                checksum_schema_version="rfc8785-v1",
            )
        )
        connection.execute(
            update(proposal).where(proposal.c.id == ids["proposal"]).values(
                current_version_id=ids["proposal_version"]
            )
        )

    proposal_value = ProposalV1(
        proposal_id=ids["proposal"], proposal_version_id=ids["proposal_version"],
        scenario_id=ids["scenario"], scenario_version_id=ids["scenario_version"],
        canonical_hash="d" * 64, resource_version=1,
    )
    context = ScenarioContext(
        scenario_name="Concurrency Fixture", scenario_id=ids["scenario"],
        scenario_version_id=ids["scenario_version"], fixture_version="v1",
        checksum_algorithm="sha256", checksum_schema_version="rfc8785-v1",
        checksum_digest="c" * 64, site_id=ids["site"], baseline_schedule_version=None,
    )
    settings = SimpleNamespace(
        solver_engine_name="cpsat", solver_seed=42, solver_num_search_workers=1,
        solver_max_deterministic_time=30.0, solver_wall_time_limit_seconds=30.0,
        site_max_concurrent_runs=1,
    )
    barrier = Barrier(2)

    def _enqueue(index: int) -> str:
        barrier.wait()
        try:
            with governed_postgres_engine.begin() as connection:
                _runtime(connection, ids["site"])
                enqueue_compute(
                    _ProposalRepository(proposal_value, lease_ids["actor"]),
                    _Catalogue(context), PostgresScheduleRunRepository(), connection,
                    proposal_id=ids["proposal"], site_id=ids["site"],
                    actor_id=lease_ids["actor"], expected_proposal_resource_version=1,
                    idempotency_key=f"concurrent-{index}", capability_version="1",
                    settings=settings,
                )
            return "created"
        except SiteConcurrencyExhaustedError:
            return "exhausted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(_enqueue, (1, 2)))

    assert sorted(outcomes) == ["created", "exhausted"]
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(schedule_run).where(
                schedule_run.c.site_id == ids["site"]
            )
        ) == 1
        # Exactly one job too: the losing session must leave no queued work
        # behind. Asserting only the run count would pass if the advisory lock
        # serialized the count but both sessions still enqueued a job.
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.site_id == ids["site"]
            )
        ) == 1


def _only_leasable(engine, job_id):
    """Take every other row out of the leasable set.

    `lease_next_job` orders by `created_at, id`, and the module-scoped fixture
    means earlier tests leave queued rows behind that are OLDER than this
    test's. Without this the test would silently lease someone else's job.
    """
    with engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id != job_id)
            .values(status="completed")
        )


def _candidate(run_id, ids):
    return ScheduleVersionV1(
        schedule_version_id=uuid4(),
        schedule_run_id=run_id,
        scenario_id=ids["scenario"],
        scenario_version_id=ids["scenario_version"],
        proposal_id=ids["proposal"],
        proposal_version_id=ids["proposal_version"],
        feasible_solver_status="OPTIMAL",
        assignments=(),
        created_at=datetime.now(timezone.utc),
    )


def test_a_stale_worker_writes_no_candidate_and_the_current_epoch_writes_exactly_one(
    governed_postgres_engine, lease_ids
) -> None:
    """AC3's second half, which `candidate=None` could never exercise.

    "stable job/effect uniqueness prevents duplicate terminal evidence or
    candidate creation" is a claim about REAL candidate rows. Every earlier
    fencing test finalized with `candidate=None`, so its `schedule_version`
    count assertion held vacuously and `uq_schedule_version_run` was never
    observed doing anything.
    """
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    first = _lease(governed_postgres_engine, "worker-old")
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id == job_id)
            .values(lease_expires_at=func.now() - text("interval '1 second'"))
        )
    second = _lease(governed_postgres_engine, "worker-new")
    assert first["id"] == second["id"] == job_id
    assert second["fencing_epoch"] == first["fencing_epoch"] + 1

    repository = PostgresScheduleRunRepository()
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=second["fencing_epoch"],
        )

    # The stale worker finishes its solve and tries to commit a real candidate.
    with pytest.raises(StaleLeaseError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=first["fencing_epoch"],
            status="solver_completed",
            reason=None,
            candidate=_candidate(run_id, lease_ids),
        )

    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 0

    # The recovered worker commits under the current epoch.
    survivor = _candidate(run_id, lease_ids)
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.finalize_run(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=second["fencing_epoch"],
            status="solver_completed",
            reason=None,
            candidate=survivor,
        )

    with governed_postgres_engine.connect() as connection:
        rows = connection.execute(
            select(schedule_version.c.id).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ).scalars().all()
        assert rows == [survivor.schedule_version_id]
        assert connection.scalar(
            select(schedule_run.c.candidate_schedule_version_id).where(
                schedule_run.c.id == run_id
            )
        ) == survivor.schedule_version_id


def test_transition_events_are_monotonic_and_lost_cas_writes_none(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, "event-worker")
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
            status="solver_failed",
            reason="seeded_failure",
            candidate=None,
        )

    with governed_postgres_engine.connect() as connection:
        events = connection.execute(
            select(
                persisted_event.c.sequence,
                persisted_event.c.event_type,
                persisted_event.c.resource_version,
                persisted_event.c.payload,
            )
            .where(persisted_event.c.stream_id == run_id)
            .order_by(persisted_event.c.sequence)
        ).all()
    assert [(row.sequence, row.event_type, row.resource_version) for row in events] == [
        (1, "run.running.v1", 2),
        (2, "run.failed.v1", 3),
    ]
    assert events[-1].payload["reason"] == "seeded_failure"

    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        head = repository.event_head(
            connection, run_id=run_id, site_id=lease_ids["site"]
        )
        replay = repository.events_after(
            connection, stream_id=run_id, after=1, limit=200
        )
        run_view = repository.get_run(
            connection, run_id=run_id, site_id=lease_ids["site"]
        )
    assert head.max_sequence == 2
    assert len(replay) == 1
    assert replay[0].payload.activity_type == "run_progress"
    assert replay[0].payload.status == "solver_failed"
    assert replay[0].sequence == 2
    assert run_view.schedule_run_id == run_id
    assert run_view.status == "solver_failed"
    assert run_view.reason == "seeded_failure"
    assert run_view.resource_version == 3
    assert run_view.cancellation_requested is False

    with pytest.raises(RunTransitionConflictError), governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        repository.mark_running(
            connection,
            run_id=run_id,
            site_id=lease_ids["site"],
            fencing_epoch=lease["fencing_epoch"],
        )
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(persisted_event).where(
                persisted_event.c.stream_id == run_id
            )
        ) == 2


def test_fatal_failure_after_lease_is_terminal_and_never_released(
    governed_postgres_engine, lease_ids
) -> None:
    """A deterministic cause ends the job permanently: replay cannot help it."""
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)

    class _FailingLoadRepository(PostgresScheduleRunRepository):
        def load_snapshot(self, connection, *, run_id, site_id):
            raise FatalJobError("injected after lease")

    from tests.test_cancellation_race_postgres import _run_worker

    outcome = _run_worker(
        governed_postgres_engine,
        _FailingLoadRepository(),
        SimpleNamespace(solve=lambda snapshot: None),
    )
    assert outcome.status == "solver_failed"

    with governed_postgres_engine.connect() as connection:
        assert connection.execute(
            select(job_queue.c.status, schedule_run.c.status, schedule_run.c.reason)
            .select_from(
                job_queue.join(
                    schedule_run,
                    (schedule_run.c.id == job_queue.c.schedule_run_id)
                    & (schedule_run.c.site_id == job_queue.c.site_id),
                )
            )
            .where(job_queue.c.id == job_id)
        ).one() == ("failed", "solver_failed", "job_execution_failed")
        assert connection.execute(
            select(persisted_event.c.event_type).where(
                persisted_event.c.stream_id == run_id
            )
        ).scalars().all() == ["run.failed.v1"]

    with governed_postgres_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            assert PostgresScheduleRunRepository().lease_next_job(
                connection,
                lease_owner="second-worker",
                lease_seconds=30,
            ) is None
        finally:
            connection.exec_driver_sql("RESET ROLE")


def test_heartbeat_keeps_a_slow_solve_inside_its_fencing_epoch(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    from tests.test_cancellation_race_postgres import (
        _runtime_connection,
        _seed_valid_snapshot,
    )

    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)

    class _SlowScheduler:
        def solve(self, snapshot):
            time.sleep(3.1)
            error = RuntimeError("slow seeded failure")
            error.code = "slow_seeded_failure"
            raise error

    with governed_postgres_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as lease_connection:
        lease_connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            outcome = lease_and_execute_schedule_run(
                lease_connection,
                lambda site_id: _runtime_connection(
                    governed_postgres_engine, site_id
                ),
                PostgresScheduleRunRepository(),
                _SlowScheduler(),
                lease_owner="heartbeat-worker",
                lease_seconds=2,
            )
        finally:
            lease_connection.exec_driver_sql("RESET ROLE")

    assert outcome.status == "solver_failed"
    with governed_postgres_engine.connect() as connection:
        row = connection.execute(
            select(
                job_queue.c.status,
                job_queue.c.fencing_epoch,
                job_queue.c.heartbeat_at,
                schedule_run.c.status,
                schedule_run.c.reason,
            )
            .select_from(
                job_queue.join(
                    schedule_run,
                    (schedule_run.c.id == job_queue.c.schedule_run_id)
                    & (schedule_run.c.site_id == job_queue.c.site_id),
                )
            )
            .where(job_queue.c.id == job_id)
        ).one()
    assert row.status == "completed"
    assert row.fencing_epoch == 1
    assert row.heartbeat_at is not None
    assert row[3:] == ("solver_failed", "slow_seeded_failure")


def test_renew_job_lease_extends_only_the_epoch_the_caller_still_holds(
    governed_postgres_engine, lease_ids
) -> None:
    """`renew_job_lease` had zero callers and zero behavioural cover."""
    job_id, _ = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, "worker-a")
    assert lease["id"] == job_id
    repository = PostgresScheduleRunRepository()

    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        renewed = repository.renew_job_lease(
            connection,
            job_id=job_id,
            fencing_epoch=lease["fencing_epoch"],
            extension_seconds=600,
        )
    assert renewed.renewed is True
    assert renewed.cancellation_requested is False

    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        stale = repository.renew_job_lease(
            connection,
            job_id=job_id,
            fencing_epoch=lease["fencing_epoch"] - 1,
            extension_seconds=600,
        )
    assert stale.renewed is False


def test_renew_job_lease_reads_the_cancellation_flag(
    governed_postgres_engine, lease_ids
) -> None:
    """Decision 7: both lease functions READ the flag so Story 3.4 does not
    have to invent new plumbing. Nothing in this story SETS it, so the test
    seeds the row directly."""
    job_id, _ = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, "worker-a")
    assert lease["id"] == job_id
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id == job_id)
            .values(cancellation_requested=True)
        )

    with governed_postgres_engine.begin() as connection:
        _runtime(connection, lease_ids["site"])
        renewal = PostgresScheduleRunRepository().renew_job_lease(
            connection,
            job_id=job_id,
            fencing_epoch=lease["fencing_epoch"],
            extension_seconds=600,
        )
    assert renewal == LeaseRenewalV1(renewed=True, cancellation_requested=True)


def test_renew_job_lease_refuses_a_job_belonging_to_another_site(
    governed_postgres_engine, lease_ids
) -> None:
    """The function is SECURITY DEFINER and its owner carries BYPASSRLS, so
    without an explicit site predicate any runtime session could extend another
    tenant's lease given the job id and epoch."""
    job_id, _ = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, "worker-a")
    assert lease["id"] == job_id

    with governed_postgres_engine.begin() as connection:
        _runtime(connection, uuid4())
        foreign = PostgresScheduleRunRepository().renew_job_lease(
            connection,
            job_id=job_id,
            fencing_epoch=lease["fencing_epoch"],
            extension_seconds=600,
        )
    assert foreign.renewed is False


@pytest.mark.parametrize(
    ("status", "reason", "event_type"),
    [
        ("solver_completed", None, "run.completed.v1"),
        ("solver_infeasible", "infeasible", "run.infeasible.v1"),
        # AC3: wall-time exhaustion becomes timed-out with a stable
        # `budget_exhausted` reason. Every `budget_exhausted` assertion in the
        # suite was on the AgentRun aggregate; none drove a ScheduleRun.
        ("solver_timed_out", "budget_exhausted", "run.timed_out.v1"),
    ],
)
def test_each_terminal_status_publishes_its_own_event_once(
    governed_postgres_engine, lease_ids, status, reason, event_type
) -> None:
    """Close the three terminal names that had no assertion anywhere."""
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    lease = _lease(governed_postgres_engine, "terminal-worker")
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
            status=status,
            reason=reason,
            candidate=None,
        )

    with governed_postgres_engine.connect() as connection:
        events = connection.execute(
            select(
                persisted_event.c.sequence,
                persisted_event.c.event_type,
                persisted_event.c.payload,
            )
            .where(persisted_event.c.stream_id == run_id)
            .order_by(persisted_event.c.sequence)
        ).all()

    # Exactly one event per transition, monotonic, and terminal last (AD-7:
    # persist and emit once, with no implicit retry).
    assert [(row.sequence, row.event_type) for row in events] == [
        (1, "run.running.v1"),
        (2, event_type),
    ]
    assert events[-1].payload["status"] == status
    assert events[-1].payload["reason"] == reason


def test_transient_failure_after_lease_stays_leasable_for_recovery(
    governed_postgres_engine, lease_ids
) -> None:
    """AD-6: an expired lease is re-leased and recomputed, so never go terminal.

    `failed` is absorbing -- `lease_next_job` selects only `queued` or an
    expired `leased` -- so marking a transient failure terminal would discard
    work the system is built to retry. This drives the whole path against a
    real database: the original exception escapes unmasked, nothing terminal is
    written, and a second worker recovers the job once the lease lapses.
    """
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)

    class _FailingLoadRepository(PostgresScheduleRunRepository):
        def load_snapshot(self, connection, *, run_id, site_id):
            raise RuntimeError("transient database blip")

    from tests.test_cancellation_race_postgres import _run_worker

    with pytest.raises(RuntimeError, match="transient database blip"):
        _run_worker(
            governed_postgres_engine,
            _FailingLoadRepository(),
            SimpleNamespace(solve=lambda snapshot: None),
        )

    with governed_postgres_engine.connect() as connection:
        # The job is still leased and the run is still queued: no terminal
        # state was fabricated for a failure that may not recur.
        assert connection.execute(
            select(job_queue.c.status, schedule_run.c.status)
            .select_from(
                job_queue.join(
                    schedule_run,
                    (schedule_run.c.id == job_queue.c.schedule_run_id)
                    & (schedule_run.c.site_id == job_queue.c.site_id),
                )
            )
            .where(job_queue.c.id == job_id)
        ).one() == ("leased", "solver_queued")
        # Nothing was emitted at all. (`_queue_jobs` seeds rows directly rather
        # than through `create_queued_run`, so this stream starts empty and any
        # row here would be one the worker wrote.)
        assert connection.execute(
            select(persisted_event.c.event_type).where(
                persisted_event.c.stream_id == run_id
            )
        ).scalars().all() == []

    # Expire the lease exactly as a dead worker's would lapse.
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id == job_id)
            .values(lease_expires_at=text("pg_catalog.now() - interval '1 second'"))
        )

    with governed_postgres_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.exec_driver_sql("SET ROLE shiftmind_lease")
        try:
            recovered = PostgresScheduleRunRepository().lease_next_job(
                connection,
                lease_owner="second-worker",
                lease_seconds=30,
            )
        finally:
            connection.exec_driver_sql("RESET ROLE")

    assert recovered is not None
    assert recovered.schedule_run_id == run_id
