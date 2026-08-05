from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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
from adapters.postgres.scenario_projection import (
    _horizon,
    _normalize_constraints,
    _normalize_demand,
    _normalize_tasks,
    _normalize_workers,
    _slice_window,
)
from api.auth_security import SESSION_COOKIE_NAME
from api.deps import get_identity_store, get_projection_reader, get_site_context
from api.main import app
from api.routers import scenario_projection
from api import schemas
from application.ports.scenario_projection import (
    AssignmentPageV1,
    ConstraintPageV1,
    DemandIntervalPageV1,
    LockPageV1,
    TaskPageV1,
    WorkerPageV1,
)
from application.ports.session import ResolvedSession


REPO_ROOT = Path(__file__).resolve().parents[2]
NFR35_EVIDENCE = (
    REPO_ROOT / "evidence" / "story-1.4" / "nfr35-scenario-data-load.json"
)


def _fixture(name: str) -> dict:
    return json.loads((REPO_ROOT / "data" / name).read_text(encoding="utf-8"))


def test_projection_contracts_are_frozen_and_keep_transport_out() -> None:
    task = TaskV1(
        record_id="task-1",
        task_id="task-1",
        name="Pick",
        function="Picking",
        area_id="area-1",
        area_name="Ambient",
        unit_type_id=None,
    )
    with pytest.raises(FrozenInstanceError):
        task.name = "changed"  # type: ignore[misc]

    assert "fastapi" not in TaskV1.__module__
    assert "pydantic" not in TaskV1.__module__
    assert "sqlalchemy" not in TaskV1.__module__


def test_projection_contracts_cover_every_normalized_group() -> None:
    qualification = QualificationRefV1(task_id="task-1", rate=12.5)
    window = AvailabilityWindowV1(
        kind="roster", start_minute=0, end_minute=60
    )
    worker = WorkerV1(
        record_id="worker-1",
        contact_id="worker-1",
        name="Alex",
        employment_type="Full Time",
        grade="Grade 3",
        eba="EA",
        contracted_hours=38.0,
        qualifications=(qualification,),
        availability_windows=(window,),
    )
    demand = DemandIntervalV1(
        record_id="inbound:0:0",
        family="inbound",
        task_id="task-1",
        area_id="area-1",
        start_minute=0,
        end_minute=30,
        amount=2.0,
        unit="volume",
    )
    assignment = AssignmentV1(
        record_id="assignment-1",
        worker_id="worker-1",
        task_id="task-1",
        shift_id=None,
        start_minute=0,
        end_minute=30,
    )
    lock = LockV1(
        record_id="lock-1",
        target_type="assignment",
        target_ref="assignment-1",
        scope="exact",
        source="planner",
    )
    constraint = ConstraintV1(
        record_id="constraint:0",
        constraint_type="MaximumHours",
        value="38",
        value_type="number",
    )

    assert worker.qualifications == (qualification,)
    assert worker.availability_windows == (window,)
    assert demand.unit == "volume"
    assert assignment.shift_id is None
    assert lock.target_ref == "assignment-1"
    assert constraint.value == "38"


def test_scenario_overview_requires_utc_horizon_and_projection_times() -> None:
    now = datetime.now(timezone.utc)
    overview = ScenarioOverviewV1(
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        site_id=uuid4(),
        fixture_id="fixture",
        scenario_name="Scenario",
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        horizon_start=now,
        site_timezone="Australia/Sydney",
        horizon_minutes=10_080,
        baseline_schedule_version=None,
        projection_generated_at=now,
        work_area_count=3,
        task_count=6,
        worker_count=23,
        demand_interval_count=1_000,
        baseline_assignment_count=0,
        lock_count=0,
        constraint_count=14,
    )
    assert overview.horizon_start.tzinfo is timezone.utc

    with pytest.raises(ValueError, match="UTC-aware"):
        ScenarioOverviewV1(
            **{
                **overview.__dict__,
                "horizon_start": datetime(2026, 6, 1),
            }
        )


@pytest.mark.parametrize(
    ("port_type", "response_model", "extra_fields"),
    [
        (ScenarioOverviewV1, schemas.ScenarioOverviewOut, {"schema_version"}),
        (TaskV1, schemas.TaskProjectionOut, set()),
        (QualificationRefV1, schemas.QualificationRefOut, set()),
        (AvailabilityWindowV1, schemas.AvailabilityWindowOut, set()),
        (WorkerV1, schemas.WorkerProjectionOut, set()),
        (DemandIntervalV1, schemas.DemandIntervalOut, set()),
        (AssignmentV1, schemas.AssignmentOut, set()),
        (LockV1, schemas.LockOut, set()),
        (ConstraintV1, schemas.ConstraintProjectionOut, set()),
    ],
)
def test_response_models_carry_every_contract_field(
    port_type, response_model, extra_fields
) -> None:
    """A field added to a contract dataclass must reach the wire. Pydantic
    ignores unknown keys, so without this the API would quietly keep the old
    shape (Story 1.3's review found exactly this via a `**vars()` splat)."""
    contract_fields = {field.name for field in fields(port_type)}
    model_fields = set(response_model.model_fields)

    assert contract_fields <= model_fields
    assert model_fields - contract_fields == extra_fields


