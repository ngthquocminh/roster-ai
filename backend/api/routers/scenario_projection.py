"""Versioned read-only normalized scenario projection endpoints."""
from __future__ import annotations

from typing import Any, Callable, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection
from starlette.responses import JSONResponse

from api.deps import get_projection_reader, get_site_context
from api.problems import problem_response
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
from application.contracts.evidence_ref import (
    AssignmentResolutionV1,
    ConstraintResolutionV1,
    DemandIntervalResolutionV1,
    LockResolutionV1,
    TaskResolutionV1,
    WorkerResolutionV1,
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

_ResolutionV1 = (
    TaskResolutionV1
    | WorkerResolutionV1
    | DemandIntervalResolutionV1
    | AssignmentResolutionV1
    | LockResolutionV1
    | ConstraintResolutionV1
)
_MappedT = TypeVar("_MappedT")


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


def _resolve_or_problem(
    resolution: _ResolutionV1 | None,
    mapper: Callable[[Any], _MappedT],
) -> _MappedT | JSONResponse:
    """Map a resolve-endpoint outcome to its response, or a distinct 404 problem."""
    if resolution is None:
        raise HTTPException(status_code=404)
    if resolution.outcome == "not_found":
        return problem_response(
            status=404,
            code="evidence_not_found",
            title="Evidence not found",
            detail="The cited evidence record was not found.",
        )
    if resolution.outcome == "version_mismatch":
        return problem_response(
            status=404,
            code="evidence_version_mismatch",
            title="Evidence version mismatch",
            detail=(
                "The cited scenario version does not match the current "
                f"scenario version {resolution.current_scenario_version_id}."
            ),
        )
    if resolution.item is None:
        raise HTTPException(status_code=500)
    return mapper(resolution.item)


@router.get(
    "/{scenario_id}/projection/work-areas-and-tasks/{record_id}",
    response_model=TaskProjectionOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_task(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> TaskProjectionOut | JSONResponse:
    resolution = reader.resolve_task(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _task_out)


@router.get(
    "/{scenario_id}/projection/workers/{record_id}",
    response_model=WorkerProjectionOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_worker(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> WorkerProjectionOut | JSONResponse:
    resolution = reader.resolve_worker(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _worker_out)


@router.get(
    "/{scenario_id}/projection/demand/{record_id}",
    response_model=DemandIntervalOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_demand_interval(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> DemandIntervalOut | JSONResponse:
    resolution = reader.resolve_demand_interval(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _demand_out)


@router.get(
    "/{scenario_id}/projection/baseline-assignments/{record_id}",
    response_model=AssignmentOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_assignment(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> AssignmentOut | JSONResponse:
    resolution = reader.resolve_assignment(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _assignment_out)


@router.get(
    "/{scenario_id}/projection/locks/{record_id}",
    response_model=LockOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_lock(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> LockOut | JSONResponse:
    resolution = reader.resolve_lock(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _lock_out)


@router.get(
    "/{scenario_id}/projection/constraints-and-objectives/{record_id}",
    response_model=ConstraintProjectionOut,
    responses=_PROBLEM_RESPONSES,
)
def resolve_constraint(
    scenario_id: UUID,
    record_id: str,
    scenario_version_id: UUID,
    connection: Connection = Depends(get_site_context),
    reader: ScenarioProjectionReader = Depends(get_projection_reader),
) -> ConstraintProjectionOut | JSONResponse:
    resolution = reader.resolve_constraint(
        connection, scenario_id, scenario_version_id, record_id
    )
    return _resolve_or_problem(resolution, _constraint_out)
