"""Tests for POST /constraints and end-to-end NL -> override -> re-solve round-trip.

Exercises (plan 01-02):
- POST /constraints with a valid text -> 200 with structured body (applied[], rejected[],
  clarification_needed, no_constraint_found)
- Override is persisted to scenario.overrides JSON (idempotent re-submission, D-04/D-05)
- Unknown scenario_id -> 404
- Text that yields no constraint -> 200 with no_constraint_found=True (D-03)
- Ambiguous task token (matches >1 task) -> 200 with clarification_needed (NLC-05)
- Unknown task token -> 200 with rejected[0] naming the token (VAL-02)
- n <= 0 -> 200 with rejected[0] (not 400)
- Nothing persisted on rejected/clarification paths (T-02-02)

Exercises (plan 01-03 — end-to-end round-trip, TEST-02):
- POST /constraints + trigger run -> stored override is threaded into SolverConfig.overrides
- Control: scenario with no constraint completes with empty SolverConfig.overrides (baseline, ENG-06)

Exercises (plan 02-01 — Phase-2 parse-UX contract, NLC-03/04/05, VAL-02/03):
- Partial phrasing ("more people on packing") -> clarification_needed (NLC-05)
- Mixed valid + partial text -> applied[] and clarification_needed both non-null (D-02)
- Conjunction-split ("...and...") -> multiple tool calls parsed from one text

Exercises (plan 02-04 — TEST-03 validation suite):
- Unknown task token in scale_demand -> rejected[] naming the token, not persisted (VAL-02/TEST-03)
- scale_demand factor=0 -> rejected[] naming 'factor', not persisted (VAL-01/TEST-03)
- Rejection error strings name the offending ref AND list valid options (VAL-03/TEST-03)
- Mixed valid+unknown-member multi-tool -> applied[]+rejected[] in one 200; only valid persisted
  (criterion 5/TEST-03/T-02-11)
- Mixed valid+out-of-bounds-arg multi-tool -> applied[]+rejected[] in one 200; only valid persisted
  (criterion 5/TEST-03/T-02-11)
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
# Happy path — Phase-2 structured response (applied[] field)
# ---------------------------------------------------------------------------

def test_post_constraints_returns_200(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 200


def test_post_constraints_response_has_structured_body(client, scenario_id):
    """Response body must have the four Phase-2 top-level fields (D-01)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    body = r.json()
    assert "applied" in body
    assert "rejected" in body
    assert "clarification_needed" in body
    assert "no_constraint_found" in body


def test_post_constraints_applied_has_required_fields(client, scenario_id):
    """applied[0] must carry id, tool, args, parsed_constraint (NLC-04)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    body = r.json()
    assert len(body["applied"]) == 1
    entry = body["applied"][0]
    assert "id" in entry
    assert "tool" in entry
    assert "args" in entry
    assert "parsed_constraint" in entry


def test_post_constraints_echoes_correct_tool(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.json()["applied"][0]["tool"] == "set_min_workers_per_task"


def test_post_constraints_args_has_resolved_task_id(client, scenario_id):
    """args.task_id should be the real GUID, not the human token."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    args = r.json()["applied"][0]["args"]
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
    assert r.json()["applied"][0]["id"].startswith("ov_")


