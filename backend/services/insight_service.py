"""Insight generation: load run -> status gate -> cache hit -> generate -> guard -> persist.

Orchestrates on-demand NL report generation for a completed run.  Runs synchronously
on the FastAPI anyio threadpool (sync def route in runs.py) — never touches the
single-worker solve pool (D-02).

Key design properties:
- Failure isolation: provider/guard errors raise InsightGenerationError and write
  nothing to the DB — run status and result_json are never modified (D-08, INS-02).
- Cache: on a second call the stored insight_json is returned before calling the
  provider, capping generation at one per run (INS-04).
- Grounding: _grounding_guard runs BEFORE set_insight so a fabricated number is
  never persisted (D-06, Pitfall 2).
- Overrides: read from the scenario's CURRENT overrides JSON — the run stores no
  overrides snapshot (Research Pitfall 5); D-05 item 4.
"""
from __future__ import annotations

import json
import re
import sqlite3

from llm.base import LLMProvider
from store.repositories import RunRepo, ScenarioRepo


class InsightGenerationError(RuntimeError):
    """Raised when the provider fails or the grounding guard rejects the report."""


# ---------------------------------------------------------------------------
# D-06 grounding guard
# ---------------------------------------------------------------------------

# Matches digit runs with optional thousands-commas and an optional decimal part.
# Examples: "123", "1,234", "80.5", "2.0"
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


def _allowed_values(metrics: dict) -> set[float]:
    """Build the set of floating-point values derivable from the run metrics dict.

    Admits each metric value plus round(.,1)/round(.,2) variants.  For coverage
    pct values (stored as fractions, e.g. 0.8 = 80%) also admits value×100 so
    a report line "80%" passes the guard (Pitfall 3).
    None metrics contribute nothing — any number emitted for a null metric is caught.
    """
    vals: set[float] = set()

    def admit(x):
        if x is None or not isinstance(x, (int, float)):
            return
        for y in (x, round(x, 1), round(x, 2)):
            vals.add(float(y))

    admit(metrics.get("total_cost"))
    admit(metrics.get("total_unmet_hours"))
    admit(metrics.get("scheduled_shifts"))
    admit(metrics.get("scheduled_members"))
    for c in (metrics.get("coverage_by_function") or {}).values():
        admit(c.get("required_h"))
        admit(c.get("served_h"))
        admit(c.get("pct"))
        pct = c.get("pct")
        if isinstance(pct, (int, float)):  # fraction -> percentage (Pitfall 3)
            for y in (pct * 100, round(pct * 100, 1)):
                vals.add(float(y))
    for p in (metrics.get("coverage_by_day") or {}).values():
        admit(p)
        if isinstance(p, (int, float)):
            vals.add(float(p * 100))
    return vals


def _grounding_guard(report: str, metrics: dict, *, tol: float = 0.05) -> None:
    """Raise InsightGenerationError if any numeric token in report is not in allowed values.

    Strips thousands-commas from each token, parses to float, and checks against
    the allowed-value set (within tolerance tol) built from the run's metrics dict.
    This ensures every number cited in the report comes from the run's own data (D-06).
    """
    allowed = _allowed_values(metrics)
    for tok in _NUM_RE.findall(report):
        v = float(tok.replace(",", ""))
        if not any(abs(v - a) <= tol for a in allowed):
            raise InsightGenerationError(
                f"Ungrounded number {tok!r} not found in run metrics (D-06)"
            )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def get_or_generate(
    conn: sqlite3.Connection,
    provider: LLMProvider,
    run_id: str,
) -> dict:
    """Load the run, apply status gate + cache check, generate and guard if needed, persist.

    Returns:
        {ready: True, run_id, report}   — COMPLETED + report available (fresh or cached)
        {ready: False, run_id, status, reason} — run not yet COMPLETED (D-07)

    Raises:
        LookupError           — unknown run_id (router translates -> 404)
        InsightGenerationError — provider raised or grounding guard failed (router -> 502)
    """
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise LookupError(f"Run {run_id!r} not found")  # router -> 404

    # Status gate: only COMPLETED runs with a result can yield an insight.
    if run["status"] != "COMPLETED" or not run["result_json"]:
        return {  # deliberate 200 (not 409 / not an error), D-07
            "ready": False,
            "run_id": run_id,
            "status": run["status"],
            "reason": f"Insights available only for COMPLETED runs (status: {run['status']})",
        }

    # Cache hit: return stored insight without calling the provider (INS-04).
    if run["insight_json"]:
        return {"ready": True, "run_id": run_id, "report": run["insight_json"]}

    # Cache miss: build grounded summary dict -> generate -> guard -> persist -> return.
    result = json.loads(run["result_json"])
    metrics = result["metrics"]
    warnings = result.get("warnings", [])

    # Read current scenario overrides (no snapshot stored on the run — Research Pitfall 5).
    scenario = ScenarioRepo(conn).get(run["scenario_id"])
    raw_overrides = json.loads((scenario or {}).get("overrides") or "{}")
    overrides = [{"tool": v["tool"], "args": v["args"]} for v in raw_overrides.values()]

    summary = {"metrics": metrics, "warnings": warnings, "overrides": overrides}

    # Provider call is wrapped so any exception becomes InsightGenerationError (D-08).
    try:
        report = provider.generate_insights(summary)
    except Exception as exc:  # noqa: BLE001
        raise InsightGenerationError(f"Provider failed: {exc}") from exc

    # Guard BEFORE persisting — never cache an ungrounded report (Pitfall 2).
    _grounding_guard(report, metrics)

    repo.set_insight(run_id, report)
    conn.commit()
    return {"ready": True, "run_id": run_id, "report": report}
