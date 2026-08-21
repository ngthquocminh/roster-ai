from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.contracts.proposal import ProposalV1
from application.ports.proposal import ProposalRecordV1
from application.ports.scenario_catalogue import ScenarioContext
from application.ports.schedule_run import IdempotentScheduleRunResultV1
from application.use_cases.enqueue_compute import (
    IdempotencyKeyConflictError,
    NON_TERMINAL_RUN_STATUSES,
    SiteConcurrencyExhaustedError,
    enqueue_compute,
)
from application.contracts.schedule_version import ScheduleRunStatusV1
from typing import get_args


class _ProposalRepository:
    def __init__(self, proposal: ProposalV1, actor_id) -> None:
        self.proposal = proposal
        self.actor_id = actor_id

    def get_current(self, _connection, *, proposal_id, for_update=False):
        assert proposal_id == self.proposal.proposal_id
        return ProposalRecordV1(self.proposal, 1, self.actor_id)


class _Catalogue:
    def __init__(self, context: ScenarioContext) -> None:
        self.context = context

    def get_scenario_context(self, _connection, scenario_id):
        assert scenario_id == self.context.scenario_id
        return self.context


class _RunRepository:
    def __init__(self) -> None:
        self.snapshots = []
        self.jobs = []
        self.idempotency = {}

    def create_queued_run(self, _connection, *, snapshot, site_id, actor_id):
        self.snapshots.append((snapshot, site_id, actor_id))

    def enqueue_job(self, _connection, *, job, site_id):
        self.jobs.append((job, site_id))

    def get_idempotent_result(
        self, _connection, *, site_id, actor_id, operation, idempotency_key
    ):
        return self.idempotency.get((site_id, actor_id, operation, idempotency_key))

    def _store_idempotent_result(
        self,
        _connection,
        *,
        site_id,
        actor_id,
        operation,
        idempotency_key,
        body_hash,
        response_payload,
    ):
        key = (site_id, actor_id, operation, idempotency_key)
        self.idempotency.setdefault(
            key, IdempotentScheduleRunResultV1(body_hash, response_payload)
        )

    def acquire_site_enqueue_lock(self, _connection, *, site_id):
        self.locked_site = site_id

    def count_runs_with_statuses(self, _connection, *, site_id, statuses):
        assert site_id == self.locked_site
        assert statuses == NON_TERMINAL_RUN_STATUSES
        return len(self.jobs)


def _fixture():
    actor_id = uuid4()
    site_id = uuid4()
    scenario_id = uuid4()
    scenario_version_id = uuid4()
    proposal = ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        canonical_hash="a" * 64,
        resource_version=1,
    )
    context = ScenarioContext(
        scenario_name="Scenario",
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="b" * 64,
        site_id=site_id,
        baseline_schedule_version=None,
    )
    settings = SimpleNamespace(
        solver_engine_name="cpsat",
        solver_seed=42,
        solver_num_search_workers=1,
        solver_max_deterministic_time=30.0,
        solver_wall_time_limit_seconds=30.0,
        site_max_concurrent_runs=2,
    )
    return actor_id, site_id, proposal, context, settings


def test_enqueue_compute_creates_snapshot_job_and_idempotent_result_together() -> None:
    """AC1's enqueue-compute bundle: snapshot + queued run + job + replay record.

    Story 3.5 extends this bundle with one schedule-run-owned queued event;
    the PostgreSQL integration test proves that fourth durable effect and its
    idempotent replay count because this unit fake intentionally stores only
    repository calls.

    `attempt_id` is likewise absent by design (Decision 5): an attempt is per
    lease ACQUISITION, and nothing has leased this job yet.
    """
    actor_id, site_id, proposal, context, settings = _fixture()
    runs = _RunRepository()
    accepted_at = datetime(2026, 8, 20, 5, 0, tzinfo=timezone.utc)

    result = enqueue_compute(
        _ProposalRepository(proposal, actor_id),
        _Catalogue(context),
        runs,
        object(),
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        actor_id=actor_id,
        expected_proposal_resource_version=1,
        idempotency_key="enqueue-1",
        settings=settings,
        clock=lambda: accepted_at,
    )

    assert len(runs.snapshots) == len(runs.jobs) == len(runs.idempotency) == 1
    snapshot = runs.snapshots[0][0]
    job = runs.jobs[0][0]
    assert result.schedule_run_id == snapshot.schedule_run_id == job.schedule_run_id
    assert result.job_id == job.job_id
    assert job.actor_id == actor_id
    assert job.site_id == site_id
    assert job.attempt_id is None
    assert job.capability_version == "1"
    assert job.idempotency_key == "enqueue-1"
    assert job.created_at == accepted_at