def test_post_constraints_parsed_constraint_is_string(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    pc = r.json()["applied"][0]["parsed_constraint"]
    assert isinstance(pc, str)
    assert len(pc) > 0


def test_post_constraints_persists_override_to_scenario(client, scenario_id):
    """Override dict must be written to the scenario's overrides column."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 200
    applied = r.json()["applied"][0]
    override_id = applied["id"]

    # Direct verification: re-submit same constraint, should return same id.
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick",
    })
    assert r2.status_code == 200
    assert r2.json()["applied"][0]["id"] == override_id  # idempotent (D-04/D-05)

    # D-02: the stored overrides JSON must carry parsed_constraint alongside
    # tool/args, matching the value returned in applied[] (persistence fidelity).
    from settings import default_settings
    from store import db as db_module

    conn = db_module.connect(default_settings().db_path)
    try:
        row = conn.execute(
            "SELECT overrides FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
    finally:
        conn.close()
    stored = json.loads(row["overrides"])
    assert override_id in stored
    assert stored[override_id]["parsed_constraint"] == applied["parsed_constraint"]
    assert stored[override_id]["tool"] == applied["tool"]
    assert stored[override_id]["args"] == applied["args"]


def test_post_constraints_idempotent_same_id(client, scenario_id):
    """Re-submitting the same constraint is idempotent: same id, no duplicate."""
    r1 = client.post("/constraints", json={
        "scenario_id": scenario_id, "text": "at least 3 on C Pick"})
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id, "text": "at least 3 on C Pick"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["applied"][0]["id"] == r2.json()["applied"][0]["id"]


# ---------------------------------------------------------------------------
# Error paths — 404 preserved; per-call failures become structured signals
# ---------------------------------------------------------------------------

def test_post_constraints_unknown_scenario_returns_404(client):
    r = client.post("/constraints", json={
        "scenario_id": "nonexistent-scenario-id",
        "text": "at least 2 on C Pick",
    })
    assert r.status_code == 404


def test_post_constraints_rejects_tampered_path_traversal_fixture(tmp_path, monkeypatch):
    """A scenario row whose stored fixture escapes data_dir (e.g. written by a
    path other than the validated POST /scenarios route) must still be
    rejected cleanly at parse time — 404, never a 500 (CR-03 defense-in-depth).
    """
    import sqlite3

    db_path = tmp_path / "test-traversal.db"
    monkeypatch.setenv("ROSTERAI_DB", str(db_path))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    with TestClient(app) as c:
        r = c.post("/scenarios", json={
            "name": "test-traversal",
            "fixture": "sample_tiny_input.json",
            "time_limit_s": 5,
        })
        assert r.status_code == 201
        scenario_id = r.json()["id"]

        # Simulate a stored fixture value that escapes data_dir — bypasses the
        # POST /scenarios validation (e.g. legacy row, manual DB edit).
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE scenarios SET fixture=? WHERE id=?",
            ("../../backend/settings.py", scenario_id),
        )
        conn.commit()
        conn.close()

        r2 = c.post("/constraints", json={
            "scenario_id": scenario_id,
            "text": "at least 2 on C Pick",
        })
        assert r2.status_code == 404, (
            f"A tampered/escaping fixture path must map to 404, got {r2.status_code}: {r2.text}"
        )
    app.dependency_overrides.clear()


def test_post_constraints_provider_failure_returns_503(tmp_path, monkeypatch):
    """A raised LLMProviderError must map to a clean 503, never a bare 500 (quick-260709-m9m)."""
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test-503.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.base import LLMProviderError

    class _FailingProvider:
        name = "failing"

        def parse_constraints(self, text: str):
            raise LLMProviderError("boom")

        def generate_insights(self, summary: dict) -> str:
            raise LLMProviderError("boom")

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    app.dependency_overrides[get_llm_provider] = lambda: _FailingProvider()
    with TestClient(app) as c:
        r = c.post("/scenarios", json={
            "name": "test-503",
            "fixture": "sample_tiny_input.json",
            "time_limit_s": 5,
        })
        assert r.status_code == 201
        scenario_id = r.json()["id"]

        r2 = c.post("/constraints", json={
            "scenario_id": scenario_id,
            "text": "at least 2 on C Pick",
        })
        assert r2.status_code == 503
        assert r2.json()["detail"] == (
            "The scheduling assistant is temporarily unavailable. Please try again shortly."
        )
    app.dependency_overrides.clear()


def test_malformed_llm_tool_args_rejected_not_500(tmp_path, monkeypatch):
    """A provider that emits malformed/missing tool-call args must yield a clean
    200 with rejected[] entries, never an uncaught 500 (CR-02).

    Exercises all five tool branches with a mix of a missing required key and a
    non-numeric value in a single request, proving the KeyError/ValueError guard
    added around each branch's arg extraction routes failures into rejected[]
    instead of letting them escape.
    """
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test-malformed-args.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from domain.overrides import OverrideCall

    class _MalformedArgsProvider:
        name = "malformed"

        def parse_constraints(self, text: str):
            return [
                # Missing required numeric key entirely. "C Pick" resolves
                # uniquely (unlike bare "Pick", which is ambiguous across
                # three tasks) so this exercises the numeric-arg guard, not
                # the clarification path.
                OverrideCall(id="c1", tool="set_min_workers_per_task",
                             args={"task_id": "C Pick"}),
                # Non-numeric value the LLM might emit for a free-text slot.
                OverrideCall(id="c2", tool="scale_demand",
                             args={"task_id": "C Pick", "factor": "a lot"}),
                # Missing member_id entirely.
                OverrideCall(id="c3", tool="lock_worker_shift", args={"day": 0}),
                # Non-string member_id (e.g. a stray null from the LLM).
                OverrideCall(id="c4", tool="exclude_worker_from_task",
                             args={"member_id": None, "task_id": "C Pick"}),
                OverrideCall(id="c5", tool="set_max_hours",
                             args={"member_id": "Gary", "max_hours": "forty"}),
            ]

        def generate_insights(self, summary: dict) -> str:
            return "n/a"

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    app.dependency_overrides[get_llm_provider] = lambda: _MalformedArgsProvider()
    with TestClient(app) as c:
        r = c.post("/scenarios", json={
            "name": "test-malformed-args",
            "fixture": "sample_tiny_input.json",
            "time_limit_s": 5,
        })
        assert r.status_code == 201
        scenario_id = r.json()["id"]

        r2 = c.post("/constraints", json={
            "scenario_id": scenario_id,
            "text": "irrelevant — provider is stubbed to emit malformed args",
        })
        assert r2.status_code == 200, (
            f"Malformed LLM tool args must never 500, got {r2.status_code}: {r2.text}"
        )
        body = r2.json()
        assert body["applied"] == [], "No malformed call should ever apply"
        assert len(body["rejected"]) == 5, (
            f"All five malformed calls must land in rejected[], got: {body['rejected']}"
        )
    app.dependency_overrides.clear()


def test_no_constraint_found_in_text_returns_200_with_flag(client, scenario_id):
    """Gibberish text -> 200 with no_constraint_found=True (NLC-03/D-03)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "hello there",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["no_constraint_found"] is True
    assert body["applied"] == []
    assert body["clarification_needed"] is None


def test_ambiguous_task_token_returns_clarification_needed(client, scenario_id):
    """'Pick' alone matches C Pick, F Pick, A Pick -> clarification_needed not None (NLC-05/D-04)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on Pick",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["clarification_needed"] is not None
    assert "Pick" in body["clarification_needed"]
    assert body["applied"] == []


def test_unknown_task_token_returns_rejected(client, scenario_id):
    """Unknown token -> 200 with rejected[0].error naming the offending token (VAL-02/D-11)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on NonExistentTask",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) == 1
    assert "NonExistentTask" in body["rejected"][0]["error"]
    assert body["applied"] == []


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
# Phase-2 parse-UX contract: partial phrasing + conjunction-split (NLC-05/D-02)
# ---------------------------------------------------------------------------

def test_partial_phrasing_clarification(client, scenario_id):
    """'more people on <task>' (no number) -> 200 with clarification_needed (NLC-05)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "more people on C Pick",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["clarification_needed"] is not None
    assert "C Pick" in body["clarification_needed"]
    assert body["no_constraint_found"] is False


def test_mixed_applied_and_clarification(client, scenario_id):
    """'at least 2 on C Pick and more people on packing' -> one applied + clarification_needed (D-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick and more people on packing",
    })
    assert r.status_code == 200
    body = r.json()
    # One valid constraint applied
    assert len(body["applied"]) == 1
    assert body["applied"][0]["tool"] == "set_min_workers_per_task"
    # And a clarification signal from the partial fragment
    assert body["clarification_needed"] is not None
    assert body["no_constraint_found"] is False


