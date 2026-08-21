from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.ports.schedule_run import (
    IdempotentScheduleRunResultV1,
    RunNotCancellableError,
    ScheduleRunStateV1,
)
from application.use_cases.cancel_schedule_run import (
    CancelScheduleRunError,
    IdempotencyKeyConflictError,
    RunNotCancellableError as CommandRunNotCancellableError,
    StaleResourceVersionError,
    cancel_schedule_run,
)


class _Result:
    def __init__(self, *, row=None, rowcount=1, scalar=None) -> None:
        self._row = row
        self.rowcount = rowcount
        self._scalar = scalar

    def one_or_none(self):
        return self._row

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar or uuid4()


class _Connection:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0) if self.results else _Result()


def test_get_run_state_returns_status_and_resource_version() -> None:
    connection = _Connection(
        _Result(row=SimpleNamespace(status="solver_running", resource_version=4))
    )

    state = PostgresScheduleRunRepository().get_run_state(
        connection, run_id=uuid4(), site_id=uuid4()
    )

    assert state == ScheduleRunStateV1("solver_running", 4)


@pytest.mark.parametrize(
    ("method_name", "from_status", "to_status", "sets_finished_at"),
    (
        ("cancel_queued_run", "solver_queued", "solver_cancelled", True),
        (
            "request_cancellation",
            "solver_running",
            "cancellation_requested",
            False,
        ),
    ),
)
def test_cancellation_transitions_are_versioned_compare_and_sets(
    method_name, from_status, to_status, sets_finished_at
) -> None:
    connection = _Connection(_Result(row=SimpleNamespace(resource_version=4)))
    repository = PostgresScheduleRunRepository()

    getattr(repository, method_name)(
        connection,
        run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        expected_resource_version=3,
    )

    statement = connection.statements[0]
    sql = str(statement)
    assert from_status in str(statement.compile().params.values())
    assert "resource_version" in sql
    assert 3 in statement.compile().params.values()
    assert to_status in statement.compile().params.values()
    assert ("finished_at" in statement._values) is sets_finished_at


def test_failed_cancellation_compare_and_set_is_distinct() -> None:
    with pytest.raises(RunNotCancellableError):
        PostgresScheduleRunRepository().cancel_queued_run(
            _Connection(_Result(rowcount=0)),
            run_id=uuid4(),
            site_id=uuid4(),
            actor_id=uuid4(),
            expected_resource_version=2,
        )


def test_job_cancellation_flag_is_site_scoped_and_zero_rows_are_allowed() -> None:
    connection = _Connection(_Result(rowcount=0))

    PostgresScheduleRunRepository().set_job_cancellation_requested(
        connection, run_id=uuid4(), site_id=uuid4()
    )

    statement = connection.statements[0]
    assert statement.table.fullname == "workflow.job_queue"
    assert "schedule_run_id" in str(statement)
    assert "site_id" in str(statement)
    assert True in statement.compile().params.values()


def test_existing_run_updates_bump_resource_version() -> None:
    repository = PostgresScheduleRunRepository()
    mark_connection = _Connection(
        _Result(),
        _Result(row=SimpleNamespace(resource_version=2)),
        _Result(scalar=uuid4()),
    )
    repository.mark_running(
        mark_connection, run_id=uuid4(), site_id=uuid4(), fencing_epoch=1
    )

    finalize_connection = _Connection(
        _Result(),
        _Result(row=SimpleNamespace(
            resource_version=3,
            finished_at=None,
        )),
        _Result(scalar=uuid4()),
    )
    repository.finalize_run(
        finalize_connection,
        run_id=uuid4(),
        site_id=uuid4(),
        fencing_epoch=1,
        status="solver_failed",
        reason="seeded",
        candidate=None,
    )

    # `mark_running` and `finalize_run` both claim the job row first now, so
    # select the schedule_run statement rather than trusting a position.
    mark = next(
        s for s in mark_connection.statements
        if str(s).startswith("UPDATE schedule_run")
    )
    finalize = next(
        s for s in finalize_connection.statements
        if str(s).startswith("UPDATE schedule_run")
    )
    assert "resource_version" in mark._values
    assert "resource_version" in finalize._values
    assert "cancellation_requested" in str(finalize.compile().params.values())


