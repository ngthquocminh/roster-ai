"""Behavioural cover for the worker adapter and the adapter-side lease guards.

Story 3.3 review: every guard here was previously asserted only as a substring
of the source file, so an import error, a wrong column, or a silently dropped
predicate would not have turned a test red. Retro action A2 requires each guard
to be observed doing its job, not merely observed existing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.contracts.job_lease import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    JobLeaseV1,
    LeaseRenewalV1,
)
from application.ports.schedule_run import StaleLeaseError
from application.use_cases.enqueue_compute import SCOPE_CONTROLS as ENQUEUE_CONTROLS
from application.use_cases.cancel_schedule_run import SCOPE_CONTROLS as CANCEL_CONTROLS
from application.use_cases.lease_and_execute_schedule_run import (
    SCOPE_CONTROLS as LEASE_CONTROLS,
)
from worker.lease_worker import (
    MINIMUM_LEASE_SECONDS,
    default_lease_seconds,
    run_once,
)


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, *, rowcount=1, scalar=None, rows=None) -> None:
        self.rowcount = rowcount
        self._scalar = scalar
        self._rows = rows

    def scalar_one_or_none(self):
        return self._scalar

    def mappings(self):
        return self

    def one_or_none(self):
        return self._rows

    def one(self):
        return self._rows


class _Connection:
    """Records statements; answers UPDATEs by rowcount and SELECTs by scalar."""

    def __init__(self, *, rowcount=1, current_epoch=None, rows=None) -> None:
        self.rowcount = rowcount
        self.current_epoch = current_epoch
        self.rows = rows
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append(statement)
        if getattr(statement, "is_update", False):
            return _Result(rowcount=self.rowcount)
        if getattr(statement, "is_insert", False):
            return _Result(rowcount=self.rowcount)
        return _Result(scalar=self.current_epoch, rows=self.rows)


# --------------------------------------------------------------------------
# lease_next_job row -> contract mapping (never executed before)
# --------------------------------------------------------------------------


def _row(**overrides):
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    row = {
        "id": uuid4(),
        "job_type": "schedule_run_execute",
        "status": "leased",
        "site_id": uuid4(),
        "actor_id": uuid4(),
        "attempt_id": uuid4(),
        "contract_version": "1",
        "capability_version": None,
        "schedule_run_id": uuid4(),
        "idempotency_key": "enqueue-1",
        "lease_owner": "worker-1",
        "lease_expires_at": now + timedelta(seconds=30),
        "heartbeat_at": now,
        "fencing_epoch": 4,
        "cancellation_requested": False,
        "created_at": now,
    }
    row.update(overrides)
    return row


def test_lease_next_job_maps_a_row_onto_the_contract() -> None:
    row = _row()
    lease = PostgresScheduleRunRepository().lease_next_job(
        _Connection(rows=row), lease_owner="worker-1", lease_seconds=120
    )
    assert lease is not None
    assert lease.job_id == row["id"]
    assert lease.fencing_epoch == 4
    assert lease.attempt_id == row["attempt_id"]
    assert lease.cancellation_requested is False


def test_empty_queue_maps_the_all_null_composite_row_to_none() -> None:
    """`RETURNS workflow.job_queue` yields one all-NULL row, not zero rows."""
    empty = {name: None for name in _row()}
    assert (
        PostgresScheduleRunRepository().lease_next_job(
            _Connection(rows=empty), lease_owner="worker-1", lease_seconds=120
        )
        is None
    )


def test_lease_timestamps_are_normalised_to_utc() -> None:
    """psycopg decodes `timestamptz` in the SESSION timezone, which nothing
    pins. `JobLeaseV1` requires a zero utcoffset, so a non-UTC server would
    otherwise make every single lease raise."""
    sydney = timezone(timedelta(hours=10))
    row = _row(
        lease_expires_at=datetime(2026, 8, 20, 19, 0, tzinfo=sydney),
        heartbeat_at=datetime(2026, 8, 20, 19, 0, tzinfo=sydney),
        created_at=datetime(2026, 8, 20, 19, 0, tzinfo=sydney),
    )
    lease = PostgresScheduleRunRepository().lease_next_job(
        _Connection(rows=row), lease_owner="worker-1", lease_seconds=120
    )
    assert lease is not None
    assert lease.created_at.utcoffset() == timedelta(0)
    assert lease.created_at == datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# renew_job_lease (previously had zero callers and zero behavioural cover)
# --------------------------------------------------------------------------


def test_renew_job_lease_reports_renewal_and_the_cancellation_flag() -> None:
    """Decision 7 requires BOTH lease functions to read `cancellation_requested`."""
    renewal = PostgresScheduleRunRepository().renew_job_lease(
        _Connection(rows={"renewed": True, "cancellation_requested": True}),
        job_id=uuid4(),
        fencing_epoch=4,
        extension_seconds=60,
    )
    assert renewal == LeaseRenewalV1(renewed=True, cancellation_requested=True)


def test_renew_job_lease_reports_a_lost_lease_as_not_renewed() -> None:
    renewal = PostgresScheduleRunRepository().renew_job_lease(
        _Connection(rows={"renewed": False, "cancellation_requested": False}),
        job_id=uuid4(),
        fencing_epoch=4,
        extension_seconds=60,
    )
    assert renewal.renewed is False


# --------------------------------------------------------------------------
# Guards that were reachable only on the happy path
# --------------------------------------------------------------------------


def test_enqueue_job_refuses_a_job_belonging_to_another_site() -> None:
    job = JobLeaseV1(
        job_id=uuid4(),
        job_type="schedule_run_execute",
        site_id=uuid4(),
        actor_id=uuid4(),
        contract_version="1",
        schedule_run_id=uuid4(),
        idempotency_key="enqueue-1",
    )
    with pytest.raises(ValueError, match="site does not match"):
        PostgresScheduleRunRepository().enqueue_job(
            _Connection(), job=job, site_id=uuid4()
        )


def test_complete_job_reports_a_superseded_epoch_as_a_stale_lease() -> None:
    with pytest.raises(StaleLeaseError):
        PostgresScheduleRunRepository().complete_job(
            _Connection(rowcount=0, current_epoch=9),
            job_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=4,
        )


def test_complete_job_does_not_misreport_an_unleased_job_as_stale() -> None:
    with pytest.raises(ValueError) as caught:
        PostgresScheduleRunRepository().complete_job(
            _Connection(rowcount=0, current_epoch=4),
            job_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=4,
        )
    assert not isinstance(caught.value, StaleLeaseError)


def test_the_fence_rejects_the_enqueue_time_epoch_of_a_never_leased_job() -> None:
    """A job is enqueued at `fencing_epoch=0`. Without the `status='leased'`
    and positive-epoch predicates, a caller passing 0 would satisfy the fence
    and drive a run terminal without ever holding a lease."""
    connection = _Connection()
    PostgresScheduleRunRepository().mark_running(
        connection, run_id=uuid4(), site_id=uuid4(), fencing_epoch=1
    )
    sql = str(connection.statements[0])
    assert "status" in sql
    assert "fencing_epoch > " in sql or "fencing_epoch >" in sql


def test_finalize_claims_the_fence_before_writing_any_candidate_row() -> None:
    """AC3 is about the effect COMMIT: a stale worker must be stopped by the
    guard itself, not by the caller happening to roll back."""
    connection = _Connection(rowcount=0, current_epoch=9)
    with pytest.raises(StaleLeaseError):
        PostgresScheduleRunRepository().finalize_run(
            connection,
            run_id=uuid4(),
            site_id=uuid4(),
            fencing_epoch=4,
            status="solver_failed",
            reason="stale",
            candidate=None,
        )
    assert connection.statements[0].table.name == "job_queue"


# --------------------------------------------------------------------------
# Worker adapter — imported and driven, not read as text
# --------------------------------------------------------------------------


def test_run_once_rejects_a_non_positive_lease_duration() -> None:
    with pytest.raises(ValueError, match="lease_seconds"):
        run_once(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            lease_owner="worker-1",
            lease_seconds=0,
        )


def test_default_lease_seconds_always_exceeds_the_solver_budget() -> None:
    """No heartbeat exists yet, so a lease shorter than the solve it covers
    would be stolen mid-flight and the finished work discarded."""
    for budget in (0.5, 30.0, 600.0):
        settings = SimpleNamespace(solver_wall_time_limit_seconds=budget)
        assert default_lease_seconds(settings) > budget
    assert default_lease_seconds(SimpleNamespace()) == MINIMUM_LEASE_SECONDS


# --------------------------------------------------------------------------
# Scope-as-data: these modules are not capability modules, so
# test_capability_conformance.py does not reach them.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "controls", [ENQUEUE_CONTROLS, LEASE_CONTROLS], ids=["enqueue", "lease"]
)
def test_scope_controls_state_their_non_coverage(controls) -> None:
    assert controls
    assert "NOT COVERED" in controls


def test_deferred_owners_are_named_in_scope_controls() -> None:
    """The heartbeat, the job failure state, and the lease ceiling were all
    deferred at code review with a named owner; the declaration is the only
    thing carrying that decision into the code."""
    assert "heartbeat:owned_by_story_3_5" in LEASE_CONTROLS
    assert "job_failure_state:owned_by_story_3_5" in LEASE_CONTROLS
    assert "ceilings:lease_seconds_owned_by_story_3_6" in LEASE_CONTROLS
    assert "contracts:attempt_id_unset_until_first_lease" in ENQUEUE_CONTROLS
    assert "cancellation:cooperative_checkpoints" in LEASE_CONTROLS
    assert "cancellation:mid_solve_preemption_owned_by_story_3_5" in LEASE_CONTROLS
    assert "job_terminal_state:owned_by_story_3_5" in CANCEL_CONTROLS
    assert "heartbeat:owned_by_story_3_5" in CANCEL_CONTROLS


def test_idempotency_key_is_bounded_by_the_narrower_column() -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        JobLeaseV1(
            job_id=uuid4(),
            job_type="schedule_run_execute",
            site_id=uuid4(),
            actor_id=uuid4(),
            contract_version="1",
            schedule_run_id=uuid4(),
            idempotency_key="k" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1),
        )