def test_rejected_entries_not_persisted(client, scenario_id):
    """Rejected entries must not be written to scenario.overrides (T-02-02)."""
    # Post an unknown task (goes to rejected[])
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on GhostTask",
    })
    assert r.status_code == 200
    assert len(r.json()["rejected"]) == 1

    # Now post a valid constraint and check its id in applied[]
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 3 on C Pick",
    })
    assert r2.status_code == 200
    # Only the valid one should be persisted (idempotency shows it was stored)
    r3 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 3 on C Pick",
    })
    assert r3.json()["applied"][0]["id"] == r2.json()["applied"][0]["id"]


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
    posted_id = r.json()["applied"][0]["id"]
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


# ---------------------------------------------------------------------------
# Plan 02-02: Four new tools — happy-path round-trips (NLC-02/NLC-04)
# ---------------------------------------------------------------------------

def test_scale_demand_applied(client, scenario_id):
    """'scale C Pick demand by 1.5x' -> applied[] with tool='scale_demand' (NLC-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "scale C Pick demand by 1.5x",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1
    entry = body["applied"][0]
    assert entry["tool"] == "scale_demand"
    assert len(entry["parsed_constraint"]) > 0, "parsed_constraint must be non-empty (NLC-04)"


def test_lock_worker_shift_applied(client, scenario_id):
    """'keep Gary on Monday' -> applied[] with tool='lock_worker_shift' (NLC-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "keep Gary on Monday",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1
    entry = body["applied"][0]
    assert entry["tool"] == "lock_worker_shift"
    assert len(entry["parsed_constraint"]) > 0, "parsed_constraint must be non-empty (NLC-04)"


def test_exclude_worker_from_task_applied(client, scenario_id):
    """'exclude Gary from C Pick' -> applied[] with tool='exclude_worker_from_task' (NLC-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "exclude Gary from C Pick",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1
    entry = body["applied"][0]
    assert entry["tool"] == "exclude_worker_from_task"
    assert len(entry["parsed_constraint"]) > 0, "parsed_constraint must be non-empty (NLC-04)"


def test_set_max_hours_applied(client, scenario_id):
    """'cap Gary at 40 hours' -> applied[] with tool='set_max_hours' (NLC-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "cap Gary at 40 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1
    entry = body["applied"][0]
    assert entry["tool"] == "set_max_hours"
    assert len(entry["parsed_constraint"]) > 0, "parsed_constraint must be non-empty (NLC-04)"


# ---------------------------------------------------------------------------
# Plan 02-02: Argument bounds validation (VAL-01)
# ---------------------------------------------------------------------------

def test_scale_demand_bad_factor_rejected(client, scenario_id):
    """factor=0 is invalid -> rejected[] entry naming the arg (VAL-01/D-12)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "scale C Pick demand by 0x",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) >= 1, "factor=0 must be rejected"
    assert any("factor" in e["error"].lower() or "0" in e["error"] for e in body["rejected"]), (
        "rejection error must mention the offending arg (VAL-03)"
    )


def test_max_hours_zero_rejected(client, scenario_id):
    """max_hours=0 is invalid -> rejected[] entry naming the arg (VAL-01/D-12)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "cap Gary at 0 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) >= 1, "max_hours=0 must be rejected"
    assert any("max_hours" in e["error"].lower() or "0" in e["error"] for e in body["rejected"]), (
        "rejection error must mention the offending arg (VAL-03)"
    )


def test_unknown_member_rejected(client, scenario_id):
    """Unknown member ref -> rejected[] entry naming the unknown token (VAL-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "cap XYZ_NONEXISTENT_MEMBER at 40 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) >= 1, "unknown member must be rejected"
    assert any("XYZ_NONEXISTENT_MEMBER" in e["error"] for e in body["rejected"]), (
        "rejection error must name the unknown token (VAL-03)"
    )


def test_lock_out_of_horizon_day_rejected(client, scenario_id):
    """day=7 is outside a 7-day horizon (valid days 0..6) -> rejected[] (VAL-01/D-12)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "lock Gary on 7",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) >= 1, "out-of-horizon day must be rejected"


# ---------------------------------------------------------------------------
# Plan 02-02: Multi-match member -> clarification_needed (NLC-05)
# ---------------------------------------------------------------------------

def test_multi_row_same_person_resolves_without_clarification(client, scenario_id):
    """'Jae' matches two Member rows sharing one contact_id -> resolves cleanly, no
    clarification (CR-01 regression test).

    The fixture has two roster entries for Jae Rerekura (same contact_id but two
    Member objects from two windows). Before CR-01, `_resolve_member` counted these
    as two distinct candidates and always asked an unanswerable clarification
    question ("'Jae Rerekura' matches multiple members: 'Jae Rerekura', 'Jae
    Rerekura'"). Deduping by contact_id means a single real person triggers a
    normal apply, not a clarification.
    """
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "cap Jae at 40 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["clarification_needed"] is None, (
        "A single real person spanning multiple roster rows must not trigger "
        "clarification (CR-01)"
    )
    assert len(body["applied"]) == 1, "The constraint must apply once dedup resolves 'Jae' uniquely"
    assert body["applied"][0]["args"]["member_id"] == "DF47249E-8864-41B6-93CB-004100655A58"


