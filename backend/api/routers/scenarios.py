"""Scenario CRUD."""
from __future__ import annotations

import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_settings
from api.schemas import OverrideOut, ScenarioCreate, ScenarioOut
from services import scenario_service
from settings import Settings, resolve_fixture_path

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("", response_model=ScenarioOut, status_code=201,
             responses={400: {"description": "Unknown fixture"}})
def create_scenario(
    body: ScenarioCreate,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    # CR-03: reject a fixture value that is absolute or that normalizes
    # outside data_dir (path traversal) before ever touching the filesystem.
    fixture_path = resolve_fixture_path(settings.data_dir, body.fixture)
    if fixture_path is None or not os.path.isfile(fixture_path):
        raise HTTPException(status_code=400, detail=f"Unknown fixture: {body.fixture!r}")
    return scenario_service.create_scenario(
        conn, name=body.name, fixture=body.fixture, time_limit_s=body.time_limit_s)


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    return scenario_service.list_scenarios(conn)


@router.get("/{scenario_id}", response_model=ScenarioOut,
            responses={404: {"description": "Scenario not found"}})
def get_scenario(scenario_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    s = scenario_service.get_scenario(conn, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return s


@router.get("/{scenario_id}/overrides", response_model=list[OverrideOut],
            responses={404: {"description": "Scenario not found"}})
def get_scenario_overrides(
    scenario_id: str, conn: sqlite3.Connection = Depends(get_db)
) -> list[dict]:
    s = scenario_service.get_scenario(conn, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    raw = json.loads(s["overrides"] or "{}")
    # Natural insertion order (first-applied-first), no server-side re-sort — deliberate (D-01).
    # Spread `v` first so the dict's own "id" key (the JSON store key) always
    # wins over any same-named field a stored value might ever carry (WR-02).
    return [{**v, "id": k} for k, v in raw.items()]
