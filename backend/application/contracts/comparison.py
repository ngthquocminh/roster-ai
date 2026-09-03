"""Immutable candidate-to-baseline comparison contracts (AD-11, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import ConstraintResultV1, MetricSetV1

SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class AssignmentDiffV1:
    added_worker_ids: tuple[str, ...] = ()
    removed_worker_ids: tuple[str, ...] = ()
    added_shift_ids: tuple[str, ...] = ()
    removed_shift_ids: tuple[str, ...] = ()
    added_task_ids: tuple[str, ...] = ()
    removed_task_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ComparisonV1:
    candidate_schedule_version_id: UUID
    candidate_schedule_run_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    expected_baseline_schedule_version: str | None
    current_baseline_schedule_version: str | None
    stale: bool
    assignment_diff: AssignmentDiffV1 | None
    candidate_metrics: MetricSetV1
    baseline_metrics: MetricSetV1 | None
    candidate_constraint_results: tuple[ConstraintResultV1, ...]
    baseline_hard_constraint_results: tuple[ConstraintResultV1, ...]
    warnings: tuple[str, ...]
    unresolved_gap_record_ids: tuple[str, ...]
    evidence_refs: tuple[EvidenceRefV1, ...]
    schema_version: str = SCHEMA_VERSION


__all__ = ["SCHEMA_VERSION", "AssignmentDiffV1", "ComparisonV1"]
