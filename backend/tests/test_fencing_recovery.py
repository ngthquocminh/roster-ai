from __future__ import annotations

from uuid import uuid4

import pytest

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.ports.schedule_run import StaleLeaseError


class _Result:
    def __init__(self, *, rowcount=1, scalar=None) -> None:
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _Connection:
    def __init__(self, *, rowcount=1, current_epoch=None) -> None:
        self.rowcount = rowcount
        self.current_epoch = current_epoch
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if statement.is_update:
            # `mark_running` now issues TWO updates: `_claim_epoch`'s job_queue
            # touch, then the schedule_run compare-and-set. `rowcount` models
            # the CAS only -- the claim succeeds unless a test says otherwise.
            # Match the TARGET, not any mention: the schedule_run CAS also
            # names workflow.job_queue inside its EXISTS subquery.
            if str(statement).startswith("UPDATE workflow.job_queue"):
                return _Result(rowcount=1)
            return _Result(rowcount=self.rowcount)
        return _Result(scalar=self.current_epoch)


class _EpochSensitiveConnection(_Connection):
    """Model the database accepting a stale write if its epoch predicate vanishes."""

    def execute(self, statement):
        self.statements.append(statement)
        if statement.is_update:
            return _Result(rowcount=0 if "fencing_epoch" in str(statement) else 1)
        return _Result(scalar=8)


def test_mark_running_compare_and_set_contains_the_epoch_predicate() -> None:
    connection = _Connection()
    PostgresScheduleRunRepository().mark_running(
        connection,
        run_id=uuid4(),
        site_id=uuid4(),
        fencing_epoch=7,
    )

    statements = [str(statement) for statement in connection.statements]
    # Lock order is load-bearing: the job row is claimed BEFORE the run row, so
    # Transaction A acquires the two locks in the same order as `finalize_run`
    # and the cancellation command. Reversing it deadlocks (40P01).
    assert statements[0].startswith("UPDATE workflow.job_queue")
    sql = next(s for s in statements if s.startswith("UPDATE schedule_run"))
    assert "EXISTS" in sql
    assert "workflow.job_queue" in sql
    assert "fencing_epoch" in sql


def test_epoch_mismatch_raises_distinct_stale_lease_error() -> None:
    with pytest.raises(StaleLeaseError):
        PostgresScheduleRunRepository().mark_running(
            _Connection(rowcount=0, current_epoch=8),
            run_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=7,
        )


def test_stale_epoch_is_rejected_by_the_compare_and_set_itself() -> None:
    with pytest.raises(StaleLeaseError):
        PostgresScheduleRunRepository().mark_running(
            _EpochSensitiveConnection(),
            run_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=7,
        )


def test_status_mismatch_is_not_misreported_as_a_stale_lease() -> None:
    with pytest.raises(ValueError) as caught:
        PostgresScheduleRunRepository().mark_running(
            _Connection(rowcount=0, current_epoch=7),
            run_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=7,
        )
    assert not isinstance(caught.value, StaleLeaseError)
    assert "solver_queued" in str(caught.value)
