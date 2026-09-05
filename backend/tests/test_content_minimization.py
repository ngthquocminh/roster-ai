"""Release-blocking checks for the four content-minimization channels.

The matrix is four channels x three fixture classes (Decision 10), one distinct
test per cell so a regression is attributable to a channel and a fixture class
rather than to "the suite". `backend/evals/content_minimization_report.py` binds
each cell to the test below that proves it; the machinery test in
`test_content_minimization_report.py` enforces that the twelve cells name twelve
*different*, existing tests.

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
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from sqlalchemy.exc import StatementError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from adapters.telemetry.json_logs import JsonLogFormatter, JsonLogTelemetrySink
from application.contracts.telemetry import TelemetryRecordV1
from worker.main import _report_error
from settings import default_settings
from application.contracts.agent_runtime import AgentTurnRequestV1
from tests.test_agent_runtime_adapter import _call_demo, _runtime

BACKEND_ROOT = Path(__file__).resolve().parents[1]

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

#: Decision 10 class 1. Synthetic only -- never a real credential.
CREDENTIAL_CANARIES = {
    "GEMINI_API_KEY": "CANARY-GEMINI-5-2",
    "OPENROUTER_API_KEY": "CANARY-OPENROUTER-5-2",
    "OIDC_CLIENT_SECRET": "CANARY-OIDC-5-2",
    "CSRF_SECRET": "CANARY-CSRF-5-2",
    "AGENT_RUNTIME_API_KEY": "CANARY-AGENT-5-2",
    "ROSTERAI_DATABASE_URL": "postgresql://CANARY-DB-5-2@localhost/db",
    "ROSTERAI_PROVISIONING_DATABASE_URL": (
        "postgresql://CANARY-PROVISIONING-5-2@localhost/db"
    ),
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


def _spans_for(prompt: str, tool_label: str):
    """Drive one full tool-calling turn and return its finished spans."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not any(isinstance(message, ModelResponse) for message in messages):
            return _call_demo(label=tool_label)
        return ModelResponse(parts=[TextPart(content="done")])

    _runtime(model=FunctionModel(scripted), tracer_provider=provider).run_turn(
        AgentTurnRequestV1(prompt=prompt)
    )
    return exporter.get_finished_spans()


def _span_blob(spans) -> str:
    """Every exported surface of a span -- attributes AND events.

    Events matter: OpenTelemetry's `record_exception` writes
    `exception.message` and `exception.stacktrace` as event attributes, which
    an OTLP exporter ships alongside ordinary attributes. Asserting only on
    `span.attributes` would leave that channel unchecked (code review of
    story-5.2).
    """
    payload = []
    for span in spans:
        payload.append({key: str(value) for key, value in (span.attributes or {}).items()})
        for event in (span.events or []):
            payload.append(
                {"event": event.name}
                | {key: str(value) for key, value in (event.attributes or {}).items()}
            )
    return json.dumps(payload)


def _span_keys(spans) -> set[str]:
    return {key for span in spans for key in (span.attributes or {})}


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

def test_c4_spans_withhold_secret_prompt_and_tool_content() -> None:
    spans = _spans_for(f"deploy using {SECRET_CANARY}", tool_label=SECRET_CANARY)

    assert spans
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST
    assert SECRET_CANARY not in _span_blob(spans)


def test_c4_spans_withhold_pinned_prompt_injection_text() -> None:
    injection = INJECTION_PROMPTS["scheduling-inspect-injection-chat-text"]
    spans = _spans_for(
        injection, tool_label=INJECTION_PROMPTS["scheduling-inspect-injection-tool-output"]
    )

    assert spans
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST
    blob = _span_blob(spans)
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in blob


def test_c4_spans_withhold_exception_content_on_the_provider_error_path() -> None:
    """The failing path exports span EVENTS, not just attributes."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def failing(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError(f"upstream rejected {ADVERSARIAL_TEXT} {SECRET_CANARY}")

    try:
        _runtime(model=FunctionModel(failing), tracer_provider=provider).run_turn(
            AgentTurnRequestV1(prompt=INJECTION_TEXT)
        )
    except Exception:  # noqa: BLE001 - the failure is the fixture
        pass

    spans = exporter.get_finished_spans()
    assert spans
    assert any(span.events for span in spans), "provider-error path exported no span event"
    blob = _span_blob(spans)
    assert _span_keys(spans) <= SPAN_ATTRIBUTE_ALLOW_LIST

    # The blob must actually span BOTH exported surfaces. Without this the
    # canary assertions below hold vacuously if `_span_blob` ever stops
    # walking `span.events` -- which is exactly how the original suite missed
    # this channel (verified: dropping events from the blob left every other
    # assertion here green).
    assert '"event": "exception"' in blob, "_span_blob no longer covers span events"

    # What this story guarantees on the failing path: no prompt text and no
    # tool payload reaches EITHER attributes or events.
    for prompt in INJECTION_PROMPTS.values():
        assert prompt not in blob

    # What it does NOT guarantee, asserted here so the boundary is executable
    # rather than a comment: OpenTelemetry's `record_exception` writes the
    # raised exception's own `str()` into `exception.message`, and neither
    # `include_content=False` nor any other InstrumentationSettings option
    # suppresses it. Suppressing it needs a sanitizing TracerProvider wrapper,
    # which is Epic 6's exporter work (deferred-work.md, code review of
    # story-5.2). Latent today: no exporter is wired, so these spans go
    # nowhere. If this assertion ever fails, the wrapper landed -- delete it
    # and tighten the check above to the whole blob.
    exception_events = [
        event for span in spans for event in (span.events or []) if event.name == "exception"
    ]
    assert exception_events
    assert any(
        SECRET_CANARY in str((event.attributes or {}).get("exception.message", ""))
        for event in exception_events
    ), "exception.message no longer carries raised text -- see the note above"


# ------------------------------------------------------- configuration surfaces

def test_every_credential_environment_value_is_absent_from_settings_repr(monkeypatch) -> None:
    for name, value in CREDENTIAL_CANARIES.items():
        monkeypatch.setenv(name, value)

    rendered = repr(default_settings())

    canaries = (
        "CANARY-GEMINI-5-2", "CANARY-OPENROUTER-5-2", "CANARY-OIDC-5-2",
        "CANARY-CSRF-5-2", "CANARY-AGENT-5-2", "CANARY-DB-5-2",
        "CANARY-PROVISIONING-5-2",
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