# ---------------------------------------------------------------------------
# Plan 02-02: Multi-tool sentence yields multiple applied[] entries (NLC-02)
# ---------------------------------------------------------------------------

def test_multi_tool_applied(client, scenario_id):
    """Two-constraint text yields two applied[] entries (NLC-02/D-02)."""
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick and cap Gary at 40 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 2, (
        f"Expected 2 applied entries for two-constraint text, got {len(body['applied'])}: "
        f"{[e['tool'] for e in body['applied']]}"
    )
    tools = {e["tool"] for e in body["applied"]}
    assert "set_min_workers_per_task" in tools
    assert "set_max_hours" in tools
    assert body["no_constraint_found"] is False


# ---------------------------------------------------------------------------
# Plan 02-04: TEST-03 validation suite — unknown IDs and out-of-bounds args
# ---------------------------------------------------------------------------

def test_unknown_task_rejected(client, scenario_id):
    """scale_demand with an unknown task token -> 200, rejected[] naming the token (VAL-02/TEST-03).

    Tests the rejection path for the scale_demand tool (one of the four new tools added
    in plan 02-02) to ensure unknown task references are rejected with a plain-English error
    and are never persisted to scenario.overrides.
    """
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "scale GHOST_TASK_NONEXISTENT demand by 2.0x",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) == 1, (
        f"Unknown task must produce exactly one rejected entry, got {len(body['rejected'])}"
    )
    assert "GHOST_TASK_NONEXISTENT" in body["rejected"][0]["error"], (
        "Rejection error must name the unknown token (VAL-02)"
    )
    assert body["applied"] == [], "No override must be applied for an unknown task reference"
    # Rejected item must not be persisted: re-submit still rejects (non-persistence proof)
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "scale GHOST_TASK_NONEXISTENT demand by 2.0x",
    })
    assert r2.status_code == 200
    assert r2.json()["applied"] == [], "Ghost task must never appear in applied[] after re-submit"
    assert len(r2.json()["rejected"]) == 1, "Ghost task must still be rejected on re-submit"


