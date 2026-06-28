"""Run use-cases: create a run row, then execute the solve in a worker thread.

The solve is CPU-heavy and long (seconds to minutes), so it must never run on
the event loop. We submit it to a single-worker pool (solves are serialized —
one CPU-bound solve at a time) and persist status transitions
PENDING -> RUNNING -> COMPLETED/FAILED to SQLite. The worker opens its own
connection (sqlite connections aren't shared across threads).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from domain.overrides import OverrideCall
from engine.base import SchedulerEngine, SolverConfig
from ingest.input_adapter import load_problem
from services.serialize import serialize_result
from store import db
from store.repositories import RunRepo

# Single-worker pool: solves are CPU-bound, run one at a time. Created lazily and
# recreated after shutdown() so the app (and tests with repeated lifespans) can
# spin it up again.
_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="solve")
        return _pool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def shutdown() -> None:
    """Stop accepting new solves (called on app shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
            _pool = None


def create_run(conn: sqlite3.Connection, scenario_id: str) -> dict:
    """Insert a PENDING run and commit so the worker thread can see it."""
    rid = uuid.uuid4().hex
    repo = RunRepo(conn)
    repo.insert({
        "id": rid,
        "scenario_id": scenario_id,
        "status": "PENDING",
        "created_at": _now(),
    })
    conn.commit()
    return repo.get(rid)


def submit_run(run_id: str, scenario: dict, engine: SchedulerEngine,
               db_path: str, data_dir: str) -> None:
    """Schedule the solve on the worker pool. Returns immediately."""
    _get_pool().submit(_execute, run_id, scenario, engine, db_path, data_dir)


def _execute(run_id: str, scenario: dict, engine: SchedulerEngine,
             db_path: str, data_dir: str) -> None:
    conn = db.connect(db_path)
    repo = RunRepo(conn)
    try:
        repo.set_running(run_id, _now())
        conn.commit()

        path = os.path.join(data_dir, scenario["fixture"])
        problem = load_problem(path)
        # Parse scenario's stored overrides JSON (dict keyed by content-hash id, D-04)
        # into a list[OverrideCall] for SolverConfig. An empty store yields [] and the
        # solve is byte-identical to the baseline (ENG-06). Malformed entries raise
        # inside this try/except, marking the run FAILED rather than crashing the pool.
        raw = json.loads(scenario["overrides"] or "{}")
        overrides = [OverrideCall(id=k, tool=v["tool"], args=v["args"]) for k, v in raw.items()]
        config = SolverConfig(time_limit_s=float(scenario["time_limit_s"]), overrides=overrides)
        result = engine.solve(problem, config)

        repo.set_completed(run_id, result.status,
                           json.dumps(serialize_result(result)), _now())
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - persist any failure as run state
        repo.set_failed(run_id, f"{type(exc).__name__}: {exc}", _now())
        conn.commit()
    finally:
        conn.close()
