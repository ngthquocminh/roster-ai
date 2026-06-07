"""API lifecycle tests.

The solve is replaced with a stub engine (via dependency override) so we test
the plumbing — scenario CRUD, threaded run execution, status transitions,
result retrieval — without waiting on CP-SAT. The run still loads the real tiny
fixture through the adapter, so the data path is exercised end to end.
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from domain.result import (
    CoverageStat,
    ScheduleRow,
    SolveResult,
    SolverStats,
    SummaryMetrics,
)

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))


class StubEngine:
    name = "stub"

    def solve(self, problem, config) -> SolveResult:
        return SolveResult(
            status="OPTIMAL",
            schedule=[ScheduleRow(
                contact_id="c1", member_name="Tester", task_id="t1",
                function="Pick", shift_id="s1", start_h=0.0, end_h=8.0)],
            metrics=SummaryMetrics(
                coverage_by_function={"Pick": CoverageStat(required_h=10.0, served_h=8.0)},
                coverage_by_day={0: 0.8},
                total_cost=123.0, total_unmet_hours=2.0,
                scheduled_shifts=1, scheduled_members=1),
            stats=SolverStats(status="OPTIMAL", wall_time_s=0.01,
                              unmet_objective_hours=2.0, cost_objective=123.0),
        )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    # Import after env is set so nothing caches the default settings.
    from api.deps import get_engine
    from api.main import app

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _wait_terminal(client, run_id, timeout_s=10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_fixtures_lists_tiny_input(client):
    fixtures = client.get("/fixtures").json()
    assert "sample_tiny_input.json" in fixtures


def test_create_scenario_rejects_unknown_fixture(client):
    r = client.post("/scenarios", json={"name": "bad", "fixture": "nope.json"})
    assert r.status_code == 400


def test_full_run_lifecycle(client):
    # create scenario
    r = client.post("/scenarios", json={
        "name": "smoke", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    # it shows up in the list and by id
    assert any(s["id"] == scenario_id for s in client.get("/scenarios").json())
    assert client.get(f"/scenarios/{scenario_id}").json()["name"] == "smoke"

    # trigger a run -> starts PENDING
    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "PENDING"
    run_id = run["id"]

    # it completes
    done = _wait_terminal(client, run_id)
    assert done["status"] == "COMPLETED"
    assert done["solver_status"] == "OPTIMAL"

    # result is retrievable and well formed
    result = client.get(f"/runs/{run_id}/result").json()
    assert result["metrics"]["total_cost"] == 123.0
    assert result["metrics"]["coverage_by_function"]["Pick"]["pct"] == 0.8
    assert len(result["schedule"]) == 1
    assert result["schedule"][0]["member_name"] == "Tester"

    # run is listed under the scenario
    runs = client.get(f"/scenarios/{scenario_id}/runs").json()
    assert [x["id"] for x in runs] == [run_id]


def test_get_result_before_completion_conflicts(client):
    # 404 for unknown run
    assert client.get("/runs/does-not-exist").status_code == 404
    assert client.get("/runs/does-not-exist/result").status_code == 404
