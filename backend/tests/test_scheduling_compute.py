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


class ProjectionStub:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, int]] = []
        self.demand = (
            DemandIntervalV1("d1", "outbound", "pick", None, 0, 30, 2, "headcount"),
            DemandIntervalV1("d2", "outbound", "pick", None, 30, 60, 1, "headcount"),
            DemandIntervalV1("d3", "inbound", "pick", None, 0, 60, 9, "headcount"),
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
        page_items = items[query.cursor : query.cursor + query.limit]
        next_cursor = query.cursor + len(page_items)
        if next_cursor >= len(items):
            next_cursor = None
        return page_type(
            scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
            items=page_items, next_cursor=next_cursor, total_count=len(items),
            matching_count=len(items),
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
        site_id=SITE, metric="required_demand_minutes",
        arguments=ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60
        ),
        page_size=1, max_rows=10,
    )

    assert result.value == 90
    assert result.unit == "minutes"
    assert [ref.record_id for ref in result.evidence_refs] == ["d1", "d2"]
    assert all(ref.baseline_schedule_version == "baseline-v1" for ref in result.evidence_refs)
    assert [query[1] for query in reader.queries] == [0, 1, 2]


def test_page_bound_raises_instead_of_returning_a_truncated_total() -> None:
    with pytest.raises(CalculationLimitError):
        calculate_metric(
            ProjectionStub(), object(), scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE,
            metric="required_demand_minutes",
            arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
            page_size=1, max_rows=2,
        )


@pytest.mark.parametrize(
    ("metric", "expected", "unit"),
    [("staffed_minutes", 50, "minutes"),
     ("shortfall_minutes", 40, "minutes"),
     ("qualified_worker_count", 2, "workers")],
)
def test_remaining_closed_metrics(metric, expected, unit) -> None:
    result = calculate_metric(
        ProjectionStub(), object(), scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric=metric,
        arguments=ClaimArgumentsV1(
            task_id="pick", family="outbound", start_minute=0, end_minute=60
        ),
        page_size=2, max_rows=10,
    )
    assert (result.value, result.unit) == (expected, unit)


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
