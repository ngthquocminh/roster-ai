"""The one export boundary: every span this process exports passes through here.

Story 5.9, AD-12. This is the only module besides `api/tracing.py` that may
import the OpenTelemetry SDK, exporter or instrumentation packages (enforced by
`tests/architecture/test_trace_export_boundaries.py`). Its policy is data in
`adapters/telemetry/span_policy.py`.

Invariants kept here, each measured at story creation:

* No token -> `build_process_tracing` returns `None` and constructs nothing:
  no exporter, provider, propagator change or instrumentation.
* The global tracer provider is NEVER set. Every instrumentation receives the
  provider explicitly, so an un-wired library records nothing.
* The exporter is built from settings only, never from `OTEL_EXPORTER_OTLP_*`
  or `OTEL_BSP_*`/`OTEL_RESOURCE_ATTRIBUTES` environment variables.
* Export never blocks a request or a job: a bounded batch processor, a 5 s
  exporter deadline, and a sanitizer whose failure drops the batch rather than
  raising or exporting it unsanitized (NFR10).
"""
from __future__ import annotations

import time
import weakref
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.sqlalchemy.engine import EngineTracer
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.sdk.version import __version__ as _SDK_VERSION
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from adapters.telemetry import span_policy
from application.app_version import APP_VERSION
from settings import TRACE_CONTENT_SYNTHETIC_EVAL, Settings

#: Decision 12: explicit, so `OTEL_BSP_*` cannot change them.
EXPORT_TIMEOUT_SECONDS = 5
MAX_QUEUE_SIZE = 2048
SCHEDULE_DELAY_MILLIS = 5000
MAX_EXPORT_BATCH_SIZE = 512
EXPORT_TIMEOUT_MILLIS = 5000
FORCE_FLUSH_TIMEOUT_MILLIS = 5000

DATABASE_SCOPE = "opentelemetry.instrumentation.sqlalchemy"