@pytest.mark.parametrize(
    ("fixture_name", "worker_count"),
    (("sample_tiny_input.json", 10), ("sample_tiny_input_more_tm.json", 22)),
)
def test_gate_a_fixtures_normalize_to_exact_group_counts(
    fixture_name: str,
    worker_count: int,
) -> None:
    payload = _fixture(fixture_name)
    horizon_start, horizon_minutes = _horizon(payload)
    tasks = _normalize_tasks(payload)
    workers = _normalize_workers(payload, horizon_start)
    demand = _normalize_demand(payload, horizon_start)
    constraints = _normalize_constraints(payload)

    assert horizon_start.tzinfo is timezone.utc
    assert horizon_minutes == 10_080
    assert len({task.area_id for task in tasks}) == 3
    assert len(tasks) == 6
    assert len(workers) == worker_count
    assert len(demand) == 1_547
    assert len(constraints) == 14

    first_task = tasks[0]
    assert first_task.record_id == "1E5596F1-C9AD-43F1-8DC4-7CF8013C9D0B"
    assert first_task.area_name == "Chiller"
    assert demand[493].record_id == "inbound:0:0"
    assert demand[493].task_id == "3C1950FE-0C75-48AB-95B7-5C58909A0CCE"
    assert demand[493].amount == pytest.approx(2.964)


def test_worker_rate_uses_override_then_default_and_keeps_unqualified_workers() -> None:
    payload = _fixture("sample_tiny_input.json")
    horizon_start, _ = _horizon(payload)
    qualified = payload["Team Member"][0]
    task_id = payload["Task"][0]["TaskID"]
    payload["Team Member Qualification and Performance"] = [
        {
            "ContactID": qualified["ContactID"],
            "TaskID": task_id,
            "DefaultTaskRate": 10,
            "TeamMemberTaskRateOverride": 17.5,
        },
        {
            "ContactID": qualified["ContactID"],
            "TaskID": payload["Task"][1]["TaskID"],
            "DefaultTaskRate": 9.25,
            "TeamMemberTaskRateOverride": None,
        },
    ]

    workers = _normalize_workers(payload, horizon_start)
    worker = next(w for w in workers if w.contact_id == qualified["ContactID"])
    assert [q.rate for q in worker.qualifications] == [17.5, 9.25]
    assert len(workers) == len({m["ContactID"] for m in payload["Team Member"]})


def test_offset_cursor_window_is_deterministic_and_bounded() -> None:
    payload = _fixture("sample_tiny_input_more_tm.json")
    horizon_start, _ = _horizon(payload)
    demand = _normalize_demand(payload, horizon_start)

    first, next_cursor, total = _slice_window(demand, cursor=0, limit=50)
    last, last_cursor, last_total = _slice_window(
        demand, cursor=1_500, limit=50
    )

    assert tuple(item.record_id for item in first) == tuple(
        item.record_id for item in demand[:50]
    )
    assert next_cursor == 50
    assert total == 1_547
    assert len(last) == 47
    assert last_cursor is None
    assert last_total == total


class _ProjectionReader:
    def __init__(self) -> None:
        self.scenario_id = uuid4()
        self.scenario_version_id = uuid4()
        self.site_id = uuid4()
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.overview = ScenarioOverviewV1(
            scenario_id=self.scenario_id,
            scenario_version_id=self.scenario_version_id,
            site_id=self.site_id,
            fixture_id="fixture-a",
            scenario_name="Fixture A",
            fixture_version="v1",
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            horizon_start=now,
            site_timezone="Australia/Sydney",
            horizon_minutes=10_080,
            baseline_schedule_version=None,
            projection_generated_at=now,
            work_area_count=1,
            task_count=1,
            worker_count=0,
            demand_interval_count=0,
            baseline_assignment_count=0,
            lock_count=0,
            constraint_count=0,
        )
        task = TaskV1("task-1", "task-1", "Pick", "Pick", "a", "A", None)
        meta = (self.scenario_id, self.scenario_version_id, self.site_id)
        self.tasks = TaskPageV1(*meta, (task,), None, 1, 1)
        self.workers = WorkerPageV1(*meta, (), None, 0, 0)
        self.demand = DemandIntervalPageV1(*meta, (), None, 0, 0)
        self.assignments = AssignmentPageV1(*meta, (), None, 0, 0)
        self.locks = LockPageV1(*meta, (), None, 0, 0)
        self.constraints = ConstraintPageV1(*meta, (), None, 0, 0)

    def _known(self, scenario_id, value):
        return value if scenario_id == self.scenario_id else None

    def get_overview(self, _connection, scenario_id):
        return self._known(scenario_id, self.overview)

    def get_tasks(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.tasks)

    def get_workers(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.workers)

    def get_demand(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.demand)

    def get_baseline_assignments(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.assignments)

    def get_locks(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.locks)

    def get_constraints(self, _connection, scenario_id, cursor, limit):
        return self._known(scenario_id, self.constraints)


