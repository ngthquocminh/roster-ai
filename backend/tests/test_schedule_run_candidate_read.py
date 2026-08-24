from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from pydantic import TypeAdapter

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.contracts.schedule_version import ScheduleVersionV1


class _Connection:
    def __init__(self, payload):
        self.payload = payload
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        payload = self.payload

        class _Result:
            @staticmethod
            def one_or_none():
                return None if payload is None else SimpleNamespace(payload=payload)

        return _Result()


def test_candidate_payload_reads_back_identically_and_is_site_scoped() -> None:
    run_id, site_id = uuid4(), uuid4()
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=run_id,
        scenario_id=uuid4(), scenario_version_id=uuid4(),
        proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL",
    )
    connection = _Connection(TypeAdapter(ScheduleVersionV1).dump_python(candidate, mode="json"))

    restored = PostgresScheduleRunRepository().get_candidate(
        connection, schedule_run_id=run_id, site_id=site_id
    )

    assert restored == candidate
    compiled = str(connection.statement)
    assert "schedule_run_id" in compiled
    assert "site_id" in compiled


def test_candidate_read_returns_none_when_run_has_no_candidate() -> None:
    assert PostgresScheduleRunRepository().get_candidate(
        _Connection(None), schedule_run_id=uuid4(), site_id=uuid4()
    ) is None