class ExtractOnlyTraceContext(TextMapPropagator):
    """W3C trace context that reads but never writes.

    Measured: the default propagator sent `traceparent` and pydantic-ai's
    `baggage` (including the conversation UUID) to the model provider -- trace
    and conversation identifiers leaving the process (NFR30). Extraction is
    kept only for the boundary's own synthesized parent (Decision 6).
    """

    _inner = TraceContextTextMapPropagator()

    def extract(
        self,
        carrier: CarrierT,
        context: otel_context.Context | None = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> otel_context.Context:
        return self._inner.extract(carrier, context=context, getter=getter)

    def inject(
        self,
        carrier: CarrierT,
        context: otel_context.Context | None = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        return None

    @property
    def fields(self) -> set[str]:
        return set()


class ShiftMindSampler(Sampler):
    """Roots, SSE polls and stray statements (Decision 7).

    * Root span: sampled iff SERVER kind or a `shiftmind.` name -- this drops
      the worker's idle-poll statements (4 root spans a second, measured).
    * Local parent: a CLIENT span under a quiet parent (the two SSE routes'
      server spans) is dropped; the predicate is kind + parent NAME because a
      statement span carries no `db.*` attribute when it starts.
    * Otherwise the parent's sampled flag (for a remote parent, only ever the
      boundary's synthesized `01`).
    """

    def __init__(self, quiet_parent_span_names: frozenset[str] = frozenset()) -> None:
        self._quiet = frozenset(quiet_parent_span_names)

    def should_sample(
        self,
        parent_context: otel_context.Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Any = None,
        links: Any = None,
        trace_state: Any = None,
    ) -> SamplingResult:
        parent = trace.get_current_span(parent_context)
        parent_span_context = parent.get_span_context()
        if not parent_span_context.is_valid:
            sampled = kind == SpanKind.SERVER or name.startswith("shiftmind.")
            return self._result(sampled, None, attributes)
        if (
            not parent_span_context.is_remote
            and kind == SpanKind.CLIENT
            and getattr(parent, "name", None) in self._quiet
        ):
            return self._result(False, parent_span_context.trace_state, attributes)
        return self._result(
            parent_span_context.trace_flags.sampled,
            parent_span_context.trace_state,
            attributes,
        )

    @staticmethod
    def _result(sampled: bool, trace_state: Any, attributes: Any) -> SamplingResult:
        # The SDK builds the span's attributes FROM the sampling result, so a
        # sampled span must be handed the start attributes back.
        if not sampled:
            return SamplingResult(Decision.DROP, None, trace_state)
        return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes, trace_state)

    def get_description(self) -> str:
        return "ShiftMindSampler"


class SanitizingSpanExporter(SpanExporter):
    """Hands the inner exporter sanitized copies only (Decision 4).

    Attributes are default-deny by category; `exception` events keep their type
    only and every other event drops; the status description is never
    exported (it echoed provider errors and bound SQL values); links drop; the
    resource is rebuilt from its allow-list. Any sanitization error fails the
    whole batch -- it never raises and never exports an unsanitized span.
    """

    def __init__(self, inner: SpanExporter, *, content_mode: str) -> None:
        self._inner = inner
        self._content_mode = content_mode

    def sanitize(self, span: ReadableSpan) -> ReadableSpan:
        scope = span.instrumentation_scope
        category = span_policy.categorize(scope.name if scope else None)
        attributes = span_policy.sanitize_attributes(
            category,
            dict(span.attributes or {}),
            content_mode=self._content_mode,
            content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
        )
        events = []
        for event in span.events:
            kept = span_policy.sanitize_event(event.name, dict(event.attributes or {}))
            if kept is not None:
                events.append(Event(kept[0], kept[1], event.timestamp))
        resource = Resource(
            span_policy.sanitize_resource(
                dict(span.resource.attributes) if span.resource else {},
                content_mode=self._content_mode,
                content_mode_on=TRACE_CONTENT_SYNTHETIC_EVAL,
            )
        )
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=resource,
            attributes=attributes,
            events=tuple(events),
            links=(),
            kind=span.kind,
            status=Status(span.status.status_code),
            start_time=span.start_time,
            end_time=span.end_time,
            # Name and version only: scope attributes are not on the allow-list.
            instrumentation_scope=(
                InstrumentationScope(scope.name, scope.version, scope.schema_url)
                if scope is not None
                else None
            ),
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            sanitized = [self.sanitize(span) for span in spans]
        except Exception:  # noqa: BLE001 - never export or raise on a policy error
            return SpanExportResult.FAILURE
        try:
            return self._inner.export(sanitized)
        except Exception:  # noqa: BLE001 - AD-12: export never breaks product work
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


@dataclass
class ProcessTracing:
    """One process's tracing: the provider every instrumentation receives."""

    provider: TracerProvider
    content_mode: str
    service_name: str
    _previous_textmap: TextMapPropagator | None = None

    def tracer(self, name: str) -> trace.Tracer:
        return self.provider.get_tracer(name)

    def shutdown(self) -> None:
        """Force-flush (bounded), then shut the provider down."""
        try:
            self.provider.force_flush(FORCE_FLUSH_TIMEOUT_MILLIS)
        finally:
            self.provider.shutdown()
            self.restore_textmap()

    def restore_textmap(self) -> None:
        if self._previous_textmap is not None:
            propagate.set_global_textmap(self._previous_textmap)
            self._previous_textmap = None


def _resource(service_name: str, content_mode: str) -> Resource:
    """Built explicitly, never merged from `OTEL_RESOURCE_ATTRIBUTES`."""
    attributes: dict[str, str] = {
        "service.name": service_name,
        "service.version": APP_VERSION,
        "service.instance.id": uuid4().hex,
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
        "telemetry.sdk.version": _SDK_VERSION,
    }
    if content_mode == TRACE_CONTENT_SYNTHETIC_EVAL:
        attributes[span_policy.DEPLOYMENT_ENVIRONMENT_KEY] = span_policy.LIVE_EVAL_ENVIRONMENT
    return Resource(attributes)


def build_process_tracing(
    settings: Settings,
    *,
    service_name: str,
    quiet_parent_span_names: frozenset[str] = frozenset(),
    session: Any = None,
) -> ProcessTracing | None:
    """Return this process's tracing, or `None` -- constructing nothing -- keyless.

    `session` is a test seam (a `requests.Session`); `None` in production.
    """
    # `getattr`: worker composition is also built from narrow settings stubs,
    # and a stub without the field is simply keyless.
    token = getattr(settings, "logfire_token", None)
    if not token:
        return None
    content_mode = settings.agent_trace_content_mode
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.logfire_base_url}/v1/traces",
        headers={"Authorization": token},
        timeout=EXPORT_TIMEOUT_SECONDS,
        compression=Compression.Gzip,
        session=session,
    )
    provider = TracerProvider(
        resource=_resource(service_name, content_mode),
        sampler=ShiftMindSampler(quiet_parent_span_names),
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            SanitizingSpanExporter(exporter, content_mode=content_mode),
            max_queue_size=MAX_QUEUE_SIZE,
            schedule_delay_millis=SCHEDULE_DELAY_MILLIS,
            max_export_batch_size=MAX_EXPORT_BATCH_SIZE,
            export_timeout_millis=EXPORT_TIMEOUT_MILLIS,
        )
    )
    previous = propagate.get_global_textmap()
    propagate.set_global_textmap(ExtractOnlyTraceContext())
    return ProcessTracing(
        provider=provider,
        content_mode=content_mode,
        service_name=service_name,
        _previous_textmap=previous,
    )


