"""Story 5.9 Tasks 4-5: the export-boundary policy and its OpenTelemetry wiring.

Unit tests built from the MEASURED samples in the story's allow-list tables --
one per transform, per event rule, per category's drop set -- plus the
sanitizing exporter, sampler, propagator and keyless construction, observed
through the real `OTLPSpanExporter` (tests/trace_capture.py).
"""
from __future__ import annotations

import json
import os
import typing
from uuid import uuid4

import pytest
from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from adapters.telemetry import span_policy
from adapters.telemetry.span_policy import (
    AGENT,
    DATABASE,
    HTTP_CLIENT,
    HTTP_SERVER,
    OTHER,
    WORKER,
    categorize,
    sanitize_attributes,
    sanitize_event,
    sanitize_resource,
)
from adapters.telemetry.spans import (
    ExtractOnlyTraceContext,
    SanitizingSpanExporter,
    build_process_tracing,
)
from settings import TRACE_CONTENT_SYNTHETIC_EVAL, default_settings
from tests.trace_capture import capture_tracing, exported_spans, flush, payload_text

ON = TRACE_CONTENT_SYNTHETIC_EVAL
UUID_SAMPLE = "3b52c7b4-6c0a-4f5e-9d0e-8a7b6c5d4e3f"


def _off(category: str, attributes: dict) -> dict:
    return sanitize_attributes(category, attributes, content_mode="off", content_mode_on=ON)


def _on(category: str, attributes: dict) -> dict:
    return sanitize_attributes(category, attributes, content_mode=ON, content_mode_on=ON)


# --- categories --------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "category"),
    [
        ("opentelemetry.instrumentation.fastapi", HTTP_SERVER),
        ("opentelemetry.instrumentation.asgi", HTTP_SERVER),
        ("opentelemetry.instrumentation.httpx", HTTP_CLIENT),
        ("opentelemetry.instrumentation.sqlalchemy", DATABASE),
        ("pydantic-ai", AGENT),
        ("shiftmind.worker", WORKER),
        ("some.future.library", OTHER),
        (None, OTHER),
    ],
)
def test_category_comes_from_the_instrumentation_scope(scope, category) -> None:
    assert categorize(scope) == category


def test_an_unknown_scope_exports_no_attributes_at_all() -> None:
    assert _off(OTHER, {"http.method": "GET", "anything": "CANARY"}) == {}
    assert _on(OTHER, {"gen_ai.tool.call.arguments": "CANARY"}) == {}


# --- HTTP server -------------------------------------------------------------

_MEASURED_SERVER = {
    "http.method": "POST",
    "http.route": "/api/v1/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute",
    "http.status_code": 200,
    "http.scheme": "http",
    "http.flavor": "1.1",
    "net.host.port": 80,
    "http.target": (
        f"/api/v1/conversations/{UUID_SAMPLE}/agent-runs/{UUID_SAMPLE}/execute"
        "?probe=CANARY-QUERY-5-9#frag"
    ),
    "http.url": "http://shiftmind.test/api/v1/conversations?scenario_id=x&probe=CANARY-QUERY-5-9",
    "http.host": "shiftmind.test",
    "http.server_name": "shiftmind.test",
    "http.user_agent": "testclient",
    "net.peer.ip": "198.51.100.7",
    "net.peer.port": 50000,
    "http.request.header.cookie": ("CANARY-COOKIE",),
    "http.response.header.set_cookie": ("CANARY-COOKIE",),
}


def test_http_server_keeps_the_allow_list_and_cuts_the_target_query() -> None:
    kept = _off(HTTP_SERVER, _MEASURED_SERVER)
    assert kept == {
        "http.method": "POST",
        "http.route": _MEASURED_SERVER["http.route"],
        "http.status_code": 200,
        "http.scheme": "http",
        "http.flavor": "1.1",
        "net.host.port": 80,
        "http.target": f"/api/v1/conversations/{UUID_SAMPLE}/agent-runs/{UUID_SAMPLE}/execute",
    }
    # Content mode widens nothing outside the agent category.
    assert _on(HTTP_SERVER, _MEASURED_SERVER) == kept


