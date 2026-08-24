"""Deterministic candidate-to-baseline comparison over immutable evidence."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from application.contracts.comparison import AssignmentDiffV1, ComparisonV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import (
    ScheduleVersionV1,
    ValidationFactsV1,
    WorkerSchedulingFactV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    DemandIntervalV1,
    TaskV1,
    WorkerV1,
)
from application.grounding.pagination import drain_projection_group
from application.ports.scenario_projection import ScenarioProjectionReader
from application.scheduling.candidate_metrics import calculate_candidate_metrics
from application.scheduling.hard_constraints import validate_hard_constraints

SCOPE_CONTROLS = (
    "COVERS: candidate and baseline metrics are recomputed from version-pinned projection rows.",
    "NOT COVERED: comparisons over a scenario exceeding 2000 rows in any one group.",
    "NOT COVERED: non-empty production baselines need authoritative wages and selected shift windows; projection workers expose neither today.",
)


class ComparisonIntegrityError(ValueError):
    """Persisted candidate evidence disagrees with deterministic recomputation."""


def _facts(workers: tuple[WorkerV1, ...], tasks: tuple[TaskV1, ...], demand: tuple[DemandIntervalV1, ...], horizon_minutes: int) -> ValidationFactsV1:
    # The projection deliberately has no wage or solver-selected shift facts.
    # A zero wage and empty selected-shift tuple are truthful only while the
    # real baseline assignment supply is empty; the first story that populates
    # it owns replacing both placeholders (recorded in deferred-work.md).
    return ValidationFactsV1(
        horizon_minutes=horizon_minutes,
        workers=tuple(
            WorkerSchedulingFactV1(
                worker_id=worker.record_id,
                employment_type=worker.employment_type,
                contracted_hours=worker.contracted_hours,
                wage_per_hour=0.0,
                qualifications=worker.qualifications,
                availability_windows=worker.availability_windows,
            )
            for worker in workers
        ),
        selected_shifts=(),
        max_hours_per_week=(),
        max_shifts_per_day=(),
        minimum_gap_minutes=0,
        tasks=tasks,
        demand_intervals=demand,
    )


def _ids(assignments: tuple[AssignmentV1, ...], field: str) -> set[str]:
    return {value for assignment in assignments if (value := getattr(assignment, field)) is not None}


def calculate_comparison(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    candidate: ScheduleVersionV1,
    scenario_id: UUID,
    scenario_version_id: UUID,
    site_id: UUID,
    expected_baseline_schedule_version: str | None,
) -> ComparisonV1:
    overview = reader.get_overview(connection, scenario_id)
    if overview is None:
        raise ComparisonIntegrityError(f"scenario {scenario_id} has no projection")
    if overview.scenario_version_id != scenario_version_id or overview.site_id != site_id:
        raise ComparisonIntegrityError("candidate scenario binding does not match projection")
    if candidate.schedule_version_id is None or candidate.schedule_run_id is None:
        raise ComparisonIntegrityError("candidate version and run identifiers are required")
    if candidate.metrics is None:
        raise ComparisonIntegrityError("candidate metrics are required")

    drain_args = dict(
        scenario_version_id=scenario_version_id,
        site_id=site_id,
        page_size=200,
        max_rows=2000,
    )
    tasks = cast(tuple[TaskV1, ...], drain_projection_group(reader.get_tasks, connection, scenario_id, **drain_args))
    demand = cast(tuple[DemandIntervalV1, ...], drain_projection_group(reader.get_demand, connection, scenario_id, **drain_args))
    workers = cast(tuple[WorkerV1, ...], drain_projection_group(reader.get_workers, connection, scenario_id, **drain_args))
    baseline = cast(tuple[AssignmentV1, ...], drain_projection_group(reader.get_baseline_assignments, connection, scenario_id, **drain_args))
    facts = _facts(workers, tasks, demand, overview.horizon_minutes)

    recomputed_candidate, _ = calculate_candidate_metrics(
        candidate.assignments, tasks, demand, facts, constraints=()
    )
    # Candidate wage was captured only inside the solver snapshot and is not
    # readable through this projection. Preserve its immutable persisted cost,
    # while verifying every projection-recomputable field.
    recomputed_candidate = replace(recomputed_candidate, total_cost=candidate.metrics.total_cost)
    if recomputed_candidate != candidate.metrics:
        raise ComparisonIntegrityError("persisted candidate metrics disagree with recomputation")

    baseline_metrics, _ = calculate_candidate_metrics(
        baseline, tasks, demand, facts, constraints=()
    )
    baseline_hard = validate_hard_constraints(baseline, facts, preserved_locks=())

    candidate_workers, baseline_workers = _ids(candidate.assignments, "worker_id"), _ids(baseline, "worker_id")
    candidate_shifts, baseline_shifts = _ids(candidate.assignments, "shift_id"), _ids(baseline, "shift_id")
    candidate_tasks, baseline_tasks = _ids(candidate.assignments, "task_id"), _ids(baseline, "task_id")
    assignment_diff = AssignmentDiffV1(
        added_worker_ids=tuple(sorted(candidate_workers - baseline_workers)),
        removed_worker_ids=tuple(sorted(baseline_workers - candidate_workers)),
        added_shift_ids=tuple(sorted(candidate_shifts - baseline_shifts)),
        removed_shift_ids=tuple(sorted(baseline_shifts - candidate_shifts)),
        added_task_ids=tuple(sorted(candidate_tasks - baseline_tasks)),
        removed_task_ids=tuple(sorted(baseline_tasks - candidate_tasks)),
    )
    served = dict(recomputed_candidate.interval_coverage_served_minutes)
    unresolved = tuple(
        record_id
        for record_id, required in recomputed_candidate.interval_coverage_required_minutes
        if served.get(record_id, 0.0) < required
    )
    baseline_refs = tuple(
        EvidenceRefV1(
            scenario_version_id=scenario_version_id,
            checksum_algorithm=overview.checksum_algorithm,
            checksum_schema_version=overview.checksum_schema_version,
            checksum_digest=overview.checksum_digest,
            producing_run_version=None,
            baseline_schedule_version=expected_baseline_schedule_version,
            group="baseline-assignments",
            record_id=assignment.record_id,
        )
        for assignment in baseline
    )
    current_baseline = overview.baseline_schedule_version
    return ComparisonV1(
        candidate_schedule_version_id=candidate.schedule_version_id,
        candidate_schedule_run_id=candidate.schedule_run_id,
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        expected_baseline_schedule_version=expected_baseline_schedule_version,
        current_baseline_schedule_version=current_baseline,
        stale=expected_baseline_schedule_version != current_baseline,
        assignment_diff=assignment_diff,
        candidate_metrics=recomputed_candidate,
        baseline_metrics=baseline_metrics,
        candidate_constraint_results=candidate.constraint_results,
        baseline_hard_constraint_results=baseline_hard,
        warnings=candidate.warnings,
        unresolved_gap_record_ids=unresolved,
        evidence_refs=tuple(candidate.evidence_refs) + baseline_refs,
    )


__all__ = ["SCOPE_CONTROLS", "ComparisonIntegrityError", "calculate_comparison"]
