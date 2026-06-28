"""Tests for POST /constraints and end-to-end NL -> override -> re-solve round-trip.

Exercises (plan 01-02):
- POST /constraints with a valid text -> 200 with echoed override (id, tool, args, parsed_constraint)
- Override is persisted to scenario.overrides JSON (idempotent re-submission, D-04/D-05)
- Unknown scenario_id -> 404
- Text that yields no constraint -> 400
- Ambiguous task token (matches >1 task) -> 400
- n <= 0 -> 400
- Nothing persisted on rejection paths

Exercises (plan 01-03 — end-to-end round-trip, TEST-02):
- POST /constraints + trigger run -> stored override is threaded into SolverConfig.overrides
- Control: scenario with no constraint completes with empty SolverConfig.overrides (baseline, ENG-06)
"""
from __future__ import annotations

import json
import os
import threading
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


def _wait_terminal(client, run_id, timeout_s=10.0):
    """Poll until a run reaches COMPLETED or FAILED (mirrors test_api.py helper)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    # Import after env is set so settings are not cached with wrong paths.
    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    # Use the real StubLLMProvider (deterministic, no live API in CI — TEST-01)
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def scenario_id(client):
    """Create a scenario using the real tiny fixture and return its id."""
    r = client.post("/scenarios", json={
        "name": "test-constraints",
        "fixture": "sample_tiny_input.json",
        "time_limit_s": 5,
    })
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_post_constraints_returns_200(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 200


def test_post_constraints_response_has_required_fields(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    body = r.json()
    assert "id" in body
    assert "tool" in body
    assert "args" in body
    assert "parsed_constraint" in body


def test_post_constraints_echoes_correct_tool(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.json()["tool"] == "set_min_workers_per_task"


def test_post_constraints_args_has_resolved_task_id(client, scenario_id):
    """args.task_id should be the real GUID, not the human token."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    args = r.json()["args"]
    assert args["n"] == 2
    # The resolved task_id must be a GUID-like string (not the human token "C Pick")
    task_id = args["task_id"]
    assert task_id != "C Pick"
    # Should be the UUID for "C Pick | Picking chill 080"
    assert task_id == "99260066-B32A-423D-97A1-8A649BABBAAD"


def test_post_constraints_id_starts_with_ov(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.json()["id"].startswith("ov_")


def test_post_constraints_parsed_constraint_is_string(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert isinstance(r.json()["parsed_constraint"], str)
    assert len(r.json()["parsed_constraint"]) > 0


def test_post_constraints_persists_override_to_scenario(client, scenario_id):
    """Override dict must be written to the scenario's overrides column."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 200
    override_id = r.json()["id"]

    # Fetch the scenario — note ScenarioOut doesn't expose overrides, so we
    # trust the idempotency test below to prove persistence.
    # Direct verification: re-submit same constraint, should return same id.
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == override_id  # idempotent (D-04/D-05)


def test_post_constraints_idempotent_same_id(client, scenario_id):
    """Re-submitting the same constraint is idempotent: same id, no duplicate."""
    r1 = client.post("/constraints", json={
        "scenario_id": scenario_id, "text": "at least 3 on C Pick"})
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id, "text": "at least 3 on C Pick"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_post_constraints_unknown_scenario_returns_404(client):
    r = client.post("/constraints", json={
        "scenario_id": "nonexistent-scenario-id",
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 404


def test_post_constraints_no_constraint_in_text_returns_400(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "hello there",
    })
    assert r.status_code == 400


def test_post_constraints_ambiguous_task_token_returns_400(client, scenario_id):
    """'Pick' alone matches C Pick, F Pick, A Pick -> ambiguous -> 400."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on Pick",
    })
    assert r.status_code == 400


def test_post_constraints_unknown_task_token_returns_400(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on NonExistentTask",
    })
    assert r.status_code == 400


