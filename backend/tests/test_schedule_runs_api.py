from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_capability_registry,
    get_catalogue_reader,
    get_identity_store,
    get_proposal_repository,
    get_projection_reader,
    get_schedule_run_repository,
    get_settings,
    get_site_context,
)
from api.main import app
from application.ports.schedule_run import (
    IdempotentScheduleRunResultV1,
    ScheduleRunPageV1,
    ScheduleRunSummaryV1,
    ScheduleRunViewV1,
    ScheduleRunStateV1,
)
from application.ports.scenario_catalogue import ScenarioContext
from application.ports.session import ResolvedSession
from application.contracts.comparison import AssignmentDiffV1, ComparisonV1
from application.contracts.schedule_version import MetricSetV1, ScheduleVersionV1
from application.scheduling.comparison import ComparisonIntegrityError
from application.use_cases.cancel_schedule_run import (
    CancelScheduleRunError,
    IdempotencyKeyConflictError,
    RunNotCancellableError,
    ScheduleRunCancellationV1,
    StaleResourceVersionError,
)
from application.use_cases.create_run_snapshot import SnapshotCreationError
from application.use_cases.enqueue_compute import (
    EnqueueComputeResultV1,
    ProposalNotFoundError,
    SiteConcurrencyExhaustedError,
    StaleProposalResourceVersionError,
)
from application.capabilities.scheduling_optimize import scheduling_optimize_module
from settings import default_settings


_SESSION_TOKEN = "schedule-run-session"
_CSRF_TOKEN = "schedule-run-csrf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    monkeypatch.setenv(
        "ROSTERAI_MAINTENANCE_FLAG", str(tmp_path / "gate-a-maintenance")
    )
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class _IdentityStore:
        def resolve_session(self, token_hash):
            return session if token_hash == hash_secret(_SESSION_TOKEN) else None

    settings = replace(default_settings())
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_schedule_run_repository] = lambda: object()
    try:
        with TestClient(app) as test_client:
            yield test_client, settings, session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _headers(settings, *, key="cancel-1"):
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
        "X-CSRF-Token": _CSRF_TOKEN,
        "Idempotency-Key": key,
    }


@pytest.mark.parametrize(
    "status",
    ("solver_queued", "solver_running", "cancellation_requested", "solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed"),
)
def test_result_route_preserves_literal_run_without_candidate(client, status) -> None:
    test_client, settings, session = client
    run_id = uuid4()

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, status, "literal-reason", 2, status == "cancellation_requested")

        def get_candidate(self, *_args, **_kwargs):
            raise AssertionError("non-completed runs must not read a candidate")

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()
    response = test_client.get(f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings))

    assert response.status_code == 200
    assert response.json()["run"]["status"] == status
    assert response.json()["candidate"] is None
    assert response.json()["comparison"] is None


def test_result_route_returns_completed_candidate_and_comparison(client, monkeypatch) -> None:
    test_client, settings, session = client
    run_id, scenario_id, version_id = uuid4(), uuid4(), uuid4()
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=run_id, scenario_id=scenario_id,
        scenario_version_id=version_id, proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL", metrics=MetricSetV1(),
    )
    comparison = ComparisonV1(
        candidate.schedule_version_id, run_id, scenario_id, version_id, None, None, False,
        AssignmentDiffV1(), MetricSetV1(), MetricSetV1(), (), (), (), (), (),
    )

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, "solver_completed", None, 3, False)

        def get_candidate(self, *_args, **_kwargs):
            return candidate

        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(baseline_schedule_version=None)

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()
    app.dependency_overrides[get_projection_reader] = lambda: object()
    monkeypatch.setattr("api.routers.schedule_runs.calculate_comparison", lambda *_args, **_kwargs: comparison)

    response = test_client.get(f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings))

    assert response.status_code == 200
    assert response.json()["candidate"]["schedule_run_id"] == str(run_id)
    assert response.json()["comparison"]["stale"] is False


