"""A tiny, real scenario projection for the deterministic evaluation harness.

Why this exists at all: the harness previously read an EMPTY projection, so a
grounded case could never produce a supported claim from a real calculation and
the driver fabricated the "trusted" capability result instead. That made all
four grounding cases self-fulfilling -- and it is why the row bound and the
volume-unit defects both survived Phase A. Real rows here are what let the
oracle fail.

Deliberately a handful of hand-authored rows rather than `sample_tiny_input`'s
1547: `expected_evidence_refs` is authored by hand into the case files, so the
fixture has to stay small enough that a human can read the expectation and see
whether it is right.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from application.contracts.evidence_ref import (
    AssignmentResolutionV1,
    DemandIntervalResolutionV1,
    WorkerResolutionV1,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    DemandIntervalV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    WorkerV1,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    DemandIntervalPageV1,
    GroupQueryKeysV1,
    WorkerPageV1,
)

FIXTURE_IDENTITY = UUID(int=1)
# Wednesday of the fixture week, as the golden cases phrase it.
WEDNESDAY_START = 2880
WEDNESDAY_END = 4320

DEMAND: tuple[DemandIntervalV1, ...] = (
    DemandIntervalV1("d-outbound-0", "outbound", "pick", None, 2880, 3600, 2, "headcount"),
    DemandIntervalV1("d-outbound-1", "outbound", "pick", None, 3600, 4320, 1, "headcount"),
    # Present so the metric has something to correctly EXCLUDE: a different
    # family, a different task, a volume row the minutes metric must not touch,
    # and a row outside Wednesday.
    DemandIntervalV1("d-inbound-0", "inbound", "pick", None, 2880, 3600, 5, "headcount"),
    DemandIntervalV1("d-outbound-pack", "outbound", "pack", None, 2880, 3600, 4, "headcount"),
    DemandIntervalV1("d-outbound-vol", "outbound", "pick", None, 2880, 3600, 120, "volume"),
    DemandIntervalV1("d-outbound-thu", "outbound", "pick", None, 4320, 5040, 9, "headcount"),
)
ASSIGNMENTS: tuple[AssignmentV1, ...] = (
    AssignmentV1("a-wed-0", "w1", "pick", "s1", 2880, 3240),
)
WORKERS: tuple[WorkerV1, ...] = (
    WorkerV1("w1", "w1", "A", "FT", "1", "eba", 38, (QualificationRefV1("pick", 1.0),), ()),
    WorkerV1("w2", "w2", "B", "FT", "1", "eba", 38, (), ()),
)

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
_KEYS = {
    "demand": (("start_minute",), ("family", "task_id")),
    "assignments": (("start_minute",), ("worker_id", "task_id")),
    "workers": (("contact_id",), ("contact_id", "qualified_task_id")),
    "locks": (("scope",), ("scope",)),
    "constraints": (("constraint_type",), ("constraint_type",)),
}


@dataclass(frozen=True)
class _EmptyPage:
    scenario_id: UUID = FIXTURE_IDENTITY
    scenario_version_id: UUID = FIXTURE_IDENTITY
    site_id: UUID = FIXTURE_IDENTITY
    items: tuple = ()
    next_cursor: int | None = None
    total_count: int = 0
    matching_count: int = 0


class FixtureProjectionReader:
    """Filters and pages exactly as the real adapter does, over a few rows."""

    def get_query_keys(self, group: str) -> GroupQueryKeysV1:
        sorts, filters = _KEYS.get(group, ((), ()))
        return GroupQueryKeysV1(group=group, sort_keys=sorts, filter_keys=filters)

    def get_overview(self, _connection: Any, _scenario_id: UUID) -> ScenarioOverviewV1:
        return ScenarioOverviewV1(
            scenario_id=FIXTURE_IDENTITY,
            scenario_version_id=FIXTURE_IDENTITY,
            site_id=FIXTURE_IDENTITY,
            fixture_id="eval-fixture",
            scenario_name="evaluation fixture",
            fixture_version="v1",
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="e" * 64,
            horizon_start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            site_timezone="UTC",
            horizon_minutes=10080,
            baseline_schedule_version="baseline-v1",
            projection_generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            work_area_count=1,
            task_count=2,
            worker_count=len(WORKERS),
            demand_interval_count=len(DEMAND),
            baseline_assignment_count=len(ASSIGNMENTS),
            lock_count=0,
            constraint_count=0,
        )

    def _page(self, group, rows, query, page_type):
        table = _FILTERS[group]
        filtered = tuple(
            row
            for row in rows
            if all(table[name](row, value) for name, value in query.filters)
        )
        items = filtered[query.cursor : query.cursor + query.limit]
        end = query.cursor + len(items)
        return page_type(
            scenario_id=FIXTURE_IDENTITY,
            scenario_version_id=FIXTURE_IDENTITY,
            site_id=FIXTURE_IDENTITY,
            items=items,
            next_cursor=end if end < len(filtered) else None,
            total_count=len(rows),
            matching_count=len(filtered),
        )

    def get_demand(self, _connection, _scenario_id, query):
        return self._page("demand", DEMAND, query, DemandIntervalPageV1)

    def get_baseline_assignments(self, _connection, _scenario_id, query):
        return self._page("assignments", ASSIGNMENTS, query, AssignmentPageV1)

    def get_workers(self, _connection, _scenario_id, query):
        return self._page("workers", WORKERS, query, WorkerPageV1)

    def get_locks(self, *_args):
        return _EmptyPage()

    def get_constraints(self, *_args):
        return _EmptyPage()

    def _resolve(self, rows, record_id, resolution_type, scenario_id):
        """Resolve ONLY records that exist. The previous stub echoed whatever it
        was asked for, which made the gate's exact-target check unfalsifiable.
        """
        item = next((row for row in rows if row.record_id == record_id), None)
        return resolution_type(
            outcome="resolved" if item is not None else "not_found",
            scenario_id=scenario_id,
            current_scenario_version_id=FIXTURE_IDENTITY,
            item=item,
        )

    def resolve_demand_interval(self, _connection, scenario_id, _version, record_id):
        return self._resolve(DEMAND, record_id, DemandIntervalResolutionV1, scenario_id)

    def resolve_assignment(self, _connection, scenario_id, _version, record_id):
        return self._resolve(ASSIGNMENTS, record_id, AssignmentResolutionV1, scenario_id)

    def resolve_worker(self, _connection, scenario_id, _version, record_id):
        return self._resolve(WORKERS, record_id, WorkerResolutionV1, scenario_id)


__all__ = [
    "ASSIGNMENTS", "DEMAND", "FIXTURE_IDENTITY", "WEDNESDAY_END", "WEDNESDAY_START",
    "WORKERS", "FixtureProjectionReader",
]