def test_http_server_drops_the_target_of_an_unmatched_route() -> None:
    """An unmatched route's raw path is client free text (measured fact 5)."""
    kept = _off(HTTP_SERVER, {"http.method": "GET", "http.target": "/CANARY-PATH-5-9"})
    assert kept == {"http.method": "GET"}


@pytest.mark.parametrize(
    "target",
    [
        # Observed in hosted Logfire at code review: Starlette matched the
        # route before FastAPI rejected the non-UUID segment.
        "/api/v1/conversations/IGNORE-PREVIOUS-INSTRUCTIONS-CANARY/messages",
        # A decoded `%2F` becomes an extra segment.
        f"/api/v1/conversations/{UUID_SAMPLE}/CANARY/messages",
        f"/api/v1/conversations/{UUID_SAMPLE}/messages/CANARY",
        f"/api/v1/CANARY/{UUID_SAMPLE}/messages",
    ],
)
def test_http_server_drops_a_matched_route_target_carrying_free_text(target) -> None:
    route = "/api/v1/conversations/{conversation_id}/messages"
    kept = _off(HTTP_SERVER, {"http.route": route, "http.target": target})
    assert kept == {"http.route": route}


@pytest.mark.parametrize(
    ("route", "target"),
    [
        ("/api/v1/conversations/{conversation_id}/messages",
         f"/api/v1/conversations/{UUID_SAMPLE.upper()}/messages"),
        ("/runs/{run_id}", "/runs/42"),
        ("/api/v1/scenarios", "/api/v1/scenarios"),
    ],
)
def test_http_server_keeps_a_target_of_template_segments_and_identifiers(route, target) -> None:
    kept = _off(HTTP_SERVER, {"http.route": route, "http.target": f"{target}?q=CANARY"})
    assert kept["http.target"] == target


def test_the_schedule_run_join_key_must_be_a_uuid() -> None:
    assert _off(HTTP_SERVER, {"shiftmind.schedule_run.id": UUID_SAMPLE}) == {
        "shiftmind.schedule_run.id": UUID_SAMPLE
    }
    assert _off(HTTP_SERVER, {"shiftmind.schedule_run.id": "CANARY-not-a-uuid"}) == {}


# --- HTTP client -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "http://127.0.0.1:58645/v1?probe=CANARY-QUERY-5-9/chat/completions",
            "http://127.0.0.1:58645/v1",
        ),
        (
            "https://user:CANARY-PASS@openrouter.ai/api/v1/chat/completions#CANARY",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
        ("not a url", None),
    ],
)
def test_http_client_url_keeps_origin_and_path_only(raw, expected) -> None:
    kept = _off(HTTP_CLIENT, {"http.method": "POST", "http.url": raw, "http.status_code": 200})
    assert kept.get("http.url") == expected
    assert kept["http.method"] == "POST" and kept["http.status_code"] == 200


# --- database ----------------------------------------------------------------


def test_database_drops_the_login_and_topology() -> None:
    kept = _off(DATABASE, {
        "db.system": "postgresql",
        "db.name": "rosterai",
        "db.operation": "SELECT rosterai",
        "db.statement": "SELECT set_config('app.site_id', %(site_id)s, true)",
        "db.user": "shiftmind_login",
        "net.peer.name": "localhost",
        "net.peer.port": 5432,
    })
    assert set(kept) == {"db.system", "db.name", "db.operation", "db.statement"}


# --- agent -------------------------------------------------------------------