def test_result_route_does_not_disclose_unknown_or_cross_site_run(client) -> None:
    test_client, settings, _ = client

    class _MissingRepository:
        def get_run(self, *_args, **_kwargs):
            return None

        def get_candidate(self, *_args, **_kwargs):
            raise AssertionError("an unknown run must never reach candidate reads")

    app.dependency_overrides[get_schedule_run_repository] = lambda: _MissingRepository()
    response = test_client.get(
        f"/api/v1/schedule-runs/{uuid4()}/result", headers=_headers(settings)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "schedule_run_not_found"


def test_result_route_reports_missing_candidate_as_a_distinct_problem(client) -> None:
    test_client, settings, _ = client
    run_id = uuid4()

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, "solver_completed", None, 3, False)

        def get_candidate(self, *_args, **_kwargs):
            return None

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()

    response = test_client.get(f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings))

    assert response.status_code == 500
    assert response.json()["code"] == "schedule_candidate_missing"


def test_result_route_reports_missing_snapshot_as_a_distinct_problem(client) -> None:
    test_client, settings, _ = client
    run_id, scenario_id, version_id = uuid4(), uuid4(), uuid4()
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=run_id, scenario_id=scenario_id,
        scenario_version_id=version_id, proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL", metrics=MetricSetV1(),
    )

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, "solver_completed", None, 3, False)

        def get_candidate(self, *_args, **_kwargs):
            return candidate

        def load_snapshot(self, *_args, **_kwargs):
            return None

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()

    response = test_client.get(f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings))

    assert response.status_code == 500
    assert response.json()["code"] == "run_snapshot_missing"


def test_result_route_reports_comparison_integrity_failure_as_a_distinct_problem(
    client, monkeypatch
) -> None:
    test_client, settings, _ = client
    run_id, scenario_id, version_id = uuid4(), uuid4(), uuid4()
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=run_id, scenario_id=scenario_id,
        scenario_version_id=version_id, proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL", metrics=MetricSetV1(),
    )

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, "solver_completed", None, 3, False)

        def get_candidate(self, *_args, **_kwargs):
            return candidate

        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(baseline_schedule_version=None)

    def _raise(*_args, **_kwargs):
        raise ComparisonIntegrityError("persisted candidate metrics disagree with recomputation")

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()
    app.dependency_overrides[get_projection_reader] = lambda: object()
    monkeypatch.setattr("api.routers.schedule_runs.calculate_comparison", _raise)

    response = test_client.get(f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings))

    assert response.status_code == 500
    assert response.json()["code"] == "comparison_calculation_failed"


def test_result_route_lets_an_unrelated_bug_surface_as_the_generic_internal_error(
    client, monkeypatch
) -> None:
    """The narrowed `except ComparisonIntegrityError` must not swallow other bugs.

    Before this fix, a bare `except Exception` mapped ANY failure inside
    `calculate_comparison` -- including an unrelated `KeyError`/`AttributeError`
    -- to the same `comparison_calculation_failed` code as a genuine integrity
    violation. This proves an unrelated exception now falls through to
    `api/main.py`'s global handler and reports as `internal_error` instead.
    """
    test_client, settings, _ = client
    run_id, scenario_id, version_id = uuid4(), uuid4(), uuid4()
    candidate = ScheduleVersionV1(
        schedule_version_id=uuid4(), schedule_run_id=run_id, scenario_id=scenario_id,
        scenario_version_id=version_id, proposal_id=uuid4(), proposal_version_id=uuid4(),
        feasible_solver_status="OPTIMAL", metrics=MetricSetV1(),
    )

    class _Repository:
        def get_run(self, *_args, **_kwargs):
            return ScheduleRunViewV1(run_id, "solver_completed", None, 3, False)

        def get_candidate(self, *_args, **_kwargs):
            return candidate

        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(baseline_schedule_version=None)

    def _raise(*_args, **_kwargs):
        raise KeyError("unrelated bug, not an integrity failure")

    app.dependency_overrides[get_schedule_run_repository] = lambda: _Repository()
    app.dependency_overrides[get_projection_reader] = lambda: object()
    monkeypatch.setattr("api.routers.schedule_runs.calculate_comparison", _raise)

    # The shared `client` fixture's TestClient re-raises server exceptions by
    # default; the global handler's own docstring documents that Starlette's
    # `BaseHTTPMiddleware` re-raises even a handled exception through
    # `TestClient`, so this specific assertion needs `raise_server_exceptions=False`
    # (matching the established pattern in `test_scenario_catalogue_api.py`).
    with TestClient(app, raise_server_exceptions=False) as unraising_client:
        response = unraising_client.get(
            f"/api/v1/schedule-runs/{run_id}/result", headers=_headers(settings)
        )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


