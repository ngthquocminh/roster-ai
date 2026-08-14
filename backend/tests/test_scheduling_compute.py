from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.installed import installed_modules
from application.capabilities.scheduling_compute import (
    SCHEDULING_COMPUTE_POLICY,
    SchedulingComputeRequestV1,
    derive_result_id,
    scheduling_compute,
    scheduling_compute_manifest,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.grounding import ClaimArgumentsV1
from application.contracts.scenario_projection import (
    AssignmentV1,
    DemandIntervalV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    WorkerV1,
)
from application.grounding.calculators import (
    CalculationArgumentsError,
    CalculationLimitError,
    calculate_metric,
    interval_overlap_minutes,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    DemandIntervalPageV1,
    GroupQueryKeysV1,
    WorkerPageV1,
)

SITE = UUID("00000000-0000-0000-0000-000000000001")
SCENARIO = UUID("00000000-0000-0000-0000-000000000002")
VERSION = UUID("00000000-0000-0000-0000-000000000003")


# Mirrors the adapter's GROUP_QUERY_TABLES so the stub filters exactly where
# the real reader does. Without this the stub would ignore `filters`, report
# `matching_count` for the whole group, and the pushdown the row bound depends
# on would be untested in the only place it is exercised.
_FILTERS = {
    "demand": {
        "family": lambda item, value: item.family == value,
        "task_id": lambda item, value: item.task_id == value,
    },
    "assignments": {"task_id": lambda item, value: item.task_id == value},
    "workers": {
        "qualified_task_id": lambda item, value: any(
            qualification.task_id == value for qualification in item.qualifications
        )
    },
}


class ProjectionStub:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, int]] = []
        self.filters: list[tuple[str, tuple]] = []
        self.demand = (
            DemandIntervalV1("d1", "outbound", "pick", None, 0, 30, 2, "headcount"),
            DemandIntervalV1("d2", "outbound", "pick", None, 30, 60, 1, "headcount"),
            DemandIntervalV1("d3", "inbound", "pick", None, 0, 60, 9, "headcount"),
            # Volume is the realistic majority: 1541 of 1547 demand rows in
            # `sample_tiny_input` carry unit "volume". A stub that only emitted
            # "headcount" is why multiplying volume into minutes stayed green.
            DemandIntervalV1("d4", "outbound", "pick", None, 0, 60, 100, "volume"),
        )
        self.assignments = (
            AssignmentV1("a1", "w1", "pick", "s1", 0, 20),
            AssignmentV1("a2", "w2", "pick", "s2", 20, 50),
            AssignmentV1("a3", "w3", "pack", "s3", 0, 60),
        )
        self.workers = (
            WorkerV1("w1", "w1", "A", "FT", "1", "x", 38, (QualificationRefV1("pick", 1),), ()),
            WorkerV1("w2", "w2", "B", "FT", "1", "x", 38, (), ()),
            WorkerV1("w3", "w3", "C", "FT", "1", "x", 38, (QualificationRefV1("pick", .5),), ()),
        )

    def get_query_keys(self, group):
        return GroupQueryKeysV1(group, (), ())

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
            fixture_id="fixture", scenario_name="scenario", fixture_version="v1",
            checksum_algorithm="sha256", checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            horizon_start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            site_timezone="UTC", horizon_minutes=10080,
            baseline_schedule_version="baseline-v1",
            projection_generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            work_area_count=1, task_count=2, worker_count=len(self.workers),
            demand_interval_count=len(self.demand),
            baseline_assignment_count=len(self.assignments), lock_count=0,
            constraint_count=0,
        )

    def _page(self, group, items, query, page_type):
        self.queries.append((group, query.cursor, query.limit))
        self.filters.append((group, tuple(query.filters)))
        table = _FILTERS[group]
        filtered = tuple(
            item
            for item in items
            if all(table[name](item, value) for name, value in query.filters)
        )
        page_items = filtered[query.cursor : query.cursor + query.limit]
        next_cursor = query.cursor + len(page_items)
        if next_cursor >= len(filtered):
            next_cursor = None
        return page_type(
            scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
            items=page_items, next_cursor=next_cursor, total_count=len(items),
            matching_count=len(filtered),
        )

    def get_demand(self, connection, scenario_id, query):
        return self._page("demand", self.demand, query, DemandIntervalPageV1)

    def get_baseline_assignments(self, connection, scenario_id, query):
        return self._page("assignments", self.assignments, query, AssignmentPageV1)

    def get_workers(self, connection, scenario_id, query):
        return self._page("workers", self.workers, query, WorkerPageV1)