def test_message_structure_projection_keeps_role_and_part_shape_only() -> None:
    raw = json.dumps([
        {"role": "user", "parts": [{"type": "text", "content": "CANARY-PROMPT"}]},
        {
            "role": "assistant",
            "finish_reason": "stop",
            "parts": [{
                "type": "tool_call", "id": "c1", "name": "scheduling_inspect",
                "arguments": {"q": "CANARY-ARGS"},
            }],
        },
    ])
    kept = _off(AGENT, {"gen_ai.input.messages": raw, "pydantic_ai.all_messages": raw})
    assert json.loads(kept["gen_ai.input.messages"]) == [
        {"role": "user", "parts": [{"type": "text"}]},
        {"role": "assistant", "parts": [{"type": "tool_call", "id": "c1", "name": "scheduling_inspect"}]},
    ]
    assert "CANARY" not in json.dumps(kept)
    assert _off(AGENT, {"gen_ai.output.messages": "not json"}) == {}
    assert _off(AGENT, {"gen_ai.output.messages": json.dumps({"role": "x"})}) == {}


def test_model_request_parameters_lose_instruction_parts() -> None:
    """Measured fact 3: the static system prompt rides this key in default mode."""
    raw = json.dumps({
        "function_tools": [{"name": "scheduling_inspect"}],
        "output_mode": "tool",
        "instruction_parts": [{"content": "CANARY-INSTRUCTIONS"}],
    })
    kept = json.loads(_off(AGENT, {"model_request_parameters": raw})["model_request_parameters"])
    assert kept == {"function_tools": [{"name": "scheduling_inspect"}], "output_mode": "tool"}


def test_content_mode_keys_pass_only_in_synthetic_eval() -> None:
    content = {key: "CANARY-CONTENT" for key in span_policy.AGENT_CONTENT_MODE_KEYS}
    assert _off(AGENT, content) == {}
    assert _on(AGENT, content) == content
    assert "invented-mode" != ON
    assert sanitize_attributes(AGENT, content, content_mode="invented-mode", content_mode_on=ON) == {}


def test_content_mode_passes_messages_as_emitted() -> None:
    raw = json.dumps([{"role": "user", "parts": [{"type": "text", "content": "hi"}]}])
    assert _on(AGENT, {"gen_ai.input.messages": raw}) == {"gen_ai.input.messages": raw}


def test_agent_numeric_and_correlation_keys_are_shape_validated() -> None:
    kept = _off(AGENT, {
        "gen_ai.usage.input_tokens": 133,
        "gen_ai.usage.output_tokens": 7,
        "gen_ai.usage.details.reasoning_tokens": 3,
        "gen_ai.aggregated_usage.input_tokens": 337,
        "gen_ai.request.temperature": 0.2,
        "gen_ai.usage.cache_read.input_tokens": True,  # a bool is not a count
        "gen_ai.request.seed": "CANARY",
        "shiftmind.agent_run.id": UUID_SAMPLE,
        "shiftmind.site.id": "CANARY-SITE",
        "gen_ai.agent.description": "CANARY-DESCRIPTION",
        "metadata": "CANARY-METADATA",
        "tool_arguments": "CANARY",
        "tool_response": "CANARY",
    })
    assert kept == {
        "gen_ai.usage.input_tokens": 133,
        "gen_ai.usage.output_tokens": 7,
        "gen_ai.usage.details.reasoning_tokens": 3,
        "gen_ai.aggregated_usage.input_tokens": 337,
        "gen_ai.request.temperature": 0.2,
        "shiftmind.agent_run.id": UUID_SAMPLE,
    }


# --- worker ------------------------------------------------------------------


def test_worker_vocabularies_are_the_application_contracts() -> None:
    from application.contracts.job_lease import JobTypeV1
    from application.contracts.schedule_version import ScheduleRunStatusV1, SolverStatusV1

    assert span_policy.SCHEDULE_RUN_STATUSES == set(typing.get_args(ScheduleRunStatusV1))
    assert span_policy.SOLVER_STATUSES == set(typing.get_args(SolverStatusV1))
    assert span_policy.JOB_TYPES == set(typing.get_args(JobTypeV1))