class _StartRepository:
    """Answers the run read the start route performs after enqueueing."""

    def __init__(self, view: ScheduleRunViewV1) -> None:
        self.view = view
        self.reads: list[object] = []

    def get_run(self, _connection, *, run_id, site_id):
        self.reads.append((run_id, site_id))
        return self.view


def _grant_optimize() -> None:
    app.dependency_overrides[get_capability_registry] = lambda: (
        lambda _context: (scheduling_optimize_module(),)
    )
    app.dependency_overrides[get_proposal_repository] = lambda: object()
    app.dependency_overrides[get_catalogue_reader] = lambda: object()


def _queued_view(run_id, *, status="solver_queued", resource_version=1):
    return ScheduleRunViewV1(
        schedule_run_id=run_id,
        status=status,
        reason=None,
        resource_version=resource_version,
        cancellation_requested=False,
    )


def test_start_route_composes_explicit_compute_grant_and_enqueues_once(
    client, monkeypatch
) -> None:
    test_client, settings, session = client
    proposal_id = uuid4()
    run_id = uuid4()
    job_id = uuid4()
    observed = {}

    def _compose(context):
        observed["context"] = context
        return (scheduling_optimize_module(),)

    def _enqueue(*_args, **kwargs):
        observed["enqueue"] = kwargs
        return EnqueueComputeResultV1(run_id, job_id)

    app.dependency_overrides[get_capability_registry] = lambda: _compose
    app.dependency_overrides[get_proposal_repository] = lambda: object()
    app.dependency_overrides[get_catalogue_reader] = lambda: object()
    repository = _StartRepository(_queued_view(run_id))
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository
    monkeypatch.setattr("api.routers.schedule_runs.enqueue_compute", _enqueue)

    response = test_client.post(
        "/api/v1/schedule-runs",
        json={"proposal_id": str(proposal_id), "expected_resource_version": 3},
        headers=_headers(settings, key="start-1"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schedule_run_id"] == str(run_id)
    assert body["status"] == "solver_queued"
    assert body["resource_version"] == 1
    assert observed["context"].explicit_run_request is True
    assert observed["enqueue"]["actor_id"] == session.app_user_id
    assert observed["enqueue"]["site_id"] == session.site_id
    assert observed["enqueue"]["proposal_id"] == proposal_id
    assert observed["enqueue"]["expected_proposal_resource_version"] == 3
    assert observed["enqueue"]["idempotency_key"] == "start-1"
    # The capability version travels from the validated result into the job,
    # so the generic bundle names no capability of its own.
    assert observed["enqueue"]["capability_version"] == (
        scheduling_optimize_module().manifest.capability_version
    )
    assert repository.reads == [(run_id, session.site_id)]


def test_start_route_returns_the_runs_live_state_not_creation_constants(
    client, monkeypatch
) -> None:
    """AC3: a replay returns the ORIGINAL semantic run response.

    The route used to answer with the literals `solver_queued` and
    `resource_version=1` regardless of what the run had become. On the replay
    path `enqueue_compute` returns the stored identifiers for a run a worker may
    already have leased, so those constants described a state that had passed --
    and the version they reported is exactly what a caller pins its next
    cancellation to, guaranteeing a 409.
    """
    test_client, settings, session = client
    run_id = uuid4()
    _grant_optimize()
    repository = _StartRepository(
        _queued_view(run_id, status="solver_running", resource_version=2)
    )
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository
    monkeypatch.setattr(
        "api.routers.schedule_runs.enqueue_compute",
        lambda *_a, **_k: EnqueueComputeResultV1(run_id, uuid4()),
    )

    response = test_client.post(
        "/api/v1/schedule-runs",
        json={"proposal_id": str(uuid4()), "expected_resource_version": 1},
        headers=_headers(settings, key="start-replay"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "solver_running"
    assert response.json()["resource_version"] == 2
    assert repository.reads == [(run_id, session.site_id)]


def test_start_route_refuses_when_compute_is_not_granted(client) -> None:
    """`SCHEDULING_OPTIMIZE_ENABLED=false` is a denial, not a validation failure."""
    test_client, settings, _ = client
    app.dependency_overrides[get_capability_registry] = lambda: (lambda _context: ())
    app.dependency_overrides[get_proposal_repository] = lambda: object()
    app.dependency_overrides[get_catalogue_reader] = lambda: object()

    response = test_client.post(
        "/api/v1/schedule-runs",
        json={"proposal_id": str(uuid4()), "expected_resource_version": 1},
        headers=_headers(settings, key="start-ungranted"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "compute_not_granted"


def test_start_route_maps_capability_validation_failures(client) -> None:
    """The handler runs INSIDE the route's try, so its declared codes are mapped.

    Raised outside it, `InvalidRunRequestError` escaped every mapping and became
    `500 internal_error`. A nil UUID passes Pydantic and reaches the handler, so
    any client could produce that 500.
    """
    test_client, settings, _ = client
    _grant_optimize()

    response = test_client.post(
        "/api/v1/schedule-runs",
        json={
            "proposal_id": "00000000-0000-0000-0000-000000000000",
            "expected_resource_version": 1,
        },
        headers=_headers(settings, key="start-nil-uuid"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_query"


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    (
        (SiteConcurrencyExhaustedError("limit"), 429, "site_concurrency_exhausted"),
        (SnapshotCreationError("stale_proposal", "stale"), 409, "stale_proposal"),
        (StaleProposalResourceVersionError(1, 2), 409, "stale_resource_version"),
        # AD-13 keeps missing, denied, stale and invalid distinct. These four
        # all collapsed into one 422 `invalid_run_command`, so a deleted
        # proposal and an unreadable scenario were reported as bad input.
        (ProposalNotFoundError("gone"), 404, "proposal_not_found"),
        (
            SnapshotCreationError("proposal_not_found", "gone"),
            404,
            "proposal_not_found",
        ),
        (
            SnapshotCreationError("rejected_proposal", "rejected"),
            409,
            "rejected_proposal",
        ),
        (
            SnapshotCreationError("scenario_unavailable", "unreadable"),
            503,
            "scenario_unavailable",
        ),
        (
            SnapshotCreationError("invalid_proposal", "no identifiers"),
            422,
            "invalid_proposal",
        ),
    ),
)
def test_start_route_maps_bounded_and_stale_problems(
    client, monkeypatch, exception, status, code
) -> None:
    test_client, settings, _ = client
    _grant_optimize()

    def _raise(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr("api.routers.schedule_runs.enqueue_compute", _raise)
    response = test_client.post(
        "/api/v1/schedule-runs",
        json={"proposal_id": str(uuid4()), "expected_resource_version": 1},
        headers=_headers(settings, key="start-problem"),
    )

    assert response.status_code == status
    assert response.json()["code"] == code


def test_start_route_does_not_echo_internal_exception_text(
    client, monkeypatch
) -> None:
    """The catch-all used `str(exc)`, so a driver message could cross AD-3."""
    test_client, settings, _ = client
    _grant_optimize()

    def _raise(*_args, **_kwargs):
        raise SnapshotCreationError("unmapped_future_code", "connection to 10.0.0.7 failed")

    monkeypatch.setattr("api.routers.schedule_runs.enqueue_compute", _raise)
    response = test_client.post(
        "/api/v1/schedule-runs",
        json={"proposal_id": str(uuid4()), "expected_resource_version": 1},
        headers=_headers(settings, key="start-opaque"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_run_command"
    assert "10.0.0.7" not in response.text


def test_cancellation_route_returns_the_replayed_semantic_result(
    client, monkeypatch
) -> None:
    test_client, settings, _ = client
    run_id = uuid4()
    result = ScheduleRunCancellationV1(
        run_id, "cancellation_requested", "cancellation_requested", 4, True
    )
    monkeypatch.setattr(
        "api.routers.schedule_runs.cancel_schedule_run", lambda *_a, **_k: result
    )

    response = test_client.post(
        f"/api/v1/schedule-runs/{run_id}/cancellation",
        json={"expected_resource_version": 3},
        headers=_headers(settings),
    )

    assert response.status_code == 200
    assert response.json()["schedule_run_id"] == str(run_id)
    assert response.json()["status"] == "cancellation_requested"
    assert response.json()["resource_version"] == 4
    assert response.json()["cancellation_requested"] is True


def test_cancellation_route_reports_the_flag_it_was_given_not_a_constant() -> None:
    """Decision 4 permits a run with no job row, where the flag is genuinely false.

    The field used to be a hard-coded `True`, so this assertion could not fail
    and Story 3.7 would have rendered a constant as a distinct literal state.
    """
    assert (
        ScheduleRunCancellationV1(
            uuid4(), "solver_cancelled", "cancelled", 2
        ).cancellation_requested
        is False
    )


def test_polling_fallback_returns_literal_persisted_run_state(client) -> None:
    test_client, _, session = client
    run_id = uuid4()

    class _ReadRepository:
        def get_run(self, _connection, *, run_id: object, site_id):
            assert site_id == session.site_id
            return ScheduleRunViewV1(
                schedule_run_id=run_id,
                status="cancellation_requested",
                reason="cancellation_requested",
                resource_version=3,
                cancellation_requested=True,
            )

    app.dependency_overrides[get_schedule_run_repository] = lambda: _ReadRepository()
    response = test_client.get(
        f"/api/v1/schedule-runs/{run_id}",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "schedule_run_id": str(run_id),
        "status": "cancellation_requested",
        "reason": "cancellation_requested",
        "resource_version": 3,
        "cancellation_requested": True,
        "created_at": None,
        "finished_at": None,
    }


def test_polling_fallback_does_not_disclose_unknown_or_cross_site_run(client) -> None:
    test_client, _, _ = client

    class _MissingRepository:
        def get_run(self, _connection, *, run_id, site_id):
            return None

    app.dependency_overrides[get_schedule_run_repository] = lambda: _MissingRepository()
    response = test_client.get(
        f"/api/v1/schedule-runs/{uuid4()}",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "schedule_run_not_found"


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    (
        (IdempotencyKeyConflictError("conflict"), 409, "idempotency_key_conflict"),
        (StaleResourceVersionError(2, 3), 409, "stale_resource_version"),
        (RunNotCancellableError("terminal"), 409, "run_not_cancellable"),
        (CancelScheduleRunError("bad"), 422, "invalid_cancellation_command"),
    ),
)
def test_cancellation_route_maps_command_problems(
    client, monkeypatch, exception, status, code
) -> None:
    test_client, settings, _ = client

    def _raise(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr("api.routers.schedule_runs.cancel_schedule_run", _raise)
    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=_headers(settings),
    )

    assert response.status_code == status
    assert response.json()["code"] == code


def test_cancellation_route_does_not_disclose_unknown_or_other_site_run(
    client, monkeypatch
) -> None:
    test_client, settings, _ = client
    monkeypatch.setattr(
        "api.routers.schedule_runs.cancel_schedule_run", lambda *_a, **_k: None
    )

    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=_headers(settings),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "schedule_run_not_found"


@pytest.mark.parametrize("key", (None, "x" * 41))
def test_cancellation_route_enforces_idempotency_header_bounds(client, key) -> None:
    test_client, settings, _ = client
    headers = _headers(settings)
    if key is None:
        headers.pop("Idempotency-Key")
    else:
        headers["Idempotency-Key"] = key

    response = test_client.post(
        f"/api/v1/schedule-runs/{uuid4()}/cancellation",
        json={"expected_resource_version": 1},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


class _WiringRepository:
    """Minimal repository that satisfies the REAL use case, not a monkeypatch.

    Every other route test replaces `cancel_schedule_run` wholesale, so they
    prove `_command_problem`'s isinstance ladder and nothing else -- a signature
    mismatch between the router's call site and the use case's keyword-only
    parameters would pass all of them.
    """

    def __init__(self) -> None:
        self.stored = {}
        self.flag = False

    def get_run_state(self, _connection, *, run_id, site_id):
        return ScheduleRunStateV1("solver_running", 3)

    def get_idempotent_result(
        self, _connection, *, site_id, actor_id, operation, idempotency_key
    ):
        return self.stored.get((site_id, actor_id, operation, idempotency_key))

    def set_job_cancellation_requested(self, _connection, *, run_id, site_id):
        self.flag = True

    def get_job_cancellation_requested(self, _connection, *, run_id, site_id):
        return self.flag

    def request_cancellation(
        self, _connection, *, run_id, site_id, actor_id, expected_resource_version
    ):
        return None

    def _store_idempotent_result(
        self,
        _connection,
        *,
        site_id,
        actor_id,
        operation,
        idempotency_key,
        body_hash,
        response_payload,
    ):
        self.stored[(site_id, actor_id, operation, idempotency_key)] = (
            IdempotentScheduleRunResultV1(body_hash, response_payload)
        )


def test_cancellation_route_drives_the_real_use_case(client) -> None:
    """Exercise router -> use case -> repository without monkeypatching the seam."""
    test_client, settings, _ = client
    repository = _WiringRepository()
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository
    run_id = uuid4()

    response = test_client.post(
        f"/api/v1/schedule-runs/{run_id}/cancellation",
        json={"expected_resource_version": 3},
        headers=_headers(settings, key="wiring-1"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schedule_run_id"] == str(run_id)
    assert body["status"] == "cancellation_requested"
    assert body["resource_version"] == 4
    # Read back from the repository, not asserted by the router.
    assert body["cancellation_requested"] is True
    assert repository.flag is True

    # A replay on the same key returns the stored result through the same wiring.
    replay = test_client.post(
        f"/api/v1/schedule-runs/{run_id}/cancellation",
        json={"expected_resource_version": 3},
        headers=_headers(settings, key="wiring-1"),
    )
    assert replay.status_code == 200
    assert replay.json() == body
    assert len(repository.stored) == 1


def _scenario_context(*, site_id) -> ScenarioContext:
    return ScenarioContext(
        scenario_name="Scenario",
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        site_id=site_id,
        baseline_schedule_version=None,
    )


def _summary(**overrides) -> ScheduleRunSummaryV1:
    values = {
        "schedule_run_id": uuid4(),
        "status": "solver_completed",
        "reason": None,
        "resource_version": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "scenario_version_id": uuid4(),
        "proposal_id": uuid4(),
        "proposal_version": 1,
        "baseline_schedule_version": None,
    }
    values.update(overrides)
    return ScheduleRunSummaryV1(**values)


class _ListRepository:
    def __init__(self, page: ScheduleRunPageV1) -> None:
        self.page = page
        self.calls: list[dict] = []

    def list_runs(self, _connection, **kwargs):
        self.calls.append(kwargs)
        return self.page


def test_list_route_returns_a_page_shaped_by_the_repository(client) -> None:
    test_client, settings, session = client
    scenario_id = uuid4()
    app.dependency_overrides[get_catalogue_reader] = lambda: type(
        "Reader", (), {"get_scenario_context": staticmethod(
            lambda _connection, _scenario_id: _scenario_context(site_id=session.site_id)
        )},
    )()
    summary = _summary(baseline_schedule_version=None)
    repository = _ListRepository(ScheduleRunPageV1(items=(summary,), next_cursor=None, total_count=1, matching_count=1))
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository

    response = test_client.get(
        "/api/v1/schedule-runs",
        params={"scenario_id": str(scenario_id)},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    # The page envelope carries the counts `PaginationControls` needs, and the
    # scenario it was read for. No `group`, no `schema_version` -- see
    # `ScheduleRunPageOut`.
    assert body["scenario_id"] == str(scenario_id)
    assert body["total_count"] == 1
    assert body["matching_count"] == 1
    assert "schema_version" not in body
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["schedule_run_id"] == str(summary.schedule_run_id)
    assert item["status"] == "solver_completed"
    assert item["proposal_id"] == str(summary.proposal_id)
    assert item["proposal_version"] == 1
    # AC1's "updated time" is its own field, distinct from `finished_at`, so a
    # non-terminal run still reports when it last changed.
    assert datetime.fromisoformat(
        item["updated_at"].replace("Z", "+00:00")
    ) == summary.updated_at
    # Trap 4: None renders as JSON null, never "" or 0 -- the client decides
    # to show "—".
    assert item["baseline_schedule_version"] is None
    assert repository.calls == [
        {
            "scenario_id": scenario_id,
            "site_id": session.site_id,
            "cursor": 0,
            "limit": 50,
        }
    ]


def test_list_route_reports_updated_at_for_a_run_with_no_finish_time(client) -> None:
    # AC1 asks for an "updated time". `finished_at` is NULL for every
    # non-terminal run -- exactly the set a planner monitors -- so the two
    # fields must not be the same value wearing two names.
    test_client, settings, session = client
    scenario_id = uuid4()
    app.dependency_overrides[get_catalogue_reader] = lambda: type(
        "Reader", (), {"get_scenario_context": staticmethod(
            lambda _connection, _scenario_id: _scenario_context(site_id=session.site_id)
        )},
    )()
    changed_at = datetime.now(timezone.utc)
    summary = _summary(
        status="solver_running",
        finished_at=None,
        updated_at=changed_at,
    )
    repository = _ListRepository(ScheduleRunPageV1(items=(summary,), next_cursor=None, total_count=1, matching_count=1))
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository

    response = test_client.get(
        "/api/v1/schedule-runs",
        params={"scenario_id": str(scenario_id)},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["finished_at"] is None
    assert datetime.fromisoformat(
        item["updated_at"].replace("Z", "+00:00")
    ) == changed_at


def test_list_route_paginates_with_a_cursor_and_bounded_limit(client) -> None:
    test_client, settings, session = client
    scenario_id = uuid4()
    app.dependency_overrides[get_catalogue_reader] = lambda: type(
        "Reader", (), {"get_scenario_context": staticmethod(
            lambda _connection, _scenario_id: _scenario_context(site_id=session.site_id)
        )},
    )()
    repository = _ListRepository(ScheduleRunPageV1(items=(), next_cursor=100, total_count=250, matching_count=250))
    app.dependency_overrides[get_schedule_run_repository] = lambda: repository

    response = test_client.get(
        "/api/v1/schedule-runs",
        params={"scenario_id": str(scenario_id), "cursor": 50, "limit": 10},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json()["next_cursor"] == 100
    assert repository.calls == [
        {
            "scenario_id": scenario_id,
            "site_id": session.site_id,
            "cursor": 50,
            "limit": 10,
        }
    ]


def test_list_route_rejects_a_limit_beyond_the_bound(client) -> None:
    test_client, _, _ = client

    response = test_client.get(
        "/api/v1/schedule-runs",
        params={"scenario_id": str(uuid4()), "limit": 500},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 422


def test_list_route_reports_an_unknown_or_cross_site_scenario_as_not_found(
    client,
) -> None:
    test_client, _, _ = client
    app.dependency_overrides[get_catalogue_reader] = lambda: type(
        "Reader", (), {"get_scenario_context": staticmethod(lambda _c, _s: None)},
    )()

    response = test_client.get(
        "/api/v1/schedule-runs",
        params={"scenario_id": str(uuid4())},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "scenario_not_found"
