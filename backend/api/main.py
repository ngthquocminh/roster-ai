"""ShiftMind backend API.

Run from backend/:
    uv run uvicorn api.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import get_settings
from api.routers import fixtures, health, runs, scenarios
from services import run_service
from store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(get_settings().db_path)
    yield
    run_service.shutdown()


app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(fixtures.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
