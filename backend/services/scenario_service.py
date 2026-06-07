"""Scenario use-cases: create/list/get. Pure orchestration over the repo."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from store.repositories import ScenarioRepo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_scenario(conn: sqlite3.Connection, name: str, fixture: str,
                    time_limit_s: float = 60.0,
                    overrides: Optional[dict] = None) -> dict:
    sid = uuid.uuid4().hex
    repo = ScenarioRepo(conn)
    repo.insert({
        "id": sid,
        "name": name,
        "fixture": fixture,
        "time_limit_s": float(time_limit_s),
        "overrides": json.dumps(overrides or {}),
        "created_at": _now(),
    })
    conn.commit()
    return repo.get(sid)


def list_scenarios(conn: sqlite3.Connection) -> list[dict]:
    return ScenarioRepo(conn).list()


def get_scenario(conn: sqlite3.Connection, scenario_id: str) -> Optional[dict]:
    return ScenarioRepo(conn).get(scenario_id)
