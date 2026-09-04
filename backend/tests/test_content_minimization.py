"""Release-blocking checks for the four content-minimization channels."""
from __future__ import annotations

import io
import json
import logging
from contextlib import redirect_stderr

from sqlalchemy.exc import StatementError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adapters.telemetry.json_logs import JsonLogFormatter, JsonLogTelemetrySink
from application.contracts.telemetry import TelemetryRecordV1
from worker.main import _report_error
from settings import default_settings
from application.contracts.agent_runtime import AgentTurnRequestV1
from tests.test_agent_runtime_adapter import _call_demo, _runtime

SPAN_ATTRIBUTE_ALLOW_LIST = frozenset({
    "agent_name", "gen_ai.agent.call.id", "gen_ai.agent.name",
    "gen_ai.aggregated_usage.input_tokens", "gen_ai.aggregated_usage.output_tokens",
    "gen_ai.conversation.id", "gen_ai.input.messages", "gen_ai.operation.name",
    "gen_ai.output.messages", "gen_ai.provider.name", "gen_ai.request.model",
    "gen_ai.response.model", "gen_ai.system", "gen_ai.tool.call.id",
    "gen_ai.tool.definitions", "gen_ai.tool.name", "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens", "logfire.json_schema", "logfire.msg", "model_name",
    "model_request_parameters", "pydantic_ai.all_messages",
    "pydantic_ai.tool.deferral.name",
})


def _formatted_exception_line(logger_name: str, error: BaseException) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    try:
        logger.exception("database operation failed for %s", "safe-id", exc_info=error)
    finally:
        logger.removeHandler(handler)
        logger.propagate = True
    return stream.getvalue()


def test_application_log_drops_statement_parameters_and_exception_text() -> None:
    canary = "WORKER-SECRET-5-2"
    error = StatementError("failed", "select ?", (canary,), RuntimeError(canary))

    line = _formatted_exception_line("api.test", error)

    assert canary not in line
    assert set(json.loads(line)) == {
        "occurred_at", "level", "logger", "event", "exception_type", "call_site"
    }


def test_worker_error_path_does_not_write_exception_content_to_stderr() -> None:
    canary = "WORKER-STDERR-SECRET-5-2"
    stream = io.StringIO()

    with redirect_stderr(stream):
        try:
            raise RuntimeError(canary)
        except RuntimeError as error:
            _report_error(error, 1.0)

    assert canary not in stream.getvalue()


def test_every_credential_environment_value_is_absent_from_settings_repr(monkeypatch) -> None:
    values = {
        "GEMINI_API_KEY": "CANARY-GEMINI-5-2",
        "OPENROUTER_API_KEY": "CANARY-OPENROUTER-5-2",
        "OIDC_CLIENT_SECRET": "CANARY-OIDC-5-2",
        "CSRF_SECRET": "CANARY-CSRF-5-2",
        "AGENT_RUNTIME_API_KEY": "CANARY-AGENT-5-2",
        "ROSTERAI_DATABASE_URL": "postgresql://CANARY-DB-5-2@localhost/db",
        "ROSTERAI_PROVISIONING_DATABASE_URL": "postgresql://CANARY-PROVISIONING-5-2@localhost/db",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    rendered = repr(default_settings())

    canaries = (
        "CANARY-GEMINI-5-2", "CANARY-OPENROUTER-5-2", "CANARY-OIDC-5-2",
        "CANARY-CSRF-5-2", "CANARY-AGENT-5-2", "CANARY-DB-5-2",
        "CANARY-PROVISIONING-5-2",
    )
    assert all(canary not in rendered for canary in canaries)


def test_both_instrumentation_constructors_disable_binary_capture() -> None:
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "agent/runtime.py").read_text(encoding="utf-8")
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


def test_third_party_log_replaces_message_with_fixed_event() -> None:
    canary = "THIRD-PARTY-SECRET-5-2"
    line = _formatted_exception_line("sqlalchemy.pool", RuntimeError(canary))
    payload = json.loads(line)

    assert canary not in line
    assert payload["event"] == "third_party"


def test_telemetry_sink_drops_unknown_labels_and_truncates_allowed_values() -> None:
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("shiftmind.test.capture")
    handler = Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        JsonLogTelemetrySink(logger=logger).emit(
            TelemetryRecordV1(labels={"failure_reason": "x" * 200, "worker_id": "SECRET"})
        )
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    payload = getattr(records[0], "shiftmind_telemetry")
    assert payload["labels"] == {"failure_reason": "x" * 128}


def test_observed_spans_are_allow_listed_and_drop_prompt_and_tool_content() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    prompt_canary = "PROMPT-INJECTION-CANARY-5-2"
    tool_canary = "TOOL-ARGUMENT-CANARY-5-2"
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(label=tool_canary)
        return ModelResponse(parts=[TextPart(content="done")])

    _runtime(model=FunctionModel(scripted), tracer_provider=provider).run_turn(
        AgentTurnRequestV1(prompt=prompt_canary)
    )
    spans = exporter.get_finished_spans()
    assert spans
    keys = {key for span in spans for key in (span.attributes or {})}
    blob = json.dumps([{key: str(value) for key, value in (span.attributes or {}).items()} for span in spans])

    assert keys <= SPAN_ATTRIBUTE_ALLOW_LIST, keys - SPAN_ATTRIBUTE_ALLOW_LIST
    assert prompt_canary not in blob
    assert tool_canary not in blob
