from __future__ import annotations

from uuid import uuid4

from pydantic import TypeAdapter

from application.contracts.comparison import AssignmentDiffV1, ComparisonV1
from application.contracts.schedule_version import ConstraintResultV1, MetricSetV1


def test_comparison_v1_round_trips_every_required_concept() -> None:
    candidate_id = uuid4()
    run_id = uuid4()
    scenario_id = uuid4()
    scenario_version_id = uuid4()
    metrics = MetricSetV1(
        interval_coverage_required_minutes=(("demand-1", 60.0),),
        interval_coverage_served_minutes=(("demand-1", 45.0),),
        overtime_minutes=10.0,
        total_cost=125.0,
        objective_components=(("unmet_minutes", 15.0),),
        assignment_count=1,
        member_count=1,
    )
    hard = ConstraintResultV1(
        constraint_id="hard:qualification",
        constraint_type="qualification",
        satisfied=True,
        unit="assignments",
    )
    comparison = ComparisonV1(
        candidate_schedule_version_id=candidate_id,
        candidate_schedule_run_id=run_id,
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        expected_baseline_schedule_version="baseline-v1",
        current_baseline_schedule_version="baseline-v2",
        stale=True,
        assignment_diff=AssignmentDiffV1(
            added_worker_ids=("worker-1",),
            removed_worker_ids=("worker-2",),
            added_shift_ids=("shift-1",),
            removed_shift_ids=("shift-2",),
            added_task_ids=("task-1",),
            removed_task_ids=("task-2",),
        ),
        candidate_metrics=metrics,
        baseline_metrics=MetricSetV1(),
        candidate_constraint_results=(hard,),
        baseline_hard_constraint_results=(hard,),
        warnings=("warning",),
        unresolved_gap_record_ids=("demand-1",),
        evidence_refs=(),
    )

    payload = TypeAdapter(ComparisonV1).dump_python(comparison, mode="json")
    restored = TypeAdapter(ComparisonV1).validate_python(payload)

    assert restored == comparison
    assert restored.schema_version == "1"
    assert restored.assignment_diff.schema_version == "1"
    assert restored.stale is True
    assert restored.candidate_metrics.total_cost == 125.0
    assert restored.unresolved_gap_record_ids == ("demand-1",)