def test_scale_demand_bad_factor(client, scenario_id):
    """scale_demand with factor=0 -> 200, rejected[] naming 'factor', not persisted (VAL-01/TEST-03).

    Distinct from test_scale_demand_bad_factor_rejected: uses an alternate phrasing and
    explicitly asserts non-persistence via a re-submit check (T-02-02/TEST-03).
    """
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "boost C Pick volume by 0x",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) >= 1, "factor=0 must produce at least one rejected entry (VAL-01)"
    error = body["rejected"][0]["error"]
    assert "factor" in error.lower(), (
        f"Rejection error must name the offending arg 'factor', got: {error!r}"
    )
    assert body["applied"] == [], "No override must be applied for an out-of-bounds factor"
    # Rejected item must not be persisted: re-submit still rejects
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "boost C Pick volume by 0x",
    })
    assert r2.status_code == 200
    assert r2.json()["applied"] == [], "OOB factor must never appear in applied[] after re-submit"
    assert len(r2.json()["rejected"]) >= 1, "OOB factor must still be rejected on re-submit"


def test_rejection_error_names_ref(client, scenario_id):
    """Rejection errors must name the offending reference AND list valid options (VAL-03/TEST-03).

    Verifies that the service embeds both the bad token and a list of valid alternatives in
    every zero-match rejection error, so the user can immediately self-correct.
    """
    # --- Unknown task ---
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "scale BAD_TASK_REF demand by 1.5x",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) == 1, "Unknown task must be rejected"
    task_error = body["rejected"][0]["error"]
    assert "BAD_TASK_REF" in task_error, (
        f"Error must name the offending token 'BAD_TASK_REF', got: {task_error!r}"
    )
    assert "Valid tasks:" in task_error, (
        f"Error must list valid task options (VAL-03), got: {task_error!r}"
    )

    # --- Unknown member ---
    r2 = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "cap BAD_MEMBER_REF at 40 hours",
    })
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["rejected"]) == 1, "Unknown member must be rejected"
    member_error = body2["rejected"][0]["error"]
    assert "BAD_MEMBER_REF" in member_error, (
        f"Error must name the offending token 'BAD_MEMBER_REF', got: {member_error!r}"
    )
    assert "Valid members:" in member_error, (
        f"Error must list valid member options (VAL-03), got: {member_error!r}"
    )


