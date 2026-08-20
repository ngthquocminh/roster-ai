"""Atomically persist a literal terminal run and optional validated candidate."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import (
    ScheduleRunStatusV1,
    ScheduleVersionV1,
    SolverOutcomeV1,
)
from application.ports.schedule_run import ScheduleRunRepository
from application.scheduling.candidate_metrics import calculate_candidate_metrics
from application.scheduling.hard_constraints import (
    HardConstraintViolation,
    require_hard_constraints,
)


@dataclass(frozen=True)
class FinalizedScheduleRunV1:
    status: ScheduleRunStatusV1
    reason: str | None
    candidate: ScheduleVersionV1 | None


def _terminal(outcome: SolverOutcomeV1) -> tuple[ScheduleRunStatusV1, str | None]:
    if outcome.reason == "cancelled":
        return "solver_cancelled", "cancelled"
    if outcome.reason == "deterministic_budget_exhausted":
        return "solver_failed", "budget_exhausted"
    if outcome.reason:
        return "solver_failed", outcome.reason
    if outcome.solver_status == "INFEASIBLE":
        return "solver_infeasible", "model_infeasible"
    if outcome.solver_status == "MODEL_INVALID":
        return "solver_failed", "model_invalid"
    if outcome.solver_status == "UNKNOWN":
        return "solver_timed_out", "budget_exhausted"
    if outcome.solver_status in ("OPTIMAL", "FEASIBLE"):
        return "solver_completed", None
    return "solver_failed", outcome.reason or "solver_error"


def finalize_schedule_run(
    repository: ScheduleRunRepository,
    connection: Any,
    *,
    snapshot: RunSnapshotV1,
    outcome: SolverOutcomeV1,
    site_id: UUID,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FinalizedScheduleRunV1:
    assert snapshot.schedule_run_id is not None
    status, reason = _terminal(outcome)
    candidate = None
    if status == "solver_completed":
        if outcome.validation_facts is None:
            status, reason = "solver_failed", "validation_facts_missing"
        else:
            try:
                hard = require_hard_constraints(
                    outcome.assignments,
                    outcome.validation_facts,
                    preserved_locks=snapshot.preserved_locks,
                )
                metrics, soft = calculate_candidate_metrics(
                    outcome.assignments,
                    outcome.validation_facts.tasks,
                    outcome.validation_facts.demand_intervals,
                    outcome.validation_facts,
                    constraints=snapshot.constraints,
                )
            except HardConstraintViolation:
                status, reason = "solver_failed", "hard_constraint_violated"
            else:
                schedule_version_id = uuid4()
                evidence_refs = tuple(
                    replace(reference, producing_run_version=str(schedule_version_id))
                    for reference in snapshot.input_evidence_refs
                )
                candidate = ScheduleVersionV1(
                    schedule_version_id=schedule_version_id,
                    schedule_run_id=snapshot.schedule_run_id,
                    scenario_id=snapshot.scenario_id,
                    scenario_version_id=snapshot.scenario_version_id,
                    proposal_id=snapshot.proposal_id,
                    proposal_version_id=snapshot.proposal_version_id,
                    feasible_solver_status=outcome.solver_status,
                    assignments=outcome.assignments,
                    metrics=metrics,
                    constraint_results=hard + soft,
                    warnings=outcome.warnings,
                    evidence_refs=evidence_refs,
                    created_at=clock(),
                )
    repository.finalize_run(
        connection,
        run_id=snapshot.schedule_run_id,
        site_id=site_id,
        status=status,
        reason=reason,
        candidate=candidate,
        finished_at=clock(),
    )
    return FinalizedScheduleRunV1(status, reason, candidate)


__all__ = ["FinalizedScheduleRunV1", "finalize_schedule_run"]
