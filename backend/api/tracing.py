"""HTTP-side tracing: FastAPI and httpx instrumentation plus the trace boundary.

Story 5.9, Decisions 6, 7 and 11. The only API module that imports an
OpenTelemetry instrumentation package; the SDK, exporter and sanitizer live in
`adapters/telemetry/spans.py`.

Two placements were measured to fail silently and must not be "simplified":

* Instrumenting inside the lifespan records ZERO server spans -- Starlette
  builds the middleware stack on the lifespan's own first ASGI message. The API
  installs at import time instead (`api/main.py`).
* A boundary added with `app.add_middleware` (before or after instrumenting)
  runs INSIDE the OpenTelemetry middleware and adopts the client's
  `traceparent`. Only a header rewrite wrapped OUTSIDE the instrumented stack
  works, so `install_api_tracing` wraps `build_middleware_stack` itself.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from uuid import UUID

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from starlette.types import ASGIApp, Receive, Scope, Send

from adapters.telemetry.conversation_trace import conversation_traceparent_header
from adapters.telemetry.spans import ProcessTracing

#: Client trace context is never trusted, on any route (AD-12).
_DISCARDED_HEADERS = frozenset({b"traceparent", b"tracestate", b"baggage"})
_CONVERSATION_PATH = re.compile(r"^/api/v1/conversations/([^/]{36})(?:/|$)")


def conversation_traceparent(path: str) -> bytes | None:
    """The synthesized parent for a conversation-scoped path, else `None`.

    The trace ID IS the conversation UUID, so every turn's request, agent and
    database spans share one trace. The parent span ID (the UUID's low 64
    bits, never zero) is never exported itself.
    """
    match = _CONVERSATION_PATH.match(path)
    if match is None:
        return None
    try:
        conversation_id = UUID(match.group(1))
    except ValueError:
        return None
    return conversation_traceparent_header(conversation_id).encode("ascii")


class TraceContextBoundary:
    """Outermost ASGI wrapper: drop client trace headers, add the derived one.

    It runs before authentication (it must: fact 6), so a request naming a
    conversation it may not read still joins that conversation's trace --
    telemetry integrity only, ledgered at code review 2026-09-24.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") in ("http", "websocket"):
            headers = [
                (name, value)
                for name, value in scope.get("headers", ())
                if name.lower() not in _DISCARDED_HEADERS
            ]
            traceparent = conversation_traceparent(scope.get("path", ""))
            if traceparent is not None:
                headers.append((b"traceparent", traceparent))
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


def install_api_tracing(
    app: FastAPI,
    tracing: ProcessTracing,
) -> Callable[[], None]:
    """Instrument `app` and outbound httpx; return the undo (for tests).

    Must run before the app serves its first message (import time in
    production). The undo uninstruments FastAPI, restores
    `build_middleware_stack`, resets `app.middleware_stack`, uninstruments httpx
    and restores the global textmap.
    """
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracing.provider,
        excluded_urls="/health$",
        exclude_spans=["receive", "send"],
    )
    instrumented_build = app.build_middleware_stack

    def build_middleware_stack() -> ASGIApp:
        return TraceContextBoundary(instrumented_build())

    app.build_middleware_stack = build_middleware_stack  # type: ignore[method-assign]
    app.middleware_stack = None
    httpx_instrumentor = HTTPXClientInstrumentor()
    httpx_instrumentor.instrument(tracer_provider=tracing.provider)

    def undo() -> None:
        httpx_instrumentor.uninstrument()
        app.build_middleware_stack = instrumented_build  # type: ignore[method-assign]
        FastAPIInstrumentor.uninstrument_app(app)
        app.middleware_stack = None
        tracing.restore_textmap()

    return undo


def quiet_parent_span_names(sse_route_templates: Iterable[str]) -> frozenset[str]:
    """Server span names whose CLIENT children (SSE poll statements) drop."""
    return frozenset(f"GET {template}" for template in sse_route_templates)


__all__ = [
    "TraceContextBoundary",
    "conversation_traceparent",
    "install_api_tracing",
    "quiet_parent_span_names",
]