_TRACED_ENGINES: "weakref.WeakSet[Any]" = weakref.WeakSet()


def trace_engine(engine: Any, tracing: ProcessTracing | None) -> Any:
    """Attach statement spans to ONE engine instance; idempotent; no-op keyless.

    Never the global `SQLAlchemyInstrumentor().instrument()`: it patches
    `sqlalchemy.create_engine` after `api/deps.py` has bound it under another
    name (measured: connect spans, no statement spans) and is a process
    singleton. Metrics are out of scope, so the usage counter is a no-op.
    """
    if tracing is None or engine in _TRACED_ENGINES:
        return engine
    meter = NoOpMeterProvider().get_meter(DATABASE_SCOPE)
    EngineTracer(
        tracing.tracer(DATABASE_SCOPE),
        engine,
        meter.create_up_down_counter("db.client.connections.usage"),
    )
    _TRACED_ENGINES.add(engine)
    return engine


def annotate_enqueued_schedule_run(schedule_run_id: UUID | str | None) -> None:
    """F3's join key on the enqueueing request's server span; no-op keyless."""
    if schedule_run_id is None:
        return
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("shiftmind.schedule_run.id", str(schedule_run_id))


# --- worker (Decision 10) ---------------------------------------------------


class _TracedLeaseRepository:
    """Delegates everything; times `lease_next_job` and opens the job's root."""

    def __init__(self, inner: Any, scope: "_JobScope") -> None:
        self._inner = inner
        self._scope = scope

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def lease_next_job(self, *args: Any, **kwargs: Any) -> Any:
        started = time.time_ns()
        lease = self._inner.lease_next_job(*args, **kwargs)
        ended = time.time_ns()
        if lease is not None:
            self._scope.open(lease, started, ended)
        return lease


