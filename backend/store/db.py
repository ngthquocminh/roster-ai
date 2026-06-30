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
    result_json   TEXT,                         -- serialized SolveResult (metrics + schedule)
    insight_json  TEXT                          -- cached NL insight report (INS-04)
);

CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);
"""


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    """Return True if the given column exists on the table (used for additive migrations)."""
    # PRAGMA does not support parameterised names; validate to prevent injection-style errors.
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table!r}")
    return any(r["name"] == col
               for r in conn.execute(f"PRAGMA table_info({table})"))


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
        conn.executescript(_SCHEMA)                            # fresh DBs: column already in DDL
        if not _has_column(conn, "runs", "insight_json"):     # existing DBs: additive migration
            conn.execute("ALTER TABLE runs ADD COLUMN insight_json TEXT")
        conn.commit()
    finally:
        conn.close()
