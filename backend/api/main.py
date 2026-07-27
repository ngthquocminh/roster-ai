"""ShiftMind backend API.

Run from backend/:
    uv run uvicorn api.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import get_identity_store, get_settings
from api.problems import problem_response
from api.routers import (
    auth,
    constraints,
    fixtures,
    health,
    runs,
    scenario_catalogue,
    scenarios,
)
from services import run_service
from store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(get_settings().db_path)
    yield
    run_service.shutdown()


app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)


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

app.include_router(health.router)
app.include_router(fixtures.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
app.include_router(constraints.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(scenario_catalogue.router, prefix="/api/v1")
