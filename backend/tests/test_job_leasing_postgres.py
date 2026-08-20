from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
from application.ports.schedule_run import StaleLeaseError
from application.use_cases.enqueue_compute import (
    IdempotencyKeyConflictError,
    enqueue_compute,
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
    )
    repository = PostgresScheduleRunRepository()
    arguments = dict(
        proposal_id=lease_ids["proposal"],
        site_id=lease_ids["site"],
        expected_proposal_resource_version=1,
        idempotency_key="live-enqueue",
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
                for table in (run_snapshot, schedule_run, job_queue, command_idempotency)
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
        assert connection.scalar(
            select(func.count()).select_from(job_queue).where(
                job_queue.c.idempotency_key == "rolled-back-enqueue"
            )
        ) == 0


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
