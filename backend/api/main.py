"""ShiftMind backend API.

Run from backend/:
    uv run uvicorn api.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from api.deps import get_settings
from api.routers import constraints, fixtures, health, runs, scenarios
from services import run_service
from store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(get_settings().db_path)
    yield
    run_service.shutdown()


app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)

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
