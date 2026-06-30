"""Tests for GET /runs/{run_id}/insights — happy path, not-ready, cache, and negative-path matrix.

Exercises (plan 03-01):
- test_insights_returns_report_for_completed_run: COMPLETED run -> 200 ready=true with
  a non-empty report that cites the run's metric values (D-01, INS-01).
- test_insights_not_ready_returns_200_body: not-COMPLETED run -> 200 (NOT 409) with
  ready=false and a status field (D-07).

Exercises (plan 03-02 — negative-path + edge matrix):
- test_second_fetch_uses_cache: CountingInsightProvider proves call_count stays 1 across
  two sequential GETs and both return identical bodies (INS-04).
- test_provider_failure_leaves_run_completed: forcing the provider to fail returns 502 and
  leaves run COMPLETED with result_json untouched; nothing is cached (D-08, INS-02).
- test_grounding_guard_rejects_fabricated_number: FabricatingInsightProvider returns a
  number absent from metrics -> 502, nothing cached (D-06, INS-03).
- test_report_narrates_degenerate_warnings: solve result with a zero-coverage warning ->
  200, report narrates the warning honestly (D-05 item 3, INS-03).
- test_unknown_and_failed_run: unknown run id -> 404; FAILED run -> 200 ready=false (D-07).
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


def _wait_terminal(client, run_id, timeout_s=10.0):
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

    # Import after env is set so nothing caches the default settings.
    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    # Stub drives generation with zero network calls (TEST-01, D-09).
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_and_complete_run(client):
    """Create a scenario, trigger a run, wait for COMPLETED; return (scenario_id, run_id)."""
    r = client.post("/scenarios", json={
        "name": "insight-smoke", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201, r.text
    scenario_id = r.json()["id"]

    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]

    done = _wait_terminal(client, run_id)
    assert done["status"] == "COMPLETED"
    return scenario_id, run_id


def test_insights_returns_report_for_completed_run(client):
    """COMPLETED run -> 200, ready=true, non-empty report citing the run's metrics (D-01, INS-01)."""
    _, run_id = _create_and_complete_run(client)

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True
    assert body["run_id"] == run_id
    report = body["report"]
    assert report, "report must be non-empty"
    # The StubEngine returns total_cost=123.0 and total_unmet_hours=2.0;
    # the insight report must cite these values (grounded metrics, INS-03).
    assert "123" in report, f"report must cite total_cost=123; got: {report!r}"
    assert "2" in report, f"report must cite total_unmet_hours=2; got: {report!r}"