def test_worker_keys_are_closed_vocabularies_uuids_and_numbers() -> None:
    kept = _off(WORKER, {
        "shiftmind.schedule_run.id": UUID_SAMPLE,
        "shiftmind.job.type": "schedule_run_execute",
        "shiftmind.schedule_run.status": "solver_completed",
        "shiftmind.solver.status": "FEASIBLE",
        "shiftmind.solver.wall_time_s": 10.08,
        "shiftmind.job.queue_age_s": 0.4,
        "shiftmind.job.id": "CANARY",
        "shiftmind.solver.reason": "CANARY-REASON",
    })
    assert kept == {
        "shiftmind.schedule_run.id": UUID_SAMPLE,
        "shiftmind.job.type": "schedule_run_execute",
        "shiftmind.schedule_run.status": "solver_completed",
        "shiftmind.solver.status": "FEASIBLE",
        "shiftmind.solver.wall_time_s": 10.08,
        "shiftmind.job.queue_age_s": 0.4,
    }
    assert _off(WORKER, {"shiftmind.schedule_run.status": "CANARY"}) == {}


# --- events, resource, drift -------------------------------------------------


def test_exception_events_keep_the_type_only_and_other_events_drop() -> None:
    assert sanitize_event("exception", {
        "exception.type": "RuntimeError",
        "exception.message": "upstream rejected CANARY-PROMPT-5-9",
        "exception.stacktrace": "Traceback ... CANARY",
        "exception.escaped": "False",
    }) == ("exception", {"exception.type": "RuntimeError"})
    assert sanitize_event("gen_ai.content.prompt", {"content": "CANARY"}) is None
    assert sanitize_event("exception", {}) == ("exception", {})


def test_resource_is_rebuilt_from_its_allow_list() -> None:
    raw = {
        "service.name": "shiftmind-api",
        "service.version": "0.1.0",
        "service.instance.id": "abc",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
        "telemetry.sdk.version": "1.44.0",
        "host.name": "CANARY-HOST",
        "process.command_line": "CANARY-ARGV",
        "deployment.environment": "live-eval",
    }
    off = sanitize_resource(raw, content_mode="off", content_mode_on=ON)
    assert set(off) == span_policy.RESOURCE_ALLOW
    on = sanitize_resource(raw, content_mode=ON, content_mode_on=ON)
    assert on["deployment.environment"] == "live-eval"
    assert sanitize_resource(
        {**raw, "deployment.environment": "production"}, content_mode=ON, content_mode_on=ON
    ).get("deployment.environment") is None


def test_a_new_key_names_itself() -> None:
    """The drift check's naming property. The check itself runs on OBSERVED,
    pre-sanitizer keys in every C4-C8 cell (`assert_raw_keys_classified`); a
    table checked against a hand-typed copy of itself proves nothing."""
    for category in (HTTP_SERVER, HTTP_CLIENT, DATABASE, AGENT, WORKER):
        assert span_policy.unclassified_keys(category, {"brand.new_key"}) == {"brand.new_key"}
    assert span_policy.unclassified_keys(HTTP_SERVER, {"http.request.header.cookie"}) == set()


# --- the exporter, sampler and propagator ----------------------------------


def test_the_test_process_has_no_process_tracing() -> None:
    """Decision 3: conftest pops the token, so the suite never exports."""
    import api.main
    from api.deps import get_process_tracing

    assert "LOGFIRE_TOKEN" not in os.environ
    assert "AGENT_TRACE_CONTENT_MODE" not in os.environ
    assert api.main._process_tracing is None
    assert get_process_tracing() is None


def test_keyless_settings_construct_nothing(monkeypatch) -> None:
    import adapters.telemetry.spans as spans

    def refuse(*_args, **_kwargs):
        raise AssertionError("an exporter was constructed without a token")

    monkeypatch.setattr(spans.OTLPSpanExporter, "__init__", refuse)
    before = propagate.get_global_textmap()
    assert build_process_tracing(default_settings(), service_name="shiftmind-api") is None
    assert propagate.get_global_textmap() is before


