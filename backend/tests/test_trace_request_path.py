"""Story 5.9 AC2, end to end: one conversation, one trace; runs joinable by ID.

The real `api.main.app`, a throwaway PostgreSQL database bootstrapped the way a
developer's is, fake OIDC and CSRF, the keyless deterministic model, and the
real worker `run_once` -- every span read from what the REAL `OTLPSpanExporter`
posted (tests/trace_capture.py), never from an in-memory provider.

What this proves:

* a turn's request, agent and database spans, and the SSE stream, share one
  trace whose ID IS the conversation UUID;
* a hostile `traceparent`/`tracestate`/`baggage` is discarded on a
  conversation route, a non-conversation route and an auth route;
* `invoke_agent` carries `shiftmind.agent_run.id`/`site.id`/`conversation.id`;
* the enqueueing request and the worker's job trace share
  `shiftmind.schedule_run.id` (API->worker stays two traces, F3);
* an SSE connection exports exactly one span, `/health` none, an idle
  `run_once` none.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.solver_input import PostgresSolverInputSource
from adapters.telemetry.spans import trace_engine, traced_scheduler
from api.deps import set_process_tracing
from api.main import _SSE_ROUTE_TEMPLATES, app
from api.tracing import install_api_tracing, quiet_parent_span_names
from engine.governed_adapter import GovernedSchedulerAdapter
from evals.live_conversations.http_client import ApplicationConversation
from scripts.bootstrap_local import bootstrap_local
from settings import default_settings
from tests.compose_proof import _create_deterministic_draft
from tests.trace_capture import capture_tracing, exported_spans, flush
from worker.lease_worker import run_once

pytestmark = pytest.mark.postgres

ORIGIN = "http://shiftmind.test"
HOSTILE_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
HOSTILE_HEADERS = {
    "traceparent": f"00-{HOSTILE_TRACE_ID}-00f067aa0ba902b7-01",
    "tracestate": "canary=CANARY-TRACESTATE-5-9",
    "baggage": "canary=CANARY-BAGGAGE-5-9",
}
SERVER_KIND = 2


@pytest.fixture
def traced_stack(fresh_postgres_database_url, monkeypatch, tmp_path):
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
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_SUBJECT", "local-planner")
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_EMAIL", "planner@shiftmind.local")
    monkeypatch.setenv("ROSTERAI_DATABASE_URL", login)
    monkeypatch.setenv("ROSTERAI_PROVISIONING_DATABASE_URL", provisioning)
    monkeypatch.setenv("ROSTERAI_MAINTENANCE_FLAG", str(tmp_path / "maintenance.flag"))
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.sqlite3"))
    # A short, still-real CP-SAT solve.
    monkeypatch.setenv("SOLVER_WALL_TIME_LIMIT_SECONDS", "5")
    monkeypatch.setenv("SOLVER_MAX_DETERMINISTIC_TIME", "5")
    settings = replace(
        default_settings(),
        provisioning_database_url=provisioning,
        database_url=provisioning,
    )
    bootstrap_local(settings=settings)

    api_tracing, api_session = capture_tracing(
        service_name="shiftmind-api",
        quiet_parent_span_names=quiet_parent_span_names(_SSE_ROUTE_TEMPLATES),
    )
    worker_tracing, worker_session = capture_tracing(service_name="shiftmind-worker")
    undo = install_api_tracing(app, api_tracing)
    # The API engines are cached per URL; this throwaway URL is new, so they
    # are built -- and traced -- after tracing is installed (Decision 8).
    set_process_tracing(api_tracing)
    worker_engine = trace_engine(create_engine(login, hide_parameters=True), worker_tracing)
    try:
        yield SimpleNamespace(
            api_tracing=api_tracing,
            api_session=api_session,
            worker_tracing=worker_tracing,
            worker_session=worker_session,
            worker_engine=worker_engine,
            login_url=login,
        )
    finally:
        undo()
        set_process_tracing(None)
        worker_engine.dispose()
        api_tracing.shutdown()
        worker_tracing.shutdown()


async def _sse_for(path: str, cookie: str, seconds: float) -> list[dict]:
    """Drive the SSE route at the ASGI boundary, then disconnect."""
    sent: list[dict] = []
    requested = False

    async def receive() -> dict:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(seconds)
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"shiftmind.test"),
            (b"cookie", cookie.encode("latin-1")),
            *((name.encode(), value.encode()) for name, value in HOSTILE_HEADERS.items()),
        ],
        "client": ("198.51.100.7", 50000),
        "server": ("shiftmind.test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    return sent


def test_one_conversation_is_one_trace_and_runs_join_by_id(traced_stack) -> None:
    worker_tracing = traced_stack.worker_tracing
    repository = PostgresScheduleRunRepository()
    scheduler = traced_scheduler(
        lambda connection: GovernedSchedulerAdapter(PostgresSolverInputSource(connection)),
        worker_tracing,
    )

    # An idle poll exports nothing: its statements are root CLIENT spans.
    assert run_once(
        traced_stack.worker_engine, repository, scheduler,
        lease_owner="trace-idle", lease_seconds=120, tracing=worker_tracing,
    ) is None
    flush(worker_tracing)
    assert exported_spans(traced_stack.worker_session) == []

    # Other modules set `models.ALLOW_MODEL_REQUESTS = False` at import. The
    # model here is the keyless deterministic FunctionModel -- no network.
    with models.override_allow_model_requests(True), TestClient(
        app, base_url=ORIGIN, follow_redirects=False
    ) as client:
        assert client.get("/health", headers=HOSTILE_HEADERS).status_code == 200
        planner = ApplicationConversation(ORIGIN, client=client)
        session = planner.login()
        planner.headers.update(HOSTILE_HEADERS)
        conversation = planner.create("sample_tiny_input")
        conversation_id = UUID(conversation["id"])
        accepted, executed = planner.send("What does this scenario cover?")
        assert executed["agent_run_status"] == "agent_completed"
        tasks = planner.projection("work-areas-and-tasks", limit=1)

        proposal = _create_deterministic_draft(
            database_url=traced_stack.login_url,
            site_id=UUID(session["site_id"]),
            actor_id=UUID(session["app_user_id"]),
            conversation_id=conversation_id,
            scenario_id=UUID(planner.fixture["scenario_id"]),
            scenario_version_id=UUID(planner.fixture["scenario_version_id"]),
            task_record_id=tasks["items"][0]["record_id"],
        )
        started = planner._request(
            "POST", "/api/v1/schedule-runs", command=True,
            body={"proposal_id": str(proposal.proposal_id), "expected_resource_version": 1},
        )
        run_id = started["schedule_run_id"]
        cookie = planner.headers["Cookie"]

    asyncio.run(_sse_for(f"/api/v1/conversations/{conversation_id}/events", cookie, 1.5))

    outcome = run_once(
        traced_stack.worker_engine, repository, scheduler,
        lease_owner="trace-worker", lease_seconds=120, tracing=worker_tracing,
    )
    assert outcome is not None and str(outcome.schedule_run_id) == run_id
    flush(traced_stack.api_tracing)
    flush(worker_tracing)

    api_spans = exported_spans(traced_stack.api_session)
    worker_spans = exported_spans(traced_stack.worker_session)
    conversation_trace = conversation_id.hex

    # --- one conversation, one trace ---------------------------------------
    def server(name: str) -> list:
        return [s for s in api_spans if s.kind == SERVER_KIND and s.name == name]

    messages = server("POST /api/v1/conversations/{conversation_id}/messages")
    execute = server(
        "POST /api/v1/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute"
    )
    sse = server("GET /api/v1/conversations/{conversation_id}/events")
    assert len(messages) == 1 and len(execute) == 1 and len(sse) == 1
    for span in (*messages, *execute, *sse):
        assert span.trace_id == conversation_trace
    agent = [s for s in api_spans if s.scope == "pydantic-ai"]
    assert {s.name.split(" ")[0] for s in agent} >= {"invoke_agent", "chat", "execute_tool"}
    assert {s.trace_id for s in agent} == {conversation_trace}
    database_in_turn = [
        s for s in api_spans
        if s.scope == "opentelemetry.instrumentation.sqlalchemy"
        and s.trace_id == conversation_trace
    ]
    assert database_in_turn, "no database span joined the conversation trace"

    # --- client trace context is discarded on every route ------------------
    assert HOSTILE_TRACE_ID not in {s.trace_id for s in api_spans}
    scenarios = server("GET /api/v1/scenarios")
    session_spans = server("GET /api/v1/auth/session")
    assert scenarios and session_spans
    assert all(s.parent_span_id == "" for s in (*scenarios, *session_spans))

    # --- the agent root carries ShiftMind's run identifiers ----------------
    [invoke] = [s for s in agent if s.name.startswith("invoke_agent")]
    assert invoke.attributes["shiftmind.agent_run.id"] == accepted["agent_run_id"]
    assert invoke.attributes["shiftmind.conversation.id"] == str(conversation_id)
    assert invoke.attributes["shiftmind.site.id"] == session["site_id"]

    # --- the enqueue span and the worker's job trace share the run ID ------
    [enqueue] = server("POST /api/v1/schedule-runs")
    assert enqueue.attributes["shiftmind.schedule_run.id"] == run_id
    [root] = [s for s in worker_spans if s.name == "shiftmind.worker.execute"]
    assert root.parent_span_id == ""
    assert root.attributes["shiftmind.schedule_run.id"] == run_id
    assert root.attributes["shiftmind.schedule_run.status"] == outcome.status
    assert root.trace_id != enqueue.trace_id  # two traces, joined by attribute (F3)
    children = {s.name: s for s in worker_spans if s.parent_span_id == root.span_id}
    assert {"shiftmind.worker.lease", "shiftmind.worker.solve"} <= set(children)
    assert children["shiftmind.worker.solve"].attributes["shiftmind.schedule_run.id"] == run_id
    assert children["shiftmind.worker.solve"].attributes["shiftmind.solver.status"]
    assert {s.trace_id for s in worker_spans} == {root.trace_id}
    assert all(s.resource["service.name"] == "shiftmind-worker" for s in worker_spans)
    assert all(s.resource["service.name"] == "shiftmind-api" for s in api_spans)

    # --- noise ------------------------------------------------------------
    [stream] = sse
    assert not [s for s in api_spans if s.parent_span_id == stream.span_id]
    assert not [s for s in api_spans if "/health" in s.name]
    assert not [s for s in api_spans if s.name.endswith((" http send", " http receive"))]
