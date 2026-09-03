"""Deterministic candidate-to-baseline comparison over immutable evidence."""
from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Literal, cast
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

SCOPE_CONTROLS = (
    "COVERS: candidate and baseline metrics derive from version-pinned schedule versions and projection rows.",
    "NOT COVERED: comparisons over a scenario exceeding 2000 rows in any one group.",
    "COVERS: a pinned non-null baseline version that is unreadable, incompatible, or lacks persisted metrics fails closed.",
    "NOT COVERED: a baseline and candidate priced under different wage epochs are compared without detecting the mix.",
)


class ComparisonIntegrityError(ValueError):
    """Persisted candidate evidence disagrees with deterministic recomputation."""


BaselineUnavailableReasonV1 = Literal["unreadable", "scenario_version_mismatch", "metrics_unavailable"]


class BaselineSupplyUnavailableError(ValueError):
    """A real frozen baseline exists but its assignments cannot be read.

    Carries the LIVE baseline alongside the frozen one. The comparison is what
    normally publishes `current_baseline_schedule_version`, and the approval
    request is parameterised on it -- so a caller that degrades to "no
    comparison" still needs this value to offer a well-formed next approval.
    Without it, refusing the comparison would also silently remove the ability
    to request one.
    """

    def __init__(
        self,
        baseline_schedule_version: str,
        current_baseline_schedule_version: str | None = None,
        reason: BaselineUnavailableReasonV1 = "unreadable",
    ):
        self.baseline_schedule_version = baseline_schedule_version
        self.current_baseline_schedule_version = current_baseline_schedule_version
        self.reason = reason
        super().__init__("authoritative baseline assignment supply is unavailable")


def _facts(workers: tuple[WorkerV1, ...], tasks: tuple[TaskV1, ...], demand: tuple[DemandIntervalV1, ...], horizon_minutes: int) -> ValidationFactsV1:
    # The projection deliberately has no wage or solver-selected shift facts.
    # A zero wage and empty selected-shift tuple would misprice a recomputed
    # total_cost or hard-constraint result -- but neither side trusts this
    # function for those two fields. calculate_comparison overrides both
    # candidate and baseline total_cost with their authoritative persisted
    # values, and baseline_hard_constraint_results comes straight from the
    # baseline's persisted constraint_results, never from a recompute against
    # these facts.
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


def _sorted_values(pairs: tuple[tuple[str, float], ...]) -> tuple[float, ...]:
    """Compare interval-coverage minutes by value only, never by record_id.

    A demand row's `record_id` is a content hash at solve time
    (`engine/governed_adapter.py`'s `contract_digest`) but a positional index
    at comparison time (`adapters/postgres/scenario_projection.py`'s
    `_normalize_demand`, e.g. "outbound:0"). The two identifier namespaces
    were never meant to agree, so pairing (record_id, value) tuples for
    equality would raise `ComparisonIntegrityError` for every completed run
    with real demand. The sorted value multiset still proves the recomputed
    numbers agree with what was persisted.
    """
    return tuple(sorted(value for _, value in pairs))


# Proven necessary by `test_solve_time_and_comparison_time_metrics_agree_on_a_real_fixture`:
# the same underlying rate/coverage arithmetic run through solve-time's
# `engine/governed_adapter.py` facts versus comparison-time's freshly
# re-normalized projection facts produces values that differ at the ~1e-9
# relative level (float summation-order noise, not a real disagreement) --
# e.g. 15929.70961666407 vs 15929.709616664071 for the same fixture. Both
# tolerances sit ~1000x above that observed noise floor and ~1000x below the
# 2-decimal-place precision the frontend actually renders, so a real drift
# large enough to change a displayed number still raises.
_FLOAT_REL_TOL = 1e-9
_FLOAT_ABS_TOL = 1e-9


def _floats_close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_FLOAT_REL_TOL, abs_tol=_FLOAT_ABS_TOL)