class _RunRepository:
    def __init__(self, state: ScheduleRunStateV1 | None) -> None:
        self.state = state
        self.idempotency = {}
        self.calls = []
        # Decision 4: a run with no job row carries no cancellation request.
        # The response must read this back, never assert it.
        self.job_cancellation_requested = False

    def get_run_state(self, _connection, *, run_id, site_id):
        self.calls.append(("state", run_id, site_id))
        return self.state

    def get_idempotent_result(
        self, _connection, *, site_id, actor_id, operation, idempotency_key
    ):
        return self.idempotency.get((site_id, actor_id, operation, idempotency_key))

    def cancel_queued_run(self, _connection, **values):
        self.calls.append(("cancel", values))
        self.state = ScheduleRunStateV1("solver_cancelled", self.state.resource_version + 1)

    def request_cancellation(self, _connection, **values):
        self.calls.append(("request", values))
        self.state = ScheduleRunStateV1(
            "cancellation_requested", self.state.resource_version + 1
        )

    def set_job_cancellation_requested(self, _connection, **values):
        self.calls.append(("flag", values))
        self.job_cancellation_requested = True

    def get_job_cancellation_requested(self, _connection, *, run_id, site_id):
        self.calls.append(("read_flag", run_id, site_id))
        return self.job_cancellation_requested

    def _store_idempotent_result(self, _connection, **values):
        key = (
            values["site_id"],
            values["actor_id"],
            values["operation"],
            values["idempotency_key"],
        )
        self.idempotency.setdefault(
            key,
            IdempotentScheduleRunResultV1(
                values["body_hash"], values["response_payload"]
            ),
        )


@pytest.mark.parametrize(
    ("initial_status", "expected_status", "expected_reason", "call_name"),
    (
        ("solver_queued", "solver_cancelled", "cancelled", "cancel"),
        (
            "solver_running",
            "cancellation_requested",
            "cancellation_requested",
            "request",
        ),
    ),
)
def test_cancel_command_persists_each_supported_edge_once(
    initial_status, expected_status, expected_reason, call_name
) -> None:
    run_id, site_id, actor_id = uuid4(), uuid4(), uuid4()
    repository = _RunRepository(ScheduleRunStateV1(initial_status, 3))
    arguments = dict(
        run_id=run_id,
        site_id=site_id,
        actor_id=actor_id,
        expected_resource_version=3,
        idempotency_key="cancel-1",
    )

    first = cancel_schedule_run(repository, object(), **arguments)
    replay = cancel_schedule_run(repository, object(), **arguments)

    assert first == replay
    assert first.schedule_run_id == run_id
    assert (first.status, first.reason, first.resource_version) == (
        expected_status,
        expected_reason,
        4,
    )
    assert [call[0] for call in repository.calls].count(call_name) == 1
    assert [call[0] for call in repository.calls].count("flag") == 1
    assert len(repository.idempotency) == 1


def test_cancel_command_conflicts_when_expected_version_changes_on_replay() -> None:
    run_id, site_id, actor_id = uuid4(), uuid4(), uuid4()
    repository = _RunRepository(ScheduleRunStateV1("solver_queued", 1))
    common = dict(
        run_id=run_id,
        site_id=site_id,
        actor_id=actor_id,
        idempotency_key="cancel-1",
    )
    cancel_schedule_run(
        repository, object(), expected_resource_version=1, **common
    )

    with pytest.raises(IdempotencyKeyConflictError):
        cancel_schedule_run(
            repository, object(), expected_resource_version=2, **common
        )


def test_cancel_command_returns_none_without_disclosing_another_site() -> None:
    assert cancel_schedule_run(
        _RunRepository(None),
        object(),
        run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        expected_resource_version=1,
        idempotency_key="cancel-1",
    ) is None


def test_cancel_command_checks_version_before_terminal_status() -> None:
    repository = _RunRepository(ScheduleRunStateV1("solver_completed", 5))
    arguments = dict(
        run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        idempotency_key="cancel-1",
    )
    with pytest.raises(StaleResourceVersionError):
        cancel_schedule_run(
            repository, object(), expected_resource_version=4, **arguments
        )
    with pytest.raises(CommandRunNotCancellableError):
        cancel_schedule_run(
            repository, object(), expected_resource_version=5, **arguments
        )


def test_already_requested_cancellation_is_a_replayable_success() -> None:
    repository = _RunRepository(ScheduleRunStateV1("cancellation_requested", 2))
    result = cancel_schedule_run(
        repository,
        object(),
        run_id=uuid4(),
        site_id=uuid4(),
        actor_id=uuid4(),
        expected_resource_version=2,
        idempotency_key="cancel-1",
    )

    assert result.status == "cancellation_requested"
    assert result.resource_version == 2
    assert all(call[0] not in {"cancel", "request", "flag"} for call in repository.calls)


@pytest.mark.parametrize("key", ("", "x" * 41))
def test_cancel_command_bounds_idempotency_key_before_reading_state(key) -> None:
    repository = _RunRepository(ScheduleRunStateV1("solver_queued", 1))
    with pytest.raises(CancelScheduleRunError):
        cancel_schedule_run(
            repository,
            object(),
            run_id=uuid4(),
            site_id=uuid4(),
            actor_id=uuid4(),
            expected_resource_version=1,
            idempotency_key=key,
        )
    assert repository.calls == []