def test_enqueue_compute_replays_without_creating_a_second_effect() -> None:
    actor_id, site_id, proposal, context, settings = _fixture()
    runs = _RunRepository()
    arguments = dict(
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        actor_id=actor_id,
        expected_proposal_resource_version=1,
        idempotency_key="enqueue-1",
        settings=settings,
    )
    first = enqueue_compute(
        _ProposalRepository(proposal, actor_id),
        _Catalogue(context),
        runs,
        object(),
        **arguments,
    )
    replay = enqueue_compute(
        _ProposalRepository(proposal, actor_id),
        _Catalogue(context),
        runs,
        object(),
        **arguments,
    )

    assert replay == first
    assert len(runs.snapshots) == len(runs.jobs) == 1


def test_enqueue_compute_rejects_same_key_with_a_different_expected_version() -> None:
    actor_id, site_id, proposal, context, settings = _fixture()
    runs = _RunRepository()
    common = dict(
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        actor_id=actor_id,
        idempotency_key="enqueue-1",
        settings=settings,
    )
    enqueue_compute(
        _ProposalRepository(proposal, actor_id),
        _Catalogue(context),
        runs,
        object(),
        expected_proposal_resource_version=1,
        **common,
    )
    with pytest.raises(IdempotencyKeyConflictError):
        enqueue_compute(
            _ProposalRepository(proposal, actor_id),
            _Catalogue(context),
            runs,
            object(),
            expected_proposal_resource_version=2,
            **common,
        )
    assert len(runs.jobs) == 1


def test_same_key_is_scoped_to_the_requesting_actor() -> None:
    proposal_author, site_id, proposal, context, settings = _fixture()
    first_actor = uuid4()
    second_actor = uuid4()
    runs = _RunRepository()
    common = dict(
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        expected_proposal_resource_version=1,
        idempotency_key="shared-key",
        settings=settings,
    )

    first = enqueue_compute(
        _ProposalRepository(proposal, proposal_author),
        _Catalogue(context),
        runs,
        object(),
        actor_id=first_actor,
        **common,
    )
    second = enqueue_compute(
        _ProposalRepository(proposal, proposal_author),
        _Catalogue(context),
        runs,
        object(),
        actor_id=second_actor,
        **common,
    )

    assert first != second
    assert [actor_id for _snapshot, _site_id, actor_id in runs.snapshots] == [
        first_actor,
        second_actor,
    ]
    assert [job.actor_id for job, _site_id in runs.jobs] == [first_actor, second_actor]
    assert len(runs.idempotency) == 2


def test_replay_succeeds_even_when_site_concurrency_is_exhausted() -> None:
    actor_id, site_id, proposal, context, settings = _fixture()
    settings.site_max_concurrent_runs = 1
    runs = _RunRepository()
    arguments = dict(
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        actor_id=actor_id,
        expected_proposal_resource_version=1,
        idempotency_key="replay-at-limit",
        settings=settings,
    )
    first = enqueue_compute(
        _ProposalRepository(proposal, actor_id), _Catalogue(context), runs, object(), **arguments
    )

    replay = enqueue_compute(
        _ProposalRepository(proposal, actor_id), _Catalogue(context), runs, object(), **arguments
    )

    assert replay == first
    assert len(runs.jobs) == 1


def test_new_request_fails_closed_when_site_concurrency_is_exhausted() -> None:
    actor_id, site_id, proposal, context, settings = _fixture()
    settings.site_max_concurrent_runs = 1
    runs = _RunRepository()
    common = dict(
        proposal_id=proposal.proposal_id,
        site_id=site_id,
        actor_id=actor_id,
        expected_proposal_resource_version=1,
        settings=settings,
    )
    enqueue_compute(
        _ProposalRepository(proposal, actor_id), _Catalogue(context), runs, object(),
        idempotency_key="first", **common,
    )

    with pytest.raises(SiteConcurrencyExhaustedError):
        enqueue_compute(
            _ProposalRepository(proposal, actor_id), _Catalogue(context), runs, object(),
            idempotency_key="second", **common,
        )
    assert len(runs.jobs) == 1


def test_non_terminal_status_enumeration_is_exhaustive() -> None:
    terminal = {
        "solver_completed", "solver_infeasible", "solver_timed_out",
        "solver_cancelled", "solver_failed",
    }
    assert set(get_args(ScheduleRunStatusV1)) == set(NON_TERMINAL_RUN_STATUSES) | terminal
    assert set(NON_TERMINAL_RUN_STATUSES).isdisjoint(terminal)
