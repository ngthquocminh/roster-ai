"""ShiftMind backend API.

Run from backend/:
    uv run uvicorn api.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import compile_path

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import get_identity_store, get_settings, get_telemetry_sink
from api.problems import problem_response
from application.app_version import APP_VERSION
from application.contracts.telemetry import CorrelationV1, TelemetryRecordV1
from adapters.telemetry.json_logs import configure_json_logging
from application.ports.conversation import AgentRunNotQueuedError
from application.use_cases.decide_approval import PostWriteApprovalNotPendingError
from application.use_cases.promote_baseline import ApprovalPayloadUnreadableError, BaselineConcurrentlyMovedError
from api.routers import (
    agent_availability,
    approvals,
    auth,
    constraints,
    conversations,
    fixtures,
    health,
    proposals,
    runs,
    schedule_runs,
    scenario_catalogue,
    scenario_projection,
    scenarios,
)
from services import run_service
from store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_json_logging()
    db.init_db(get_settings().db_path)
    yield
    run_service.shutdown()


app = FastAPI(title="ShiftMind API", version=APP_VERSION, lifespan=lifespan)


@app.exception_handler(PostWriteApprovalNotPendingError)
@app.exception_handler(BaselineConcurrentlyMovedError)
@app.exception_handler(ApprovalPayloadUnreadableError)
@app.exception_handler(AgentRunNotQueuedError)
async def rollback_required_decision_problem(request: Request, exc: Exception):
    """Render only after the endpoint exception has unwound its transaction.

    These are the failures that must ESCAPE the decision endpoint rather than be
    caught and returned: `get_site_context` rolls back only when an exception
    leaves the endpoint function, so rendering here — after the dependency has
    unwound — is what makes TX2 atomic. This module is also the SINGLE source of
    status and copy for these codes; `routers/approvals.py` deliberately omits
    them from its own maps so the wire contract cannot drift between the two.
    """
    if not request.url.path.startswith("/api/v1/"):
        # `AgentRunNotQueuedError` is a conversation-layer exception with other
        # producers. Without this guard, any future escape from an unversioned
        # route would render approval-flavoured copy for an unrelated failure.
        return await versioned_unhandled_problem(request, exc)
    status = 409
    if isinstance(exc, PostWriteApprovalNotPendingError):
        code, detail = "approval_not_pending", "The approval already reached a terminal state."
        expected, current = exc.expected, exc.current
    elif isinstance(exc, BaselineConcurrentlyMovedError):
        code, detail = "stale_baseline_version", "The site baseline changed while the approval was being consumed."
        expected, current = exc.expected, exc.current
    elif isinstance(exc, ApprovalPayloadUnreadableError):
        # A data-integrity fault, not a conflict the planner can resolve by
        # refreshing — so it is honestly a 500, with a stable code rather than
        # the generic `internal_error` a bare RuntimeError would have produced.
        status = 500
        code = "approval_payload_unreadable"
        detail = "The approval's stored agent payload could not be read; the promotion was rolled back."
        expected, current = exc.expected, exc.current
    else:
        # Reached on BOTH the reject edge (cancel) and the approve edge (resume),
        # so the copy must not claim a cancellation was attempted.
        code = "agent_run_not_cancellable"
        detail = "The agent run awaiting this approval is no longer in the expected state."
        expected = {"agent_run_status": "approval_required"}
        current = {"agent_run_status": "changed"}
    return problem_response(
        status=status, code=code, title="Approval decision could not be completed",
        detail=detail, extra={"expected": expected, "current": current},
    )


@app.exception_handler(RequestValidationError)
async def versioned_validation_problem(
    request: Request,
    exc: RequestValidationError,
):
    if request.url.path.startswith("/api/v1/"):
        return problem_response(
            status=422,
            code="invalid_request",
            title="Invalid request",
            detail="The request could not be validated.",
        )
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(HTTPException)
async def versioned_http_problem(request: Request, exc: HTTPException):
    if not request.url.path.startswith("/api/v1/"):
        return await http_exception_handler(request, exc)
    code, title, detail = {
        401: (
            "authentication_required",
            "Authentication required",
            "A valid application session is required.",
        ),
        403: (
            "request_forbidden",
            "Request forbidden",
            "The request is not allowed.",
        ),
        404: (
            "resource_not_found",
            "Resource not found",
            "The requested resource was not found.",
        ),
    }.get(
        exc.status_code,
        ("request_failed", "Request failed", "The request could not be completed."),
    )
    return problem_response(
        status=exc.status_code,
        code=code,
        title=title,
        detail=detail,
    )


@app.exception_handler(Exception)
async def versioned_unhandled_problem(request: Request, exc: Exception):
    """Keep the RFC 7807 contract intact when something unplanned fails.

    Without this, an unhandled error on a versioned path — a PostgreSQL outage
    reaching `get_site_context`, a statement timeout, a revoked grant — escapes
    to Starlette's default handler and returns `text/plain` "Internal Server
    Error", even though every `/api/v1` route advertises `ProblemDetailsV1`.
    Clients coded against problem details get an unparseable body at exactly the
    moment they most need a structured one.

    Renders only fixed copy: the exception may carry a connection URL, a query,
    or a traceback, and none of that may cross the boundary (AD-3). Starlette
    re-raises after this returns, so the ASGI server still logs the original
    error and `TestClient` still surfaces it.
    """
    if request.url.path.startswith("/api/v1/"):
        return problem_response(
            status=500,
            code="internal_error",
            title="Internal server error",
            detail="The request could not be completed.",
        )
    # Legacy unversioned paths keep Starlette's default shape.
    return PlainTextResponse("Internal Server Error", status_code=500)


# Legacy SQLite-backed routes: gated in full (reads and writes) once Gate A's
# flag is set. /health and /fixtures are not SQLite-backed and stay available.
_LEGACY_ROUTE_PREFIXES = ("/scenarios", "/runs", "/constraints")


def _gate_a_flag_is_set() -> bool:
    """True if anything at all is present at the flag path (file, directory, or
    symlink) or if we can't determine that due to a filesystem error. Only a
    definitively absent path permits normal legacy-route access — every other
    outcome fails closed, since this check exists to keep legacy data offline."""
    try:
        return Path(get_settings().maintenance_flag_path).exists()
    except OSError:
        return True


@app.middleware("http")
async def refuse_legacy_routes_during_gate_a(request: Request, call_next):
    """Keep legacy SQLite-backed routes offline once the Gate A flag has been written."""
    if request.url.path.startswith(_LEGACY_ROUTE_PREFIXES) and _gate_a_flag_is_set():
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Gate A maintenance window",
                "status": 503,
                "detail": "Legacy SQLite-backed routes are offline during cutover.",
            },
            status_code=503,
            media_type="application/problem+json",
            headers={"Retry-After": "3600"},
        )
    return await call_next(request)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PUBLIC_VERSIONED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/callback",
    "/api/v1/auth/session",
}


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if not referer:
        return None
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


@app.middleware("http")
async def enforce_versioned_session_and_csrf(request: Request, call_next):
    """Authenticate only /api/v1 and enforce same-origin unsafe requests."""
    path = request.url.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    if not path.startswith("/api/v1/") or path in _PUBLIC_VERSIONED_PATHS:
        return await call_next(request)

    settings_override = request.app.dependency_overrides.get(get_settings)
    settings = settings_override() if settings_override else get_settings()
    store_override = request.app.dependency_overrides.get(get_identity_store)
    store = store_override() if store_override else get_identity_store(settings)
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    resolved = None
    if session_token:
        try:
            resolved = await run_in_threadpool(
                store.resolve_session,
                hash_secret(session_token),
            )
        except Exception:
            return problem_response(
                status=502,
                code="session_store_unavailable",
                title="Authentication unavailable",
                detail="The application session could not be verified.",
            )
    if session_token is None or resolved is None:
        return problem_response(
            status=401,
            code="authentication_required",
            title="Authentication required",
            detail="A valid application session is required.",
        )

    request.state.shiftmind_session = resolved
    request.state.shiftmind_session_token = session_token
    if request.method in _UNSAFE_METHODS:
        allowed_origins = {
            settings.app_base_url.rstrip("/"),
            *(origin.rstrip("/") for origin in settings.cors_origins),
        }
        supplied_csrf = request.headers.get("x-csrf-token")
        supplied_origin = _request_origin(request)
        csrf_valid = bool(supplied_csrf) and hmac.compare_digest(
            hash_secret(supplied_csrf),
            resolved.csrf_token_hash,
        )
        if supplied_origin not in allowed_origins or not csrf_valid:
            return problem_response(
                status=403,
                code="csrf_validation_failed",
                title="Request forbidden",
                detail="Origin and CSRF validation failed.",
            )

    return await call_next(request)


# NOTE: CORS origins are resolved once here, at process/import time — unlike
# every other Settings field, which default_settings() re-reads fresh on every
# call so env overrides apply at request time. That promise does not hold
# here because add_middleware only runs once, at app construction. This is a
# conscious tradeoff, not a bug, but an undocumented one reads as a bug to the
# next person (and a test that sets CORS_ORIGINS after import will fail
# silently confusingly — no exception, headers just absent).
# allow_credentials is left at Starlette's default False: D-02 means this app
# never sends cookies or an Authorization header, so nothing needs it, and a
# wildcard-with-credentials combination is invalid per the Fetch spec anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


_SSE_ROUTE_TEMPLATES = {
    "/api/v1/conversations/{conversation_id}/events",
    "/api/v1/schedule-runs/{run_id}/events",
}


def _declared_route_template(request: Request) -> str:
    route = request.scope.get("route")
    resolved = getattr(route, "path_format", None)
    if resolved:
        return resolved
    # Authentication and maintenance middleware may return before FastAPI's
    # router annotates the scope. Match only against declared OpenAPI paths so
    # the raw URL can never become a metric label.
    for template, operations in request.app.openapi()["paths"].items():
        if request.method.lower() not in operations:
            continue
        path_regex, _path_format, _convertors = compile_path(template)
        if path_regex.match(request.url.path):
            return template
    return "unmatched"


def _emit_api_request_telemetry(
    request: Request, request_id: UUID, started: float, status_class: str
) -> None:
    # `duration_ms` is captured FIRST, before `_declared_route_template`'s
    # possible `app.openapi()` fallback -- that fallback rebuilds the whole
    # schema and must never be charged to the request's own latency (code
    # review of story-5.1). Everything below (including route-template
    # resolution and sink lookup) is inside this function's own guard, so
    # nothing here can turn a completed response into a 500 -- also code
    # review of story-5.1.
    duration_ms = (perf_counter() - started) * 1_000
    try:
        route_template = _declared_route_template(request)
        if route_template in _SSE_ROUTE_TEMPLATES:
            return
        sink_override = request.app.dependency_overrides.get(get_telemetry_sink)
        sink = sink_override() if sink_override else get_telemetry_sink()
        sink.emit(
            TelemetryRecordV1(
                event="api.request.completed",
                occurred_at=datetime.now(timezone.utc),
                app_version=APP_VERSION,
                correlation=CorrelationV1(request_id=request_id),
                labels={
                    "route_template": route_template,
                    "method": request.method,
                    "status_class": status_class,
                },
                duration_ms=duration_ms,
            )
        )
    except Exception:  # noqa: BLE001 - telemetry never affects a response
        pass


# Registered after CORS deliberately: Starlette applies middleware in reverse
# registration order, making this the outermost timer over total handling.
@app.middleware("http")
async def emit_request_telemetry(request: Request, call_next):
    request_id = uuid4()
    request.state.telemetry_request_id = request_id
    started = perf_counter()
    try:
        response = await call_next(request)
    except BaseException:
        # Starlette's own `@app.exception_handler` machinery re-raises after
        # building its response (see `versioned_unhandled_problem`'s
        # docstring), so an unhandled 500 propagates through here too --
        # without this, exactly the requests an operator most needs latency
        # and rate data for produced zero telemetry (code review of
        # story-5.1).
        _emit_api_request_telemetry(request, request_id, started, "5xx")
        raise
    _emit_api_request_telemetry(
        request, request_id, started, f"{response.status_code // 100}xx"
    )
    return response

app.include_router(health.router)
app.include_router(fixtures.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
app.include_router(constraints.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(agent_availability.router, prefix="/api/v1")
app.include_router(scenario_catalogue.router, prefix="/api/v1")
app.include_router(scenario_projection.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(proposals.router, prefix="/api/v1")
app.include_router(schedule_runs.router, prefix="/api/v1")
app.include_router(approvals.router, prefix="/api/v1")
