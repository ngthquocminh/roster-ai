"""The calculators, driven against the projection the product actually ships.

Every other calculator test drives a 3-6 row stub. That is why two defects
survived Phase A and the first code review: a 200-row bound that breached on the
first real question, and a volume/headcount unit mix that produced a
dimensionally wrong number. Both are invisible at stub scale and obvious here.

This suite is deliberately about SHAPE OF THE REAL DATA, not about arithmetic --
the exact-value assertions live in `test_scheduling_compute.py` where the inputs
are hand-authored and readable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from application.contracts.scenario_projection import (
    AssignmentV1,
    DemandIntervalV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    WorkerV1,
)
from application.contracts.grounding import ClaimArgumentsV1
from application.grounding.calculators import (
    CalculationDimensionError,
    CalculationLimitError,
    calculate_metric,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    DemandIntervalPageV1,
    GroupQueryKeysV1,
    WorkerPageV1,
)
from settings import default_settings

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "data" / "contract" / "sample_tiny_input.projection-v1.json"
)
IDENTITY = UUID(int=1)

_FILTERS = {
    "demand": {
        "family": lambda row, value: row.family == value,
        "task_id": lambda row, value: row.task_id == value,
    },
    "assignments": {"task_id": lambda row, value: row.task_id == value},
    "workers": {
        "qualified_task_id": lambda row, value: any(
            qualification.task_id == value for qualification in row.qualifications
        )
    },
}


def _load():
    groups = json.loads(FIXTURE.read_text(encoding="utf-8"))["groups"]
    demand = tuple(DemandIntervalV1(**row) for row in groups["demand"])
    assignments = tuple(AssignmentV1(**row) for row in groups["baseline-assignments"])
    workers = tuple(
        WorkerV1(
            **{
                **row,
                "qualifications": tuple(
                    QualificationRefV1(**qualification)
                    for qualification in row["qualifications"]
                ),
                "availability_windows": tuple(row["availability_windows"]),
            }
        )
        for row in groups["workers"]
    )
    return demand, assignments, workers


class ShippedProjectionReader:
    """Pages and filters exactly where the real adapter does."""

    def __init__(self) -> None:
        self.demand, self.assignments, self.workers = _load()

    def get_query_keys(self, group):
        return GroupQueryKeysV1(group, (), ())

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            scenario_id=IDENTITY, scenario_version_id=IDENTITY, site_id=IDENTITY,
            fixture_id="sample_tiny_input", scenario_name="sample",
            fixture_version="v1", checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1", checksum_digest="b" * 64,
            horizon_start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            site_timezone="UTC", horizon_minutes=10080,
            baseline_schedule_version="baseline-v1",
            projection_generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            work_area_count=1, task_count=6, worker_count=len(self.workers),
            demand_interval_count=len(self.demand),
            baseline_assignment_count=len(self.assignments),
            lock_count=0, constraint_count=0,
        )

    def _page(self, group, rows, query, page_type):
        table = _FILTERS[group]
        filtered = tuple(
            row for row in rows
            if all(table[name](row, value) for name, value in query.filters)
        )
        items = filtered[query.cursor : query.cursor + query.limit]
        next_cursor = query.cursor + len(items)
        return page_type(
            scenario_id=IDENTITY, scenario_version_id=IDENTITY, site_id=IDENTITY,
            items=items,
            next_cursor=None if next_cursor >= len(filtered) else next_cursor,
            total_count=len(rows), matching_count=len(filtered),
        )

    def get_demand(self, connection, scenario_id, query):
        return self._page("demand", self.demand, query, DemandIntervalPageV1)

    def get_baseline_assignments(self, connection, scenario_id, query):
        return self._page("assignments", self.assignments, query, AssignmentPageV1)

    def get_workers(self, connection, scenario_id, query):
        return self._page("workers", self.workers, query, WorkerPageV1)


def _calculate(reader, metric, arguments, max_rows=None):
    settings = default_settings()
    return calculate_metric(
        reader, object(), scenario_id=IDENTITY, scenario_version_id=IDENTITY,
        site_id=IDENTITY, metric=metric, arguments=arguments, page_size=50,
        max_rows=settings.scheduling_compute_row_limit if max_rows is None else max_rows,
    )


@pytest.fixture(scope="module")
def reader() -> ShippedProjectionReader:
    return ShippedProjectionReader()


def test_the_shipped_fixture_still_has_the_shape_these_assertions_assume(reader) -> None:
    """Pin the measurement the decisions were taken on.

    If the fixture is ever regenerated with a different mix, the decisions about
    unit handling and the row bound need revisiting -- so this fails loudly
    rather than letting the suite below quietly stop testing anything.
    """
    by_unit_family = {}
    for row in reader.demand:
        by_unit_family[(row.unit, row.family)] = by_unit_family.get((row.unit, row.family), 0) + 1
    assert by_unit_family == {
        ("volume", "outbound"): 493,
        ("volume", "inbound"): 1048,
        ("headcount", "indirect"): 6,
    }
    assert reader.assignments == (), "no baseline assignments ship in this fixture"


def test_the_flagship_outbound_question_is_answerable_with_real_locators(reader) -> None:
    """AC1 on shipped data: a real number, from real rows, with real evidence.

    Outbound demand is volume, so `required_demand_volume` is the metric that
    answers it -- and it must produce a positive value carrying one locator per
    row consumed, under the configured bound.
    """
    task_id = next(row.task_id for row in reader.demand if row.family == "outbound")
    result = _calculate(
        reader, "required_demand_volume",
        ClaimArgumentsV1(
            task_id=task_id, family="outbound", start_minute=2880, end_minute=4320
        ),
    )
    assert result.value > 0
    assert result.unit == "units"
    assert result.evidence_refs
    assert len(result.evidence_refs) == result.consumed_row_count
    assert all(ref.scenario_version_id == IDENTITY for ref in result.evidence_refs)
    assert all(ref.group == "demand" for ref in result.evidence_refs)


def test_asking_outbound_for_headcount_minutes_fails_closed_on_real_data(reader) -> None:
    """The D1 defect, on the data that exhibits it.

    Before the dimension guard this returned `value=0, evidence_refs=()`, which
    the gate reported as a SUPPORTED zero -- the planner was told outbound demand
    was zero, with no locator and nothing marking it as unanswerable.
    """
    task_id = next(row.task_id for row in reader.demand if row.family == "outbound")
    with pytest.raises(CalculationDimensionError):
        _calculate(
            reader, "required_headcount_minutes",
            ClaimArgumentsV1(
                task_id=task_id, family="outbound", start_minute=2880, end_minute=4320
            ),
        )


def test_indirect_demand_answers_headcount_minutes_on_real_data(reader) -> None:
    """The other side of the split: headcount demand yields minutes, with refs."""
    task_id = next(row.task_id for row in reader.demand if row.family == "indirect")
    result = _calculate(
        reader, "required_headcount_minutes",
        ClaimArgumentsV1(
            task_id=task_id, family="indirect", start_minute=0, end_minute=10080
        ),
    )
    assert result.unit == "minutes"
    assert result.value > 0
    assert len(result.evidence_refs) == result.consumed_row_count > 0


def test_task_pushdown_keeps_a_real_week_inside_the_configured_row_bound(reader) -> None:
    """The D1 bound, measured rather than assumed.

    `scheduling_compute_row_limit` is sized for demand (400) instead of
    borrowing `scheduling_inspect_row_limit` (200), and `task_id` is pushed into
    the query so the bound is tested against the filtered subset. The largest
    single task in this fixture is what makes that necessary.
    """
    counts: dict[str, int] = {}
    for row in reader.demand:
        counts[row.task_id] = counts.get(row.task_id, 0) + 1
    largest = max(counts.values())
    assert 200 < largest <= default_settings().scheduling_compute_row_limit, (
        f"largest task has {largest} rows: breaches the old 200 bound, fits the new one"
    )


def test_the_row_bound_still_fails_closed_when_it_is_genuinely_exceeded(reader) -> None:
    """Non-vacuity for the bound: shrink it and the same call must fail."""
    task_id = max(
        {row.task_id for row in reader.demand},
        key=lambda task: sum(1 for row in reader.demand if row.task_id == task),
    )
    with pytest.raises(CalculationLimitError):
        _calculate(
            reader, "required_demand_volume",
            ClaimArgumentsV1(task_id=task_id, start_minute=0, end_minute=10080),
            max_rows=10,
        )
