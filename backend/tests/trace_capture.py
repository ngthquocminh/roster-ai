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
from dataclasses import dataclass, field, replace
from typing import Any

import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

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

    def post(self, url, data=None, **_kwargs):  # type: ignore[override]
        self.bodies.append(bytes(data or b""))
        self.headers_seen.append(dict(self.headers))
        response = requests.Response()
        response.status_code = self.status
        response._content = b""
        response.url = url
        return response

    def requests(self) -> list[ExportTraceServiceRequest]:
        decoded = []
        for body in self.bodies:
            raw = gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
            message = ExportTraceServiceRequest()
            message.ParseFromString(raw)
            decoded.append(message)
        return decoded

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


def exported_spans(session: CapturingSession) -> list[ExportedSpan]:
    spans: list[ExportedSpan] = []
    for request in session.requests():
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
    return tracing, session


def flush(tracing: ProcessTracing) -> None:
    assert tracing.provider.force_flush(10_000)