def test_the_exporter_is_built_from_settings_not_otel_env(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://CANARY-ENDPOINT")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-canary=CANARY-HEADER")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "canary.attr=CANARY-RESOURCE")
    tracing, session = capture_tracing(service_name="shiftmind-api")
    try:
        with tracing.tracer("shiftmind.worker").start_as_current_span("shiftmind.probe"):
            pass
        flush(tracing)
    finally:
        tracing.shutdown()
    [span] = exported_spans(session)
    assert span.resource["service.name"] == "shiftmind-api"
    assert set(span.resource) == span_policy.RESOURCE_ALLOW
    # The endpoint is the settings' Logfire origin, not the env's collector.
    assert session.urls_seen == [f"{default_settings().logfire_base_url}/v1/traces"]
    assert session.headers_seen[0]["Authorization"] == "CANARY-LOGFIRE-5-9"
    assert "x-canary" not in session.headers_seen[0]
    assert "CANARY-RESOURCE" not in payload_text(session)


def test_the_environment_cannot_choose_the_exporters_session_or_ca(monkeypatch) -> None:
    """With `session=None` (production) the OTLP exporter would load a session
    from the credential-provider variable, and take its CA bundle from
    `OTEL_EXPORTER_OTLP_CERTIFICATE` -- both decide who sees the token."""
    from dataclasses import replace

    import requests

    import adapters.telemetry.spans as spans

    monkeypatch.setenv(
        "_OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER", "canary-provider"
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CERTIFICATE", "/CANARY/ca.pem")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE", "/CANARY/ca.pem")
    tracing = build_process_tracing(
        replace(default_settings(), logfire_token="CANARY-LOGFIRE-5-9"),
        service_name="shiftmind-api",
    )
    assert tracing is not None
    try:
        exporter = tracing.provider._active_span_processor._span_processors[0].span_exporter
        inner = exporter._inner
        assert type(inner._session) is requests.Session
        assert inner._certificate_file is True
    finally:
        tracing.shutdown()
    assert isinstance(exporter, spans.SanitizingSpanExporter)


def test_the_sanitizer_strips_events_status_links_and_scope_on_real_spans() -> None:
    tracing, session = capture_tracing()
    try:
        tracer = tracing.provider.get_tracer("pydantic-ai")
        linked = trace.SpanContext(0xABC, 0xDEF, is_remote=False)
        with tracing.tracer("shiftmind.worker").start_as_current_span("shiftmind.root"):
            with tracer.start_as_current_span(
                "chat stub-model",
                links=[trace.Link(linked, {"CANARY-LINK": "x"})],
                attributes={"gen_ai.system": "openai", "prompt": "CANARY-PROMPT"},
            ) as span:
                span.record_exception(RuntimeError("upstream rejected CANARY-PROMPT-5-9"))
                span.add_event("gen_ai.choice", {"content": "CANARY-CHOICE"})
                span.set_status(Status(StatusCode.ERROR, "RuntimeError: CANARY-PROMPT-5-9"))
        flush(tracing)
    finally:
        tracing.shutdown()
    chat = next(s for s in exported_spans(session) if s.name == "chat stub-model")
    assert chat.attributes == {"gen_ai.system": "openai"}
    assert chat.events == [("exception", {"exception.type": "RuntimeError"})]
    assert chat.status_code == 2 and chat.status_message == ""
    assert chat.links == 0
    assert "CANARY" not in payload_text(session)


def test_a_sanitizer_failure_drops_the_batch_and_never_raises() -> None:
    exported = []

    class Inner:
        def export(self, spans):
            exported.extend(spans)

    class Unreadable:
        @property
        def instrumentation_scope(self):
            raise RuntimeError("CANARY")

    exporter = SanitizingSpanExporter(Inner(), content_mode="off")  # type: ignore[arg-type]
    result = exporter.export([Unreadable()])  # type: ignore[list-item]
    assert result.name == "FAILURE"
    assert exported == []


def test_the_sampler_keeps_server_and_shiftmind_roots_only() -> None:
    tracing, session = capture_tracing()
    try:
        http = tracing.tracer("opentelemetry.instrumentation.fastapi")
        db = tracing.tracer("opentelemetry.instrumentation.sqlalchemy")
        with db.start_as_current_span("SELECT rosterai", kind=SpanKind.CLIENT):
            pass  # idle-poll statement: a root CLIENT span
        with http.start_as_current_span("GET /health", kind=SpanKind.SERVER):
            with db.start_as_current_span("SELECT rosterai", kind=SpanKind.CLIENT):
                pass
        with tracing.tracer("shiftmind.worker").start_as_current_span("shiftmind.worker.execute"):
            pass
        flush(tracing)
    finally:
        tracing.shutdown()
    names = sorted(span.name for span in exported_spans(session))
    assert names == ["GET /health", "SELECT rosterai", "shiftmind.worker.execute"]


def test_the_sampler_drops_client_children_of_a_quiet_parent() -> None:
    quiet = "GET /api/v1/conversations/{conversation_id}/events"
    tracing, session = capture_tracing(quiet_parent_span_names=frozenset({quiet}))
    try:
        http = tracing.tracer("opentelemetry.instrumentation.fastapi")
        db = tracing.tracer("opentelemetry.instrumentation.sqlalchemy")
        with http.start_as_current_span(quiet, kind=SpanKind.SERVER):
            with db.start_as_current_span("SELECT rosterai", kind=SpanKind.CLIENT):
                pass
        flush(tracing)
    finally:
        tracing.shutdown()
    assert [span.name for span in exported_spans(session)] == [quiet]


def test_the_propagator_extracts_and_never_injects() -> None:
    propagator = ExtractOnlyTraceContext()
    trace_id = uuid4().hex
    context = propagator.extract({"traceparent": f"00-{trace_id}-00000000000000aa-01"})
    assert f"{trace.get_current_span(context).get_span_context().trace_id:032x}" == trace_id
    carrier: dict[str, str] = {}
    token = otel_context.attach(context)
    try:
        propagator.inject(carrier)
    finally:
        otel_context.detach(token)
    assert carrier == {}
    assert propagator.fields == set()


def test_building_tracing_swaps_and_shutdown_restores_the_global_textmap() -> None:
    before = propagate.get_global_textmap()
    tracing, _session = capture_tracing()
    assert isinstance(propagate.get_global_textmap(), ExtractOnlyTraceContext)
    tracing.shutdown()
    assert propagate.get_global_textmap() is before
    # And the global tracer provider was never set.
    assert not isinstance(trace.get_tracer_provider(), type(tracing.provider))


def test_a_none_tracing_override_is_honoured_over_the_process_global() -> None:
    """`dependency_overrides[get_process_tracing] = lambda: None` must turn the
    runtime factory keyless even when the process global is set (code review
    2026-09-24: the `None` used to fall back to the global)."""
    from functools import partial

    from agent.runtime import create_agent_runtime
    from api.deps import get_agent_runtime_factory, set_process_tracing

    tracing, _session = capture_tracing()
    set_process_tracing(tracing)
    try:
        assert get_agent_runtime_factory(None) is create_agent_runtime
        called_directly = get_agent_runtime_factory()  # the `Depends` default
        assert isinstance(called_directly, partial)
        assert called_directly.keywords == {"tracer_provider": tracing.provider}
    finally:
        set_process_tracing(None)
        tracing.shutdown()


# --- the ASGI trace boundary (Decision 6) ------------------------------------


def test_the_conversation_uuid_is_the_trace_id() -> None:
    from uuid import UUID

    from api.tracing import conversation_traceparent

    conversation = UUID(UUID_SAMPLE)
    parent = conversation.int & ((1 << 64) - 1)
    for path in (
        f"/api/v1/conversations/{UUID_SAMPLE}/messages",
        f"/api/v1/conversations/{UUID_SAMPLE}",
    ):
        assert conversation_traceparent(path) == (
            f"00-{conversation.hex}-{parent:016x}-01".encode("ascii")
        )


def test_no_parent_is_synthesized_off_the_conversation_routes() -> None:
    from api.tracing import conversation_traceparent

    # 36 characters that do not parse as a UUID: an ordinary root trace.
    assert conversation_traceparent("/api/v1/conversations/" + "x" * 36 + "/messages") is None
    for path in (
        "/api/v1/conversations",
        f"/api/v1/scenarios/{UUID_SAMPLE}",
        f"/conversations/{UUID_SAMPLE}/messages",  # not under /api/v1
        f"/api/v1/conversations/{UUID_SAMPLE}x/messages",
    ):
        assert conversation_traceparent(path) is None


def test_a_zero_low_half_still_yields_a_valid_parent_span_id() -> None:
    from api.tracing import conversation_traceparent

    header = conversation_traceparent(
        "/api/v1/conversations/3b52c7b4-6c0a-4f5e-0000-000000000000/events"
    )
    assert header is not None and header.decode().split("-")[2] == "0000000000000001"


@pytest.mark.parametrize("scope_type", ["http", "websocket"])
def test_the_boundary_drops_client_trace_context_and_adds_the_derived_one(scope_type) -> None:
    import asyncio

    from api.tracing import TraceContextBoundary, conversation_traceparent

    seen: list[dict] = []

    async def inner(scope, _receive, _send) -> None:
        seen.append(scope)

    path = f"/api/v1/conversations/{UUID_SAMPLE}/events"
    scope = {
        "type": scope_type,
        "path": path,
        "headers": [
            (b"TraceParent", b"00-" + b"a" * 32 + b"-" + b"b" * 16 + b"-01"),
            (b"tracestate", b"canary=CANARY-TRACESTATE"),
            (b"Baggage", b"canary=CANARY-BAGGAGE"),
            (b"cookie", b"kept"),
        ],
    }
    asyncio.run(TraceContextBoundary(inner)(scope, None, None))
    assert seen[0]["headers"] == [
        (b"cookie", b"kept"), (b"traceparent", conversation_traceparent(path)),
    ]
    assert scope["headers"][0][0] == b"TraceParent"  # the caller's scope is not mutated


def test_the_boundary_passes_lifespan_scopes_through_untouched() -> None:
    import asyncio

    from api.tracing import TraceContextBoundary

    seen: list[dict] = []

    async def inner(scope, _receive, _send) -> None:
        seen.append(scope)

    scope = {"type": "lifespan"}
    asyncio.run(TraceContextBoundary(inner)(scope, None, None))
    assert seen == [scope] and seen[0] is scope


# --- Story 5.10: the live-evaluation publisher's categories (Decision 4) -----

LIVE_EVAL_SAMPLE = {
    "shiftmind.live_eval.turn_index": 1,
    "shiftmind.live_eval.repetition": 2,
    "shiftmind.live_eval.attempt": 1,
    "shiftmind.live_eval.final_attempt": True,
    "shiftmind.live_eval.verdict": "needs_review",
    "shiftmind.live_eval.agent_run_status": "agent_completed",
    "shiftmind.live_eval.factual_failures": ("unauthorized_effect",),
    "shiftmind.live_eval.scenario": "A",
    "shiftmind.live_eval.agent_model": "openrouter:openai/gpt-5.6-luna",
    "shiftmind.live_eval.configuration_digest": "8c" * 32,
    "shiftmind.live_eval.report.sha256": "c2" * 32,
    "shiftmind.live_eval.report.run_id": "64ca2862-a81c-45f7-adcb-56586f62d57f",
    "shiftmind.conversation.id": "5bbccde3-a4f9-48cd-b61f-58a67aec1b20",
    "shiftmind.agent_run.id": "c7a1c1a0-8d1c-4c4d-b9fa-717550482462",
    "logfire.msg": "live_eval.verdict",
    "logfire.span_type": "span",
}


def _live_eval(attributes: dict) -> dict:
    return sanitize_attributes(
        span_policy.LIVE_EVAL, attributes, content_mode="off",
        content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
    )


def test_the_publisher_scopes_map_to_their_categories() -> None:
    assert categorize(span_policy.LIVE_EVAL_SCOPE) == span_policy.LIVE_EVAL
    assert categorize("pydantic-evals") == span_policy.EVALS


def test_a_valid_verdict_span_passes_whole_and_an_unlisted_key_drops() -> None:
    assert _live_eval({**LIVE_EVAL_SAMPLE, "shiftmind.live_eval.note": "x"}) == LIVE_EVAL_SAMPLE


@pytest.mark.parametrize("key", sorted(
    key for key, value in LIVE_EVAL_SAMPLE.items()
    if isinstance(value, (str, tuple)) and not key.startswith("logfire.")
))
def test_a_canary_in_any_string_valued_live_eval_key_drops_it(key) -> None:
    # Free-text shaped: the scenario validator bounds SHAPE, so a bare
    # identifier-shaped canary would pass it (the planner additionally admits
    # only the authored scenario IDs).
    value = LIVE_EVAL_SAMPLE[key]
    text = "CANARY-DB-5-2 leaked: ignore previous instructions"
    canary = (text,) if isinstance(value, tuple) else text
    assert key not in _live_eval({**LIVE_EVAL_SAMPLE, key: canary})


@pytest.mark.parametrize(("key", "value"), [
    ("shiftmind.live_eval.turn_index", 0),
    ("shiftmind.live_eval.turn_index", True),
    ("shiftmind.live_eval.repetition", "1"),
    ("shiftmind.live_eval.final_attempt", 1),
    ("shiftmind.live_eval.verdict", "passed"),
    ("shiftmind.live_eval.agent_run_status", "agent_done"),
    ("shiftmind.live_eval.factual_failures", ()),
    ("shiftmind.live_eval.factual_failures", "unsuccessful_agent_turn"),
    ("shiftmind.live_eval.factual_failures", ("ok_code", "Bad Code")),
    ("shiftmind.live_eval.scenario", "A B"),
    ("shiftmind.live_eval.agent_model", "gpt-5"),
    ("shiftmind.live_eval.configuration_digest", "8C" * 32),
])
def test_live_eval_validators_reject_off_shape_values(key, value) -> None:
    assert key not in _live_eval({key: value})


def test_live_eval_vocabularies_are_their_sources() -> None:
    import inspect
    import re

    from adapters.postgres import schema
    from evals.live_conversations import protocol, runner

    constraint = next(
        str(c.sqltext) for c in schema.agent_run.constraints
        if getattr(c, "name", None) == "ck_agent_run_status"
    )
    assert span_policy.AGENT_RUN_STATUSES == set(re.findall(r"'([a-z_]+)'", constraint))
    returns = "\n".join(
        line for line in inspect.getsource(protocol.turn_verdict).splitlines()
        if line.strip().startswith("return")
    )
    assert set(re.findall(r"'([a-z_]+)'", returns)) == span_policy.TURN_VERDICTS
    assert "'verdict': 'incomplete'" in inspect.getsource(runner.execute_prefix)


def test_the_evals_category_keeps_measured_keys_and_drops_code_location() -> None:
    kept = sanitize_attributes(
        span_policy.EVALS,
        {
            "name": "m r", "gen_ai.operation.name": "experiment", "inputs": "{}",
            "code.filepath": "C:/Users/someone/x.py", "code.lineno": 3,
            "code.function": "f", "logfire.pending_parent_id": "00",
        },
        content_mode="off", content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
    )
    assert kept == {"name": "m r", "gen_ai.operation.name": "experiment", "inputs": "{}"}
    assert span_policy.unclassified_keys(span_policy.EVALS, {"logfire.pending_parent_id"}) == {
        "logfire.pending_parent_id"
    }


def test_the_live_eval_channel_tags_the_resource_whatever_it_carried() -> None:
    raw = {"service.name": "p", "host.name": "ThunderPie", "deployment.environment": "prod"}
    tagged = sanitize_resource(
        raw, content_mode="off", content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
        live_eval_channel=True,
    )
    assert tagged == {"service.name": "p", "deployment.environment": "live-eval"}
    # Off the channel, 5.9's rule is unchanged: no tag outside content mode.
    assert sanitize_resource(
        {**raw, "deployment.environment": "live-eval"}, content_mode="off",
        content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
    ) == {"service.name": "p"}