def test_post_constraints_nothing_persisted_on_404(client):
    """On 404 path nothing should be stored — calling again still 404."""
    r = client.post("/constraints", json={
        "scenario_id": "nonexistent",
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 404
    # A second call should also 404 (not 200 from a ghost persist)
    r2 = client.post("/constraints", json={
        "scenario_id": "nonexistent",
        "text": "at least 2 on C Pick",
    })
    assert r2.status_code == 404


def test_post_constraints_empty_text_returns_422(client, scenario_id):
    """Empty text fails Pydantic validation (min_length=1) -> 422."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "",
    })
    assert r.status_code == 422


def test_post_constraints_missing_scenario_id_returns_422(client):
    """Missing required field returns Pydantic 422."""
    r = client.post("/constraints", json={"text": "at least 2 on C Pick"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Plan 01-03: End-to-end round-trip tests (NL -> override -> re-solve)
# TEST-02: zero network calls; override threaded into SolverConfig.overrides
# ---------------------------------------------------------------------------

class CapturingEngine:
    """Stub engine that records every SolverConfig passed to solve().

    Thread-safe: _execute runs in a worker thread; solve() is called there and
    stores the config in a list guarded by a lock. The test reads captured_config
    after _wait_terminal confirms the run is done.
    """

    name = "capturing"

    def __init__(self):
        self._lock = threading.Lock()
        self._configs: list = []

    def solve(self, problem, config) -> SolveResult:
        with self._lock:
            self._configs.append(config)
        # Return a minimal valid SolveResult so the run reaches COMPLETED.
        return SolveResult(
            status="OPTIMAL",
            schedule=[],
            metrics=SummaryMetrics(
                coverage_by_function={},
                coverage_by_day={},
                total_cost=0.0,
                total_unmet_hours=0.0,
                scheduled_shifts=0,
                scheduled_members=0,
            ),
            stats=SolverStats(
                status="OPTIMAL",
                wall_time_s=0.01,
                unmet_objective_hours=0.0,
                cost_objective=0.0,
            ),
        )

    @property
    def captured_config(self):
        """Return the last captured SolverConfig, or None if solve not called yet."""
        with self._lock:
            return self._configs[-1] if self._configs else None


@pytest.fixture()
def _capture_pair(tmp_path, monkeypatch):
    """Yield (TestClient, CapturingEngine) with LLM stub; engine NOT overridden for honoring."""
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "capture.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    engine = CapturingEngine()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


def test_override_is_threaded_into_solver_config(_capture_pair):
    """Core threading test (plan 01-03, Task 1): stored override reaches SolverConfig.overrides.

    Before run_service._execute is patched (Task 1), config.overrides is always [].
    After the patch, it contains the OverrideCall persisted by POST /constraints.
    This test FAILS in RED (before Task 1) and PASSES in GREEN (after Task 1).
    """
    c, engine = _capture_pair

    # Create scenario and store a constraint.
    r = c.post("/scenarios", json={
        "name": "threading-test",
        "fixture": "sample_tiny_input.json",
        "time_limit_s": 5,
    })
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    r = c.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 200
    posted_id = r.json()["id"]
    assert posted_id.startswith("ov_")

    # Trigger a run and wait for it to reach a terminal state.
    r = c.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run_id = r.json()["id"]
    done = _wait_terminal(c, run_id, timeout_s=10.0)
    assert done["status"] == "COMPLETED"

    # The stored override MUST have been threaded into SolverConfig.overrides.
    cfg = engine.captured_config
    assert cfg is not None, "engine.solve was never called"
    assert len(cfg.overrides) == 1, (
        f"Expected 1 override in SolverConfig.overrides, got {len(cfg.overrides)}. "
        "Likely cause: run_service._execute does not read scenario['overrides'] (Task 1 not implemented)."
    )
    ov = cfg.overrides[0]
    assert ov.tool == "set_min_workers_per_task"
    assert ov.args["n"] == 2
    assert ov.args["task_id"] == "99260066-B32A-423D-97A1-8A649BABBAAD"
    assert ov.id == posted_id  # id is stable content hash (D-05)


def test_no_constraint_yields_empty_overrides_in_config(_capture_pair):
    """Control (ENG-06): scenario with no constraint -> SolverConfig.overrides is []."""
    c, engine = _capture_pair

    r = c.post("/scenarios", json={
        "name": "baseline",
        "fixture": "sample_tiny_input.json",
        "time_limit_s": 5,
    })
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    # No POST /constraints — run immediately.
    r = c.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run_id = r.json()["id"]
    done = _wait_terminal(c, run_id, timeout_s=10.0)
    assert done["status"] == "COMPLETED"

    cfg = engine.captured_config
    assert cfg is not None, "engine.solve was never called"
    assert cfg.overrides == [], (
        "SolverConfig.overrides must be empty when no constraint was posted (ENG-06). "
        f"Got: {cfg.overrides}"
    )
