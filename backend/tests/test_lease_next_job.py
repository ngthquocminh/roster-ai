from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from application.contracts.job_lease import JobLeaseV1
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
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


def _lease(*, cancelled=False) -> JobLeaseV1:
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
        cancellation_requested=cancelled,
        created_at=now,
    )


class _Repository:
    def __init__(self, lease) -> None:
        self.lease = lease
        self.calls = []

    def lease_next_job(self, connection, *, lease_owner, lease_seconds):
        self.calls.append(("lease", connection, lease_owner, lease_seconds))
        return self.lease

    def load_snapshot(self, connection, *, run_id, site_id):
        self.calls.append(("load", connection, run_id, site_id))
        return _snapshot(run_id)

    def mark_running(self, connection, **values):
        self.calls.append(("running", connection, values))

    def finalize_run(self, connection, **values):
        self.calls.append(("finalize", connection, values))

    def complete_job(self, connection, **values):
        self.calls.append(("complete", connection, values))


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
        yield "runtime-connection"


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


def test_cancelled_job_finalizes_without_calling_the_solver() -> None:
    lease = _lease(cancelled=True)
    repository = _Repository(lease)
    scheduler = _Scheduler()

    result = lease_and_execute_schedule_run(
        "lease-connection",
        _RuntimeFactory(),
        repository,
        scheduler,
        lease_owner="worker-1",
        lease_seconds=30,
    )

    assert scheduler.calls == 0
    assert result.status == "solver_cancelled"
    finalize = next(call for call in repository.calls if call[0] == "finalize")
    assert finalize[2]["fencing_epoch"] == lease.fencing_epoch
    assert finalize[2]["status"] == "solver_cancelled"


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
    assert runtime.site_ids == [lease.site_id]
    running = next(call for call in repository.calls if call[0] == "running")
    complete = next(call for call in repository.calls if call[0] == "complete")
    assert running[2]["fencing_epoch"] == lease.fencing_epoch
    assert complete[2]["fencing_epoch"] == lease.fencing_epoch
