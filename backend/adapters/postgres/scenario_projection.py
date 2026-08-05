"""PostgreSQL adapter for the normalized scenario projection."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Numeric, and_, cast, func, nulls_last, select

from adapters.postgres.schema import scenario, scenario_version
from application.contracts.scenario_projection import (
    AvailabilityWindowV1,
    ConstraintV1,
    DemandIntervalV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    TaskV1,
    WorkerV1,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    ConstraintPageV1,
    DemandIntervalPageV1,
    LockPageV1,
    TaskPageV1,
    WorkerPageV1,
)
from domain.types import DemandFamily, WindowKind
from ingest.scenario_time import parse_dt, parse_time_of_day


SITE_TIMEZONE = "Australia/Sydney"
_SITE_ZONE = ZoneInfo(SITE_TIMEZONE)
T = TypeVar("T")

# Keep this expression identical to scenario_catalogue.py's governed latest
# version ordering so the catalogue and projection cannot resolve differently.
_VERSION_ORDINAL = cast(
    func.nullif(
        func.regexp_replace(scenario_version.c.version, r"\D", "", "g"),
        "",
    ),
    Numeric,
)


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    return value if isinstance(value, list) else []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_utc(value: str) -> datetime:
    return parse_dt(value).replace(tzinfo=_SITE_ZONE).astimezone(timezone.utc)


def _minute_offset(horizon_start: datetime, value: str) -> int:
    return int((_as_utc(value) - horizon_start).total_seconds() / 60)


def _day_window_offsets(
    horizon_start: datetime,
    date_value: str,
    start_value: str,
    end_value: str,
) -> tuple[int, int]:
    day = parse_dt(date_value)
    start_hours = parse_time_of_day(start_value)
    end_hours = parse_time_of_day(end_value)
    start = day + timedelta(hours=start_hours)
    end = day + timedelta(
        hours=end_hours + (24.0 if end_hours <= start_hours else 0.0)
    )
    return (
        _minute_offset(horizon_start, start.isoformat()),
        _minute_offset(horizon_start, end.isoformat()),
    )


def _horizon(payload: dict[str, Any]) -> tuple[datetime, int]:
    ranges = _rows(payload, "Scenario Range")
    if not ranges:
        raise ValueError("Scenario Range must contain one row")
    row = ranges[0]
    start = _as_utc(row["PeriodStartDate"])
    end = _as_utc(row["PeriodEndDate"])
    return start, int((end - start).total_seconds() / 60)


def _task_ids(payload: dict[str, Any]) -> set[str]:
    return {
        str(row["TaskID"])
        for row in _rows(payload, "Task")
        if row.get("TaskID")
    }


def _normalize_tasks(payload: dict[str, Any]) -> tuple[TaskV1, ...]:
    area_names = {
        row.get("AreaID"): str(row.get("Name", ""))
        for row in _rows(payload, "Area")
        if row.get("AreaID")
    }
    function_names = {
        row.get("FunctionID"): str(row.get("Name", "Unknown"))
        for row in _rows(payload, "Function")
        if row.get("FunctionID")
    }
    seen: set[str] = set()
    normalized: list[TaskV1] = []
    for row in _rows(payload, "Task"):
        task_id = row.get("TaskID")
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        area_id = str(row.get("AreaID", ""))
        normalized.append(
            TaskV1(
                record_id=str(task_id),
                task_id=str(task_id),
                name=str(row.get("Task", "")),
                function=function_names.get(
                    row.get("FunctionID"), "Unknown"
                ),
                area_id=area_id,
                area_name=area_names.get(row.get("AreaID"), "Unknown"),
                unit_type_id=(
                    str(row["UnitTypeID"])
                    if row.get("UnitTypeID") is not None
                    else None
                ),
            )
        )
    return tuple(normalized)


def _normalize_workers(
    payload: dict[str, Any], horizon_start: datetime
) -> tuple[WorkerV1, ...]:
    valid_task_ids = _task_ids(payload)
    qualifications: dict[str, list[QualificationRefV1]] = defaultdict(list)
    for row in _rows(payload, "Team Member Qualification and Performance"):
        task_id = row.get("TaskID")
        contact_id = row.get("ContactID")
        if task_id not in valid_task_ids or not contact_id:
            continue
        override = row.get("TeamMemberTaskRateOverride")
        rate = _to_float(
            override if override is not None else row.get("DefaultTaskRate")
        )
        if rate <= 0:
            continue
        qualifications[str(contact_id)].append(
            QualificationRefV1(task_id=str(task_id), rate=rate)
        )

    windows: dict[str, list[AvailabilityWindowV1]] = defaultdict(list)
    for table, kind in (
        ("Roster Profile", WindowKind.ROSTER),
        ("Availability", WindowKind.AVAILABILITY),
    ):
        for row in _rows(payload, table):
            contact_id = row.get("ContactID")
            if not contact_id:
                continue
            try:
                start = _minute_offset(horizon_start, row["StartDateTime"])
                end = _minute_offset(horizon_start, row["EndDateTime"])
            except (KeyError, TypeError, ValueError):
                continue
            windows[str(contact_id)].append(
                AvailabilityWindowV1(
                    kind=kind.value,
                    start_minute=start,
                    end_minute=end,
                )
            )

    seen: set[str] = set()
    normalized: list[WorkerV1] = []
    for row in _rows(payload, "Team Member"):
        contact_id = row.get("ContactID")
        if not contact_id or contact_id in seen:
            continue
        seen.add(contact_id)
        normalized.append(
            WorkerV1(
                record_id=str(contact_id),
                contact_id=str(contact_id),
                name=str(row.get("Team Member", "Unknown")),
                employment_type=str(row.get("EmploymentType", "Unknown")),
                grade=str(row.get("Grade", "")),
                eba=str(row.get("EBA", "")),
                contracted_hours=_to_float(row.get("ContractedHours"), 38.0),
                qualifications=tuple(qualifications.get(str(contact_id), ())),
                availability_windows=tuple(windows.get(str(contact_id), ())),
            )
        )
    return tuple(normalized)


def _normalize_demand(
    payload: dict[str, Any], horizon_start: datetime
) -> tuple[DemandIntervalV1, ...]:
    valid_task_ids = _task_ids(payload)
    normalized: list[DemandIntervalV1] = []
    for index, row in enumerate(_rows(payload, "Outbound Workload")):
        task_id = row.get("TaskID")
        if task_id not in valid_task_ids:
            continue
        try:
            start = _minute_offset(horizon_start, row["StartDateTime"])
            end = _minute_offset(horizon_start, row["EndDateTime"])
        except (KeyError, TypeError, ValueError):
            continue
        normalized.append(
            DemandIntervalV1(
                record_id=f"outbound:{index}",
                family=DemandFamily.OUTBOUND.value,
                task_id=str(task_id),
                area_id=(str(row["AreaID"]) if row.get("AreaID") else None),
                start_minute=start,
                end_minute=end,
                amount=_to_float(row.get("Volume")),
                unit="volume",
            )
        )

    for index, row in enumerate(_rows(payload, "Inbound Workload")):
        try:
            start = _minute_offset(horizon_start, row["WindowStartDateTime"])
            end = _minute_offset(horizon_start, row["WindowEndDateTime"])
        except (KeyError, TypeError, ValueError):
            continue
        tasks = row.get("Tasks", [])
        if not isinstance(tasks, list):
            continue
        for task_index, task in enumerate(tasks):
            task_id = task.get("TaskID")
            if task_id not in valid_task_ids:
                continue
            normalized.append(
                DemandIntervalV1(
                    record_id=f"inbound:{index}:{task_index}",
                    family=DemandFamily.INBOUND.value,
                    task_id=str(task_id),
                    area_id=(
                        str(row["AreaID"]) if row.get("AreaID") else None
                    ),
                    start_minute=start,
                    end_minute=end,
                    amount=_to_float(task.get("Volume")),
                    unit="volume",
                )
            )

    for index, row in enumerate(
        _rows(payload, "Indirect Workforce Requirement")
    ):
        task_id = row.get("TaskID")
        if task_id not in valid_task_ids:
            continue
        try:
            start, end = _day_window_offsets(
                horizon_start,
                row["Date"],
                row["WindowStartDateTime"],
                row["WindowEndDateTime"],
            )
        except (KeyError, TypeError, ValueError):
            continue
        normalized.append(
            DemandIntervalV1(
                record_id=f"indirect:{index}",
                family=DemandFamily.INDIRECT.value,
                task_id=str(task_id),
                area_id=(str(row["AreaID"]) if row.get("AreaID") else None),
                start_minute=start,
                end_minute=end,
                amount=_to_float(row.get("RequiredHeadcount")),
                unit="headcount",
            )
        )
    return tuple(normalized)


def _normalize_constraints(
    payload: dict[str, Any],
) -> tuple[ConstraintV1, ...]:
    return tuple(
        ConstraintV1(
            record_id=f"constraint:{index}",
            constraint_type=str(row.get("ConstraintType", "")),
            value=str(row.get("Value", "")),
            value_type=(
                str(row["ValueType"])
                if row.get("ValueType") is not None
                else None
            ),
        )
        for index, row in enumerate(_rows(payload, "Shift Constraint"))
    )


def _slice_window(
    items: Sequence[T], cursor: int, limit: int
) -> tuple[tuple[T, ...], int | None, int]:
    page = tuple(items[cursor : cursor + limit])
    total = len(items)
    end = cursor + len(page)
    return page, (end if end < total else None), total


class PostgresScenarioProjectionReader:
    """Read one immutable payload through an already site-scoped connection."""

    @staticmethod
    def _scenario_version_join():
        return scenario.join(
            scenario_version,
            and_(
                scenario.c.id == scenario_version.c.scenario_id,
                scenario.c.site_id == scenario_version.c.site_id,
            ),
        )

    def _projection_row(self, connection: Connection, scenario_id: UUID):
        return connection.execute(
            select(
                scenario.c.id.label("scenario_id"),
                scenario.c.site_id,
                scenario.c.fixture_id,
                scenario.c.name.label("scenario_name"),
                scenario_version.c.id.label("scenario_version_id"),
                scenario_version.c.version.label("fixture_version"),
                scenario_version.c.payload,
                scenario_version.c.checksum_algorithm,
                scenario_version.c.checksum_schema_version,
                scenario_version.c.checksum_digest,
            )
            .select_from(self._scenario_version_join())
            .where(scenario.c.id == scenario_id)
            .order_by(
                nulls_last(_VERSION_ORDINAL.desc()),
                scenario_version.c.version.desc(),
                scenario_version.c.id.desc(),
            )
            .limit(1)
        ).one_or_none()

    def get_overview(
        self, connection: Connection, scenario_id: UUID
    ) -> ScenarioOverviewV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        payload = row.payload
        horizon_start, horizon_minutes = _horizon(payload)
        tasks = _normalize_tasks(payload)
        workers = _normalize_workers(payload, horizon_start)
        demand = _normalize_demand(payload, horizon_start)
        constraints = _normalize_constraints(payload)
        work_areas = {
            area.get("AreaID")
            for area in _rows(payload, "Area")
            if area.get("AreaID")
        }
        return ScenarioOverviewV1(
            scenario_id=row.scenario_id,
            scenario_version_id=row.scenario_version_id,
            site_id=row.site_id,
            fixture_id=row.fixture_id,
            scenario_name=row.scenario_name,
            fixture_version=row.fixture_version,
            checksum_algorithm=row.checksum_algorithm,
            checksum_schema_version=row.checksum_schema_version,
            checksum_digest=row.checksum_digest,
            horizon_start=horizon_start,
            site_timezone=SITE_TIMEZONE,
            horizon_minutes=horizon_minutes,
            baseline_schedule_version=None,
            projection_generated_at=datetime.now(timezone.utc),
            work_area_count=len(work_areas),
            task_count=len(tasks),
            worker_count=len(workers),
            demand_interval_count=len(demand),
            baseline_assignment_count=0,
            lock_count=0,
            constraint_count=len(constraints),
        )

    def get_tasks(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> TaskPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        items, next_cursor, total = _slice_window(
            _normalize_tasks(row.payload), cursor, limit
        )
        return TaskPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            items,
            next_cursor,
            total,
            total,
        )

    def get_workers(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> WorkerPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        horizon_start, _ = _horizon(row.payload)
        items, next_cursor, total = _slice_window(
            _normalize_workers(row.payload, horizon_start), cursor, limit
        )
        return WorkerPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            items,
            next_cursor,
            total,
            total,
        )

    def get_demand(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> DemandIntervalPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        horizon_start, _ = _horizon(row.payload)
        items, next_cursor, total = _slice_window(
            _normalize_demand(row.payload, horizon_start), cursor, limit
        )
        return DemandIntervalPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            items,
            next_cursor,
            total,
            total,
        )

    def get_baseline_assignments(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> AssignmentPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        return AssignmentPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            (),
            None,
            0,
            0,
        )

    def get_locks(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> LockPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        return LockPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            (),
            None,
            0,
            0,
        )

    def get_constraints(
        self, connection: Connection, scenario_id: UUID, cursor: int, limit: int
    ) -> ConstraintPageV1 | None:
        row = self._projection_row(connection, scenario_id)
        if row is None:
            return None
        items, next_cursor, total = _slice_window(
            _normalize_constraints(row.payload), cursor, limit
        )
        return ConstraintPageV1(
            row.scenario_id,
            row.scenario_version_id,
            row.site_id,
            items,
            next_cursor,
            total,
            total,
        )
