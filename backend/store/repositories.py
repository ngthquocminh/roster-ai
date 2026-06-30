"""Thin data-access repos over SQLite. Each wraps a connection; callers commit.

Rows are returned as plain dicts so the web/service layers never depend on
sqlite types.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional


def _dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


class ScenarioRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, s: dict) -> None:
        self.conn.execute(
            "INSERT INTO scenarios (id, name, fixture, time_limit_s, overrides, created_at) "
            "VALUES (:id, :name, :fixture, :time_limit_s, :overrides, :created_at)",
            s,
        )

    def get(self, scenario_id: str) -> Optional[dict]:
        return _dict(self.conn.execute(
            "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone())

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scenarios ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def update_overrides(self, scenario_id: str, overrides_json: str) -> None:
        """Write the overrides JSON column for a scenario. Caller commits."""
        self.conn.execute(
            "UPDATE scenarios SET overrides=? WHERE id=?",
            (overrides_json, scenario_id),
        )


class RunRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, r: dict) -> None:
        self.conn.execute(
            "INSERT INTO runs (id, scenario_id, status, created_at) "
            "VALUES (:id, :scenario_id, :status, :created_at)",
            r,
        )

    def get(self, run_id: str) -> Optional[dict]:
        return _dict(self.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

    def list_by_scenario(self, scenario_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE scenario_id = ? ORDER BY created_at DESC",
            (scenario_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_running(self, run_id: str, started_at: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status='RUNNING', started_at=? WHERE id=?",
            (started_at, run_id),
        )

    def set_completed(self, run_id: str, solver_status: str,
                      result_json: str, finished_at: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status='COMPLETED', solver_status=?, result_json=?, "
            "finished_at=? WHERE id=?",
            (solver_status, result_json, finished_at, run_id),
        )

    def set_failed(self, run_id: str, error: str, finished_at: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status='FAILED', error=?, finished_at=? WHERE id=?",
            (error, finished_at, run_id),
        )

    def set_insight(self, run_id: str, insight_json: str) -> None:
        """Cache the generated NL report. Caller commits. Never touches status/result_json (D-08)."""
        self.conn.execute(
            "UPDATE runs SET insight_json=? WHERE id=?",
            (insight_json, run_id),
        )