def _value_lists_close(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return len(left) == len(right) and all(
        _floats_close(a, b) for a, b in zip(left, right)
    )


def _named_pairs_close(
    left: tuple[tuple[str, float], ...], right: tuple[tuple[str, float], ...]
) -> bool:
    left_map, right_map = dict(left), dict(right)
    return left_map.keys() == right_map.keys() and all(
        _floats_close(value, right_map[name]) for name, value in left_map.items()
    )


def _metrics_disagree(recomputed: Any, persisted: Any) -> bool:
    return (
        recomputed.assignment_count != persisted.assignment_count
        or recomputed.member_count != persisted.member_count
        or not _floats_close(recomputed.overtime_minutes, persisted.overtime_minutes)
        or not _floats_close(recomputed.total_cost, persisted.total_cost)
        or not _named_pairs_close(recomputed.objective_components, persisted.objective_components)
        or not _named_pairs_close(
            recomputed.function_coverage_required_minutes,
            persisted.function_coverage_required_minutes,
        )
        or not _named_pairs_close(
            recomputed.function_coverage_served_minutes,
            persisted.function_coverage_served_minutes,
        )
        or not _value_lists_close(
            _sorted_values(recomputed.interval_coverage_required_minutes),
            _sorted_values(persisted.interval_coverage_required_minutes),
        )
        or not _value_lists_close(
            _sorted_values(recomputed.interval_coverage_served_minutes),
            _sorted_values(persisted.interval_coverage_served_minutes),
        )
    )


def calculate_comparison(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    candidate: ScheduleVersionV1,
    scenario_id: UUID,
    scenario_version_id: UUID,
    site_id: UUID,
    expected_baseline_schedule_version: str | None,
    baseline_version: ScheduleVersionV1 | None = None,
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
    if expected_baseline_schedule_version is None and baseline_version is not None:
        raise ValueError(
            "baseline_version must not be provided when expected_baseline_schedule_version is None"
        )
    if expected_baseline_schedule_version is not None and baseline_version is None:
        raise BaselineSupplyUnavailableError(
            expected_baseline_schedule_version, overview.baseline_schedule_version
        )
    if baseline_version is not None and baseline_version.scenario_version_id != scenario_version_id:
        raise BaselineSupplyUnavailableError(
            expected_baseline_schedule_version if expected_baseline_schedule_version is not None
            else str(baseline_version.schedule_version_id),
            overview.baseline_schedule_version,
            "scenario_version_mismatch",
        )
    if baseline_version is not None and baseline_version.metrics is None:
        raise BaselineSupplyUnavailableError(
            expected_baseline_schedule_version if expected_baseline_schedule_version is not None
            else str(baseline_version.schedule_version_id),
            overview.baseline_schedule_version,
            "metrics_unavailable",
        )
    baseline = baseline_version.assignments if baseline_version is not None else ()
    facts = _facts(workers, tasks, demand, overview.horizon_minutes)

    recomputed_candidate, _ = calculate_candidate_metrics(
        candidate.assignments, tasks, demand, facts, constraints=()
    )
    # Candidate wage was captured only inside the solver snapshot and is not
    # readable through this projection. Preserve its immutable persisted cost,
    # while verifying every projection-recomputable field.
    recomputed_candidate = replace(recomputed_candidate, total_cost=candidate.metrics.total_cost)
    if _metrics_disagree(recomputed_candidate, candidate.metrics):
        raise ComparisonIntegrityError("persisted candidate metrics disagree with recomputation")

    baseline_metrics = None
    baseline_hard = ()
    if baseline_version is not None:
        baseline_metrics, _ = calculate_candidate_metrics(
            baseline, tasks, demand, facts, constraints=()
        )
        baseline_metrics = replace(
            baseline_metrics, total_cost=baseline_version.metrics.total_cost
        )
        baseline_hard = tuple(
            result
            for result in baseline_version.constraint_results
            if result.constraint_class == "hard"
        )

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
    ) if baseline_version is not None else None
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
            producing_run_version=expected_baseline_schedule_version,
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


__all__ = ["SCOPE_CONTROLS", "BaselineSupplyUnavailableError", "ComparisonIntegrityError", "calculate_comparison"]
