"""Versioned read-only normalized scenario projection endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection

from api.deps import get_projection_reader, get_site_context
from api.schemas import (
    AssignmentOut,
    AssignmentPageOut,
    AvailabilityWindowOut,
    ConstraintPageOut,
    ConstraintProjectionOut,
    DemandIntervalOut,
    DemandIntervalPageOut,
    LockOut,
    LockPageOut,
    ProblemDetailsV1,
    QualificationRefOut,
    ScenarioOverviewOut,
    TaskPageOut,
    TaskProjectionOut,
    WorkerPageOut,
    WorkerProjectionOut,
)
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    ConstraintV1,
    DemandIntervalV1,
    LockV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    TaskV1,
    WorkerV1,
)
from application.ports.scenario_projection import ScenarioProjectionReader


router = APIRouter(prefix="/scenarios", tags=["scenario projection"])
_PROBLEM_RESPONSES = {
    401: {"model": ProblemDetailsV1},
    404: {"model": ProblemDetailsV1},
    422: {"model": ProblemDetailsV1},
}


def _overview_out(value: ScenarioOverviewV1) -> ScenarioOverviewOut:
    return ScenarioOverviewOut(
        scenario_id=value.scenario_id,
        scenario_version_id=value.scenario_version_id,
        site_id=value.site_id,
        fixture_id=value.fixture_id,
        scenario_name=value.scenario_name,
        fixture_version=value.fixture_version,
        checksum_algorithm=value.checksum_algorithm,
        checksum_schema_version=value.checksum_schema_version,
        checksum_digest=value.checksum_digest,
        horizon_start=value.horizon_start,
        site_timezone=value.site_timezone,
        horizon_minutes=value.horizon_minutes,
        baseline_schedule_version=value.baseline_schedule_version,
        projection_generated_at=value.projection_generated_at,
        work_area_count=value.work_area_count,
        task_count=value.task_count,
        worker_count=value.worker_count,
        demand_interval_count=value.demand_interval_count,
        baseline_assignment_count=value.baseline_assignment_count,
        lock_count=value.lock_count,
        constraint_count=value.constraint_count,
    )


def _task_out(value: TaskV1) -> TaskProjectionOut:
    return TaskProjectionOut(
        record_id=value.record_id,
        task_id=value.task_id,
        name=value.name,
        function=value.function,
        area_id=value.area_id,
        area_name=value.area_name,
        unit_type_id=value.unit_type_id,
    )


def _qualification_out(value: QualificationRefV1) -> QualificationRefOut:
    return QualificationRefOut(task_id=value.task_id, rate=value.rate)


def _window_out(value: AvailabilityWindowV1) -> AvailabilityWindowOut:
    return AvailabilityWindowOut(
        kind=value.kind,
        start_minute=value.start_minute,
        end_minute=value.end_minute,
    )


def _worker_out(value: WorkerV1) -> WorkerProjectionOut:
    return WorkerProjectionOut(
        record_id=value.record_id,
        contact_id=value.contact_id,
        name=value.name,
        employment_type=value.employment_type,
        grade=value.grade,
        eba=value.eba,
        contracted_hours=value.contracted_hours,
        qualifications=[_qualification_out(item) for item in value.qualifications],
        availability_windows=[
            _window_out(item) for item in value.availability_windows
        ],
    )


def _demand_out(value: DemandIntervalV1) -> DemandIntervalOut:
    return DemandIntervalOut(
        record_id=value.record_id,
        family=value.family,
        task_id=value.task_id,
        area_id=value.area_id,
        start_minute=value.start_minute,
        end_minute=value.end_minute,
        amount=value.amount,
        unit=value.unit,
    )


def _assignment_out(value: AssignmentV1) -> AssignmentOut:
    return AssignmentOut(
        record_id=value.record_id,
        worker_id=value.worker_id,
        task_id=value.task_id,
        shift_id=value.shift_id,
        start_minute=value.start_minute,
        end_minute=value.end_minute,
    )


def _lock_out(value: LockV1) -> LockOut:
    return LockOut(
        record_id=value.record_id,
        target_type=value.target_type,
        target_ref=value.target_ref,
        scope=value.scope,
        source=value.source,
    )


def _constraint_out(value: ConstraintV1) -> ConstraintProjectionOut:
    return ConstraintProjectionOut(
        record_id=value.record_id,
        constraint_type=value.constraint_type,
        value=value.value,
        value_type=value.value_type,
    )


@router.get(
    "/{scenario_id}/projection",
    response_model=ScenarioOverviewOut,
    responses=_PROBLEM_RESPONSES,
)
def get_projection(
    scenario_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> ScenarioOverviewOut:
    value = reader.get_overview(connection, scenario_id)
    if value is None:
        raise HTTPException(status_code=404)
    return _overview_out(value)


@router.get(
    "/{scenario_id}/projection/work-areas-and-tasks",
    response_model=TaskPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_tasks(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> TaskPageOut:
    page = reader.get_tasks(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return TaskPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="work-areas-and-tasks",
        items=[_task_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )


@router.get(
    "/{scenario_id}/projection/workers",
    response_model=WorkerPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_workers(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> WorkerPageOut:
    page = reader.get_workers(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return WorkerPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="workers",
        items=[_worker_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )


@router.get(
    "/{scenario_id}/projection/demand",
    response_model=DemandIntervalPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_demand(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> DemandIntervalPageOut:
    page = reader.get_demand(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return DemandIntervalPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="demand",
        items=[_demand_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )


@router.get(
    "/{scenario_id}/projection/baseline-assignments",
    response_model=AssignmentPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_baseline_assignments(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> AssignmentPageOut:
    page = reader.get_baseline_assignments(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return AssignmentPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="baseline-assignments",
        items=[_assignment_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )


@router.get(
    "/{scenario_id}/projection/locks",
    response_model=LockPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_locks(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> LockPageOut:
    page = reader.get_locks(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return LockPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="locks",
        items=[_lock_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )


@router.get(
    "/{scenario_id}/projection/constraints-and-objectives",
    response_model=ConstraintPageOut,
    responses=_PROBLEM_RESPONSES,
)
def get_constraints(
    scenario_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> ConstraintPageOut:
    page = reader.get_constraints(connection, scenario_id, cursor, limit)
    if page is None:
        raise HTTPException(status_code=404)
    return ConstraintPageOut(
        scenario_id=page.scenario_id,
        scenario_version_id=page.scenario_version_id,
        site_id=page.site_id,
        group="constraints-and-objectives",
        items=[_constraint_out(item) for item in page.items],
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        matching_count=page.matching_count,
    )
