from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from adapters.postgres.scenario_projection import (
    _horizon,
    _normalize_demand,
    _normalize_tasks,
    _normalize_workers,
)
from application.contracts.canonical import contract_digest
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
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
from application.scheduling.candidate_metrics import calculate_candidate_metrics
from application.scheduling.comparison import ComparisonIntegrityError, calculate_comparison
from engine.governed_adapter import GovernedSchedulerAdapter


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


def test_candidate_metric_drift_raises_integrity_error() -> None:
    reader = _Reader()
    candidate = _candidate(reader)
    candidate = replace(candidate, metrics=replace(candidate.metrics, assignment_count=999))

    with pytest.raises(ComparisonIntegrityError, match="metrics"):
        calculate_comparison(
            reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
            scenario_version_id=reader.version_id, site_id=reader.site_id,
            expected_baseline_schedule_version="baseline-v1",
        )


def test_large_drain_completes_without_raising() -> None:
    """Independent from the drift test: a full-bound drain must succeed on its
    own merits, not merely happen to raise for the right reason before the
    drain itself could be proven complete."""
    reader = _Reader(demand_count=1547)

    result = calculate_comparison(
        reader, object(), candidate=_candidate(reader), scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )

    assert result.candidate_metrics.assignment_count == 1
    assert len(result.candidate_metrics.interval_coverage_required_minutes) == 1547


def test_interval_coverage_tuples_are_real_values_not_a_not_computed_placeholder() -> None:
    """Trap 6: a scenario with real demand must never render coverage as absent."""
    reader = _Reader()

    result = calculate_comparison(
        reader, object(), candidate=_candidate(reader), scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )

    assert result.candidate_metrics.interval_coverage_required_minutes
    assert result.candidate_metrics.interval_coverage_served_minutes
    assert result.baseline_metrics.interval_coverage_required_minutes
    assert result.baseline_metrics.interval_coverage_served_minutes


def test_assignment_diff_flips_from_red_to_green_on_a_baseline_mutation() -> None:
    """Trap 3 guard: the diff mechanism must actually react to a real change,
    not just render plausible-looking static output."""
    baseline = (AssignmentV1("baseline-a", "worker-2", "task-2", "shift-2", 0, 1),)
    reader = _Reader(baseline=baseline)
    reader.workers += (
        WorkerV1("worker-2", "worker-2", "B", "FT", "1", "eba", 40, (QualificationRefV1("task-2", 60.0),), ()),
    )
    reader.tasks += (TaskV1("task-2", "task-2", "Pack", "Packing", "area", "Area", None),)
    candidate = _candidate(reader)

    before = calculate_comparison(
        reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )
    assert before.assignment_diff.added_worker_ids == ("worker-1",)

    reader.baseline = reader.baseline + (AssignmentV1("baseline-b", "worker-1", "task-1", "shift-1", 0, 1),)
    after = calculate_comparison(
        reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )
    assert after.assignment_diff.added_worker_ids == ()


def test_second_fetch_reports_stale_but_still_describes_the_original_inputs() -> None:
    """Trap 5 guard: a baseline move between two fetches must surface as
    `stale`, never as a silently-rebased comparison wearing the same shape."""
    reader = _Reader(current_baseline="baseline-v1")
    candidate = _candidate(reader)

    first = calculate_comparison(
        reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )
    assert first.stale is False

    reader.current_baseline = "baseline-v2"
    second = calculate_comparison(
        reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )

    assert second.stale is True
    assert second.candidate_metrics == first.candidate_metrics
    assert second.baseline_metrics == first.baseline_metrics


class _PayloadSource:
    def __init__(self, payload) -> None:
        self.payload = payload

    def load(self, _scenario_version_id, _expected_digest):
        return self.payload


class _RealFixtureReader:
    """Wraps REAL `_normalize_*` output (not hand-typed fixture data) so the
    comparison recompute runs against the actual Postgres projection
    normalization path, not a stand-in."""

    def __init__(self, *, tasks, workers, demand, horizon_minutes) -> None:
        self.scenario_id = uuid4()
        self.version_id = uuid4()
        self.site_id = uuid4()
        self.tasks = tasks
        self.workers = workers
        self.demand = demand
        self.baseline = ()
        self.horizon_minutes = horizon_minutes

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            self.scenario_id, self.version_id, self.site_id, "fixture", "Scenario", "v1",
            "sha256", "rfc8785-v1", "a" * 64,
            datetime(2026, 8, 24, tzinfo=timezone.utc), "UTC", self.horizon_minutes,
            "baseline-v1", datetime(2026, 8, 24, tzinfo=timezone.utc),
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


def test_solve_time_and_comparison_time_metrics_agree_on_a_real_fixture() -> None:
    """D2 guard: `finalize_schedule_run` persists metrics computed from
    `outcome.validation_facts` -- built by `engine/governed_adapter.py` from
    `ingest/input_adapter.py`'s domain model, the solve-time path.
    `calculate_comparison` recomputes metrics from
    `adapters/postgres/scenario_projection.py`'s independent JSON normalizer,
    the comparison-time path. Nothing else in this suite runs both real code
    paths against the same fixture; every other test hand-crafts a fixture
    reader whose IDs are made to match by construction, which cannot catch
    real drift between the two normalizers (this is exactly what surfaced the
    demand `record_id` namespace mismatch fixed in `_sorted_values`).
    """
    payload = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "sample_tiny_input.json")
        .read_text(encoding="utf-8")
    )
    digest = contract_digest(payload)[2]
    snapshot = RunSnapshotV1(
        snapshot_id=uuid4(), schedule_run_id=uuid4(), scenario_id=uuid4(),
        scenario_version_id=uuid4(), checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1", checksum_digest=digest,
        proposal_id=uuid4(), proposal_version_id=uuid4(), proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(
            engine_name="cpsat", seed=42, num_search_workers=1,
            max_deterministic_time=1.0, wall_time_limit_seconds=30.0,
        ),
        component_versions=(("application", "1"), ("contract", "1"), ("ortools", "9.11.4210")),
        accepted_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )

    outcome = GovernedSchedulerAdapter(_PayloadSource(payload)).solve(snapshot)
    assert outcome.assignments, "fixture must produce a real, non-empty solve to be a meaningful proof"

    solve_metrics, _ = calculate_candidate_metrics(
        outcome.assignments,
        outcome.validation_facts.tasks,
        outcome.validation_facts.demand_intervals,
        outcome.validation_facts,
        constraints=(),
    )
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=snapshot.schedule_run_id,
        scenario_id=uuid4(), scenario_version_id=uuid4(),
        proposal_id=snapshot.proposal_id, proposal_version_id=snapshot.proposal_version_id,
        feasible_solver_status=outcome.solver_status, assignments=outcome.assignments,
        metrics=solve_metrics,
    )

    horizon_start, horizon_minutes = _horizon(payload)
    reader = _RealFixtureReader(
        tasks=_normalize_tasks(payload),
        workers=_normalize_workers(payload, horizon_start),
        demand=_normalize_demand(payload, horizon_start),
        horizon_minutes=horizon_minutes,
    )
    candidate = replace(
        candidate, scenario_id=reader.scenario_id, scenario_version_id=reader.version_id,
    )

    # Must not raise ComparisonIntegrityError: the whole point of this test.
    result = calculate_comparison(
        reader, object(), candidate=candidate, scenario_id=reader.scenario_id,
        scenario_version_id=reader.version_id, site_id=reader.site_id,
        expected_baseline_schedule_version="baseline-v1",
    )
    assert result.candidate_metrics.assignment_count == solve_metrics.assignment_count
