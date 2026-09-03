from __future__ import annotations

from dataclasses import replace

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from adapters.postgres.proposal import PostgresProposalRepository
from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.scenario_catalogue import PostgresScenarioCatalogueReader
from adapters.postgres.schema import (
    app_user,
    conversation,
    organization,
    scenario,
    scenario_version,
    schedule_version,
    site,
)
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import (
    SchedulingDraftRequestV1,
    scheduling_draft,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.proposal import DraftConstraintProposalV1
from application.contracts.schedule_version import ConstraintResultV1
from application.scheduling.comparison import calculate_comparison
from application.use_cases.cancel_schedule_run import cancel_schedule_run
from application.use_cases.enqueue_compute import enqueue_compute
from application.use_cases.manage_proposal import revise_proposal
from engine.governed_adapter import GovernedSchedulerAdapter
from evals.repair_correctness_report import CORRECTNESS_OUTPUT_ENV
from tests.fixtures.repair_correctness import (
    BASELINE_ASSIGNMENTS,
    FIXTURE_CHECKSUM_DIGEST,
    FIXTURE_PAYLOAD,
    FixturePayloadSource,
    LOCKS,
    RepairProjectionReader,
    SCENARIO_ID,
    SCENARIO_VERSION_ID,
    SITE_ID,
    TASK_ID,
    hard_constraint_failure_scheduler,
    infeasible_scheduler,
)
from tests.test_job_leasing_postgres import _only_leasable, _runtime
from worker.lease_worker import run_once


pytestmark = pytest.mark.postgres


class _RecordingScheduler:
    def __init__(self, delegate):
        self.delegate = delegate
        self.error = None
        self.solved = None

    def solve(self, snapshot):
        try:
            self.solved = self.delegate.solve(snapshot)
            return self.solved
        except Exception as exc:  # pragma: no cover - assertion reports the cause
            self.error = exc
            raise


@pytest.fixture(scope="module")
def repair_context(governed_postgres_engine):
    ids = {
        "org": uuid4(),
        "actor": uuid4(),
        "membership": uuid4(),
        "conversation": uuid4(),
    }
    reader = RepairProjectionReader()
    draft_request = SchedulingDraftRequestV1(
        expected_scenario_version_id=SCENARIO_VERSION_ID,
        constraints=(
            DraftConstraintProposalV1(
                kind="set_min_workers_per_task",
                group="work-areas-and-tasks",
                record_id=TASK_ID,
                n=1,
            ),
        ),
    )
    draft = scheduling_draft(
        AgentDepsV1(
            actor_id=ids["actor"],
            site_id=SITE_ID,
            membership_id=ids["membership"],
            request_id=uuid4(),
            agent_run_id=uuid4(),
            conversation_id=ids["conversation"],
            scenario_id=SCENARIO_ID,
            scenario_version_id=SCENARIO_VERSION_ID,
            policy_version="story-3.10",
            clock=lambda: datetime(2026, 8, 24, tzinfo=timezone.utc),
            projection_reader=reader,
            connection=object(),
            remaining_budget=AgentBudgetV1(tool_calls_limit=2),
        ),
        draft_request,
    )
    assert draft.proposal.preserved_locks == LOCKS

    with governed_postgres_engine.begin() as connection:
        connection.execute(
            insert(organization).values(id=ids["org"], name="Repair Proof Org")
        )
        connection.execute(
            insert(site).values(
                id=SITE_ID,
                organization_id=ids["org"],
                name="Repair Proof Site",
            )
        )
        connection.execute(
            insert(app_user).values(
                id=ids["actor"],
                idp_subject=f"repair-{ids['actor']}",
                email=f"repair-{ids['actor']}@example.test",
            )
        )
        connection.execute(
            insert(scenario).values(
                id=SCENARIO_ID,
                site_id=SITE_ID,
                fixture_id="story-3.10-repair",
                name="Wednesday repair correctness",
            )
        )
        connection.execute(
            insert(scenario_version).values(
                id=SCENARIO_VERSION_ID,
                site_id=SITE_ID,
                scenario_id=SCENARIO_ID,
                fixture_id="story-3.10-repair",
                version="v1",
                payload=FIXTURE_PAYLOAD,
                checksum_digest=FIXTURE_CHECKSUM_DIGEST,
            )
        )
        connection.execute(
            insert(conversation).values(
                id=ids["conversation"],
                site_id=SITE_ID,
                scenario_id=SCENARIO_ID,
                scenario_version_id=SCENARIO_VERSION_ID,
                created_by_actor_id=ids["actor"],
            )
        )
    proposals = PostgresProposalRepository()
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, SITE_ID)
        proposals.create_draft(
            connection,
            proposal=draft.proposal,
            site_id=SITE_ID,
            conversation_id=ids["conversation"],
            actor_id=ids["actor"],
        )
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, SITE_ID)
        revised = revise_proposal(
            proposals,
            reader,
            connection,
            proposal_id=draft.proposal.proposal_id,
            site_id=SITE_ID,
            actor_id=ids["actor"],
            constraints=(
                DraftConstraintProposalV1(
                    kind="set_min_workers_per_task",
                    group="work-areas-and-tasks",
                    record_id=TASK_ID,
                    n=2,
                ),
            ),
            expected_resource_version=1,
            idempotency_key="story-3.10-revise",
        )
    assert revised is not None
    assert revised.proposal.preserved_locks == LOCKS
    assert revised.proposal.constraints[0].n == 2
    return SimpleNamespace(ids=ids, proposal=revised.proposal, reader=reader)


