"""Capture what the REAL `OTLPSpanExporter` sends, for Story 5.9's proof suites.

A `requests.Session` test double is passed to `build_process_tracing(session=)`,
so every span travels the production path -- provider, sampler, batch
processor, `SanitizingSpanExporter`, OTLP protobuf encoding, gzip -- and the
assertions read the bytes that would have reached Logfire. Story 5.2 Decision 7:
assert on OBSERVED output, never on a settings object; and (Story 5.9 trap 5)
on events and status descriptions, not only attributes.
"""
from __future__ import annotations

import gzip
import json
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adapters.telemetry import span_policy
from adapters.telemetry.spans import ProcessTracing, build_process_tracing
from settings import default_settings

TOKEN_CANARY = "CANARY-LOGFIRE-5-9"


class CapturingSession(requests.Session):
    """Records every OTLP POST body and answers with a fixed status."""

    def __init__(self, status: int = 200) -> None:
        super().__init__()
        self.status = status
        self.bodies: list[bytes] = []
        self.headers_seen: list[dict[str, str]] = []
        self.urls_seen: list[str] = []
        #: Every span as the SDK produced it, BEFORE the sanitizer -- the
        #: drift check's input (Decision 4). Never what leaves the process.
        self.raw_exporter = InMemorySpanExporter()

    def post(self, url, data=None, **_kwargs):  # type: ignore[override]
        self.bodies.append(bytes(data or b""))
        self.headers_seen.append(dict(self.headers))
        self.urls_seen.append(url)
        response = requests.Response()
        response.status_code = self.status
        response._content = b""
        response.url = url
        return response

    def requests(self) -> list[ExportTraceServiceRequest]:
        return decode_bodies(self.bodies)

    def raw_bytes(self) -> bytes:
        return b"".join(
            gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
            for body in self.bodies
        )


def _value(any_value) -> Any:
    kind = any_value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_value(v) for v in any_value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _value(kv.value) for kv in any_value.kvlist_value.values}
    if kind == "bytes_value":
        return any_value.bytes_value.hex()
    return getattr(any_value, kind)


def _attributes(key_values) -> dict[str, Any]:
    return {kv.key: _value(kv.value) for kv in key_values}


@dataclass
class ExportedSpan:
    name: str
    scope: str
    kind: int
    trace_id: str
    span_id: str
    parent_span_id: str
    attributes: dict[str, Any]
    events: list[tuple[str, dict[str, Any]]]
    status_code: int
    status_message: str
    resource: dict[str, Any]
    links: int = 0
    scope_attributes: dict[str, Any] = field(default_factory=dict)
    start_time_unix_nano: int = 0
    end_time_unix_nano: int = 0


def exported_spans(session: CapturingSession) -> list[ExportedSpan]:
    return spans_from_requests(session.requests())


def spans_from_requests(requests_: list[ExportTraceServiceRequest]) -> list[ExportedSpan]:
    spans: list[ExportedSpan] = []
    for request in requests_:
        for resource_spans in request.resource_spans:
            resource = _attributes(resource_spans.resource.attributes)
            for scope_spans in resource_spans.scope_spans:
                for span in scope_spans.spans:
                    spans.append(ExportedSpan(
                        name=span.name,
                        scope=scope_spans.scope.name,
                        kind=span.kind,
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex(),
                        attributes=_attributes(span.attributes),
                        events=[(e.name, _attributes(e.attributes)) for e in span.events],
                        status_code=span.status.code,
                        status_message=span.status.message,
                        resource=resource,
                        links=len(span.links),
                        scope_attributes=_attributes(scope_spans.scope.attributes),
                        start_time_unix_nano=span.start_time_unix_nano,
                        end_time_unix_nano=span.end_time_unix_nano,
                    ))
    return spans


def payload_text(session: CapturingSession) -> str:
    """Everything that left the process, searchable: raw bytes AND decoded form."""
    decoded = [
        {
            "name": span.name,
            "attributes": span.attributes,
            "events": span.events,
            "status": span.status_message,
            "resource": span.resource,
            "scope": span.scope_attributes,
        }
        for span in exported_spans(session)
    ]
    return session.raw_bytes().decode("latin-1") + json.dumps(decoded, default=str)


def capture_tracing(
    *,
    content_mode: str = "off",
    service_name: str = "shiftmind-test",
    quiet_parent_span_names: frozenset[str] = frozenset(),
    status: int = 200,
) -> tuple[ProcessTracing, CapturingSession]:
    session = CapturingSession(status=status)
    settings = replace(
        default_settings(),
        logfire_token=TOKEN_CANARY,
        agent_trace_content_mode=content_mode,  # type: ignore[arg-type]
    )
    tracing = build_process_tracing(
        settings,
        service_name=service_name,
        quiet_parent_span_names=quiet_parent_span_names,
        session=session,
    )
    assert tracing is not None
    tracing.provider.add_span_processor(SimpleSpanProcessor(session.raw_exporter))
    return tracing, session


def assert_raw_keys_classified(session: CapturingSession, category: str) -> None:
    """Decision 4's drift check on OBSERVED spans, for any category.

    Every key the SDK emitted -- before sanitization -- on a span of
    `category` must be decided by that category's table (allowed,
    transformed, content, or known-dropped). An unclassified key reddens here
    naming itself, while the runtime independently drops it. Non-vacuous: at
    least one span of the category must have been observed.
    """
    observed: set[str] = set()
    seen = False
    for span in session.raw_exporter.get_finished_spans():
        scope = span.instrumentation_scope.name if span.instrumentation_scope else None
        if span_policy.categorize(scope) != category:
            continue
        seen = True
        observed.update((span.attributes or {}).keys())
    assert seen, f"no {category} span was observed"
    assert span_policy.unclassified_keys(category, observed) == set()


def flush(tracing: ProcessTracing) -> None:
    assert tracing.provider.force_flush(10_000)


# --- local Logfire stand-ins (moved from Story 5.9's failure suite) ---------

SLOW_SECONDS = 30


def closed_port() -> int:
    """A port that was bound and closed: connecting to it is refused."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@dataclass
class ServerRequest:
    method: str
    path: str
    body: bytes


@contextmanager
def fixture_server(behaviour: str, seen: list[ServerRequest] | None = None):
    """A local HTTP server: `slow` holds each POST, `rejected` answers 401,
    anything else 200. Every request (any method) is appended to `seen`."""

    class Handler(BaseHTTPRequestHandler):
        def _record(self, method: str) -> bytes:
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if seen is not None:
                seen.append(ServerRequest(method, self.path, body))
            return body

        def do_POST(self) -> None:  # noqa: N802
            self._record("POST")
            if behaviour == "slow":
                time.sleep(SLOW_SECONDS)
            try:
                self.send_response(401 if behaviour == "rejected" else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except OSError:
                pass

        def do_GET(self) -> None:  # noqa: N802
            self._record("GET")
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def decode_bodies(bodies: list[bytes]) -> list[ExportTraceServiceRequest]:
    decoded = []
    for body in bodies:
        raw = gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
        message = ExportTraceServiceRequest()
        message.ParseFromString(raw)
        decoded.append(message)
    return decoded
