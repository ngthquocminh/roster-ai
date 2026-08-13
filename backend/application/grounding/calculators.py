"""Exact metric calculators over the normalized immutable scenario projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence, TypeVar
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import (
    ClaimArgumentsV1,
    GroundingUnitV1,
    MetricV1,
)
from application.contracts.scenario_projection import ScenarioOverviewV1
from application.grounding.evidence_groups import evidence_group_for_scenario_fact_group
from application.ports.scenario_projection import GroupQueryV1, ScenarioProjectionReader


class CalculationError(Exception):
    """Base for application-owned calculator failures."""


class CalculationArgumentsError(CalculationError):
    pass


class CalculationScenarioNotFoundError(CalculationError):
    pass


class CalculationVersionMismatchError(CalculationError):
    pass


class CalculationSiteMismatchError(CalculationError):
    pass


class CalculationLimitError(CalculationError):
    pass


@dataclass(frozen=True)
class CalculatedMetricV1:
    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID


def interval_overlap_minutes(
    left_start: int, left_end: int, right_start: int, right_end: int
) -> int:
    """Intersection length for two half-open minute intervals."""
    return max(0, min(left_end, right_end) - max(left_start, right_start))


def _overview(
    reader: ScenarioProjectionReader,
    connection: Any,
    scenario_id: UUID,
    scenario_version_id: UUID,
    site_id: UUID,
) -> ScenarioOverviewV1:
    overview = reader.get_overview(connection, scenario_id)
    if overview is None:
        raise CalculationScenarioNotFoundError(f"scenario {scenario_id} has no projection")
    if overview.scenario_version_id != scenario_version_id:
        raise CalculationVersionMismatchError(
            f"projection version {overview.scenario_version_id} does not match pinned {scenario_version_id}"
        )
    if overview.site_id != site_id:
        raise CalculationSiteMismatchError(
            f"projection site {overview.site_id} does not match trusted {site_id}"
        )
    return overview


PageItem = TypeVar("PageItem")


def _drain(
    getter: Callable[[Any, UUID, GroupQueryV1], object | None],
    connection: Any,
    scenario_id: UUID,
    *,
    scenario_version_id: UUID,
    site_id: UUID,
    page_size: int,
    max_rows: int,
) -> tuple[object, ...]:
    if page_size < 1 or max_rows < 1:
        raise CalculationArgumentsError("page_size and max_rows must be positive")
    cursor = 0
    items: list[object] = []
    matching_count: int | None = None
    seen_cursors: set[int] = set()
    while True:
        if cursor in seen_cursors:
            raise CalculationLimitError("projection cursor did not advance")
        seen_cursors.add(cursor)
        page = getter(
            connection,
            scenario_id,
            GroupQueryV1(cursor=cursor, limit=min(page_size, max_rows - len(items))),
        )
        if page is None:
            raise CalculationScenarioNotFoundError(
                f"scenario {scenario_id} has no projection"
            )
        if page.scenario_version_id != scenario_version_id:
            raise CalculationVersionMismatchError(
                f"page version {page.scenario_version_id} does not match pinned {scenario_version_id}"
            )
        if page.site_id != site_id:
            raise CalculationSiteMismatchError(
                f"page site {page.site_id} does not match trusted {site_id}"
            )
        if matching_count is None:
            matching_count = page.matching_count
            if matching_count > max_rows:
                raise CalculationLimitError(
                    f"calculation requires {matching_count} rows; bound is {max_rows}"
                )
        elif page.matching_count != matching_count:
            raise CalculationError("matching_count changed while paging immutable projection")
        items.extend(page.items)
        if len(items) > max_rows:
            raise CalculationLimitError(f"calculation exceeded row bound {max_rows}")
        if page.next_cursor is None:
            if len(items) != matching_count:
                raise CalculationLimitError(
                    f"projection ended after {len(items)} of {matching_count} matching rows"
                )
            return tuple(items)
        if page.next_cursor <= cursor:
            raise CalculationLimitError("projection cursor did not advance")
        cursor = page.next_cursor


def _evidence(
    overview: ScenarioOverviewV1,
    group: str,
    record_id: str,
    *,
    field: str,
    start_minute: int | None = None,
    end_minute: int | None = None,
) -> EvidenceRefV1:
    evidence_group = evidence_group_for_scenario_fact_group(group)  # type: ignore[arg-type]
    if evidence_group is None:
        raise CalculationError("overview cannot be emitted as row evidence")
    return EvidenceRefV1(
        scenario_version_id=overview.scenario_version_id,
        checksum_algorithm=overview.checksum_algorithm,
        checksum_schema_version=overview.checksum_schema_version,
        checksum_digest=overview.checksum_digest,
        producing_run_version=None,
        baseline_schedule_version=overview.baseline_schedule_version,
        group=evidence_group,
        record_id=record_id,
        field=field,
        start_minute=start_minute,
        end_minute=end_minute,
    )


def _window(arguments: ClaimArgumentsV1) -> tuple[int, int]:
    if arguments.start_minute is None or arguments.end_minute is None:
        raise CalculationArgumentsError("metric requires start_minute and end_minute")
    if arguments.start_minute < 0 or arguments.end_minute <= arguments.start_minute:
        raise CalculationArgumentsError("metric window must be a non-empty half-open interval")
    return arguments.start_minute, arguments.end_minute


def _require_task(arguments: ClaimArgumentsV1) -> str:
    if not arguments.task_id:
        raise CalculationArgumentsError("metric requires task_id")
    return arguments.task_id


def calculate_metric(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    scenario_id: UUID,
    scenario_version_id: UUID,
    site_id: UUID,
    metric: MetricV1,
    arguments: ClaimArgumentsV1,
    page_size: int = 50,
    max_rows: int = 10_000,
) -> CalculatedMetricV1:
    """Produce one value and locators from every normalized row it consumes."""
    overview = _overview(reader, connection, scenario_id, scenario_version_id, site_id)
    task_id = _require_task(arguments)

    if metric == "qualified_worker_count":
        workers = _drain(
            reader.get_workers, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
        )
        matched = tuple(
            worker for worker in workers
            if any(item.task_id == task_id for item in worker.qualifications)
        )
        refs = tuple(
            _evidence(overview, "workers", worker.record_id, field="qualifications")
            for worker in matched
        )
        return CalculatedMetricV1(metric, arguments, len(matched), "workers", refs, scenario_version_id)

    window_start, window_end = _window(arguments)
    demand_rows: Sequence[object] = ()
    assignment_rows: Sequence[object] = ()
    if metric in ("required_demand_minutes", "shortfall_minutes"):
        demand_rows = _drain(
            reader.get_demand, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
        )
    if metric in ("staffed_minutes", "shortfall_minutes"):
        assignment_rows = _drain(
            reader.get_baseline_assignments, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
        )

    matched_demand = tuple(
        row for row in demand_rows
        if row.task_id == task_id
        and (arguments.family is None or row.family == arguments.family)
        and interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
    )
    required = sum(
        interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
        * row.amount
        for row in matched_demand
    )
    matched_assignments = tuple(
        row for row in assignment_rows
        if row.task_id == task_id
        and interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
    )
    staffed = sum(
        interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
        for row in matched_assignments
    )
    demand_refs = tuple(
        _evidence(
            overview, "demand", row.record_id, field="amount",
            start_minute=row.start_minute, end_minute=row.end_minute,
        )
        for row in matched_demand
    )
    assignment_refs = tuple(
        _evidence(
            overview, "assignments", row.record_id, field="task_id",
            start_minute=row.start_minute, end_minute=row.end_minute,
        )
        for row in matched_assignments
    )
    if metric == "required_demand_minutes":
        value, refs = required, demand_refs
    elif metric == "staffed_minutes":
        value, refs = staffed, assignment_refs
    elif metric == "shortfall_minutes":
        value, refs = max(0, required - staffed), demand_refs + assignment_refs
    else:
        raise CalculationArgumentsError(f"unsupported metric: {metric}")
    return CalculatedMetricV1(metric, arguments, value, "minutes", refs, scenario_version_id)


__all__ = [
    "CalculatedMetricV1", "CalculationArgumentsError", "CalculationError",
    "CalculationLimitError", "CalculationScenarioNotFoundError",
    "CalculationSiteMismatchError", "CalculationVersionMismatchError",
    "calculate_metric", "interval_overlap_minutes",
]