def _settings(*, wall_seconds=10.0, deterministic_seconds=10.0):
    return SimpleNamespace(
        solver_engine_name="cpsat",
        solver_seed=42,
        solver_num_search_workers=1,
        solver_max_deterministic_time=deterministic_seconds,
        solver_wall_time_limit_seconds=wall_seconds,
        site_max_concurrent_runs=1000,
    )


def _enqueue(engine, context, *, key, settings=None):
    repository = PostgresScheduleRunRepository()
    with engine.begin() as connection:
        _runtime(connection, SITE_ID)
        result = enqueue_compute(
            PostgresProposalRepository(),
            PostgresScenarioCatalogueReader(),
            repository,
            connection,
            proposal_id=context.proposal.proposal_id,
            site_id=SITE_ID,
            actor_id=context.ids["actor"],
            expected_proposal_resource_version=context.proposal.resource_version,
            idempotency_key=key,
            capability_version="1",
            settings=settings or _settings(),
        )
    _only_leasable(engine, result.job_id)
    return result


def test_real_pipeline_closes_gap_preserves_lock_and_does_not_add_overtime(
    governed_postgres_engine, repair_context
) -> None:
    queued = _enqueue(
        governed_postgres_engine,
        repair_context,
        key="story-3.10-completed",
    )
    scheduler = _RecordingScheduler(
        GovernedSchedulerAdapter(FixturePayloadSource())
    )
    outcome = run_once(
        governed_postgres_engine,
        PostgresScheduleRunRepository(),
        scheduler,
        lease_owner="story-3.10-completed-worker",
        lease_seconds=60,
    )
    assert outcome is not None

    repository = PostgresScheduleRunRepository()
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, SITE_ID)
        run = repository.get_run(
            connection, run_id=queued.schedule_run_id, site_id=SITE_ID
        )
        snapshot = repository.load_snapshot(
            connection, run_id=queued.schedule_run_id, site_id=SITE_ID
        )
        candidate = repository.get_candidate(
            connection, schedule_run_id=queued.schedule_run_id, site_id=SITE_ID
        )
        assert run is not None
        assert scheduler.error is None, repr(scheduler.error)
        assert (outcome.status, run.status, run.reason) == (
            "solver_completed",
            "solver_completed",
            None,
        )
        assert snapshot is not None
        assert candidate is not None
        # `metrics`/`constraint_results` are overridden too, not just
        # `assignments` -- `replace(candidate, ...)` alone would leave
        # baseline_metrics.total_cost and baseline_hard_constraint_results as
        # the CANDIDATE's own persisted values (calculate_comparison takes
        # both verbatim from `baseline_version`, never recomputing them), so
        # a comparison built this way would silently assert the candidate
        # against itself on exactly those two fields.
        baseline_version = replace(
            candidate,
            schedule_version_id=uuid4(),
            schedule_run_id=uuid4(),
            assignments=BASELINE_ASSIGNMENTS,
            metrics=replace(candidate.metrics, total_cost=42.0, assignment_count=len(BASELINE_ASSIGNMENTS)),
            constraint_results=(ConstraintResultV1(
                constraint_id="hard:baseline-repair-fixture", constraint_type="qualification",
                constraint_class="hard", satisfied=True,
            ),),
        )
        comparison = calculate_comparison(
            repair_context.reader,
            connection,
            candidate=candidate,
            scenario_id=SCENARIO_ID,
            scenario_version_id=SCENARIO_VERSION_ID,
            site_id=SITE_ID,
            expected_baseline_schedule_version=str(baseline_version.schedule_version_id),
            baseline_version=baseline_version,
        )

    assert snapshot.preserved_locks == LOCKS
    assert snapshot.input_evidence_refs
    assert len(BASELINE_ASSIGNMENTS) == 1
    assert comparison.unresolved_gap_record_ids == ()
    assert comparison.candidate_metrics.interval_coverage_required_minutes == (
        ("wed-outbound-gap", 480.0),
    )
    assert comparison.candidate_metrics.interval_coverage_served_minutes == (
        ("wed-outbound-gap", 480.0),
    )
    assert (
        comparison.candidate_metrics.overtime_minutes
        <= comparison.baseline_metrics.overtime_minutes
    )
    assert comparison.baseline_metrics.assignment_count == 1
    assert comparison.candidate_metrics.assignment_count == 2
    # The baseline's cost and hard-constraint results are genuinely its own,
    # not silently the candidate's -- see the comment above baseline_version.
    assert comparison.baseline_metrics.total_cost == 42.0
    assert comparison.baseline_metrics.total_cost != comparison.candidate_metrics.total_cost
    assert tuple(item.constraint_id for item in comparison.baseline_hard_constraint_results) == (
        "hard:baseline-repair-fixture",
    )
    assert all(item.satisfied for item in comparison.candidate_constraint_results)
    assert any(
        item.constraint_type == "preserved_lock"
        for item in comparison.candidate_constraint_results
    )
    with governed_postgres_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == queued.schedule_run_id
            )
        ) == 1

    correctness_output = os.environ.get(CORRECTNESS_OUTPUT_ENV)
    if correctness_output:
        Path(correctness_output).write_text(
            json.dumps(
                {
                    "baseline_assignment_count": comparison.baseline_metrics.assignment_count,
                    "candidate_assignment_count": comparison.candidate_metrics.assignment_count,
                    "required_minutes": sum(
                        minutes
                        for _, minutes in comparison.candidate_metrics.interval_coverage_required_minutes
                    ),
                    "served_minutes": sum(
                        minutes
                        for _, minutes in comparison.candidate_metrics.interval_coverage_served_minutes
                    ),
                    "unresolved_gap_record_ids": list(comparison.unresolved_gap_record_ids),
                    "preserved_lock_count": len(snapshot.preserved_locks),
                    "hard_violation_count": sum(
                        1
                        for item in comparison.candidate_constraint_results
                        if not item.satisfied
                    ),
                    "baseline_overtime_minutes": comparison.baseline_metrics.overtime_minutes,
                    "candidate_overtime_minutes": comparison.candidate_metrics.overtime_minutes,
                }
            ),
            encoding="utf-8",
        )


