from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import (
    SelectedShiftFactV1,
    SolverOutcomeV1,
    ValidationFactsV1,
    WorkerSchedulingFactV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    DemandIntervalV1,
    QualificationRefV1,
    TaskV1,
)
from application.use_cases.finalize_schedule_run import finalize_schedule_run
from application.use_cases.execute_schedule_run import execute_schedule_run
from application.scheduling.candidate_metrics import calculate_candidate_metrics


class _Repository:
    def __init__(self) -> None:
        self.calls = []

    def finalize_run(self, _connection, **values):
        self.calls.append(values)

    def mark_running(self, _connection, *, run_id, site_id, fencing_epoch):
        self.running = (run_id, site_id, fencing_epoch)


class _Connection:
    def __init__(self) -> None:
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(rowcount=1)


def _snapshot(*, with_evidence: bool = False) -> RunSnapshotV1:
    scenario_version_id = uuid4()
    evidence = ()
    if with_evidence:
        evidence = (EvidenceRefV1(
            scenario_version_id=scenario_version_id,
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            producing_run_version=None,
            baseline_schedule_version=None,
            group="workers",
            record_id="w1",
        ),)
    return RunSnapshotV1(
        snapshot_id=uuid4(), schedule_run_id=uuid4(), scenario_id=uuid4(),
        scenario_version_id=scenario_version_id, checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1", checksum_digest="a" * 64,
        proposal_id=uuid4(), proposal_version_id=uuid4(), proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(),
        component_versions=(("application", "1"), ("contract", "1"), ("ortools", "9.11.4210")),
        accepted_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        input_evidence_refs=evidence,
    )


def _feasible_outcome() -> SolverOutcomeV1:
    qualification = QualificationRefV1("t1", 10)
    assignment = AssignmentV1(
        "a1", "w1", "t1", "s1", 0, 60, (qualification,), "solver"
    )
    facts = ValidationFactsV1(
        horizon_minutes=60,
        workers=(WorkerSchedulingFactV1(
            "w1", "Full Time", 40, 20, (qualification,),
            (AvailabilityWindowV1("roster", 0, 60),),
        ),),
        selected_shifts=(SelectedShiftFactV1("s1", "w1", "window", "roster", 0, 60, 60),),
        max_hours_per_week=(("Full Time", 56.0),),
        max_shifts_per_day=(("Full Time", 2),),
        minimum_gap_minutes=120,
        tasks=(TaskV1("t1", "t1", "Pick", "Picking", "a1", "Area", None),),
        demand_intervals=(DemandIntervalV1("d1", "outbound", "t1", "a1", 0, 60, 10, "volume"),),
    )
    return SolverOutcomeV1(
        solver_status="OPTIMAL", assignments=(assignment,), validation_facts=facts
    )


def test_feasible_validated_outcome_creates_exactly_one_candidate() -> None:
    repository = _Repository()
    snapshot = _snapshot(with_evidence=True)
    outcome = _feasible_outcome()

    result = finalize_schedule_run(
        repository, object(), snapshot=snapshot, outcome=outcome, site_id=uuid4()
    )

    assert result.status == "solver_completed"
    assert result.reason is None
    assert result.candidate is not None
    assert result.candidate.metrics.assignment_count == 1
    assert result.candidate.evidence_refs[0].producing_run_version == str(
        result.candidate.schedule_version_id
    )
    recomputed, _ = calculate_candidate_metrics(
        result.candidate.assignments,
        outcome.validation_facts.tasks,
        outcome.validation_facts.demand_intervals,
        outcome.validation_facts,
        constraints=snapshot.constraints,
    )
    assert recomputed == result.candidate.metrics
    assert repository.calls[0]["candidate"] is result.candidate


@pytest.mark.parametrize(
    ("outcome", "status", "reason"),
    (
        (SolverOutcomeV1(solver_status="INFEASIBLE"), "solver_infeasible", "model_infeasible"),
        (SolverOutcomeV1(solver_status="UNKNOWN"), "solver_timed_out", "budget_exhausted"),
        (SolverOutcomeV1(solver_status="MODEL_INVALID"), "solver_failed", "model_invalid"),
        (SolverOutcomeV1(solver_status="UNKNOWN", reason="cancelled"), "solver_cancelled", "cancelled"),
        (SolverOutcomeV1(solver_status="UNKNOWN", reason="deterministic_budget_exhausted"), "solver_failed", "budget_exhausted"),
    ),
)
def test_non_promotable_terminal_outcomes_write_no_candidate(outcome, status, reason) -> None:
    repository = _Repository()
    result = finalize_schedule_run(
        repository, object(), snapshot=_snapshot(), outcome=outcome, site_id=uuid4()
    )
    assert (result.status, result.reason, result.candidate) == (status, reason, None)
    assert repository.calls[0]["candidate"] is None


def test_validator_failure_maps_to_failed_and_writes_no_candidate() -> None:
    repository = _Repository()
    outcome = _feasible_outcome()
    broken = SolverOutcomeV1(
        **{**outcome.__dict__, "assignments": (outcome.assignments[0].__class__(
            **{**outcome.assignments[0].__dict__, "task_id": "not-qualified"}
        ),)}
    )
    result = finalize_schedule_run(
        repository, object(), snapshot=_snapshot(), outcome=broken, site_id=uuid4()
    )
    assert (result.status, result.reason, result.candidate) == (
        "solver_failed", "hard_constraint_violated", None
    )


def test_postgres_terminal_write_inserts_candidate_only_for_completed() -> None:
    snapshot = _snapshot()
    completed = finalize_schedule_run(
        _Repository(), object(), snapshot=snapshot,
        outcome=_feasible_outcome(), site_id=uuid4(),
    )
    candidate_connection = _Connection()
    terminal_connection = _Connection()
    adapter = PostgresScheduleRunRepository()

    adapter.finalize_run(
        candidate_connection, run_id=snapshot.schedule_run_id, site_id=uuid4(),
        fencing_epoch=1, status="solver_completed", reason=None,
        candidate=completed.candidate,
    )
    adapter.finalize_run(
        terminal_connection, run_id=snapshot.schedule_run_id, site_id=uuid4(),
        fencing_epoch=1, status="solver_timed_out", reason="budget_exhausted",
        candidate=None,
    )

    # `job_queue` comes FIRST on both paths: the fence is claimed under a row
    # lock before any candidate row is written, so a stale worker is rejected
    # by the guard itself rather than by the caller happening to roll back.
    assert [statement.table.name for statement in candidate_connection.statements] == [
        "job_queue", "schedule_version", "schedule_assignment", "schedule_run"
    ]
    assert [statement.table.name for statement in terminal_connection.statements] == [
        "job_queue", "schedule_run"
    ]


def test_adapter_error_is_persisted_as_specific_solver_failure() -> None:
    class DigestError(ValueError):
        code = "snapshot_digest_mismatch"

    class Scheduler:
        def solve(self, _snapshot):
            raise DigestError("changed")

    repository = _Repository()
    result = execute_schedule_run(
        repository, Scheduler(), object(), snapshot=_snapshot(), site_id=uuid4(),
        fencing_epoch=1,
    )

    assert (result.status, result.reason, result.candidate) == (
        "solver_failed", "snapshot_digest_mismatch", None
    )