def test_insights_not_ready_returns_200_body(client):
    """Not-COMPLETED run -> 200 (NOT 409) with ready=false and a status field (D-07).

    The key D-07 property is always verified: HTTP 200 is returned for any run status
    (not 409).  The body-shape check (ready=False + status field) is exercised when the
    insights call races ahead of completion; if the stub engine completes first the run
    is COMPLETED and ready=True, which is also correct — the test checks both branches.
    We never assert based on pre-fetched status to avoid a TOCTOU race.
    """
    r = client.post("/scenarios", json={
        "name": "not-ready-test", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run_id = r.json()["id"]

    # Call insights immediately; the run may be in any state.
    r_insights = client.get(f"/runs/{run_id}/insights")

    # D-07 core property: HTTP 200 regardless of run status (never 409).
    assert r_insights.status_code == 200, (
        f"Must return 200 (not 409) for any run status; got {r_insights.status_code}: {r_insights.text}"
    )
    body = r_insights.json()
    assert "run_id" in body and body["run_id"] == run_id

    if not body["ready"]:
        # Not-ready body shape: must include status field with the run's current status (D-07).
        assert "status" in body, f"Not-ready body must include a status field: {body}"
    else:
        # Run completed before insights was called — ready=True with a report is also correct.
        assert body.get("report"), "ready=True body must include a non-empty report"


def test_second_fetch_uses_cache(client):
    """Two sequential GETs yield identical bodies; CountingInsightProvider proves call_count stays 1 (INS-04).

    Only asserts sequential behaviour — do NOT assert call_count under parallel load (Open Question 1).
    """
    from api.deps import get_llm_provider
    from api.main import app

    counter = CountingInsightProvider()
    app.dependency_overrides[get_llm_provider] = lambda: counter

    _, run_id = _create_and_complete_run(client)

    r1 = client.get(f"/runs/{run_id}/insights")
    assert r1.status_code == 200, r1.text
    assert r1.json()["ready"] is True

    r2 = client.get(f"/runs/{run_id}/insights")
    assert r2.status_code == 200, r2.text
    assert r2.json()["ready"] is True

    assert r1.json()["report"] == r2.json()["report"], (
        "Second fetch must return cached report identical to first fetch"
    )
    assert counter.call_count == 1, (
        f"generate_insights must be called exactly once (cache hit on second call); got {counter.call_count}"
    )


# ---------------------------------------------------------------------------
# Test doubles for negative-path + edge testing (plan 03-02)
# ---------------------------------------------------------------------------


class FailingInsightProvider:
    """Raises on generate_insights — tests failure isolation (D-08, INS-02)."""

    name = "failing-stub"

    def parse_constraints(self, text: str) -> list:
        return []

    def generate_insights(self, summary: dict) -> str:
        raise RuntimeError("provider down")


class FabricatingInsightProvider:
    """Returns a fabricated number absent from the run metrics — tests D-06 grounding guard (INS-03)."""

    name = "fabricating-stub"

    def parse_constraints(self, text: str) -> list:
        return []

    def generate_insights(self, summary: dict) -> str:
        # 99999 is never produced by StubEngine (total_cost=123, unmet=2); guard must reject this.
        return "Total cost was 99999."


class CountingInsightProvider:
    """Counts generate_insights calls — tests INS-04 cache (sequential only, Open Question 1)."""

    name = "counting-stub"

    def __init__(self) -> None:
        self.call_count = 0

    def parse_constraints(self, text: str) -> list:
        return []

    def generate_insights(self, summary: dict) -> str:
        self.call_count += 1
        m = summary["metrics"]
        cost = m.get("total_cost")
        return f"Cost {cost:g} unmet {m.get('total_unmet_hours'):g}."


# ---------------------------------------------------------------------------
# Negative-path + edge tests (plan 03-02)
# ---------------------------------------------------------------------------


def test_provider_failure_leaves_run_completed(client):
    """Forcing the provider to fail returns 502 but leaves run COMPLETED and result_json intact (D-08, INS-02).

    After a 502, a subsequent GET with a working provider returns 200 ready=True —
    proving nothing was cached on the failed call.
    """
    from api.deps import get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    _, run_id = _create_and_complete_run(client)

    # Capture result_json before any insight call to use as a reference for the integrity check.
    r = client.get(f"/runs/{run_id}/result")
    assert r.status_code == 200
    original_result = r.json()

    # Install failing provider.
    app.dependency_overrides[get_llm_provider] = lambda: FailingInsightProvider()

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 502, (
        f"Expected 502 from failing provider; got {r.status_code}: {r.text}"
    )

    # Run status must remain COMPLETED — insight path must never mutate it (D-08).
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETED", (
        f"Run status was corrupted after provider failure: {r.json()}"
    )

    # result_json must be unchanged.
    r = client.get(f"/runs/{run_id}/result")
    assert r.status_code == 200
    assert r.json() == original_result, "result_json was modified after provider failure"

    # Nothing was cached — restoring a working provider must generate successfully
    # (proves the failed call cached nothing, INS-02).
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, (
        f"Expected 200 from working provider after failure; got {r.status_code}: {r.text}"
    )
    assert r.json()["ready"] is True
    assert r.json()["report"], "Report must be non-empty after recovery from provider failure"


def test_grounding_guard_rejects_fabricated_number(client):
    """FabricatingInsightProvider returns 99999 (absent from metrics) → 502; nothing is cached (D-06, INS-03).

    After the 502, a subsequent GET with a working provider returns 200 ready=True,
    proving the ungrounded report was never persisted to insight_json.
    """
    from api.deps import get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    _, run_id = _create_and_complete_run(client)

    # Install fabricating provider (emits 99999 which is not in StubEngine's metric values).
    app.dependency_overrides[get_llm_provider] = lambda: FabricatingInsightProvider()

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 502, (
        f"Expected 502 from grounding guard rejection; got {r.status_code}: {r.text}"
    )

    # Nothing was cached — restoring a working provider must generate successfully.
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, (
        f"Expected 200 from working provider after grounding rejection; got {r.status_code}: {r.text}"
    )
    assert r.json()["ready"] is True
    assert r.json()["report"], "Report must be non-empty after recovery from grounding rejection"


def test_report_narrates_degenerate_warnings(client):
    """A solve result with a zero-coverage warning must be narrated honestly in the report (D-05 item 3, INS-03).

    The warning text must appear in the insight report — the stub must not mask it with a
    generic "coverage was adequate" phrase.
    """
    from api.deps import get_engine
    from api.main import app

    warning_msg = "Zero coverage for the 'Pick' function on day 0"

    class DegenerateStubEngine:
        """Stub engine that returns a SolveResult with a zero-coverage degenerate warning."""

        name = "degenerate-stub"

        def solve(self, problem, config) -> SolveResult:
            return SolveResult(
                status="OPTIMAL",
                schedule=[ScheduleRow(
                    contact_id="c1", member_name="Tester", task_id="t1",
                    function="Pick", shift_id="s1", start_h=0.0, end_h=8.0)],
                metrics=SummaryMetrics(
                    coverage_by_function={"Pick": CoverageStat(required_h=10.0, served_h=0.0)},
                    coverage_by_day={0: 0.0},
                    total_cost=123.0, total_unmet_hours=10.0,
                    scheduled_shifts=1, scheduled_members=1),
                stats=SolverStats(status="OPTIMAL", wall_time_s=0.01,
                                  unmet_objective_hours=10.0, cost_objective=123.0),
                warnings=[warning_msg],
            )

    app.dependency_overrides[get_engine] = lambda: DegenerateStubEngine()

    r = client.post("/scenarios", json={
        "name": "degenerate-warning-test", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run_id = r.json()["id"]

    done = _wait_terminal(client, run_id)
    assert done["status"] == "COMPLETED"

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True, f"Run is COMPLETED but ready=False: {body}"
    report = body["report"]
    assert "WARNING" in report, (
        f"Report must narrate the degenerate-family warning; got: {report!r}"
    )
    assert warning_msg in report, (
        f"Report must contain the exact warning text; got: {report!r}"
    )


def test_unknown_and_failed_run(client):
    """GET on an unknown run id → 404; GET on a FAILED run → 200 ready=false (D-07, INS-02)."""
    from api.deps import get_engine
    from api.main import app

    # Unknown run id → 404.
    r = client.get("/runs/nonexistent-run-id/insights")
    assert r.status_code == 404, (
        f"Expected 404 for unknown run id; got {r.status_code}: {r.text}"
    )

    # FAILED run → 200 ready=false (D-07: HTTP 200 for any non-COMPLETED status, not 409).
    class FailingStubEngine:
        """Raises on solve — causes the run to end in FAILED status."""

        name = "failing-engine-stub"

        def solve(self, problem, config):
            raise RuntimeError("engine failed deliberately for test_unknown_and_failed_run")

    app.dependency_overrides[get_engine] = lambda: FailingStubEngine()

    r = client.post("/scenarios", json={
        "name": "failed-run-test", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201
    run_id = r.json()["id"]

    done = _wait_terminal(client, run_id)
    assert done["status"] == "FAILED", f"Expected FAILED status but got {done['status']}"

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, (
        f"Expected 200 (not 409) for FAILED run insights; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body["ready"] is False, f"FAILED run must return ready=False; got: {body}"
    assert "status" in body, f"Not-ready body must include a status field: {body}"


def test_insights_succeeds_when_scenario_has_overrides(client):
    """Insight generation must return 200 when the scenario has numeric constraint args (CR-01 regression).

    A constraint with a numeric arg (n=4 from 'at least 4 on Pick') stores that arg value
    in scenario.overrides. Before the CR-01 fix, StubLLMProvider.generate_insights emitted
    ov['args'] as a Python dict repr, so '4' appeared in the report as an ungrounded numeric
    token that the D-06 grounding guard rejected with 502. The fix omits ov['args'] and only
    emits the tool name, so any constrained scenario can generate insights successfully.
    """
    r = client.post("/scenarios", json={
        "name": "with-override", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    assert r.status_code == 201, r.text
    scenario_id = r.json()["id"]

    # Apply a constraint with a numeric arg — this populates scenario.overrides with n=4.
    # "Amb Rec" uniquely matches "Amb Rec | Unloader" in the tiny fixture (avoids the
    # multi-match clarification that generic tokens like "Pick" trigger).
    r = client.post("/constraints", json={
        "scenario_id": scenario_id, "text": "at least 4 on Amb Rec"})
    assert r.status_code == 200, r.text
    assert r.json()["applied"], (
        f"Constraint must be applied (not rejected/clarification): {r.json()}"
    )

    r = client.post(f"/scenarios/{scenario_id}/runs")
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    _wait_terminal(client, run_id)

    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, (
        f"Insight generation returned {r.status_code} for a scenario with numeric override args; "
        f"expected 200. Body: {r.text}"
    )
    assert r.json()["ready"] is True, (
        f"ready must be True for a COMPLETED run with a grounded report; got: {r.json()}"
    )
