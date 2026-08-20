from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.contracts.proposal import ProposalV1, ResolvedEntityV1
from application.ports.proposal import ProposalRecordV1
from application.ports.scenario_catalogue import ScenarioContext
from application.use_cases.create_run_snapshot import (
    SnapshotCreationError,
    create_run_snapshot,
)


class _ProposalRepository:
    def __init__(self, proposal: ProposalV1 | None) -> None:
        self.proposal = proposal

    def get_current(self, _connection, *, proposal_id, for_update=False):
        assert for_update is True
        if self.proposal is None or self.proposal.proposal_id != proposal_id:
            return None
        return ProposalRecordV1(self.proposal, 1)


class _Catalogue:
    def __init__(self, context: ScenarioContext | None) -> None:
        self.context = context

    def get_scenario_context(self, _connection, scenario_id):
        if self.context is None or self.context.scenario_id != scenario_id:
            return None
        return self.context


class _RunRepository:
    def __init__(self) -> None:
        self.created = []

    def create_queued_run(self, _connection, *, snapshot, site_id):
        self.created.append((snapshot, site_id))


class _Connection:
    def __init__(self) -> None:
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)


def _proposal(*, state="active") -> ProposalV1:
    scenario_id = uuid4()
    version_id = uuid4()
    return ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=scenario_id,
        scenario_version_id=version_id,
        resolved_entities=(
            ResolvedEntityV1(
                group="work-areas-and-tasks",
                record_id="task-1",
                label="Task 1",
                scenario_version_id=version_id,
            ),
        ),
        canonical_hash="a" * 64,
        state=state,
    )


def _context(proposal: ProposalV1, *, version_id=None) -> ScenarioContext:
    assert proposal.scenario_id is not None and proposal.scenario_version_id is not None
    return ScenarioContext(
        scenario_name="Scenario",
        scenario_id=proposal.scenario_id,
        scenario_version_id=version_id or proposal.scenario_version_id,
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="b" * 64,
        site_id=uuid4(),
        baseline_schedule_version=None,
    )


def _settings():
    return SimpleNamespace(
        solver_engine_name="cpsat",
        solver_seed=42,
        solver_num_search_workers=1,
        solver_max_deterministic_time=30.0,
        solver_wall_time_limit_seconds=30.0,
    )


def test_create_run_snapshot_freezes_persisted_authority_and_evidence() -> None:
    proposal = _proposal()
    context = _context(proposal)
    runs = _RunRepository()
    accepted_at = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)

    snapshot = create_run_snapshot(
        _ProposalRepository(proposal),
        _Catalogue(context),
        runs,
        object(),
        proposal_id=proposal.proposal_id,
        settings=_settings(),
        clock=lambda: accepted_at,
    )

    assert snapshot.scenario_version_id == context.scenario_version_id
    assert snapshot.proposal_version_id == proposal.proposal_version_id
    assert snapshot.constraints == proposal.constraints
    assert snapshot.preserved_locks == proposal.preserved_locks
    assert snapshot.solver_config.num_search_workers == 1
    assert snapshot.accepted_at == accepted_at
    assert len(snapshot.input_evidence_refs) == 1
    assert snapshot.input_evidence_refs[0].record_id == "task-1"
    assert snapshot.input_evidence_refs[0].producing_run_version is None
    assert runs.created == [(snapshot, context.site_id)]


@pytest.mark.parametrize(
    ("proposal_state", "version_drift", "code"),
    (("rejected", False, "rejected_proposal"), ("active", True, "stale_proposal")),
)
def test_create_run_snapshot_fails_closed_before_write(
    proposal_state, version_drift, code
) -> None:
    proposal = _proposal(state=proposal_state)
    context = _context(proposal, version_id=uuid4() if version_drift else None)
    runs = _RunRepository()

    with pytest.raises(SnapshotCreationError) as caught:
        create_run_snapshot(
            _ProposalRepository(proposal),
            _Catalogue(context),
            runs,
            object(),
            proposal_id=proposal.proposal_id,
            settings=_settings(),
        )

    assert caught.value.code == code
    assert runs.created == []


def test_postgres_repository_uses_one_connection_for_snapshot_and_run() -> None:
    proposal = _proposal()
    context = _context(proposal)
    captures = _RunRepository()
    snapshot = create_run_snapshot(
        _ProposalRepository(proposal), _Catalogue(context), captures, object(),
        proposal_id=proposal.proposal_id, settings=_settings(),
    )
    connection = _Connection()

    PostgresScheduleRunRepository().create_queued_run(
        connection, snapshot=snapshot, site_id=context.site_id
    )

    assert [statement.table.name for statement in connection.statements] == [
        "run_snapshot", "schedule_run"
    ]