class _JobScope:
    def __init__(self, repository: Any, tracing: ProcessTracing) -> None:
        self._tracer = tracing.tracer(span_policy.WORKER_SCOPE)
        self.repository = _TracedLeaseRepository(repository, self)
        self._span: trace.Span | None = None
        self._token: object | None = None

    def open(self, lease: Any, started: int, ended: int) -> None:
        ids = {
            "shiftmind.schedule_run.id": lease.schedule_run_id,
            "shiftmind.job.id": lease.job_id,
            "shiftmind.site.id": lease.site_id,
        }
        common = {key: str(value) for key, value in ids.items() if value is not None}
        attributes: dict[str, Any] = dict(common)
        if lease.job_type is not None:
            attributes["shiftmind.job.type"] = lease.job_type
        if lease.created_at is not None:
            attributes["shiftmind.job.queue_age_s"] = max(
                0.0, (datetime.now(timezone.utc) - lease.created_at).total_seconds()
            )
        span = self._tracer.start_span(
            "shiftmind.worker.execute",
            context=otel_context.Context(),
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            start_time=started,
        )
        parent = trace.set_span_in_context(span)
        self._tracer.start_span(
            "shiftmind.worker.lease",
            context=parent,
            attributes=common,
            start_time=started,
        ).end(end_time=ended)
        self._span = span
        self._token = otel_context.attach(parent)

    def finish(self, outcome: Any) -> None:
        if self._span is not None and outcome is not None:
            self._span.set_attribute("shiftmind.schedule_run.status", outcome.status)

    def fail(self, error: BaseException) -> None:
        if self._span is not None:
            self._span.record_exception(error)
            self._span.set_status(Status(StatusCode.ERROR))

    def close(self) -> None:
        if self._token is not None:
            otel_context.detach(self._token)
            self._token = None
        if self._span is not None:
            self._span.end()
            self._span = None


class _PassThroughScope:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def finish(self, outcome: Any) -> None:
        return None

    def fail(self, error: BaseException) -> None:
        return None


@contextmanager
def traced_worker_job(repository: Any, tracing: ProcessTracing | None) -> Iterator[Any]:
    """One trace per leased job: root `shiftmind.worker.execute` -> lease, solve.

    The root opens only when a lease is returned, so an idle poll exports
    nothing. It ends -- and its context detaches -- in `finally`, exception or
    not. Keyless, the repository passes through unchanged.
    """
    if tracing is None:
        yield _PassThroughScope(repository)
        return
    scope = _JobScope(repository, tracing)
    try:
        yield scope
    except BaseException as error:
        scope.fail(error)
        raise
    finally:
        scope.close()


class _TracedScheduler:
    def __init__(self, inner: Any, tracer: trace.Tracer) -> None:
        self._inner = inner
        self._tracer = tracer

    def solve(self, snapshot: Any) -> Any:
        run_id = getattr(snapshot, "schedule_run_id", None)
        attributes = {"shiftmind.schedule_run.id": str(run_id)} if run_id else {}
        with self._tracer.start_as_current_span(
            "shiftmind.worker.solve", attributes=attributes
        ) as span:
            outcome = self._inner.solve(snapshot)
            span.set_attribute("shiftmind.solver.status", outcome.solver_status)
            span.set_attribute("shiftmind.solver.wall_time_s", float(outcome.wall_time_seconds))
            return outcome


def traced_scheduler(scheduler: Any, tracing: ProcessTracing | None) -> Any:
    """Wrap a scheduler or scheduler factory so `solve` runs inside a span."""
    if tracing is None:
        return scheduler
    tracer = tracing.tracer(span_policy.WORKER_SCOPE)
    if hasattr(scheduler, "solve"):
        return _TracedScheduler(scheduler, tracer)

    def factory(connection: Any) -> Any:
        return _TracedScheduler(scheduler(connection), tracer)

    return factory


__all__ = [
    "ExtractOnlyTraceContext",
    "ProcessTracing",
    "SanitizingSpanExporter",
    "ShiftMindSampler",
    "annotate_enqueued_schedule_run",
    "build_process_tracing",
    "trace_engine",
    "traced_scheduler",
    "traced_worker_job",
]
