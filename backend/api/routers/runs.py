"""Run lifecycle: trigger a solve, poll status, fetch results."""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_engine, get_settings
from api.schemas import RunOut
from engine.base import SchedulerEngine
from services import run_service, scenario_service
from settings import Settings
from store.repositories import RunRepo

router = APIRouter(tags=["runs"])


@router.post("/scenarios/{scenario_id}/runs", response_model=RunOut, status_code=201,
             responses={404: {"description": "Scenario not found"}})
def trigger_run(
    scenario_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
    engine: SchedulerEngine = Depends(get_engine),
) -> dict:
    scenario = scenario_service.get_scenario(conn, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    run = run_service.create_run(conn, scenario_id)
    run_service.submit_run(run["id"], scenario, engine,
                           settings.db_path, settings.data_dir)
    return run


@router.get("/scenarios/{scenario_id}/runs", response_model=list[RunOut])
def list_runs(scenario_id: str, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    return RunRepo(conn).list_by_scenario(scenario_id)


@router.get("/runs/{run_id}", response_model=RunOut,
            responses={404: {"description": "Run not found"}})
def get_run(run_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    run = RunRepo(conn).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/result",
            responses={404: {"description": "Run not found"},
                       409: {"description": "Run not completed yet"}})
def get_run_result(run_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    run = RunRepo(conn).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "COMPLETED" or not run["result_json"]:
        raise HTTPException(
            status_code=409,
            detail=f"Result not available (run status: {run['status']})",
        )
    return json.loads(run["result_json"])
