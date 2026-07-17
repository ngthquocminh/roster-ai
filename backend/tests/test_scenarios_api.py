"""Tests for GET /scenarios/{scenario_id}/overrides (plan 02-01).

Exercises (D-01, SCEN-03):
- 200 with the scenario's persisted overrides as a JSON array of
  {id, tool, args, parsed_constraint}
- 404 for an unknown scenario id
- A legacy override stored without a parsed_constraint key deserializes with
  parsed_constraint=null and the endpoint returns 200, never 500
- Empty overrides -> 200 + []
- Idempotent re-submission of the same constraint text overwrites the same
  content-hash override id in place (one entry, not two)
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    # Import after env is set so settings are not cached with wrong paths.
    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    from tests.test_constraints_api import StubEngine

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
        "name": "test-overrides",
        "fixture": "sample_tiny_input.json",
        "time_limit_s": 5,
    })
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
# GET /scenarios/{scenario_id}/overrides
# ---------------------------------------------------------------------------

def test_overrides(client, scenario_id):
    """POST a valid constraint, then GET overrides -> 200 + matching entry (D-01)."""
    post = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert post.status_code == 200
    applied = post.json()["applied"][0]

    r = client.get(f"/scenarios/{scenario_id}/overrides")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    entry = body[0]
    assert set(entry.keys()) == {"id", "tool", "args", "parsed_constraint"}
    assert entry["id"] == applied["id"]
    assert entry["tool"] == applied["tool"]
    assert entry["args"] == applied["args"]
    assert entry["parsed_constraint"] == applied["parsed_constraint"]


def test_overrides_404(client):
    """Unknown scenario id -> 404 with the same detail as the existing detail route."""
    r = client.get("/scenarios/nonexistent-scenario-id/overrides")
    assert r.status_code == 404
    assert r.json()["detail"] == "Scenario not found"


def test_overrides_legacy(client, scenario_id):
    """A legacy override (no parsed_constraint key) deserializes to null, never 500."""
    from settings import default_settings
    from store import db
    from store.repositories import ScenarioRepo

    legacy_overrides = {
        "ov_legacy1": {
            "tool": "set_min_workers_per_task",
            "args": {"task_id": "99260066-B32A-423D-97A1-8A649BABBAAD", "n": 3},
            # deliberately no parsed_constraint key
        }
    }
    conn = db.connect(default_settings().db_path)
    try:
        ScenarioRepo(conn).update_overrides(scenario_id, json.dumps(legacy_overrides))
        conn.commit()
    finally:
        conn.close()

    r = client.get(f"/scenarios/{scenario_id}/overrides")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "ov_legacy1"
    assert body[0]["parsed_constraint"] is None


def test_overrides_colliding_stored_id_never_shadows_the_real_key(client, scenario_id):
    """A stored override value carrying its own 'id' field must never clobber the
    dict's real key (WR-02). Not a shape any current writer produces, but the
    endpoint's spread order must be defensive against it regardless.
    """
    from settings import default_settings
    from store import db
    from store.repositories import ScenarioRepo

    colliding_overrides = {
        "ov_real_key": {
            "tool": "set_min_workers_per_task",
            "args": {"task_id": "99260066-B32A-423D-97A1-8A649BABBAAD", "n": 3},
            "parsed_constraint": "At least 3 workers",
            "id": "ov_should_never_win",
        }
    }
    conn = db.connect(default_settings().db_path)
    try:
        ScenarioRepo(conn).update_overrides(scenario_id, json.dumps(colliding_overrides))
        conn.commit()
    finally:
        conn.close()

    r = client.get(f"/scenarios/{scenario_id}/overrides")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "ov_real_key", (
        "The dict's own key must always win over a same-named field in the stored value"
    )


def test_overrides_empty(client, scenario_id):
    """A scenario with no overrides returns 200 + []."""
    r = client.get(f"/scenarios/{scenario_id}/overrides")
    assert r.status_code == 200
    assert r.json() == []


def test_overrides_idempotent(client, scenario_id):
    """Re-submitting the same constraint text twice overwrites the same id in place."""
    text = "at least 2 on C Pick"
    r1 = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    r2 = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["applied"][0]["id"] == r2.json()["applied"][0]["id"]

    r = client.get(f"/scenarios/{scenario_id}/overrides")
    assert r.status_code == 200
    assert len(r.json()) == 1
