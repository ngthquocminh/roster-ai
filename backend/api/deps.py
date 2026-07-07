"""FastAPI dependencies: settings, a per-request DB connection, and the engine.

`get_engine` is a seam: tests override it with a stub so the run lifecycle can
be exercised without a real (slow) solve.
"""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends

from engine.base import SchedulerEngine, create_engine
from llm.base import LLMProvider, create_provider
from settings import Settings, default_settings
from store import db


def get_settings() -> Settings:
    return default_settings()


def get_db(settings: Settings = Depends(get_settings)) -> Iterator:
    conn = db.connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_engine() -> SchedulerEngine:
    return create_engine("cpsat")


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return create_provider(settings.llm_provider, settings=settings)