def _assert_non_promotable(engine, run_id, *, status, reason):
    repository = PostgresScheduleRunRepository()
    with engine.begin() as connection:
        _runtime(connection, SITE_ID)
        run = repository.get_run(connection, run_id=run_id, site_id=SITE_ID)
        snapshot = repository.load_snapshot(connection, run_id=run_id, site_id=SITE_ID)
        candidate = repository.get_candidate(
            connection, schedule_run_id=run_id, site_id=SITE_ID
        )
    assert run is not None
    assert (run.status, run.reason) == (status, reason)
    assert snapshot is not None
    assert snapshot.input_evidence_refs
    assert candidate is None
    with engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(schedule_version).where(
                schedule_version.c.schedule_run_id == run_id
            )
        ) == 0


def test_infeasible_is_literal_and_has_no_candidate(
    governed_postgres_engine, repair_context
) -> None:
    queued = _enqueue(
        governed_postgres_engine, repair_context, key="story-3.10-infeasible"
    )
    outcome = run_once(
        governed_postgres_engine,
        PostgresScheduleRunRepository(),
        infeasible_scheduler(),
        lease_owner="story-3.10-infeasible-worker",
        lease_seconds=60,
    )
    assert outcome is not None and outcome.status == "solver_infeasible"
    _assert_non_promotable(
        governed_postgres_engine,
        queued.schedule_run_id,
        status="solver_infeasible",
        reason="model_infeasible",
    )