@pytest.fixture()
def projection_client():
    reader = _ProjectionReader()
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=reader.site_id,
        csrf_token_hash="a" * 64,
        expires_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    class _IdentityStore:
        def resolve_session(self, _token_hash):
            return resolved

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_projection_reader] = lambda: reader
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, "opaque-session")
            yield client, reader
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_projection_api_publishes_overview_and_all_six_group_pages(
    projection_client,
) -> None:
    client, reader = projection_client
    base = f"/api/v1/scenarios/{reader.scenario_id}/projection"

    overview = client.get(base)
    assert overview.status_code == 200
    assert overview.json()["schema_version"] == "v1"
    assert overview.json()["scenario_version_id"] == str(
        reader.scenario_version_id
    )
    assert overview.json()["site_id"] == str(reader.site_id)
    assert overview.json()["horizon_minutes"] == 10_080

    groups = (
        "work-areas-and-tasks",
        "workers",
        "demand",
        "baseline-assignments",
        "locks",
        "constraints-and-objectives",
    )
    for group in groups:
        response = client.get(f"{base}/{group}")
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "v1"
        assert body["group"] == group
        assert body["scenario_id"] == str(reader.scenario_id)
        assert body["scenario_version_id"] == str(reader.scenario_version_id)
        assert body["site_id"] == str(reader.site_id)


@pytest.mark.parametrize(
    "query",
    ("cursor=-1", "cursor=nope", "limit=0", "limit=201"),
)
def test_projection_cursor_validation_uses_problem_details(
    projection_client, query: str
) -> None:
    client, reader = projection_client
    response = client.get(
        f"/api/v1/scenarios/{reader.scenario_id}/projection/demand?{query}"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_projection_unknown_scenario_is_non_disclosing_404(
    projection_client,
) -> None:
    client, _ = projection_client
    response = client.get(f"/api/v1/scenarios/{uuid4()}/projection")
    assert response.status_code == 404
    assert response.json() == {
        "type": "https://shiftmind.app/problems/resource_not_found",
        "title": "Resource not found",
        "status": 404,
        "detail": "The requested resource was not found.",
        "code": "resource_not_found",
    }


def test_projection_routes_are_get_only_and_handlers_are_sync() -> None:
    projection_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if "/projection" in path
    }
    assert len(projection_paths) == 7
    unsafe = {"POST", "PUT", "PATCH", "DELETE"}
    assert all(
        not {method.upper() for method in operations}.intersection(unsafe)
        for operations in projection_paths.values()
    )
    handlers = (
        scenario_projection.get_projection,
        scenario_projection.get_tasks,
        scenario_projection.get_workers,
        scenario_projection.get_demand,
        scenario_projection.get_baseline_assignments,
        scenario_projection.get_locks,
        scenario_projection.get_constraints,
    )
    assert all(not inspect.iscoroutinefunction(handler) for handler in handlers)


def test_nfr35_release_evidence_records_all_required_passing_runs() -> None:
    evidence = json.loads(NFR35_EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["fixture"]["name"] == "sample_tiny_input_more_tm.json"
    assert evidence["fixture"]["version"] == "v1"
    assert evidence["protocol"]["warmup_requests_discarded"] == 1
    assert evidence["protocol"]["consecutive_runs"] == 3
    assert evidence["protocol"]["threshold_ms"] == 2_000
    assert evidence["protocol"]["clock_boundary"] == (
        "server-side request receipt to response completion"
    )
    measurements = evidence["measurements"]
    assert len(measurements) == 21
    assert {item["run"] for item in measurements} == {1, 2, 3}
    assert len({item["endpoint"] for item in measurements}) == 7
    assert all(item["duration_ms"] <= 2_000 for item in measurements)
    assert evidence["passed"] is True
