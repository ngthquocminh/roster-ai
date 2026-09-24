"""Release-blocking checks for the eight content-minimization channels.

C1-C3 are Story 5.2's log channels; C4-C8 are the exported span channels
(agent, HTTP server, HTTP client, database, worker), asserted since Story 5.9 on
what the real OTLP exporter receives -- attributes, events and status.

The matrix is eight channels x three fixture classes (Decision 10), one distinct
test per cell so a regression is attributable to a channel and a fixture class
rather than to "the suite". `backend/evals/content_minimization_report.py` binds
each cell to the test below that proves it; the machinery test in
`test_content_minimization_report.py` enforces that the twenty-four cells name
twenty-four *different*, existing tests.

Fixture classes, exactly as Decision 10 defines them:

1. Secrets -- synthetic canaries in every credential-bearing environment
   variable. Never a real key (`docs/CI-SECRETS-CHECKLIST.md`, NFR26).
2. Prompt injection -- the four pinned golden case ids, **reused, not
   re-authored**: `_INJECTION_PROMPTS` reads their `prompt` text off disk, so
   the coupling Decision 10 called for cannot drift silently. Story 2.9 proves
   the injection cannot widen authority; this suite proves its *text* does not
   reach a log or a span.
3. Adversarial -- values engineered against the sanitizer itself: a control
   character, a newline (JSON-lines framing), a value far over
   `_MAX_LABEL_VALUE_CHARS`, a `%`-format directive inside a log argument, a
   label key ending `_id`, and a computed label key.
"""
from __future__ import annotations