# ---------------------------------------------------------------------------
# Plan 02-04: TEST-03 — Mixed valid/invalid multi-tool calls (criterion 5)
# ---------------------------------------------------------------------------

def test_mixed_valid_invalid_multi_tool(client, scenario_id):
    """Mixed: valid set_min_workers + unknown-member exclude -> applied[]+rejected[] in one 200.

    Proves criterion 5 (must-have truth 3): a single NL sentence with one valid fragment
    and one unknown-member reference yields both applied[] and rejected[] in the same 200
    response. Only the valid fragment is persisted to scenario.overrides (T-02-11/TEST-03).
    """
    text = "at least 2 on C Pick and exclude XYZ_NONEXISTENT_MEMBER from C Pick"
    r = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1, (
        f"Expected 1 applied entry (valid fragment), got {len(body['applied'])}: "
        f"{[e['tool'] for e in body['applied']]}"
    )
    assert len(body["rejected"]) == 1, (
        f"Expected 1 rejected entry (unknown-member fragment), got {len(body['rejected'])}"
    )
    assert body["applied"][0]["tool"] == "set_min_workers_per_task"
    assert "XYZ_NONEXISTENT_MEMBER" in body["rejected"][0]["error"], (
        "Rejection error must name the unknown member token (VAL-02/VAL-03)"
    )

    # Only the valid constraint was persisted: re-submit yields same applied id (idempotent)
    applied_id = body["applied"][0]["id"]
    r2 = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    assert r2.status_code == 200
    assert r2.json()["applied"][0]["id"] == applied_id, (
        "Re-submitting the same text must return the same applied id (idempotent persist)"
    )
    assert len(r2.json()["rejected"]) == 1, (
        "Unknown-member fragment must still be rejected on re-submit (never persisted)"
    )


def test_mixed_valid_oob_multi_tool(client, scenario_id):
    """Mixed: valid set_min_workers + scale_demand with factor=0 -> applied[]+rejected[] in one 200.

    Proves criterion 5 (must-have truth 4): a single NL sentence with one valid fragment
    and one out-of-bounds arg yields both applied[] and rejected[] in the same 200
    response. Only the valid fragment is persisted to scenario.overrides (T-02-11/TEST-03).
    """
    text = "at least 3 on C Pick and boost C Pick volume by 0x"
    r = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1, (
        f"Expected 1 applied entry (valid fragment), got {len(body['applied'])}: "
        f"{[e['tool'] for e in body['applied']]}"
    )
    assert len(body["rejected"]) == 1, (
        f"Expected 1 rejected entry (out-of-bounds factor), got {len(body['rejected'])}"
    )
    assert body["applied"][0]["tool"] == "set_min_workers_per_task"
    assert "factor" in body["rejected"][0]["error"].lower(), (
        "Rejection error must name the offending arg 'factor' (VAL-01/VAL-03)"
    )

    # Only the valid constraint was persisted: re-submit yields same applied id (idempotent)
    applied_id = body["applied"][0]["id"]
    r2 = client.post("/constraints", json={"scenario_id": scenario_id, "text": text})
    assert r2.status_code == 200
    assert r2.json()["applied"][0]["id"] == applied_id, (
        "Re-submitting must return the same applied id (idempotent persist)"
    )
    assert len(r2.json()["rejected"]) == 1, (
        "OOB-factor fragment must still be rejected on re-submit (never persisted)"
    )
