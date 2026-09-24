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
    "http.target": f"/api/v1/conversations/{UUID_SAMPLE}/messages?probe=CANARY-QUERY-5-9#frag",
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
        "http.target": f"/api/v1/conversations/{UUID_SAMPLE}/messages",
    }
    # Content mode widens nothing outside the agent category.
    assert _on(HTTP_SERVER, _MEASURED_SERVER) == kept


def test_http_server_drops_the_target_of_an_unmatched_route() -> None:
    """An unmatched route's raw path is client free text (measured fact 5)."""
    kept = _off(HTTP_SERVER, {"http.method": "GET", "http.target": "/CANARY-PATH-5-9"})
    assert kept == {"http.method": "GET"}


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


def test_every_measured_key_is_classified_and_a_new_one_names_itself() -> None:
    for category, keys in {
        HTTP_SERVER: _MEASURED_SERVER,
        DATABASE: {"db.user", "net.peer.name", "db.statement"},
    }.items():
        assert span_policy.unclassified_keys(category, keys) == set()
    assert span_policy.unclassified_keys(AGENT, {"gen_ai.brand_new_key"}) == {
        "gen_ai.brand_new_key"
    }


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
    assert session.headers_seen[0]["Authorization"] == "CANARY-LOGFIRE-5-9"
    assert "x-canary" not in session.headers_seen[0]
    assert "CANARY-RESOURCE" not in payload_text(session)


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
