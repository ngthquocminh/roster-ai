"""Story 5.9 AC5: a broken Logfire never changes product work or blocks it.

Every case runs the REAL `OTLPSpanExporter` class against one of three
fixtures (Decision 12):

* unreachable -- a port that was bound and closed;
* slow        -- a local server that holds each export for 30 s;
* rejected    -- a local server answering 401.

Non-vacuity comes from a counting `requests.Session` passed as `session=`: it
forwards to the real network and counts what the exporter attempted, so a case
cannot pass because nothing was ever exported.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
import requests
from pydantic_ai import models
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from adapters.telemetry.spans import (
    MAX_QUEUE_SIZE,
    SHUTDOWN_DEADLINE_SECONDS,
    build_process_tracing,
    trace_engine,
    traced_scheduler,
)
from agent.runtime import PydanticAIAgentRuntime
from application.contracts.grounding import GroundedAnswerV1
from settings import default_settings
from tests.test_content_minimization import (
    PINNED_INJECTION_CASES,
    _sanitized_stream,
)
from tests.trace_capture import (
    TOKEN_CANARY,
    exported_spans,
    flush,
)
from tests.trace_capture import closed_port as _closed_port
from tests.trace_capture import fixture_server as _server

class CountingSession(requests.Session):
    """Forwards to the real network; counts every export attempt."""

    def __init__(self) -> None:
        super().__init__()
        self.posts = 0

    def post(self, *args, **kwargs):  # type: ignore[override]
        self.posts += 1
        return super().post(*args, **kwargs)


@contextmanager
def failing_tracing(kind: str, *, service_name: str = "shiftmind-test", **kwargs):
    """Real process tracing whose exporter targets one broken Logfire."""
    session = CountingSession()

    @contextmanager
    def endpoint():
        if kind == "unreachable":
            yield f"http://127.0.0.1:{_closed_port()}"
        else:
            with _server(kind) as url:
                yield url

    with endpoint() as base_url:
        settings = replace(
            default_settings(), logfire_token=TOKEN_CANARY, logfire_base_url=base_url
        )
        tracing = build_process_tracing(
            settings, service_name=service_name, session=session, **kwargs
        )
        assert tracing is not None
        try:
            yield tracing, session
        finally:
            tracing.shutdown()


FIXTURES = ("unreachable", "slow", "rejected")


def _export_in_background(tracing) -> threading.Thread:
    """Start an export the exporter will hold (the slow server's 30 s)."""
    with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
        pass
    worker = threading.Thread(target=tracing.provider.force_flush, args=(30_000,), daemon=True)
    worker.start()
    return worker


@pytest.mark.parametrize("kind", FIXTURES)
def test_requests_never_wait_for_the_exporter(kind) -> None:
    from fastapi.testclient import TestClient

    from api.deps import get_identity_store
    from api.main import app
    from api.tracing import install_api_tracing
    from tests.test_content_minimization import _NoSessions

    with failing_tracing(kind) as (tracing, session):
        undo = install_api_tracing(app, tracing)
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[get_identity_store] = lambda: _NoSessions()
        try:
            _export_in_background(tracing)
            time.sleep(0.2)  # the exporter is now inside its POST
            with TestClient(app, base_url="http://shiftmind.test") as client:
                for _ in range(10):
                    started = time.monotonic()
                    assert client.get("/api/v1/scenarios").status_code == 401
                    assert time.monotonic() - started < 2.0
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
            undo()
        assert session.posts >= 1


@pytest.mark.parametrize("kind", FIXTURES)
def test_ending_spans_only_enqueues_and_a_full_queue_drops(kind) -> None:
    with failing_tracing(kind) as (tracing, session):
        _export_in_background(tracing)
        tracer = tracing.tracer("shiftmind.proof")
        started = time.monotonic()
        with tracer.start_as_current_span("shiftmind.proof"):
            for _ in range(5000):
                with tracer.start_as_current_span("shiftmind.proof.child"):
                    pass
        assert time.monotonic() - started < 1.0
        assert session.posts >= 1


@pytest.mark.parametrize("kind", FIXTURES)
def test_shutdown_is_bounded(kind) -> None:
    with failing_tracing(kind) as (tracing, session):
        _export_in_background(tracing)
        with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
            pass
        started = time.monotonic()
        tracing.shutdown()
        assert time.monotonic() - started < SHUTDOWN_DEADLINE_SECONDS + 1.0
        assert session.posts >= 1


@pytest.mark.parametrize("kind", FIXTURES)
def test_shutdown_is_bounded_with_a_full_queue(kind) -> None:
    """SDK 1.44's `force_flush` ignores its timeout and drains the WHOLE queue
    synchronously: four 512-span batches at a 5 s deadline each is ~20 s
    against a broken collector, past the API's 10 s stop grace. Shutdown must
    return by its own deadline anyway (code review 2026-09-24)."""
    with failing_tracing(kind) as (tracing, session):
        tracer = tracing.tracer("shiftmind.proof")
        for _ in range(MAX_QUEUE_SIZE):
            with tracer.start_as_current_span("shiftmind.proof"):
                pass
        started = time.monotonic()
        tracing.shutdown()
        assert time.monotonic() - started < SHUTDOWN_DEADLINE_SECONDS + 1.0
        assert session.posts >= 1


def test_a_rejected_token_logs_a_third_party_error_without_the_token() -> None:
    with _sanitized_stream(
        "opentelemetry", "opentelemetry.exporter", "opentelemetry.exporter.otlp",
        "opentelemetry.exporter.otlp.proto", "opentelemetry.exporter.otlp.proto.http",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    ) as (sanitized, stderr):
        with failing_tracing("rejected") as (tracing, session):
            with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
                pass
            tracing.provider.force_flush(10_000)
            assert session.posts >= 1
    lines = [json.loads(line) for line in sanitized.getvalue().splitlines() if line]
    assert any(
        line["level"] == "ERROR" and line["event"] == "third_party" for line in lines
    ), lines
    assert TOKEN_CANARY not in sanitized.getvalue()
    assert TOKEN_CANARY not in stderr.getvalue()


# --- product outcomes -------------------------------------------------------


def _verdicts(provider) -> list[tuple[str, bool, str]]:
    """Four pinned injection cases and one grounding case, scored for real."""
    from pathlib import Path

    from application.capabilities.installed import installed_modules
    from evals import report
    from evals.cases import load_cases

    golden = Path(report.__file__).resolve().parent / "golden"
    cases = load_cases(golden)
    pinned = [case for case in cases if case.case_id in PINNED_INJECTION_CASES]
    grounding = [case for case in cases if case.expected_grounding_outcome][:1]
    assert len(pinned) == 4 and len(grounding) == 1
    verdicts = []
    for case in (*pinned, *grounding):
        results: list[object] = []
        if provider is None:
            runtime = report._runtime_for_case(case, installed_modules(), results)
        else:
            # `_runtime_for_case`'s own selection and wiring, plus the provider.
            wanted = report.EVAL_TAG_TO_CAPABILITY.get(case.capability, case.capability)
            runtime = PydanticAIAgentRuntime(
                model=report.build_model_double(case),
                capabilities=tuple(
                    module for module in installed_modules()
                    if module.manifest.capability_name == wanted
                ),
                deps=report._report_deps(results),
                answer_type=GroundedAnswerV1 if report._needs_named_output_tools(case) else None,
                tracer_provider=provider,
            )
        with runtime_root(provider):
            outcome = report._run_runtime_case(runtime, case)
        verdict, _ = report._evaluate_case(
            case, runtime, outcome, results, run_source="deterministic_double"
        )
        verdicts.append((case.case_id, verdict.passed, verdict.reason))
    return verdicts


@contextmanager
def runtime_root(provider):
    if provider is None:
        yield
        return
    with provider.get_tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
        yield


@pytest.mark.parametrize("kind", FIXTURES)
def test_eval_verdicts_are_identical_with_a_failing_exporter(kind) -> None:
    without = _verdicts(None)
    with failing_tracing(kind) as (tracing, session):
        with_failing = _verdicts(tracing.provider)
        tracing.provider.force_flush(1_000)
        assert session.posts >= 1
    assert with_failing == without


def test_worker_job_outcome_is_identical_with_a_failing_exporter() -> None:
    """A fake repository through the REAL job scope and scheduler wrapper."""
    from adapters.telemetry.spans import traced_worker_job
    from tests.test_content_minimization import _LeaseOnce

    class Scheduler:
        def solve(self, _snapshot):
            return SimpleNamespace(solver_status="FEASIBLE", wall_time_seconds=0.1)

    def job(tracing):
        with traced_worker_job(_LeaseOnce(), tracing) as scope:
            lease = scope.repository.lease_next_job()
            outcome = traced_scheduler(Scheduler(), tracing).solve(
                SimpleNamespace(schedule_run_id=lease.schedule_run_id)
            )
            result = (lease.schedule_run_id, outcome.solver_status)
            scope.finish(SimpleNamespace(status="solver_completed"))
            return result

    baseline = job(None)
    for kind in FIXTURES:
        with failing_tracing(kind, service_name="shiftmind-worker") as (tracing, session):
            assert job(tracing) == baseline
            tracing.provider.force_flush(1_000)
            assert session.posts >= 1


def test_a_failing_trace_call_never_costs_the_lease_or_the_solve() -> None:
    """AD-12: the worker's tracing runs INSIDE the product path -- after the
    database lease and after the solve -- so a failure there must cost the
    span, never the job (code review 2026-09-24)."""
    from adapters.telemetry.spans import traced_worker_job
    from tests.test_content_minimization import _LeaseOnce
    from tests.trace_capture import capture_tracing

    class NaiveLease(_LeaseOnce):
        def lease_next_job(self, *args, **kwargs):
            # `JobLeaseV1` refuses a naive timestamp, so stand in for any lease
            # whose shape the span code does not expect: a naive `created_at`
            # makes the queue-age subtraction raise.
            lease = super().lease_next_job(*args, **kwargs)
            return SimpleNamespace(**{**vars(lease), "created_at": datetime(2026, 1, 1)})

    class Unreadable:
        solver_status = "FEASIBLE"
        wall_time_seconds = None  # typed float, not enforced

    class Scheduler:
        def solve(self, _snapshot):
            return Unreadable()

    tracing, session = capture_tracing(service_name="shiftmind-worker")
    try:
        with traced_worker_job(NaiveLease(), tracing) as scope:
            lease = scope.repository.lease_next_job()
            outcome = traced_scheduler(Scheduler(), tracing).solve(
                SimpleNamespace(schedule_run_id=lease.schedule_run_id)
            )
            scope.finish(SimpleNamespace(status="solver_completed"))
        flush(tracing)
    finally:
        tracing.shutdown()
    assert lease.schedule_run_id == UUID(int=15)
    assert isinstance(outcome, Unreadable)
    # Nothing was left open: the solve span still exported, as a root of its
    # own because the job's root was abandoned.
    assert [span.name for span in exported_spans(session)] == ["shiftmind.worker.solve"]


# --- the whole path, against PostgreSQL ------------------------------------


@pytest.mark.postgres
@pytest.mark.parametrize("kind", FIXTURES)
def test_turn_and_solver_outcomes_are_unchanged_by_a_failing_exporter(
    kind, fresh_postgres_database_url, monkeypatch, tmp_path
) -> None:
    """A deterministic turn through the API and a real worker job, twice each:
    tracing off, then tracing on against a broken Logfire. Same outcomes."""
    from fastapi.testclient import TestClient

    from adapters.postgres.schedule_run import PostgresScheduleRunRepository
    from adapters.postgres.solver_input import PostgresSolverInputSource
    from api.deps import set_process_tracing
    from api.main import app
    from api.tracing import install_api_tracing
    from engine.governed_adapter import GovernedSchedulerAdapter
    from evals.live_conversations.http_client import ApplicationConversation
    from scripts.bootstrap_local import bootstrap_local
    from tests.compose_proof import _create_deterministic_draft
    from worker.lease_worker import run_once

    provisioning = fresh_postgres_database_url
    login = (
        make_url(provisioning)
        .set(username="shiftmind_login", password="shiftmind_login")
        .render_as_string(hide_password=False)
    )
    # Keyless by construction: a developer's backend/.env may select a live
    # agent model, and this test lifts ALLOW_MODEL_REQUESTS for the
    # deterministic FunctionModel -- so pin that model and drop any key.
    monkeypatch.setenv("AGENT_RUNTIME_MODEL", "deterministic")
    monkeypatch.delenv("AGENT_RUNTIME_API_KEY", raising=False)
    assert default_settings().agent_runtime_model == "deterministic"
    for name, value in {
        "SHIFTMIND_SEED_PLANNER_SUBJECT": "local-planner",
        "SHIFTMIND_SEED_PLANNER_EMAIL": "planner@shiftmind.local",
        "ROSTERAI_DATABASE_URL": login,
        "ROSTERAI_PROVISIONING_DATABASE_URL": provisioning,
        "ROSTERAI_MAINTENANCE_FLAG": str(tmp_path / "maintenance.flag"),
        "ROSTERAI_DB": str(tmp_path / "legacy.sqlite3"),
        "SOLVER_WALL_TIME_LIMIT_SECONDS": "5",
        "SOLVER_MAX_DETERMINISTIC_TIME": "5",
    }.items():
        monkeypatch.setenv(name, value)
    bootstrap_local(
        settings=replace(
            default_settings(), provisioning_database_url=provisioning, database_url=provisioning
        )
    )
    engine = create_engine(login, hide_parameters=True)

    def turn_and_job(client, planner, session, tracing) -> tuple:
        accepted, executed = planner.send("What does this scenario cover?")
        tasks = planner.projection("work-areas-and-tasks", limit=1)
        proposal = _create_deterministic_draft(
            database_url=login,
            site_id=UUID(session["site_id"]),
            actor_id=UUID(session["app_user_id"]),
            conversation_id=UUID(planner.conversation["id"]),
            scenario_id=UUID(planner.fixture["scenario_id"]),
            scenario_version_id=UUID(planner.fixture["scenario_version_id"]),
            task_record_id=tasks["items"][0]["record_id"],
        )
        started = time.monotonic()
        queued = planner._request(
            "POST", "/api/v1/schedule-runs", command=True,
            body={"proposal_id": str(proposal.proposal_id), "expected_resource_version": 1},
        )
        assert time.monotonic() - started < 2.0 or tracing is None
        outcome = run_once(
            trace_engine(engine, tracing) if tracing else engine,
            PostgresScheduleRunRepository(),
            traced_scheduler(
                lambda connection: GovernedSchedulerAdapter(PostgresSolverInputSource(connection)),
                tracing,
            ),
            lease_owner="failure-independence",
            lease_seconds=60,
            tracing=tracing,
        )
        run = planner._request("GET", f"/api/v1/schedule-runs/{queued['schedule_run_id']}")
        return (
            executed["agent_run_status"],
            executed["activity"]["activity_type"],
            queued["status"],
            outcome.status,
            run["status"],
        )

    try:
        with models.override_allow_model_requests(True), TestClient(
            app, base_url="http://shiftmind.test", follow_redirects=False
        ) as client:
            planner = ApplicationConversation("http://shiftmind.test", client=client)
            session = planner.login()
            planner.create("sample_tiny_input")
            off = turn_and_job(client, planner, session, None)

            with failing_tracing(kind, service_name="shiftmind-api") as (tracing, exports):
                undo = install_api_tracing(app, tracing)
                set_process_tracing(tracing)
                try:
                    on = turn_and_job(client, planner, session, tracing)
                finally:
                    undo()
                    set_process_tracing(None)
                tracing.provider.force_flush(1_000)
                assert exports.posts >= 1
    finally:
        engine.dispose()

    assert off == on
    # A real turn and a real terminal solve (the 5 s budget may time out; the
    # claim is equality with tracing off, and that the worker's outcome is the
    # one persisted).
    assert off[0] == "agent_completed"
    assert off[3] == off[4] and off[3] != "solver_failed"
