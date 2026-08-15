"""Exact metric calculators over the normalized immutable scenario projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence
from uuid import UUID

from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import (
    FAMILY_AWARE_METRICS,
    ClaimArgumentsV1,
    GroundingUnitV1,
    MetricV1,
)
from application.contracts.scenario_projection import ScenarioOverviewV1
from application.grounding.evidence_groups import evidence_group_for_scenario_fact_group
from application.ports.scenario_projection import GroupQueryV1, ScenarioProjectionReader

# A projection page can legitimately be empty while still advancing its cursor
# (a keyset cursor over a filtered group). `seen_cursors` catches repeats and
# `next_cursor <= cursor` catches non-advance, but neither bounds a reader that
# advances forever over empty pages, and the capability's timeout is only
# checked AFTER `calculate_metric` returns. This is that missing bound.
MAX_PAGES = 512


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


class CalculationDimensionError(CalculationError):
    """Demand exists for this task and window, but not in the unit asked for.

    The planner's QUESTION is usually fine -- it is the metric that cannot
    express it, and the two impossible directions are not symmetric:

    * "required minutes" for `outbound`/`inbound` is unanswerable HERE because
      that demand is measured in `volume`, and volume -> minutes needs
      `QualificationRefV1.rate`, which is per worker per task. That makes it an
      assignment question and therefore Epic 3's. `required_demand_volume`
      answers the same question in units, today.
    * "how many units" for `indirect` work is meaningless in itself: indirect
      workforce requirement has no output quantity.

    Note what this error does NOT mean: asking about STAFFING on an
    outbound/inbound task is perfectly valid and is answered from assignments
    (`staffed_minutes`), which are family-agnostic. Never phrase this as "that
    question is invalid".
    """


def _dimension_message(metric: MetricV1, rows: Sequence[Any]) -> str:
    present = sorted({row.unit for row in rows})
    families = sorted({row.family for row in rows})
    if metric == "required_demand_volume":
        remedy = (
            "this demand is a workforce requirement, not an output quantity, so "
            "no volume exists for it; use required_headcount_minutes"
        )
    else:
        remedy = (
            "this demand is measured in volume, which cannot be converted to "
            "minutes without a per-worker rate (Epic 3); use "
            "required_demand_volume for the quantity, or staffed_minutes to ask "
            "about the people assigned to this task"
        )
    return (
        f"{metric} needs demand measured in "
        f"{'headcount' if metric != 'required_demand_volume' else 'volume'}, but "
        f"every matching row for this task and window is {'/'.join(present)} "
        f"(family {'/'.join(families)}): {remedy}"
    )


@dataclass(frozen=True)
class CalculatedMetricV1:
    """One computed value plus a locator for every row folded into it.

    `consumed_row_count` is the completeness proof the gate needs, and it is
    deliberately NOT the port's `matching_count`: that number is measured
    before the calculator's own window-overlap and unit filters, so a task with
    200 matching rows and none overlapping the requested window would look like
    a fault rather than a correct zero. The invariant that matters downstream
    is `len(evidence_refs) == consumed_row_count` -- a calculator that folded
    rows into a value without citing them is an application fault, while
    consuming nothing is a correct empty answer.
    """

    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID
    consumed_row_count: int = 0


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


def _drain(
    getter: Callable[[Any, UUID, GroupQueryV1], object | None],
    connection: Any,
    scenario_id: UUID,
    *,
    scenario_version_id: UUID,
    site_id: UUID,
    page_size: int,
    max_rows: int,
    filters: tuple[tuple[str, str | int], ...] = (),
) -> tuple[object, ...]:
    """Drain one fact group to exhaustion under an explicit bound.

    `filters` is pushed into the query rather than applied afterwards, because
    the adapter computes `matching_count` as the size of the FILTERED set
    (`adapters/postgres/scenario_projection.py`) -- the very number the bound
    below tests. Selecting in Python instead would compare the bound against
    the whole group and fail closed on data that easily fits.
    """
    if page_size < 1 or max_rows < 1:
        raise CalculationArgumentsError("page_size and max_rows must be positive")
    cursor = 0
    items: list[object] = []
    matching_count: int | None = None
    seen_cursors: set[int] = set()
    for _ in range(MAX_PAGES):
        if cursor in seen_cursors:
            raise CalculationLimitError("projection cursor did not advance")
        seen_cursors.add(cursor)
        remaining = max_rows - len(items)
        if remaining < 1:
            # Reached only when the group still reports a next cursor at the
            # bound. Requesting `limit=0` here would come back as an empty page
            # with a non-advancing cursor and surface as a misleading "cursor
            # did not advance"; name the bound that was actually hit instead.
            raise CalculationLimitError(f"calculation exceeded row bound {max_rows}")
        page = getter(
            connection,
            scenario_id,
            GroupQueryV1(
                cursor=cursor, limit=min(page_size, remaining), filters=filters
            ),
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
    raise CalculationLimitError(
        f"projection did not terminate within {MAX_PAGES} pages"
    )


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


def _check_family_is_meaningful(metric: MetricV1, arguments: ClaimArgumentsV1) -> None:
    """`family` is a demand-row property and exists on no other record.

    One task carries demand rows in several families, so family is not a
    function of `task_id`, and neither `AssignmentV1` nor `WorkerV1` records
    it. Honouring `family` on a metric that reads assignments would subtract
    all-family staffed minutes from single-family required minutes and present
    the difference as an exact, cited shortfall. Refusing the argument on every
    metric that cannot express it is the only sound resolution.
    """
    if arguments.family is not None and metric not in FAMILY_AWARE_METRICS:
        raise CalculationArgumentsError(
            f"{metric} does not read demand rows, which are the only records "
            "carrying family; it is per-task and family-agnostic"
        )


def _demand_filters(
    task_id: str, arguments: ClaimArgumentsV1
) -> tuple[tuple[str, str | int], ...]:
    """Push task and family down; NEVER the window.

    `DEMAND_FILTERS` offers `start_minute_gte`/`end_minute_lte`, which express
    CONTAINMENT, not overlap. Using them would silently drop rows that only
    partially overlap the window -- rows `interval_overlap_minutes` counts
    correctly -- turning a fail-closed bound error into a wrong number wearing
    a valid evidence locator. Expressing overlap needs `start_minute_lt` /
    `end_minute_gt` on the adapter; see `deferred-work.md`.
    """
    filters: list[tuple[str, str | int]] = [("task_id", task_id)]
    if arguments.family is not None:
        filters.append(("family", arguments.family))
    return tuple(filters)


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
    max_rows: int = 400,
) -> CalculatedMetricV1:
    """Produce one value and locators from every normalized row it consumes."""
    overview = _overview(reader, connection, scenario_id, scenario_version_id, site_id)
    task_id = _require_task(arguments)
    _check_family_is_meaningful(metric, arguments)

    if metric == "qualified_worker_count":
        if arguments.start_minute is not None or arguments.end_minute is not None:
            # The count is horizon-wide. Accepting a window here would hash it
            # into `result_id` and let the gate verify arguments the
            # calculation never honoured -- a whole-week count rendered as if
            # it were scoped to Wednesday.
            raise CalculationArgumentsError(
                "qualified_worker_count is horizon-wide and takes no window"
            )
        workers = _drain(
            reader.get_workers, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
            filters=(("qualified_task_id", task_id),),
        )
        matched = tuple(
            worker for worker in workers
            if any(item.task_id == task_id for item in worker.qualifications)
        )
        refs = tuple(
            _evidence(overview, "workers", worker.record_id, field="qualifications")
            for worker in matched
        )
        return CalculatedMetricV1(
            metric, arguments, len(matched), "workers", refs,
            scenario_version_id, consumed_row_count=len(matched),
        )

    window_start, window_end = _window(arguments)
    demand_rows: Sequence[object] = ()
    assignment_rows: Sequence[object] = ()
    reads_demand = metric in ("required_headcount_minutes", "required_demand_volume")
    reads_assignments = metric == "staffed_minutes"
    if reads_demand:
        demand_rows = _drain(
            reader.get_demand, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
            filters=_demand_filters(task_id, arguments),
        )
    if reads_assignments:
        assignment_rows = _drain(
            reader.get_baseline_assignments, connection, scenario_id,
            scenario_version_id=scenario_version_id, site_id=site_id,
            page_size=page_size, max_rows=max_rows,
            filters=(("task_id", task_id),),
        )

    # `unit` decides which metric a demand row can answer at all. A "volume"
    # row is a quantity of work (cartons), not a rate, and the only rate in the
    # projection is `QualificationRefV1.rate` -- per WORKER, per task. So
    # volume -> minutes depends on who performs the work, which is an
    # assignment and therefore Epic 3's solver question. The two dimensions are
    # reported separately rather than silently multiplied together.
    wanted_unit = "headcount" if metric != "required_demand_volume" else "volume"
    # Everything the window admits, BEFORE the unit narrows it. Keeping this set
    # is what lets the guard below tell "there is no demand here" (a truthful
    # zero) from "there is demand here and this metric cannot express it".
    # Deriving the count after the unit filter collapses the two, which is how a
    # dimension miss came to render as an evidence-free `supported` zero.
    window_demand = tuple(
        row for row in demand_rows
        if row.task_id == task_id
        and (arguments.family is None or row.family == arguments.family)
        and interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
    )
    matched_demand = tuple(row for row in window_demand if row.unit == wanted_unit)
    if reads_demand and window_demand and not matched_demand:
        raise CalculationDimensionError(_dimension_message(metric, window_demand))
    matched_assignments = tuple(
        row for row in assignment_rows
        if row.task_id == task_id
        and interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
    )
    # headcount is a RATE (persons held over the interval), so overlap x amount
    # is exact worker-minutes with no distributional assumption.
    required_minutes = sum(
        interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
        * row.amount
        for row in matched_demand
    )
    # volume is a QUANTITY over the interval, so restricting it to a window
    # assumes the volume is spread evenly across that interval. Declared in
    # SCOPE_CONTROLS rather than left implicit.
    required_volume = sum(
        row.amount
        * interval_overlap_minutes(row.start_minute, row.end_minute, window_start, window_end)
        / (row.end_minute - row.start_minute)
        for row in matched_demand
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
    # `consumed` counts the rows folded into the VALUE and is derived from the
    # matched row sets, NOT from `refs`. Deriving it from `refs` would make the
    # gate's `len(evidence_refs) == consumed_row_count` check true by
    # construction and unable to catch the fault it exists for: a calculator
    # that used rows and cited none.
    unit: GroundingUnitV1 = "minutes"
    if metric == "required_headcount_minutes":
        value, refs, consumed = required_minutes, demand_refs, len(matched_demand)
    elif metric == "required_demand_volume":
        value, refs, consumed = required_volume, demand_refs, len(matched_demand)
        unit = "units"
    elif metric == "staffed_minutes":
        value, refs, consumed = staffed, assignment_refs, len(matched_assignments)
    else:
        raise CalculationArgumentsError(f"unsupported metric: {metric}")
    return CalculatedMetricV1(
        metric, arguments, value, unit, refs, scenario_version_id, consumed
    )


__all__ = [
    "MAX_PAGES", "CalculatedMetricV1", "CalculationArgumentsError",
    "CalculationDimensionError", "CalculationError",
    "CalculationLimitError", "CalculationScenarioNotFoundError",
    "CalculationSiteMismatchError", "CalculationVersionMismatchError",
    "calculate_metric", "interval_overlap_minutes",
]