def _deps(reader: ProjectionStub) -> AgentDepsV1:
    ids = [UUID(int=value) for value in range(10, 18)]
    return AgentDepsV1(
        actor_id=ids[0], site_id=SITE, membership_id=ids[1], request_id=ids[2],
        agent_run_id=ids[3], conversation_id=ids[4], scenario_id=SCENARIO,
        scenario_version_id=VERSION, policy_version="v1",
        clock=lambda: datetime(2026, 8, 13, tzinfo=timezone.utc),
        projection_reader=reader, connection=object(),
        remaining_budget=AgentBudgetV1(tool_calls_limit=2),
    )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [((0, 30), (30, 60), 0), ((0, 60), (10, 20), 10),
     ((10, 40), (0, 20), 10), ((10, 40), (30, 50), 10)],
)
def test_half_open_interval_overlap_boundaries(left, right, expected) -> None:
    assert interval_overlap_minutes(*left, *right) == expected


def test_calculators_page_to_exhaustion_and_emit_only_consumed_records() -> None:
    reader = ProjectionStub()
    result = calculate_metric(
        reader, object(), scenario_id=SCENARIO, scenario_version_id=VERSION,
        site_id=SITE, metric="required_headcount_minutes",
        arguments=ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60
        ),
        page_size=1, max_rows=10,
    )

    assert result.value == 90
    assert result.unit == "minutes"
    assert [ref.record_id for ref in result.evidence_refs] == ["d1", "d2"]
    assert all(ref.baseline_schedule_version == "baseline-v1" for ref in result.evidence_refs)
    # d4 is outbound/pick too, so it survives pushdown and is paged; only the
    # unit filter excludes it from the value. Three rows -> three pages at
    # page_size=1.
    assert [query[1] for query in reader.queries] == [0, 1, 2]
    assert result.consumed_row_count == 2


def test_task_and_family_are_pushed_into_the_query_but_the_window_is_not() -> None:
    """The bound is tested against `matching_count`, which the adapter measures
    on the FILTERED set -- so pushdown is what keeps a real week under it.
    The window stays client-side: the adapter can only express containment.
    """
    reader = ProjectionStub()
    calculate_metric(
        reader, object(), scenario_id=SCENARIO, scenario_version_id=VERSION,
        site_id=SITE, metric="required_headcount_minutes",
        arguments=ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60
        ),
        page_size=50, max_rows=10,
    )
    demand_filters = dict(
        next(filters for group, filters in reader.filters if group == "demand")
    )
    assert demand_filters == {"task_id": "pick", "family": "outbound"}
    assert "start_minute_gte" not in demand_filters
    assert "end_minute_lte" not in demand_filters


def test_page_bound_raises_instead_of_returning_a_truncated_total() -> None:
    with pytest.raises(CalculationLimitError):
        calculate_metric(
            ProjectionStub(), object(), scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE,
            metric="required_headcount_minutes",
            arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
            page_size=1, max_rows=2,
        )


def test_volume_demand_is_never_multiplied_into_minutes() -> None:
    """`overlap x amount` on a volume row is minutes x cartons wearing a
    "minutes" label -- trap #1 reached through units. The two dimensions are
    separate metrics and neither borrows the other's rows.
    """
    common = dict(
        scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
        page_size=50, max_rows=10,
    )
    arguments = ClaimArgumentsV1(
        task_id="pick", family="outbound", start_minute=0, end_minute=60
    )
    minutes = calculate_metric(
        ProjectionStub(), object(), metric="required_headcount_minutes",
        arguments=arguments, **common,
    )
    volume = calculate_metric(
        ProjectionStub(), object(), metric="required_demand_volume",
        arguments=arguments, **common,
    )

    assert (minutes.value, minutes.unit) == (90, "minutes")
    assert [ref.record_id for ref in minutes.evidence_refs] == ["d1", "d2"]
    assert (volume.value, volume.unit) == (100, "units")
    assert [ref.record_id for ref in volume.evidence_refs] == ["d4"]


def test_volume_is_pro_rated_across_the_rows_own_interval() -> None:
    volume = calculate_metric(
        ProjectionStub(), object(), scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric="required_demand_volume",
        arguments=ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=30
        ),
        page_size=50, max_rows=10,
    )
    assert volume.value == 50  # d4 is 100 units over [0, 60); half the window


@pytest.mark.parametrize(
    ("metric", "expected", "unit"),
    [("staffed_minutes", 50, "minutes"),
     ("shortfall_minutes", 580, "minutes")],
)
def test_assignment_reading_metrics_are_family_agnostic(metric, expected, unit) -> None:
    result = calculate_metric(
        ProjectionStub(), object(), scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric=metric,
        arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
        page_size=2, max_rows=10,
    )
    assert (result.value, result.unit) == (expected, unit)


