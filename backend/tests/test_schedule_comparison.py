from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from application.contracts.schedule_version import (
    MetricSetV1,
    ScheduleVersionV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    DemandIntervalV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    TaskV1,
    WorkerV1,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    DemandIntervalPageV1,
    TaskPageV1,
    WorkerPageV1,
)
from application.scheduling.comparison import ComparisonIntegrityError, calculate_comparison


class _Reader:
    def __init__(self, *, baseline=(), current_baseline="baseline-v1", demand_count=1):
        self.scenario_id = uuid4()
        self.version_id = uuid4()
        self.site_id = uuid4()
        self.baseline = baseline
        self.current_baseline = current_baseline
        self.tasks = (TaskV1("task-1", "task-1", "Pick", "Picking", "area", "Area", None),)
        self.workers = (
            WorkerV1(
                "worker-1", "worker-1", "A", "FT", "1", "eba", 40,
                (QualificationRefV1("task-1", 60.0),), (),
            ),
        )
        self.demand = tuple(
            DemandIntervalV1(f"demand-{index}", "outbound", "task-1", "area", index, index + 1, 1, "volume")
            for index in range(demand_count)
        )

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            self.scenario_id, self.version_id, self.site_id, "fixture", "Scenario", "v1",
            "sha256", "rfc8785-v1", "a" * 64,
            datetime(2026, 8, 24, tzinfo=timezone.utc), "UTC", 10_080,
            self.current_baseline, datetime(2026, 8, 24, tzinfo=timezone.utc),
            1, len(self.tasks), len(self.workers), len(self.demand), len(self.baseline), 0, 0,
        )

    def _page(self, rows, query, page_type):
        items = rows[query.cursor:query.cursor + query.limit]
        end = query.cursor + len(items)
        return page_type(
            self.scenario_id, self.version_id, self.site_id, items,
            end if end < len(rows) else None, len(rows), len(rows),
        )

    def get_tasks(self, _connection, _scenario_id, query):
        return self._page(self.tasks, query, TaskPageV1)

    def get_workers(self, _connection, _scenario_id, query):
        return self._page(self.workers, query, WorkerPageV1)

    def get_demand(self, _connection, _scenario_id, query):
        return self._page(self.demand, query, DemandIntervalPageV1)

    def get_baseline_assignments(self, _connection, _scenario_id, query):
        return self._page(self.baseline, query, AssignmentPageV1)


def _candidate(reader: _Reader) -> ScheduleVersionV1:
    assignment = AssignmentV1("candidate-a", "worker-1", "task-1", "shift-1", 0, 1)
    required = tuple((row.record_id, 1.0) for row in reader.demand)
    served = tuple((row.record_id, 1.0 if row.record_id == "demand-0" else 0.0) for row in reader.demand)
    return ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=uuid4(), scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL", assignments=(assignment,),
        metrics=MetricSetV1(
            interval_coverage_required_minutes=required,
            interval_coverage_served_minutes=served,
            function_coverage_required_minutes=(("Picking", float(len(reader.demand))),),
            function_coverage_served_minutes=(("Picking", 1.0),),
            objective_components=(("unmet_minutes", float(max(0, len(reader.demand) - 1))), ("overtime_minutes", 0.0)),
            assignment_count=1, member_count=1,
        ),
    )


def test_empty_baseline_is_real_net_new_comparison_and_detects_staleness() -> None:
    reader = _Reader(current_baseline="baseline-v2")
    result = calculate_comparison(
        reader, object(), candidate=_candidate(reader), scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )

    assert result.stale is True
    assert result.assignment_diff.added_worker_ids == ("worker-1",)
    assert result.baseline_metrics.assignment_count == 0
    assert result.candidate_metrics.objective_components
    assert result.unresolved_gap_record_ids == ()


def test_seeded_baseline_exercises_removed_and_added_diffs() -> None:
    baseline = (AssignmentV1("baseline-a", "worker-2", "task-2", "shift-2", 0, 1),)
    reader = _Reader(baseline=baseline)
    reader.workers += (
        WorkerV1("worker-2", "worker-2", "B", "FT", "1", "eba", 40, (QualificationRefV1("task-2", 60.0),), ()),
    )
    reader.tasks += (TaskV1("task-2", "task-2", "Pack", "Packing", "area", "Area", None),)

    result = calculate_comparison(
        reader, object(), candidate=_candidate(reader), scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )

    assert result.assignment_diff.removed_worker_ids == ("worker-2",)
    assert result.assignment_diff.added_task_ids == ("task-1",)
    assert result.baseline_metrics.assignment_count == 1


def test_candidate_metric_drift_raises_and_large_drain_completes() -> None:
    reader = _Reader(demand_count=1547)
    candidate = _candidate(reader)
    candidate = replace(candidate, metrics=replace(candidate.metrics, assignment_count=999))

    with pytest.raises(ComparisonIntegrityError, match="metrics"):
        calculate_comparison(
            reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
            scenario_version_id=reader.version_id, site_id=reader.site_id,
            expected_baseline_schedule_version="baseline-v1",
        )
