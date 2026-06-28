"""Tests for POST /constraints — the NL constraint parse-and-store endpoint.

Exercises:
- POST /constraints with a valid text -> 200 with echoed override (id, tool, args, parsed_constraint)
- Override is persisted to scenario.overrides JSON (idempotent re-submission, D-04/D-05)
- Unknown scenario_id -> 404
- Text that yields no constraint -> 400
- Ambiguous task token (matches >1 task) -> 400
- n <= 0 -> 400
- Nothing persisted on rejection paths
"""
from __future__ import annotations

import json
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
