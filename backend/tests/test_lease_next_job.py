from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import time
from uuid import uuid4

from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
from application.ports.schedule_run import ScheduleRunStateV1
from application.use_cases.lease_and_execute_schedule_run import (
    lease_and_execute_schedule_run,
)


def _snapshot(run_id) -> RunSnapshotV1:
    return RunSnapshotV1(
        snapshot_id=uuid4(),
        schedule_run_id=run_id,
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(),
        component_versions=(("application", "1"),),
        accepted_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )


def _lease() -> JobLeaseV1:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    return JobLeaseV1(
        job_id=uuid4(),
        job_type="schedule_run_execute",
        status="leased",
        site_id=uuid4(),
        actor_id=uuid4(),
        attempt_id=uuid4(),
        contract_version="1",
        schedule_run_id=uuid4(),
        idempotency_key="enqueue-1",
        lease_owner="worker-1",
        lease_expires_at=now,
        heartbeat_at=now,
        fencing_epoch=3,
        # A carrier only: Decision 4 makes the run status the authority, so
        # no worker branch reads this. AD-20 still requires it on the contract.
        cancellation_requested=False,
        created_at=now,
    )


class _Repository:
    def __init__(self, lease, *states) -> None:
        self.lease = lease
        self.states = list(states or (ScheduleRunStateV1("solver_queued", 1), ScheduleRunStateV1("solver_running", 2)))
        self.calls = []

    def lease_next_job(self, connection, *, lease_owner, lease_seconds):
        self.calls.append(("lease", connection, lease_owner, lease_seconds))
        return self.lease

    def load_snapshot(self, connection, *, run_id, site_id):
        self.calls.append(("load", connection, run_id, site_id))
        return _snapshot(run_id)

    def get_run_state(self, connection, *, run_id, site_id):
        self.calls.append(("state", connection, run_id, site_id))
        return self.states.pop(0)

    def mark_running(self, connection, **values):
        self.calls.append(("running", connection, values))

    def finalize_run(self, connection, **values):
        self.calls.append(("finalize", connection, values))

    def complete_job(self, connection, **values):
        self.calls.append(("complete", connection, values))

    def fail_job(self, connection, **values):
        self.calls.append(("fail", connection, values))

    def renew_job_lease(self, connection, **values):
        self.calls.append(("renew", connection, values))
        return LeaseRenewalV1(renewed=True)


class _Scheduler:
    def __init__(self) -> None:
        self.calls = 0

    def solve(self, _snapshot):
        self.calls += 1
        error = RuntimeError("seeded solver failure")
        error.code = "seeded_failure"
        raise error


class _RuntimeFactory:
    def __init__(self) -> None:
        self.site_ids = []

    @contextmanager
    def __call__(self, site_id):
        self.site_ids.append(site_id)
        yield f"runtime-connection-{len(self.site_ids)}"


def test_no_job_does_not_open_a_runtime_transaction() -> None:
    repository = _Repository(None)
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        _Scheduler(),
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert result is None
    assert runtime.site_ids == []


def test_exception_after_lease_fails_the_job_and_queued_run_atomically() -> None:
    lease = _lease()

    class _FailingRepository(_Repository):
        def load_snapshot(self, connection, *, run_id, site_id):
            raise RuntimeError("injected after lease")

    repository = _FailingRepository(
        lease, ScheduleRunStateV1("solver_queued", 1)
    )
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        _Scheduler(),
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert result.status == "solver_failed"
    finalize = next(call for call in repository.calls if call[0] == "finalize")
    failed = next(call for call in repository.calls if call[0] == "fail")
    assert finalize[1] == failed[1] == "runtime-connection-2"
    assert finalize[2]["status"] == "solver_failed"
    assert finalize[2]["reason"] == "job_execution_failed"
    assert failed[2]["fencing_epoch"] == lease.fencing_epoch


def test_solve_renews_its_lease_on_an_independent_runtime_connection() -> None:
    lease = _lease()
    repository = _Repository(lease)
    runtime = _RuntimeFactory()

    class _SlowScheduler(_Scheduler):
        def solve(self, snapshot):
            time.sleep(1.2)
            return super().solve(snapshot)

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        _SlowScheduler(),
        lease_owner="worker-1",
        lease_seconds=1,
    )

    assert result.status == "solver_failed"
    renewals = [call for call in repository.calls if call[0] == "renew"]
    assert renewals
    assert all(call[1] != "runtime-connection-2" for call in renewals)
    assert all(call[2]["fencing_epoch"] == lease.fencing_epoch for call in renewals)
    assert all(call[2]["extension_seconds"] == 1 for call in renewals)


def test_checkpoint_1_cancellation_finalizes_without_calling_the_solver() -> None:
    lease = _lease()
    repository = _Repository(
        lease, ScheduleRunStateV1("cancellation_requested", 2)
    )
    scheduler = _Scheduler()
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert scheduler.calls == 0
    assert result.status == "solver_cancelled"
    assert runtime.site_ids == [lease.site_id]
    finalize = next(call for call in repository.calls if call[0] == "finalize")
    assert finalize[2]["fencing_epoch"] == lease.fencing_epoch
    assert finalize[2]["status"] == "solver_cancelled"
    assert finalize[2]["reason"] == "cancelled"


def test_leased_job_executes_and_completes_under_the_returned_epoch() -> None:
    lease = _lease()
    repository = _Repository(lease)
    scheduler = _Scheduler()
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert scheduler.calls == 1
    assert result.status == "solver_failed"
    assert runtime.site_ids == [lease.site_id, lease.site_id]
    running = next(call for call in repository.calls if call[0] == "running")
    complete = next(call for call in repository.calls if call[0] == "complete")
    assert running[1] == "runtime-connection-1"
    assert complete[1] == "runtime-connection-2"
    assert running[2]["fencing_epoch"] == lease.fencing_epoch
    assert complete[2]["fencing_epoch"] == lease.fencing_epoch


def test_checkpoint_2_observes_cancellation_after_mark_running_commits() -> None:
    lease = _lease()
    repository = _Repository(
        lease,
        ScheduleRunStateV1("solver_queued", 1),
        ScheduleRunStateV1("cancellation_requested", 3),
    )
    scheduler = _Scheduler()
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert result.status == "solver_cancelled"
    assert scheduler.calls == 0
    assert runtime.site_ids == [lease.site_id, lease.site_id]
    assert [call[0] for call in repository.calls].count("running") == 1
    assert [call[0] for call in repository.calls].count("state") == 2
    finalize = next(call for call in repository.calls if call[0] == "finalize")
    assert finalize[1] == "runtime-connection-2"
    assert finalize[2]["reason"] == "cancelled"


def test_recovered_running_run_skips_mark_running_and_resumes_in_second_transaction() -> None:
    lease = _lease()
    repository = _Repository(
        lease,
        ScheduleRunStateV1("solver_running", 4),
        ScheduleRunStateV1("solver_running", 4),
    )
    scheduler = _Scheduler()
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert result.status == "solver_failed"
    assert scheduler.calls == 1
    assert all(call[0] != "running" for call in repository.calls)
    assert runtime.site_ids == [lease.site_id, lease.site_id]


def test_terminal_run_completes_job_without_opening_solve_transaction() -> None:
    lease = _lease()
    repository = _Repository(
        lease, ScheduleRunStateV1("solver_completed", 8)
    )
    scheduler = _Scheduler()
    runtime = _RuntimeFactory()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        runtime,
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert result.status == "solver_completed"
    assert scheduler.calls == 0
    assert runtime.site_ids == [lease.site_id]
    assert [call[0] for call in repository.calls].count("complete") == 1