def test_qualified_worker_count_is_horizon_wide() -> None:
    result = calculate_metric(
        ProjectionStub(), object(), scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric="qualified_worker_count",
        arguments=ClaimArgumentsV1(task_id="pick"),
        page_size=2, max_rows=10,
    )
    assert (result.value, result.unit) == (2, "workers")
    assert result.consumed_row_count == 2


@pytest.mark.parametrize(
    ("metric", "arguments"),
    [
        # family exists only on demand rows; honouring it on a metric that
        # reads assignments subtracts all-family staffing from single-family
        # demand and reports the difference as an exact, cited shortfall.
        ("staffed_minutes", ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60)),
        ("shortfall_minutes", ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60)),
        ("qualified_worker_count", ClaimArgumentsV1(task_id="pick", family="outbound")),
        # a window the calculation cannot honour would still be hashed into
        # result_id, letting the gate verify arguments the value never obeyed.
        ("qualified_worker_count", ClaimArgumentsV1(
            task_id="pick", start_minute=0, end_minute=60)),
    ],
)
def test_arguments_the_metric_cannot_honour_are_refused(metric, arguments) -> None:
    with pytest.raises(CalculationArgumentsError):
        calculate_metric(
            ProjectionStub(), object(), scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE, metric=metric,
            arguments=arguments, page_size=2, max_rows=10,
        )


def test_an_empty_match_set_is_a_proven_zero_not_a_silent_one() -> None:
    """Zero is the one value whose evidence is not a set of records, so the
    gate needs `consumed_row_count` to tell it from a calculator that used rows
    and cited none.
    """
    result = calculate_metric(
        ProjectionStub(), object(), scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric="staffed_minutes",
        arguments=ClaimArgumentsV1(task_id="nobody", start_minute=0, end_minute=60),
        page_size=2, max_rows=10,
    )
    assert (result.value, result.evidence_refs, result.consumed_row_count) == (0, (), 0)


def test_a_reader_that_advances_forever_over_empty_pages_is_bounded() -> None:
    """`seen_cursors` catches repeats and `next_cursor <= cursor` catches
    non-advance; neither bounds a keyset cursor that advances over empty pages,
    and the capability timeout is only checked after this returns.
    """

    class NeverEndingReader(ProjectionStub):
        def get_baseline_assignments(self, connection, scenario_id, query):
            return AssignmentPageV1(
                scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
                items=(), next_cursor=query.cursor + 1, total_count=1,
                matching_count=1,
            )

    with pytest.raises(CalculationLimitError, match="did not terminate"):
        calculate_metric(
            NeverEndingReader(), object(), scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE, metric="staffed_minutes",
            arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
            page_size=2, max_rows=10,
        )


def test_reaching_the_bound_with_a_live_cursor_names_the_bound() -> None:
    """At `len(items) == max_rows` with a next cursor, the old code requested
    `limit=0` and reported "cursor did not advance" -- naming the wrong cause.
    """

    class BoundedReader(ProjectionStub):
        def get_baseline_assignments(self, connection, scenario_id, query):
            return AssignmentPageV1(
                scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
                items=self.assignments[query.cursor : query.cursor + query.limit],
                next_cursor=query.cursor + query.limit, total_count=3,
                matching_count=2,
            )

    with pytest.raises(CalculationLimitError, match="row bound"):
        calculate_metric(
            BoundedReader(), object(), scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE, metric="staffed_minutes",
            arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
            page_size=1, max_rows=2,
        )


def test_result_id_is_canonical_stable_and_argument_sensitive() -> None:
    args = ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60)
    first = derive_result_id("staffed_minutes", args, VERSION)
    assert first == derive_result_id("staffed_minutes", args, VERSION)
    assert first != derive_result_id(
        "staffed_minutes",
        ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=61),
        VERSION,
    )
    assert first != derive_result_id("shortfall_minutes", args, VERSION)


def test_capability_delegates_and_is_installed_as_inspect() -> None:
    request = SchedulingComputeRequestV1(
        metric="staffed_minutes",
        arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
    )
    result = scheduling_compute(_deps(ProjectionStub()), request)
    assert result.result_id == derive_result_id(request.metric, request.arguments, VERSION)
    assert result.value == 50
    manifest = scheduling_compute_manifest()
    assert manifest.risk_class == "inspect"
    assert SCHEDULING_COMPUTE_POLICY == "scheduling_compute_enabled"
    assert "scheduling_compute" in {
        module.manifest.capability_name for module in installed_modules()
    }