import ast
import io
import json
import logging
import threading
from contextlib import contextmanager, redirect_stderr
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote_plus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import StatementError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adapters.telemetry import span_policy
from adapters.telemetry.json_logs import JsonLogFormatter, JsonLogTelemetrySink
from application.contracts.telemetry import TelemetryRecordV1
from worker.main import _report_error
from settings import TRACE_CONTENT_SYNTHETIC_EVAL, default_settings
from application.contracts.agent_runtime import AgentTurnRequestV1
from tests.test_agent_runtime_adapter import _call_demo, _runtime
from tests.trace_capture import (
    TOKEN_CANARY,
    assert_raw_keys_classified,
    capture_tracing,
    exported_spans,
    flush,
    payload_text,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: Story 5.9: the allow-list moved INTO production. The agent category's
#: default-mode key set is imported, never re-declared here.
SPAN_ATTRIBUTE_ALLOW_LIST = span_policy.AGENT_DEFAULT_ALLOW_LIST
#: Decision 10 class 1. Synthetic only -- never a real credential.
CREDENTIAL_CANARIES = {
    "GEMINI_API_KEY": "CANARY-GEMINI-5-2",
    "OPENROUTER_API_KEY": "CANARY-OPENROUTER-5-2",
    "ANTHROPIC_API_KEY": "CANARY-ANTHROPIC-5-2",
    "OIDC_CLIENT_SECRET": "CANARY-OIDC-5-2",
    "CSRF_SECRET": "CANARY-CSRF-5-2",
    "AGENT_RUNTIME_API_KEY": "CANARY-AGENT-5-2",
    "ROSTERAI_DATABASE_URL": "postgresql://CANARY-DB-5-2@localhost/db",
    "ROSTERAI_PROVISIONING_DATABASE_URL": (
        "postgresql://CANARY-PROVISIONING-5-2@localhost/db"
    ),
    "LOGFIRE_TOKEN": "CANARY-LOGFIRE-5-9",
}
SECRET_CANARY = "CANARY-DB-5-2"

#: Decision 10 class 2. The four pinned golden case ids, read from disk so the
#: coupling to Story 2.9's corpus cannot drift silently.
PINNED_INJECTION_CASES = {
    "scheduling-baseline-injection-chat-text":
        "evals/golden/scheduling_baseline/injection-chat-text.json",
    "scheduling-inspect-injection-chat-text":
        "evals/golden/scheduling_inspect/injection-chat-text.json",
    "scheduling-inspect-injection-fixture-field":
        "evals/golden/scheduling_inspect/injection-fixture-field.json",
    "scheduling-inspect-injection-tool-output":
        "evals/golden/scheduling_inspect/injection-tool-output.json",
}


def _injection_prompts() -> dict[str, str]:
    """Read the pinned cases' prompt text; assert the ids still resolve."""
    prompts: dict[str, str] = {}
    for case_id, relative in PINNED_INJECTION_CASES.items():
        document = json.loads((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
        assert document["case_id"] == case_id, f"{relative} no longer holds {case_id}"
        prompts[case_id] = document["prompt"]
    return prompts


INJECTION_PROMPTS = _injection_prompts()
INJECTION_TEXT = " ".join(INJECTION_PROMPTS.values())

#: Decision 10 class 3, engineered against the sanitizer itself.
CONTROL_CHARACTER = "\x07"
NEWLINE_PAYLOAD = 'ADVERSARIAL-NEWLINE\n{"event":"forged"}'
PERCENT_DIRECTIVE = "ADVERSARIAL-100%s-DIRECTIVE"
OVERSIZED_VALUE = "x" * 200
IDENTIFIER_LABEL_KEY = "worker_id"
ADVERSARIAL_TEXT = (
    f"ADVERSARIAL{CONTROL_CHARACTER}CONTROL {NEWLINE_PAYLOAD} {PERCENT_DIRECTIVE}"
)


@contextmanager
def _sanitized_stream(*logger_names: str):
    """Install ONLY the JSON boundary on root and capture what it writes.

    Root's own handlers are cleared for the duration. This is not decoration:
    with no handler at all `logging.lastResort` formats the record with the
    default `Formatter`, which writes the interpolated message and the full
    traceback to stderr -- so a test that leaves pytest's own root handlers in
    place proves nothing about the boundary. Yielding both streams lets each
    test assert the canary is absent from stderr *and* that the sanitized line
    was actually produced.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = [handler]
    root.setLevel(logging.DEBUG)
    # Own the whole path, not just its root. Another module's test can leave an
    # intermediate logger non-propagating or handler-bearing, which silently
    # diverted the record and left this stream empty -- a boundary test that
    # asserts "nothing reached stderr" must control every hop it asserts on.
    saved_chain = []
    for name in logger_names:
        logger = logging.getLogger(name)
        saved_chain.append(
            (logger, logger.handlers[:], logger.propagate, logger.level, logger.disabled)
        )
        logger.handlers = []
        logger.propagate = True
        logger.disabled = False
        logger.setLevel(logging.NOTSET)
    stderr = io.StringIO()
    try:
        with redirect_stderr(stderr):
            yield stream, stderr
    finally:
        for logger, handlers, propagate, level, disabled in saved_chain:
            logger.handlers = handlers
            logger.propagate = propagate
            logger.disabled = disabled
            logger.setLevel(level)
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def _formatted_line(logger_name: str, message: str, *args, error: BaseException | None = None) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger(logger_name)
    saved_handlers, saved_propagate = logger.handlers[:], logger.propagate
    logger.handlers = [handler]
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    try:
        logger.error(message, *args, exc_info=error)
    finally:
        logger.handlers = saved_handlers
        logger.propagate = saved_propagate
    return stream.getvalue()


SANITIZED_LOG_FIELDS = {"occurred_at", "level", "logger", "event", "call_site"}


def _emitted_telemetry_payload(record: TelemetryRecordV1) -> dict | None:
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, entry: logging.LogRecord) -> None:
            records.append(entry)

    logger = logging.getLogger("shiftmind.test.capture")
    handler = Capture()
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        JsonLogTelemetrySink(logger=logger).emit(record)
    finally:
        logger.handlers = []
        logger.propagate = True
    if not records:
        return None
    return getattr(records[0], "shiftmind_telemetry")


def _exported_turn(
    prompt: str,
    *,
    model=None,
    tool_label: str = "alpha",
    content_mode: str = "off",
    **runtime_kwargs,
):
    """Drive one turn and return what the REAL exporter was handed (Story 5.9).

    The spans travel the production path -- sampler, batch processor,
    `SanitizingSpanExporter`, OTLP protobuf -- into a capturing session, so
    the assertions read the bytes that would have reached Logfire. The turn
    runs under a `shiftmind.` root because the sampler drops a root agent
    span (in production it is always under a request's server span).
    """
    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(label=tool_label)
        return ModelResponse(parts=[TextPart(content="done")])

    tracing, session = capture_tracing(content_mode=content_mode)
    try:
        with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
            try:
                _runtime(
                    model=model or FunctionModel(scripted),
                    tracer_provider=tracing.provider,
                    trace_content=content_mode == TRACE_CONTENT_SYNTHETIC_EVAL,
                    **runtime_kwargs,
                ).run_turn(AgentTurnRequestV1(prompt=prompt))
            except Exception:  # noqa: BLE001 - a failing turn is a fixture here
                pass
        flush(tracing)
    finally:
        tracing.shutdown()
    return session


def _agent_spans(session):
    return [span for span in exported_spans(session) if span.scope == "pydantic-ai"]


def _span_keys(spans) -> set[str]:
    return {key for span in spans for key in span.attributes}


def _raw_agent_keys(**turn) -> set[str]:
    """PRE-sanitizer keys (in-memory), for the drift check only."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    prompt = turn.pop("prompt", "hello")
    try:
        _runtime(tracer_provider=provider, **turn).run_turn(AgentTurnRequestV1(prompt=prompt))
    except Exception:  # noqa: BLE001
        pass
    return {key for span in exporter.get_finished_spans() for key in (span.attributes or {})}


# ---------------------------------------------------------------- C1 telemetry

def test_c1_telemetry_drops_secret_bearing_labels() -> None:
    payload = _emitted_telemetry_payload(
        TelemetryRecordV1(
            labels={
                "api_key": SECRET_CANARY,
                "database_url": SECRET_CANARY,
                "failure_reason": "provider_error",
            }
        )
    )

    assert payload is not None
    # Only the allow-listed key survives; every credential-shaped key a producer
    # might invent is dropped before the record reaches the stream.
    assert set(payload["labels"]) == {"failure_reason"}
    assert SECRET_CANARY not in json.dumps(payload)


def test_c1_telemetry_drops_prompt_injection_text_in_unknown_labels() -> None:
    payload = _emitted_telemetry_payload(
        TelemetryRecordV1(
            labels={
                "planner_instruction": INJECTION_TEXT,
                "tool_output": INJECTION_TEXT,
                "status_class": "5xx",
            }
        )
    )

    assert payload is not None
    assert set(payload["labels"]) == {"status_class"}
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in json.dumps(payload)


def test_c1_telemetry_bounds_adversarial_label_keys_and_values() -> None:
    payload = _emitted_telemetry_payload(
        TelemetryRecordV1(
            labels={
                "failure_reason": OVERSIZED_VALUE,
                IDENTIFIER_LABEL_KEY: "SECRET",
                "model": f"{CONTROL_CHARACTER}{NEWLINE_PAYLOAD}{PERCENT_DIRECTIVE}",
            }
        )
    )

    assert payload is not None
    assert IDENTIFIER_LABEL_KEY not in payload["labels"]
    assert payload["labels"]["failure_reason"] == "x" * 128
    # One JSON object on one line: an embedded newline must not frame a second.
    line = json.dumps(payload, separators=(",", ":"))
    assert "\n" not in line
    assert json.loads(line) == payload


def test_c1_telemetry_survives_a_non_string_label_value() -> None:
    """A wrong-typed label must not take the whole record down with it."""
    payload = _emitted_telemetry_payload(
        TelemetryRecordV1(labels={"status_class": 500, "failure_reason": ["A" * 5000]})
    )

    assert payload is not None, "a non-str label silently dropped the entire record"
    assert payload["labels"]["status_class"] == "500"
    assert len(payload["labels"]["failure_reason"]) == 128


# --------------------------------------------------------------------- C2 logs

def test_c2_logs_drop_statement_parameters_and_secret_exception_text() -> None:
    error = StatementError("failed", "select ?", (SECRET_CANARY,), RuntimeError(SECRET_CANARY))

    line = _formatted_line("api.test", "database operation failed for %s", "safe-id", error=error)

    assert SECRET_CANARY not in line
    assert set(json.loads(line)) == SANITIZED_LOG_FIELDS | {"exception_type"}


def test_c2_logs_drop_prompt_injection_text_from_message_and_arguments() -> None:
    line = _formatted_line(
        "api.test", "planner turn failed for %s", INJECTION_TEXT,
        error=RuntimeError(INJECTION_TEXT),
    )

    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in line
    assert json.loads(line)["event"] == "planner turn failed for %s"


def test_c2_logs_neutralize_adversarial_arguments_and_third_party_records() -> None:
    line = _formatted_line("api.test", "operation failed for %s", ADVERSARIAL_TEXT)

    # A `%`-format directive riding `record.args` must never be interpolated.
    assert PERCENT_DIRECTIVE not in line
    assert CONTROL_CHARACTER not in line
    assert line.count("\n") == 1 and line.endswith("\n")  # JSON-lines framing intact
    assert json.loads(line)["event"] == "operation failed for %s"

    third_party = _formatted_line(
        "sqlalchemy.pool", "pool failure", error=RuntimeError(ADVERSARIAL_TEXT)
    )
    assert PERCENT_DIRECTIVE not in third_party
    assert json.loads(third_party)["event"] == "third_party"


# ------------------------------------------------------------- C3 worker stderr

def _report_through_boundary(error: BaseException) -> tuple[str, str]:
    with _sanitized_stream("worker", "worker.main") as (sanitized, stderr):
        _report_error(error, 1.0)
    return sanitized.getvalue(), stderr.getvalue()


def test_c3_worker_stderr_withholds_secret_exception_text() -> None:
    sanitized, stderr = _report_through_boundary(RuntimeError(SECRET_CANARY))

    assert SECRET_CANARY not in stderr
    assert SECRET_CANARY not in sanitized
    assert json.loads(sanitized)["exception_type"] == ["RuntimeError"]


def test_c3_worker_stderr_withholds_prompt_injection_text() -> None:
    sanitized, stderr = _report_through_boundary(RuntimeError(INJECTION_TEXT))

    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in stderr
        assert prompt not in sanitized


def test_c3_worker_stderr_withholds_adversarial_exception_text() -> None:
    sanitized, stderr = _report_through_boundary(RuntimeError(ADVERSARIAL_TEXT))

    assert PERCENT_DIRECTIVE not in stderr and PERCENT_DIRECTIVE not in sanitized
    assert CONTROL_CHARACTER not in sanitized
    assert sanitized.count("\n") == 1 and sanitized.endswith("\n")


# -------------------------------------------------------------------- C4 spans
#
# Story 5.9: C4 is now "exported agent spans". Every cell asserts on what the
# real `OTLPSpanExporter` received -- attributes, events AND status messages --
# so Story 5.2's residual (exception text in `exception.message`) is gone and
# the canary must be absent from the WHOLE payload.


def test_c4_spans_withhold_secret_prompt_and_tool_content() -> None:
    session = _exported_turn(f"deploy using {SECRET_CANARY}", tool_label=SECRET_CANARY)

    spans = _agent_spans(session)
    assert {span.name.split(" ")[0] for span in spans} >= {"invoke_agent", "chat", "execute_tool"}
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST
    payload = payload_text(session)
    assert SECRET_CANARY not in payload
    assert TOKEN_CANARY not in payload


def test_c4_spans_withhold_pinned_prompt_injection_text() -> None:
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-chat-text"]
    session = _exported_turn(
        injection, tool_label=INJECTION_PROMPTS["scheduling-inspect-injection-tool-output"]
    )

    spans = _agent_spans(session)
    assert spans
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST
    # Non-vacuity: the structure-only messages really were exported.
    assert any("gen_ai.input.messages" in span.attributes for span in spans)
    payload = payload_text(session)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload


def test_c4_spans_withhold_exception_content_on_the_provider_error_path() -> None:
    """The failing path exports span EVENTS and a STATUS, not just attributes."""
    def failing(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError(f"upstream rejected {ADVERSARIAL_TEXT} {SECRET_CANARY}")

    session = _exported_turn(INJECTION_TEXT, model=FunctionModel(failing))

    spans = _agent_spans(session)
    assert spans
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST
    events = [event for span in spans for event in span.events]
    assert ("exception", {"exception.type": "RuntimeError"}) in events
    assert any(span.status_code == 2 for span in spans), "no span recorded the failure"
    assert all(span.status_message == "" for span in spans)
    payload = payload_text(session)
    for forbidden in (SECRET_CANARY, "ADVERSARIAL-NEWLINE", "ADVERSARIAL-100", "upstream rejected"):
        assert forbidden not in payload
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload


def test_c4_off_mode_never_exports_the_runtime_instructions() -> None:
    """Measured fact 3: `instruction_parts` carried the system prompt in default mode."""
    from agent.runtime import AgentRuntimeConfig

    canary = "CANARY-INSTRUCTIONS-5-9"
    session = _exported_turn(
        "hello", config=AgentRuntimeConfig(instructions=f"You are a planner. {canary}")
    )

    spans = _agent_spans(session)
    assert any("model_request_parameters" in span.attributes for span in spans)
    assert canary not in payload_text(session)


# ----------------------------------------------------- C5 HTTP server spans
#
# The real app, instrumented exactly as production installs it, with the
# identity store dependency-overridden (no database). What leaves is decoded
# from the real exporter's OTLP body.

SERVER_KIND = 2


class _NoSessions:
    def resolve_session(self, _token_hash):
        return None


@contextmanager
def _instrumented_app(**overrides):
    from fastapi.testclient import TestClient

    from api.deps import get_identity_store
    from api.main import _SSE_ROUTE_TEMPLATES, app
    from api.tracing import install_api_tracing, quiet_parent_span_names

    tracing, session = capture_tracing(
        service_name="shiftmind-api",
        quiet_parent_span_names=quiet_parent_span_names(_SSE_ROUTE_TEMPLATES),
    )
    undo = install_api_tracing(app, tracing)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_identity_store] = overrides.get(
        "identity_store", lambda: _NoSessions()
    )
    try:
        with TestClient(
            app, base_url="http://shiftmind.test", raise_server_exceptions=False
        ) as client:
            yield client, tracing, session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        undo()
        tracing.shutdown()


def _server_spans(session):
    assert_raw_keys_classified(session, span_policy.HTTP_SERVER)
    return [span for span in exported_spans(session) if span.kind == SERVER_KIND]


def _decoded_payload(session) -> str:
    """The payload as sent AND percent-decoded, so an encoded canary is found too."""
    payload = payload_text(session)
    return payload + unquote_plus(payload)


def _no_query_or_url(spans) -> None:
    for span in spans:
        assert "http.url" not in span.attributes
        assert "?" not in str(span.attributes.get("http.target", ""))


def test_c5_http_server_spans_withhold_secret_headers_and_query() -> None:
    with _instrumented_app() as (client, tracing, session):
        response = client.get(
            f"/api/v1/scenarios?token={SECRET_CANARY}",
            headers={
                "Cookie": f"__Host-shiftmind_session={SECRET_CANARY}",
                "X-CSRF-Token": SECRET_CANARY,
                "Authorization": f"Bearer {SECRET_CANARY}",
                "User-Agent": SECRET_CANARY,
            },
        )
        assert response.status_code == 401
        flush(tracing)
    spans = _server_spans(session)
    assert [span.attributes.get("http.target") for span in spans] == ["/api/v1/scenarios"]
    _no_query_or_url(spans)
    payload = _decoded_payload(session)
    assert SECRET_CANARY not in payload and TOKEN_CANARY not in payload


def test_c5_http_server_spans_withhold_prompt_injection_text() -> None:
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-chat-text"]
    with _instrumented_app() as (client, tracing, session):
        client.post(
            f"/api/v1/conversations/{uuid4()}/messages",
            params={"probe": injection},
            json={"text": injection},
        )
        client.get("/" + injection.replace("/", " ")[:80])  # an unmatched route
        # A MATCHED route: Starlette matches `{conversation_id}` before FastAPI
        # rejects the non-UUID segment (code review 2026-09-24).
        client.post(
            f"/api/v1/conversations/{injection.replace('/', ' ')[:80]}/messages",
            json={"text": "x"},
        )
        flush(tracing)
    spans = _server_spans(session)
    assert len(spans) == 3
    _no_query_or_url(spans)
    assert sum("http.route" in span.attributes for span in spans) == 2
    payload = _decoded_payload(session)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload
        assert prompt[:60] not in payload


def test_c5_http_server_spans_withhold_adversarial_paths_and_exception_text() -> None:
    def exploding_store():
        raise RuntimeError(f"route exploded {ADVERSARIAL_TEXT} {SECRET_CANARY}")

    with _instrumented_app(identity_store=exploding_store) as (client, tracing, session):
        failed = client.get("/api/v1/scenarios", params={"q": ADVERSARIAL_TEXT})
        assert failed.status_code == 500
        client.get("/ADVERSARIAL-PATH-100%25s-DIRECTIVE")
        client.get("/api/v1/approvals/ADVERSARIAL-PATHPARAM-100%25s")  # a matched route
        flush(tracing)
    spans = _server_spans(session)
    _no_query_or_url(spans)
    assert any(
        span.attributes.get("http.route") == "/api/v1/approvals/{approval_id}"
        and "http.target" not in span.attributes
        for span in spans
    )
    events = [event for span in spans for event in span.events]
    assert ("exception", {"exception.type": "RuntimeError"}) in events
    assert all(span.status_message == "" for span in spans)
    payload = _decoded_payload(session)
    for forbidden in (SECRET_CANARY, "ADVERSARIAL", "route exploded"):
        assert forbidden not in payload


# ----------------------------------------------------- C6 HTTP client spans
#
# Outbound model traffic through pydantic-ai's OpenAI client to a local,
# OpenAI-shaped stub. The stub also records what it RECEIVED: no trace or
# conversation identifiers may reach a provider (measured fact 4, NFR30).


@contextmanager
def _provider_stub(*, status: int = 200, content: str = "done"):
    received: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            received.append({key.lower(): value for key, value in self.headers.items()})
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if status == 200:
                body = json.dumps({
                    "id": "chatcmpl-1", "object": "chat.completion", "created": 0,
                    "model": "stub-model",
                    "choices": [{
                        "index": 0, "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
                }).encode("utf-8")
            else:
                body = json.dumps({"error": {"message": content}}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], received
    finally:
        server.shutdown()
        server.server_close()


def _outbound_turn(prompt: str, *, base_url: str, api_key: str):
    from openai import AsyncOpenAI
    from pydantic_ai import models
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from api.main import app
    from api.tracing import install_api_tracing

    tracing, session = capture_tracing()
    undo = install_api_tracing(app, tracing)  # the production httpx wiring
    try:
        model = OpenAIChatModel(
            "stub-model",
            provider=OpenAIProvider(
                openai_client=AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=0)
            ),
        )
        with models.override_allow_model_requests(True):
            with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
                try:
                    _runtime(model=model, tracer_provider=tracing.provider).run_turn(
                        AgentTurnRequestV1(prompt=prompt)
                    )
                except Exception:  # noqa: BLE001 - a failing turn is a fixture here
                    pass
        flush(tracing)
    finally:
        undo()
        tracing.shutdown()
    assert_raw_keys_classified(session, span_policy.HTTP_CLIENT)
    assert_raw_keys_classified(session, span_policy.AGENT)
    return session


def _client_spans(session):
    return [span for span in exported_spans(session) if span.scope.endswith(".httpx")]


def _assert_no_context_sent(received) -> None:
    assert received, "the provider stub was never called"
    for headers in received:
        assert not {"traceparent", "tracestate", "baggage"} & set(headers)


def test_c6_http_client_spans_withhold_the_key_and_query() -> None:
    with _provider_stub() as (port, received):
        session = _outbound_turn(
            "hello",
            base_url=f"http://127.0.0.1:{port}/v1?probe={SECRET_CANARY}",
            api_key=SECRET_CANARY,
        )
    _assert_no_context_sent(received)
    spans = _client_spans(session)
    assert spans
    assert all(
        span.attributes["http.url"].startswith(f"http://127.0.0.1:{port}/") for span in spans
    )
    assert SECRET_CANARY not in _decoded_payload(session)


def test_c6_http_client_spans_withhold_prompt_injection_text() -> None:
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-chat-text"]
    reply = INJECTION_PROMPTS["scheduling-inspect-injection-tool-output"]
    with _provider_stub(content=reply) as (port, received):
        session = _outbound_turn(injection, base_url=f"http://127.0.0.1:{port}/v1", api_key="k")
    _assert_no_context_sent(received)
    assert _client_spans(session)
    payload = _decoded_payload(session)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload


def test_c6_http_client_spans_withhold_adversarial_url_parts_and_errors() -> None:
    error_text = f"{ADVERSARIAL_TEXT} {SECRET_CANARY}"
    with _provider_stub(status=500, content=error_text) as (port, received):
        session = _outbound_turn(
            "hello",
            base_url=(
                "http://ADVERSARIAL-USER:ADVERSARIAL-PASS@"
                f"127.0.0.1:{port}/v1#ADVERSARIAL-FRAG"
            ),
            api_key="k",
        )
    _assert_no_context_sent(received)
    spans = exported_spans(session)
    assert _client_spans(session)
    assert any(span.status_code == 2 for span in spans)
    assert all(span.status_message == "" for span in spans)
    payload = _decoded_payload(session)
    for forbidden in (SECRET_CANARY, "ADVERSARIAL"):
        assert forbidden not in payload


# -------------------------------------------------------- C7 database spans
#
# A real engine traced per instance, as the API and worker trace theirs.
# Measured fact 2: a failing statement's status description echoes the bound
# value even with `hide_parameters=True` -- psycopg's own error text.


def _database_payload(engine_url, value: str):
    from adapters.telemetry.spans import trace_engine

    tracing, session = capture_tracing()
    engine = trace_engine(create_engine(engine_url, hide_parameters=True), tracing)
    try:
        with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
            with engine.connect() as connection:
                connection.execute(text("SELECT CAST(:value AS text)"), {"value": value})
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT CAST(:value AS uuid)"), {"value": value})
            except StatementError:
                pass
        flush(tracing)
    finally:
        engine.dispose()
        tracing.shutdown()
    assert_raw_keys_classified(session, span_policy.DATABASE)
    spans = [span for span in exported_spans(session) if span.scope.endswith(".sqlalchemy")]
    assert len(spans) >= 2
    assert any(span.status_code == 2 for span in spans), "the failing statement was not traced"
    assert all(span.status_message == "" for span in spans)
    assert {span.attributes["db.statement"] for span in spans} == {
        "SELECT CAST(%(value)s AS text)", "SELECT CAST(%(value)s AS uuid)",
    }
    assert not {"db.user", "net.peer.name", "net.peer.port"} & _span_keys(spans)
    return session


@pytest.mark.postgres
def test_c7_database_spans_withhold_bound_secret_values(governed_postgres_engine) -> None:
    session = _database_payload(governed_postgres_engine.url, SECRET_CANARY)
    assert SECRET_CANARY not in payload_text(session)


@pytest.mark.postgres
def test_c7_database_spans_withhold_bound_prompt_injection_text(governed_postgres_engine) -> None:
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-fixture-field"]
    session = _database_payload(governed_postgres_engine.url, injection)
    payload = payload_text(session)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload


@pytest.mark.postgres
def test_c7_database_spans_withhold_bound_adversarial_values_and_errors(
    governed_postgres_engine,
) -> None:
    session = _database_payload(governed_postgres_engine.url, ADVERSARIAL_TEXT)
    # The engine tracer records the failure as a STATUS, whose description
    # echoed the bound value (measured fact 2); `_database_payload` asserts it
    # is exported empty, and that is the rule this cell proves (m03). The
    # tracer records NO exception event, so the event rule cannot be shown
    # here: this tripwire reddens the day it starts to, so the cell gets an
    # event assertion that can fail instead of an `all()` over nothing.
    events = [event for span in exported_spans(session) for event in span.events]
    assert events == [], "database spans now carry events; prove the event rule here"
    assert "ADVERSARIAL" not in payload_text(session)


# ---------------------------------------------------------- C8 worker spans
#
# The real job scope and scheduler wrapper, with a fake repository and
# scheduler, so a failing or content-bearing solve is a fixture.


class _LeaseOnce:
    def lease_next_job(self, *_args, **_kwargs):
        from application.contracts.job_lease import JobLeaseV1

        now = datetime.now(timezone.utc)
        return JobLeaseV1(
            job_id=UUID(int=11), job_type="schedule_run_execute", status="leased",
            site_id=UUID(int=12), actor_id=UUID(int=13), attempt_id=UUID(int=14),
            contract_version="1", schedule_run_id=UUID(int=15), idempotency_key="k",
            lease_owner="w", lease_expires_at=now, heartbeat_at=now, fencing_epoch=1,
            created_at=now,
        )


def _worker_payload(
    *,
    raises: str | None = None,
    reason: str | None = None,
    status: str = "solver_completed",
    solver_status: str = "FEASIBLE",
):
    """`solver_status`/`status` reach the two closed-vocabulary span keys; a
    fake scheduler is how text gets there past `SolverOutcomeV1`'s contract."""
    from adapters.telemetry.spans import traced_scheduler, traced_worker_job

    class Scheduler:
        def solve(self, _snapshot):
            if raises is not None:
                raise RuntimeError(raises)
            return SimpleNamespace(
                solver_status=solver_status, reason=reason, warnings=(reason or "",),
                wall_time_seconds=0.1,
            )

    tracing, session = capture_tracing(service_name="shiftmind-worker")
    try:
        try:
            with traced_worker_job(_LeaseOnce(), tracing) as job:
                job.repository.lease_next_job()
                scheduler = traced_scheduler(lambda _connection: Scheduler(), tracing)
                scheduler(None).solve(SimpleNamespace(schedule_run_id=UUID(int=15)))
                job.finish(SimpleNamespace(status=status))
        except RuntimeError:
            pass
        flush(tracing)
    finally:
        tracing.shutdown()
    assert_raw_keys_classified(session, span_policy.WORKER)
    spans = exported_spans(session)
    assert {span.name for span in spans} == {
        "shiftmind.worker.execute", "shiftmind.worker.lease", "shiftmind.worker.solve",
    }
    return session, spans


def test_c8_worker_spans_withhold_secret_exception_text() -> None:
    session, spans = _worker_payload(raises=f"solver input {SECRET_CANARY}")
    events = [event for span in spans for event in span.events]
    assert ("exception", {"exception.type": "RuntimeError"}) in events
    assert SECRET_CANARY not in payload_text(session)


def test_c8_worker_spans_withhold_prompt_injection_text() -> None:
    # The injection rides the two worker keys that DO carry solver-produced
    # strings -- solver status and run status -- plus the outcome's free-text
    # `reason`, which no span emits. The closed vocabularies are what drop it.
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-tool-output"]
    session, spans = _worker_payload(
        reason=injection, solver_status=injection, status=injection
    )
    solve = next(span for span in spans if span.name == "shiftmind.worker.solve")
    execute = next(span for span in spans if span.name == "shiftmind.worker.execute")
    assert "shiftmind.solver.status" not in solve.attributes
    assert "shiftmind.schedule_run.status" not in execute.attributes
    assert solve.attributes["shiftmind.solver.wall_time_s"] == 0.1  # the span is real
    payload = payload_text(session)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in payload


def test_c8_worker_spans_withhold_adversarial_exception_and_status_text() -> None:
    # Two jobs: one whose solve raises (events and status), and one that
    # FINISHES with adversarial status text -- the raising job never reaches
    # `job.finish`, so it cannot exercise the status vocabulary (code review).
    failed, failed_spans = _worker_payload(raises=ADVERSARIAL_TEXT)
    assert all(span.status_message == "" for span in failed_spans)
    assert any(span.events for span in failed_spans)
    assert "ADVERSARIAL" not in payload_text(failed)
    finished, finished_spans = _worker_payload(status=ADVERSARIAL_TEXT)
    execute = next(span for span in finished_spans if span.name == "shiftmind.worker.execute")
    assert "shiftmind.schedule_run.status" not in execute.attributes
    assert execute.attributes["shiftmind.job.type"] == "schedule_run_execute"
    assert "ADVERSARIAL" not in payload_text(finished)


# ------------------------------------------ export boundary surface nodes


def test_export_content_mode_key_set(monkeypatch) -> None:
    """AC4: synthetic-eval exports content keys, never credentials or exception text.

    Two turns: one that defers an approval-gated tool and then fails late (tool
    arguments, instructions, and exception text that must stay out), and one
    that COMPLETES through a tool result into a final answer -- AC4's
    "completions and tool results" (code review 2026-09-24).
    """
    from agent.runtime import create_agent_runtime
    from application.contracts.grounding import GroundedAnswerV1
    from tests.test_agent_runtime_adapter import (
        REAL_RESULT_ID,
        _claim_answer,
        _compute_stub_module,
        _compute_then,
        demonstration_module,
    )

    for name, value in CREDENTIAL_CANARIES.items():
        monkeypatch.setenv(name, value)
    settings = replace(default_settings(), agent_trace_content_mode=TRACE_CONTENT_SYNTHETIC_EVAL)
    deps = _runtime()._deps

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(label="synthetic")
        raise RuntimeError(f"late failure {SECRET_CANARY}")

    tracing, session = capture_tracing(content_mode=TRACE_CONTENT_SYNTHETIC_EVAL)
    try:
        with tracing.tracer("shiftmind.proof").start_as_current_span("shiftmind.proof"):
            try:
                create_agent_runtime(
                    settings=settings, model=FunctionModel(scripted),
                    capabilities=(demonstration_module(),), deps=deps,
                    tracer_provider=tracing.provider,
                ).run_turn(AgentTurnRequestV1(prompt="synthetic planner question"))
            except Exception:  # noqa: BLE001
                pass
            completed = create_agent_runtime(
                settings=settings,
                model=FunctionModel(_compute_then([_claim_answer(REAL_RESULT_ID)])),
                capabilities=(_compute_stub_module(),), deps=deps,
                answer_type=GroundedAnswerV1, tracer_provider=tracing.provider,
            ).run_turn(AgentTurnRequestV1(prompt="synthetic worker count"))
            assert completed.answer == _claim_answer(REAL_RESULT_ID)
        flush(tracing)
    finally:
        tracing.shutdown()
    spans = _agent_spans(session)
    keys = _span_keys(spans)
    # Every content key is exported: prompts and instructions, tool arguments
    # AND results, and the run's final result.
    assert {
        "gen_ai.tool.call.arguments", "gen_ai.tool.call.result",
        "gen_ai.system_instructions", "final_result",
    } <= keys
    assert keys <= SPAN_ATTRIBUTE_ALLOW_LIST | span_policy.AGENT_CONTENT_MODE_KEYS
    payload = payload_text(session)
    assert "synthetic planner question" in payload and "synthetic worker count" in payload
    # The tool result (the model-facing view carries the result id) and the
    # completion (the grounded answer's prose) left as content.
    assert REAL_RESULT_ID in payload
    assert " workers." in payload
    assert {span.resource.get("deployment.environment") for span in spans} == {"live-eval"}
    for value in CREDENTIAL_CANARIES.values():
        assert value not in payload
    assert SECRET_CANARY not in payload and "late failure" not in payload


def test_export_keyless_constructs_no_exporter(monkeypatch) -> None:
    """AC1: no token -> nothing is constructed and behaviour is today's."""
    import adapters.telemetry.spans as spans
    import api.main
    from agent.runtime import create_agent_runtime
    from api.deps import get_agent_runtime_factory
    from worker.composition import create_runtime

    constructed: list[object] = []
    monkeypatch.setattr(
        spans.OTLPSpanExporter, "__init__", lambda *_a, **_k: constructed.append(1)
    )
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    assert spans.build_process_tracing(default_settings(), service_name="shiftmind-api") is None
    assert get_agent_runtime_factory() is create_agent_runtime
    assert api.main._process_tracing is None
    runtime = create_runtime()
    try:
        assert runtime.tracing is None
    finally:
        runtime.engine.dispose()
    assert constructed == []


def test_export_client_trace_context_discarded() -> None:
    """AC2's last clause, fake-backed: no route adopts a client's trace context."""
    hostile_trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    headers = {
        "traceparent": f"00-{hostile_trace}-00f067aa0ba902b7-01",
        "tracestate": "canary=CANARY-TRACESTATE-5-9",
        "baggage": "canary=CANARY-BAGGAGE-5-9",
    }
    conversation_id = uuid4()
    with _instrumented_app() as (client, tracing, session):
        client.get("/api/v1/scenarios", headers=headers)
        client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers, json={})
        client.get("/api/v1/auth/session", headers=headers)
        flush(tracing)
    spans = _server_spans(session)
    assert len(spans) == 3
    assert hostile_trace not in {span.trace_id for span in spans}
    by_name = {span.name: span for span in spans}
    assert by_name[
        "POST /api/v1/conversations/{conversation_id}/messages"
    ].trace_id == conversation_id.hex
    assert by_name["GET /api/v1/scenarios"].parent_span_id == ""
    assert "CANARY-TRACESTATE" not in payload_text(session)
    assert "CANARY-BAGGAGE" not in payload_text(session)


def test_export_agent_raw_key_drift() -> None:
    """Story 5.2's "a new key names itself", kept at the export boundary.

    Every key pydantic-ai emits BEFORE sanitization, on a tool turn, a failing
    turn and a content-mode turn, must be decided by the agent table. An
    unclassified key reddens here naming itself, while the runtime
    independently drops it.
    """
    def failing(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError("boom")

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(label="drift")
        return ModelResponse(parts=[TextPart(content="done")])

    observed = (
        _raw_agent_keys(model=FunctionModel(scripted))
        | _raw_agent_keys(model=FunctionModel(scripted), trace_content=True)
        | _raw_agent_keys(model=FunctionModel(failing))
    )
    assert {
        "gen_ai.input.messages", "model_request_parameters", "gen_ai.tool.call.arguments",
    } <= observed
    assert span_policy.unclassified_keys(span_policy.AGENT, observed) == set()


# ------------------------------------------------------- configuration surfaces

def test_every_credential_environment_value_is_absent_from_settings_repr(monkeypatch) -> None:
    for name, value in CREDENTIAL_CANARIES.items():
        monkeypatch.setenv(name, value)

    rendered = repr(default_settings())

    canaries = (
        "CANARY-GEMINI-5-2", "CANARY-OPENROUTER-5-2", "CANARY-ANTHROPIC-5-2", "CANARY-OIDC-5-2",
        "CANARY-CSRF-5-2", "CANARY-AGENT-5-2", "CANARY-DB-5-2",
        "CANARY-PROVISIONING-5-2", "CANARY-LOGFIRE-5-9",
    )
    assert all(canary not in rendered for canary in canaries)


def test_worker_run_as_a_process_still_renders_an_owned_event() -> None:
    """`worker/main.py` is executable, so its module logger is `__main__`.

    Run as `python worker/main.py` or `python -m worker.main`, `__name__` is
    `"__main__"` -- and an unowned logger collapses to `event: "third_party"`,
    which discarded the worker's own failure event in exactly the deployment
    shape the file supports. The C3 cells import the module, so its logger is
    `worker.main` there and none of them can see this (code review of
    story-5.2).
    """
    line = _formatted_line("__main__", "worker run_once failed; retrying in %s seconds", 1.0)

    payload = json.loads(line)
    assert payload["event"] == "worker run_once failed; retrying in %s seconds"
    assert payload["logger"] == "__main__"


def test_both_instrumentation_constructors_disable_binary_capture() -> None:
    source = (BACKEND_ROOT / "agent/runtime.py").read_text(encoding="utf-8")
    calls = [
        node for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "InstrumentationSettings"
    ]
    assert len(calls) == 2
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        disabled = keywords.get("include_binary_content")
        assert isinstance(disabled, ast.Constant) and disabled.value is False
