"""SQLite connection + schema. WAL mode so a background solve thread can write
run status while request threads read, each on its own connection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    fixture      TEXT NOT NULL,
    time_limit_s REAL NOT NULL DEFAULT 60,
    overrides    TEXT NOT NULL DEFAULT '{}',   -- JSON; reserved for Phase 3 NL constraints
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    scenario_id   TEXT NOT NULL REFERENCES scenarios(id),
    status        TEXT NOT NULL,               -- PENDING / RUNNING / COMPLETED / FAILED
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    solver_status TEXT,                         -- OPTIMAL / FEASIBLE / UNKNOWN / ...
    error         TEXT,
    result_json   TEXT                          -- serialized SolveResult (metrics + schedule)
);

CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open a connection (one per thread/unit of work). Caller closes it."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
