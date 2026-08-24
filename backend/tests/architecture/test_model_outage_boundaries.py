"""Model outage cannot enter or disable the manual deterministic run path."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_agent_runtime_factory,
    get_capability_registry,
    get_catalogue_reader,
    get_identity_store,
    get_projection_reader,
    get_proposal_repository,
    get_schedule_run_repository,
    get_settings,
    get_site_context,
)
from api.main import app
from application.capabilities.scheduling_optimize import scheduling_optimize_module
from application.contracts.comparison import AssignmentDiffV1, ComparisonV1
from application.contracts.job_lease import JobLeaseV1, LeaseRenewalV1
from application.contracts.proposal import ProposalV1, ResolvedEntityV1
from application.contracts.schedule_version import (
    MetricSetV1,
    SolverOutcomeV1,
    ValidationFactsV1,
)
from application.ports.proposal import ProposalRecordV1
from application.ports.scenario_catalogue import ScenarioContext
from application.ports.schedule_run import (
    IdempotentScheduleRunResultV1,
    ScheduleRunStateV1,
    ScheduleRunViewV1,
)
from application.ports.session import ResolvedSession
from application.use_cases.lease_and_execute_schedule_run import (
    lease_and_execute_schedule_run,
)
from settings import default_settings

BACKEND = Path(__file__).resolve().parents[2]
MANUAL_SOLVER_PATHS: tuple[str, ...] = (
    "api/routers/schedule_runs.py",
    "application/use_cases/enqueue_compute.py",
    "application/capabilities/scheduling_compute.py",
    "worker/lease_worker.py",
    "engine",
)
FORBIDDEN_MODEL_IMPORTS: tuple[str, ...] = (
    "agent",
    "application.ports.agent_runtime",
)

_SESSION_TOKEN = "model-outage-session"
_CSRF_TOKEN = "model-outage-csrf"
_NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def _is_model_import(name: str) -> bool:
    return any(name == root or name.startswith(f"{root}.") for root in FORBIDDEN_MODEL_IMPORTS)


def _manual_solver_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in MANUAL_SOLVER_PATHS:
        path = BACKEND / relative
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else (path,))
    return tuple(files)


def test_manual_solver_path_has_no_agent_runtime_import() -> None:
    offenders = {
        path.relative_to(BACKEND).as_posix(): sorted(
            name for name in _imports(path) if _is_model_import(name)
        )
        for path in _manual_solver_files()
        if any(_is_model_import(name) for name in _imports(path))
    }
    assert offenders == {}


def test_model_import_detector_can_observe_a_forbidden_boundary(tmp_path) -> None:
    forbidden = tmp_path / "forbidden.py"
    forbidden.write_text(
        "from application.ports.agent_runtime import AgentRuntime\n",
        encoding="utf-8",
    )
    assert any(_is_model_import(name) for name in _imports(forbidden))


class _IdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self.session = session

    def resolve_session(self, token_hash: str) -> ResolvedSession | None:
        return self.session if token_hash == hash_secret(_SESSION_TOKEN) else None


class _ProposalRepository:
    def __init__(self, record: ProposalRecordV1) -> None:
        self.record = record

    def get_current(self, _connection, *, proposal_id: UUID, for_update: bool = False):
        del for_update
        return self.record if proposal_id == self.record.proposal.proposal_id else None


class _Catalogue:
    def __init__(self, context: ScenarioContext | None) -> None:
        self.context = context

    def get_scenario_context(self, _connection, scenario_id: UUID):
        if self.context is None or scenario_id != self.context.scenario_id:
            return None
        return self.context


class _StatefulRunRepository:
    def __init__(self) -> None:
        self.snapshot = None
        self.job: JobLeaseV1 | None = None
        self.idempotent: dict[tuple, IdempotentScheduleRunResultV1] = {}
        self.status = "solver_queued"
        self.reason: str | None = None
        self.resource_version = 1
        self.candidate = None
        self.create_count = 0
        self.enqueue_count = 0

    def get_idempotent_result(self, _connection, **values):
        key = (
            values["site_id"], values["actor_id"], values["operation"],
            values["idempotency_key"],
        )
        return self.idempotent.get(key)

    def _store_idempotent_result(self, _connection, **values) -> None:
        key = (
            values["site_id"], values["actor_id"], values["operation"],
            values["idempotency_key"],
        )
        self.idempotent[key] = IdempotentScheduleRunResultV1(
            values["body_hash"], values["response_payload"]
        )

    def acquire_site_enqueue_lock(self, _connection, *, site_id: UUID) -> None:
        del site_id

    def count_runs_with_statuses(self, _connection, *, site_id: UUID, statuses) -> int:
        del site_id, statuses
        return 0

    def create_queued_run(self, _connection, *, snapshot, site_id: UUID, actor_id: UUID) -> None:
        del site_id, actor_id
        self.snapshot = snapshot
        self.status = "solver_queued"
        self.resource_version = 1
        self.create_count += 1

    def enqueue_job(self, _connection, *, job: JobLeaseV1, site_id: UUID) -> None:
        del site_id
        self.job = job
        self.enqueue_count += 1

    def get_run(self, _connection, *, run_id: UUID, site_id: UUID):
        if self.snapshot is None or run_id != self.snapshot.schedule_run_id:
            return None
        return ScheduleRunViewV1(
            run_id,
            self.status,
            self.reason,
            self.resource_version,
            False,
            created_at=self.snapshot.accepted_at,
            finished_at=_NOW if self.status == "solver_completed" else None,
        )

    def lease_next_job(self, _connection, *, lease_owner: str, lease_seconds: int):
        if self.job is None or self.job.status != "queued":
            return None
        self.job = replace(
            self.job,
            status="leased",
            attempt_id=uuid4(),
            lease_owner=lease_owner,
            lease_expires_at=_NOW + timedelta(seconds=lease_seconds),
            heartbeat_at=_NOW,
            fencing_epoch=1,
        )
        return self.job

    def load_snapshot(self, _connection, *, run_id: UUID, site_id: UUID):
        del site_id
        return self.snapshot if self.snapshot and run_id == self.snapshot.schedule_run_id else None

    def get_run_state(self, _connection, *, run_id: UUID, site_id: UUID):
        del site_id
        if self.snapshot is None or run_id != self.snapshot.schedule_run_id:
            return None
        return ScheduleRunStateV1(self.status, self.resource_version)

    def mark_running(self, _connection, *, run_id: UUID, site_id: UUID, fencing_epoch: int, request_id=None) -> None:
        del run_id, site_id, fencing_epoch, request_id
        self.status = "solver_running"
        self.resource_version += 1

    def renew_job_lease(self, _connection, *, job_id: UUID, fencing_epoch: int, extension_seconds: int):
        del job_id, fencing_epoch, extension_seconds
        return LeaseRenewalV1(renewed=True, cancellation_requested=False)

    def finalize_run(self, _connection, *, run_id: UUID, site_id: UUID, fencing_epoch: int, status, reason, candidate, **_values) -> None:
        del run_id, site_id, fencing_epoch
        self.status = status
        self.reason = reason
        self.candidate = candidate
        self.resource_version += 1

    def complete_job(self, _connection, *, job_id: UUID, site_id: UUID, fencing_epoch: int) -> None:
        del job_id, site_id, fencing_epoch
        assert self.job is not None
        self.job = replace(self.job, status="completed")

    def get_candidate(self, _connection, *, schedule_run_id: UUID, site_id: UUID):
        del site_id
        if self.snapshot is None or schedule_run_id != self.snapshot.schedule_run_id:
            return None
        return self.candidate


class _DeterministicScheduler:
    def solve(self, _snapshot):
        return SolverOutcomeV1(
            solver_status="OPTIMAL",
            validation_facts=ValidationFactsV1(
                horizon_minutes=60,
                workers=(),
                selected_shifts=(),
                max_hours_per_week=(),
                max_shifts_per_day=(),
                minimum_gap_minutes=0,
            ),
        )


@contextmanager
def _runtime_connection(_site_id: UUID):
    yield object()


def _comparison(repository: _StatefulRunRepository) -> ComparisonV1:
    candidate = repository.candidate
    assert candidate is not None
    assert candidate.schedule_version_id is not None
    assert candidate.schedule_run_id is not None
    assert candidate.scenario_id is not None
    assert candidate.scenario_version_id is not None
    assert candidate.metrics is not None
    return ComparisonV1(
        candidate.schedule_version_id,
        candidate.schedule_run_id,
        candidate.scenario_id,
        candidate.scenario_version_id,
        None,
        None,
        False,
        AssignmentDiffV1(),
        candidate.metrics,
        MetricSetV1(),
        candidate.constraint_results,
        (),
        candidate.warnings,
        (),
        candidate.evidence_refs,
    )


def _headers(settings, *, key: str) -> dict[str, str]:
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
        "X-CSRF-Token": _CSRF_TOKEN,
        "Idempotency-Key": key,
    }


def _raising_runtime_factory(**_kwargs):
    raise AssertionError("the manual deterministic path reached AgentRuntime")


def _exercise_manual_run_flow(
    tmp_path, monkeypatch
) -> None:
    site_id, actor_id, scenario_id, scenario_version_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    proposal = ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        resolved_entities=(
            ResolvedEntityV1(
                group="work-areas-and-tasks",
                record_id="task-1",
                label="Task 1",
                scenario_version_id=scenario_version_id,
            ),
        ),
    )
    proposal_repository = _ProposalRepository(
        ProposalRecordV1(proposal, 1, actor_id)
    )
    catalogue = _Catalogue(
        ScenarioContext(
            "Scenario",
            scenario_id,
            scenario_version_id,
            "v1",
            "sha256",
            "rfc8785-v1",
            "a" * 64,
            site_id,
            None,
        )
    )
    repository = _StatefulRunRepository()
    session = ResolvedSession(
        app_user_id=actor_id,
        site_id=site_id,
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=_NOW + timedelta(hours=1),
    )
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(session)
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_capability_registry] = lambda: (
        lambda _context: (scheduling_optimize_module(),)
    )
    app.dependency_overrides[get_proposal_repository] = lambda: proposal_repository
    app.dependency_overrides[get_catalogue_reader] = lambda: catalogue
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository
    app.dependency_overrides[get_projection_reader] = lambda: object()
    app.dependency_overrides[get_agent_runtime_factory] = lambda: _raising_runtime_factory
    try:
        with TestClient(app) as client:
            body = {
                "proposal_id": str(proposal.proposal_id),
                "expected_resource_version": 1,
            }
            headers = _headers(settings, key="outage-run-1")
            started = client.post("/api/v1/schedule-runs", json=body, headers=headers)
            assert started.status_code == 200
            run_id = UUID(started.json()["schedule_run_id"])

            outcome = lease_and_execute_schedule_run(
                object(),
                _runtime_connection,
                repository,
                _DeterministicScheduler(),
                lease_owner="worker-model-outage-proof",
                lease_seconds=60,
            )
            assert outcome is not None
            assert outcome.status == "solver_completed"

            monkeypatch.setattr(
                "api.routers.schedule_runs.calculate_comparison",
                lambda *_args, **_kwargs: _comparison(repository),
            )
            result = client.get(
                f"/api/v1/schedule-runs/{run_id}/result", headers=headers
            )
            assert result.status_code == 200
            result_body = result.json()
            assert result_body["run"]["status"] == "solver_completed"
            assert result_body["candidate"]["evidence_refs"][0]["record_id"] == "task-1"

            replay = client.post("/api/v1/schedule-runs", json=body, headers=headers)
            assert replay.status_code == 200
            assert replay.json()["schedule_run_id"] == str(run_id)
            assert replay.json()["status"] == "solver_completed"
            reread = client.get(
                f"/api/v1/schedule-runs/{run_id}/result", headers=headers
            )
            assert reread.json() == result_body
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert repository.create_count == 1
    assert repository.enqueue_count == 1
    assert len(repository.idempotent) == 1


def test_manual_run_end_to_end_and_replay_survive_a_raising_runtime_factory(
    tmp_path, monkeypatch
) -> None:
    _exercise_manual_run_flow(tmp_path, monkeypatch)


def test_manual_run_result_and_evidence_survive_a_raising_trace_exporter(
    tmp_path, monkeypatch
) -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

    class _RaisingExporter(SpanExporter):
        def export(self, _spans):
            raise RuntimeError("simulated exporter failure")

        def shutdown(self) -> None:
            return None

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_RaisingExporter()))
    try:
        # Drive the actual failure before the manual path. The SDK records the
        # exporter error locally; it must not authorize, block, or corrupt the
        # deterministic HTTP/worker/result flow exercised below.
        with provider.get_tracer(__name__).start_as_current_span("export-fails"):
            pass
        _exercise_manual_run_flow(tmp_path, monkeypatch)
    finally:
        provider.shutdown()


def test_solver_service_failure_keeps_its_own_problem_surface(
    tmp_path,
) -> None:
    site_id, actor_id, scenario_id, scenario_version_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    proposal = ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
    )
    session = ResolvedSession(
        app_user_id=actor_id,
        site_id=site_id,
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=_NOW + timedelta(hours=1),
    )
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(session)
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_capability_registry] = lambda: (
        lambda _context: (scheduling_optimize_module(),)
    )
    app.dependency_overrides[get_proposal_repository] = lambda: _ProposalRepository(
        ProposalRecordV1(proposal, 1, actor_id)
    )
    app.dependency_overrides[get_catalogue_reader] = lambda: _Catalogue(None)
    app.dependency_overrides[get_schedule_run_repository] = lambda: _StatefulRunRepository()
    app.dependency_overrides[get_agent_runtime_factory] = lambda: _raising_runtime_factory
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/schedule-runs",
                json={
                    "proposal_id": str(proposal.proposal_id),
                    "expected_resource_version": 1,
                },
                headers=_headers(settings, key="solver-service-failure"),
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 503
    assert response.json()["code"] == "scenario_unavailable"
    assert response.json()["code"] != "agent_unavailable"