def test_real_adapter_timeout_is_literal_bounded_and_has_no_candidate(
    governed_postgres_engine, repair_context
) -> None:
    ceiling = 0.000001
    queued = _enqueue(
        governed_postgres_engine,
        repair_context,
        key="story-3.10-timeout",
        settings=_settings(wall_seconds=ceiling, deterministic_seconds=10.0),
    )
    scheduler = _RecordingScheduler(
        GovernedSchedulerAdapter(
            FixturePayloadSource(), use_deterministic_time=False
        )
    )
    outcome = run_once(
        governed_postgres_engine,
        PostgresScheduleRunRepository(),
        scheduler,
        lease_owner="story-3.10-timeout-worker",
        lease_seconds=60,
    )
    assert outcome is not None and outcome.status == "solver_timed_out"
    assert scheduler.error is None, repr(scheduler.error)
    assert scheduler.solved is not None
    # This ceiling is a microsecond, so wall_time_seconds is dominated by
    # Python/interpreter scheduling noise, not CP-SAT search time -- no
    # tolerance at this scale can discriminate a proportional (e.g. 2x)
    # ceiling-application regression; that guard already exists at a scale
    # where it can, in test_governed_solver_adapter.py's
    # test_one_wall_ceiling_bounds_both_solver_rounds (0.25s ceiling, 0.40s
    # bound). This assertion only catches a gross regression -- the ceiling
    # being ignored outright and the solve left to run to completion.
    assert scheduler.solved.wall_time_seconds <= ceiling + 0.02
    _assert_non_promotable(
        governed_postgres_engine,
        queued.schedule_run_id,
        status="solver_timed_out",
        reason="budget_exhausted",
    )


def test_cancel_command_stops_queued_run_before_solver_and_has_no_candidate(
    governed_postgres_engine, repair_context
) -> None:
    queued = _enqueue(
        governed_postgres_engine, repair_context, key="story-3.10-cancelled"
    )
    with governed_postgres_engine.begin() as connection:
        _runtime(connection, SITE_ID)
        cancelled = cancel_schedule_run(
            PostgresScheduleRunRepository(),
            connection,
            run_id=queued.schedule_run_id,
            site_id=SITE_ID,
            actor_id=repair_context.ids["actor"],
            expected_resource_version=1,
            idempotency_key="story-3.10-cancel-command",
        )
    assert cancelled.status == "solver_cancelled"

    class ForbiddenScheduler:
        calls = 0

        def solve(self, _snapshot):
            self.calls += 1
            raise AssertionError("cancelled work reached the solver")

    scheduler = ForbiddenScheduler()
    outcome = run_once(
        governed_postgres_engine,
        PostgresScheduleRunRepository(),
        scheduler,
        lease_owner="story-3.10-cancelled-worker",
        lease_seconds=60,
    )
    assert scheduler.calls == 0
    assert outcome is not None and outcome.status == "solver_cancelled"
    _assert_non_promotable(
        governed_postgres_engine,
        queued.schedule_run_id,
        status="solver_cancelled",
        reason="cancelled",
    )


def test_hard_constraint_failure_is_literal_and_has_no_candidate(
    governed_postgres_engine, repair_context
) -> None:
    queued = _enqueue(
        governed_postgres_engine, repair_context, key="story-3.10-hard-failure"
    )
    outcome = run_once(
        governed_postgres_engine,
        PostgresScheduleRunRepository(),
        hard_constraint_failure_scheduler(),
        lease_owner="story-3.10-hard-failure-worker",
        lease_seconds=60,
    )
    assert outcome is not None and outcome.status == "solver_failed"
    _assert_non_promotable(
        governed_postgres_engine,
        queued.schedule_run_id,
        status="solver_failed",
        reason="hard_constraint_violated",
    )
