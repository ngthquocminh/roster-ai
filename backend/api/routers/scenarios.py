"""Scenario CRUD."""
from __future__ import annotations

import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_settings
from api.schemas import OverrideOut, ScenarioCreate, ScenarioOut
from services import scenario_service
from settings import Settings

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("", response_model=ScenarioOut, status_code=201,
             responses={400: {"description": "Unknown fixture"}})
def create_scenario(
    body: ScenarioCreate,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not os.path.isfile(os.path.join(settings.data_dir, body.fixture)):
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
    return [{"id": k, **v} for k, v in raw.items()]
