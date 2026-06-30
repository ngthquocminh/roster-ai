# Phase 3: On-Demand Insight Reports - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 8 (6 modified, 2 new)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/api/routers/runs.py` (edit) | controller | request-response | itself — `get_run_result` (line 51) | exact |
| `backend/api/schemas.py` (edit) | schema/model | — | `RunOut` + `ConstraintParseResponse` in same file | exact |
| `backend/llm/base.py` (edit) | provider-seam protocol | — | itself — `parse_constraints` (line 16) | exact |
| `backend/llm/stub.py` (edit) | provider-seam stub | request-response | itself — `StubLLMProvider.parse_constraints` (line 126) | exact |
| `backend/store/db.py` (edit) | config/migration | — | itself — `_SCHEMA` + `init_db` (lines 9–52) | exact |
| `backend/store/repositories.py` (edit) | model/DAO | CRUD | itself — `RunRepo.set_completed` / `set_failed` (lines 72–84) | exact |
| `backend/services/insight_service.py` (new) | service | request-response | `backend/services/run_service.py` (orchestration) + `backend/services/serialize.py` (metrics shape) | role-match |
| `backend/tests/test_insights_api.py` (new) | test | — | `backend/tests/test_api.py` (StubEngine + dependency_overrides pattern) | role-match |

---

## Pattern Assignments

### `backend/api/routers/runs.py` — Add `GET /runs/{run_id}/insights`

**Analog:** `get_run_result` in same file (`backend/api/routers/runs.py` lines 51–63)

**Imports pattern** (lines 1–14 — all already present; add `get_llm_provider` and `insight_service`):
```python
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_engine, get_settings, get_llm_provider   # add get_llm_provider
from api.schemas import RunOut, InsightOut                                  # add InsightOut
from engine.base import SchedulerEngine
from llm.base import LLMProvider
from services import run_service, scenario_service, insight_service         # add insight_service
from settings import Settings
from store.repositories import RunRepo
```

**Core pattern — sync `def` route (line 51):**
```python
# Existing analog — exact shape to copy:
@router.get("/runs/{run_id}/result",
            responses={404: {"description": "Run not found"},
                       409: {"description": "Run not completed yet"}})
def get_run_result(run_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    run = RunRepo(conn).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "COMPLETED" or not run["result_json"]:
        raise HTTPException(
            status_code=409,
            detail=f"Result not available (run status: {run['status']})",
        )
    return json.loads(run["result_json"])
```

**New route — differences from analog (D-07 / D-08):**
- Add `provider: LLMProvider = Depends(get_llm_provider)` parameter (reuse LLM-03 seam)
- Not-ready → return 200 body `{ready: False, ...}` (NOT 409 — deliberate divergence, D-07)
- Provider/guard failure → raise `HTTPException(status_code=502, ...)` (D-08)
- Delegate all orchestration to `insight_service.get_or_generate(conn, provider, run_id)`
- `response_model=InsightOut`

**Error handling pattern** (lines 42–48 analog for `get_run`):
```python
# Service raises / router translates — the project-wide pattern:
run = RunRepo(conn).get(run_id)
if run is None:
    raise HTTPException(status_code=404, detail="Run not found")
```

---

### `backend/api/schemas.py` — Add `InsightOut`

**Analog:** `RunOut` (lines 23–31) and `ConstraintParseResponse` (lines 51–55) in same file

**Imports pattern** (lines 1–6 — already present):
```python
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
```

**Core pattern — `RunOut` shape to mirror:**
```python
class RunOut(BaseModel):
    id: str
    scenario_id: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    solver_status: Optional[str] = None
    error: Optional[str] = None
```

**New schema — `InsightOut`** (per RESEARCH.md code examples):
```python
class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None    # present when ready=True (INS-01)
    status: Optional[str] = None    # present when ready=False (D-07)
    reason: Optional[str] = None    # present when ready=False (D-07)
```

---

### `backend/llm/base.py` — Add `generate_insights` to `LLMProvider` Protocol

**Analog:** `parse_constraints` in same file (lines 15–19)

**Full current file (lines 1–27):**
```python
"""LLMProvider seam — the swap point for language-model backends. ..."""
from __future__ import annotations

from typing import Protocol

from domain.overrides import OverrideCall


class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...

    @property
    def name(self) -> str: ...


def create_provider(name: str) -> LLMProvider:
    """Registry of available LLM providers. Add a backend here to make it swappable."""
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub']")
```

**Edit: add `generate_insights` alongside `parse_constraints` (line 17, after `parse_constraints`):**
```python
class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    def generate_insights(self, summary: dict) -> str: ...   # NEW — D-09 second operation

    @property
    def name(self) -> str: ...
```

`summary` dict shape (built by `insight_service`, provider-neutral, no domain object crosses seam):
```python
{
    "metrics": { ...serialize_result()["metrics"]... },   # total_cost, total_unmet_hours, coverage_by_function, coverage_by_day
    "warnings": [ ...result["warnings"]... ],             # D-05 #3
    "overrides": [ {"tool": "...", "args": {...}}, ... ], # D-05 #4
}
```

---

### `backend/llm/stub.py` — Add `StubLLMProvider.generate_insights`

**Analog:** `StubLLMProvider.parse_constraints` in same file (lines 126–234)

**Class structure to mirror (lines 121–127):**
```python
class StubLLMProvider:
    """Keyword-routed stub. Deterministic and test-friendly; no external I/O."""

    name = "stub"

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        ...
```

**Add after `parse_constraints`:**
```python
def generate_insights(self, summary: dict) -> str:
    """Deterministic insight report — no external I/O (TEST-01).

    Emits only numbers that appear verbatim in summary["metrics"] so the D-06
    grounding guard passes by construction.  Small structural counts (e.g. the
    number of functions) are spelled as words, not digits, to avoid false-positive
    guard failures (Research A2).
    """
    m = summary.get("metrics", {})
    cost = m.get("total_cost")
    unmet = m.get("total_unmet_hours")
    cost_s = f"{cost:g}" if cost is not None else "not available"
    unmet_s = f"{unmet:g}" if unmet is not None else "not available"
    lines = [
        f"Schedule solved with total cost {cost_s} and {unmet_s} unmet hours.",
    ]
    for fn, c in (m.get("coverage_by_function") or {}).items():
        if c.get("pct") is not None:
            pct = c["pct"] * 100
            lines.append(
                f"- {fn}: served {c['served_h']:g}/{c['required_h']:g} h ({pct:g}%)"
            )
    for w in summary.get("warnings", []):
        lines.append(f"- WARNING: {w}")
    for ov in summary.get("overrides", []):
        lines.append(f"- override applied: {ov['tool']} {ov['args']}")
    return "\n".join(lines)
```

**Key constraint:** Every number emitted (`cost`, `unmet`, `served_h`, `required_h`, `pct×100`) must come directly from `summary["metrics"]` so the D-06 guard passes.

---

### `backend/store/db.py` — Add `insight_json` column + `ALTER TABLE` guard

**Analog:** `_SCHEMA` runs table DDL (lines 19–31) and `init_db` (lines 46–52) in same file

**Current `_SCHEMA` runs table (lines 19–31):**
```python
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
```

**Edit 1: Add `insight_json` to the DDL string** (after `result_json` line):
```sql
    result_json   TEXT,                         -- serialized SolveResult (metrics + schedule)
    insight_json  TEXT                          -- cached NL insight report (INS-04)
```

**Current `init_db` (lines 46–52):**
```python
def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
```

**Edit 2: Add idempotent `ALTER TABLE` guard** (for existing DBs — D-10):
```python
def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r["name"] == col
               for r in conn.execute(f"PRAGMA table_info({table})"))


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA)                           # fresh DBs: column already in DDL
        if not _has_column(conn, "runs", "insight_json"):    # existing DBs: additive migration
            conn.execute("ALTER TABLE runs ADD COLUMN insight_json TEXT")
        conn.commit()
    finally:
        conn.close()
```

---

### `backend/store/repositories.py` — Add `RunRepo.set_insight`

**Analog:** `RunRepo.set_failed` (lines 80–84) and `RunRepo.set_completed` (lines 72–78) in same file

**Analog pattern to copy:**
```python
def set_failed(self, run_id: str, error: str, finished_at: str) -> None:
    self.conn.execute(
        "UPDATE runs SET status='FAILED', error=?, finished_at=? WHERE id=?",
        (error, finished_at, run_id),
    )
```

**New method — add after `set_failed`:**
```python
def set_insight(self, run_id: str, insight_json: str) -> None:
    """Cache the generated NL report. Caller commits. Never touches status/result_json (D-08)."""
    self.conn.execute(
        "UPDATE runs SET insight_json=? WHERE id=?",
        (insight_json, run_id),
    )
```

**Note:** `RunRepo.get` (lines 55–57) uses `SELECT *` and needs no change — `insight_json` is returned automatically once the column exists.

---

### `backend/services/insight_service.py` (NEW)

**Analog:** `backend/services/run_service.py` (orchestration structure, lines 75–101) and `backend/services/serialize.py` (metrics dict shape, lines 20–45)

**Imports pattern** (mirror `run_service.py` imports, adapted for insight path):
```python
"""Insight generation: load run → status gate → cache hit → generate → guard → persist."""
from __future__ import annotations

import json
import re
import sqlite3

from llm.base import LLMProvider
from store.repositories import RunRepo, ScenarioRepo
```

**Orchestration pattern from `run_service._execute` (lines 75–101):**
```python
# Pattern: open own connection, use repos, catch exceptions, commit after write
def _execute(run_id, scenario, engine, db_path, data_dir) -> None:
    conn = db.connect(db_path)
    repo = RunRepo(conn)
    try:
        repo.set_running(run_id, _now())
        conn.commit()
        # ... work ...
        repo.set_completed(run_id, result.status, json.dumps(serialize_result(result)), _now())
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        repo.set_failed(run_id, f"{type(exc).__name__}: {exc}", _now())
        conn.commit()
    finally:
        conn.close()
```

**Insight service orchestration (adapted — key differences from the solve path):**
- `conn` is passed in from the router's `get_db` dependency (no separate thread/pool)
- On provider/guard failure: raise `InsightGenerationError` (router maps → 5xx); NEVER call `set_failed`/`set_completed` (D-08 / Pitfall 1)
- On not-ready: return a plain dict `{ready: False, ...}` (D-07); no raise
- Cache hit: return `{ready: True, report: run["insight_json"]}` before calling provider

```python
class InsightGenerationError(RuntimeError):
    """Raised when the provider fails or the grounding guard rejects the report."""


def get_or_generate(conn: sqlite3.Connection, provider: LLMProvider, run_id: str) -> dict:
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise LookupError(f"Run {run_id!r} not found")           # router → 404

    if run["status"] != "COMPLETED" or not run["result_json"]:
        return {                                                    # router → 200 (D-07)
            "ready": False,
            "run_id": run_id,
            "status": run["status"],
            "reason": f"Insights available only for COMPLETED runs (status: {run['status']})",
        }

    if run["insight_json"]:                                        # cache hit (INS-04)
        return {"ready": True, "run_id": run_id, "report": run["insight_json"]}

    # Cache miss: build grounded metrics dict → generate → guard → persist → return
    result = json.loads(run["result_json"])
    metrics = result["metrics"]
    warnings = result.get("warnings", [])
    scenario = ScenarioRepo(conn).get(run["scenario_id"])
    raw_overrides = json.loads((scenario or {}).get("overrides") or "{}")
    overrides = [{"tool": v["tool"], "args": v["args"]} for v in raw_overrides.values()]

    summary = {"metrics": metrics, "warnings": warnings, "overrides": overrides}
    try:
        report = provider.generate_insights(summary)
    except Exception as exc:                                       # provider error → D-08
        raise InsightGenerationError(f"Provider failed: {exc}") from exc

    _grounding_guard(report, metrics)                              # guard before persist (Pitfall 2)
    repo.set_insight(run_id, report)
    conn.commit()
    return {"ready": True, "run_id": run_id, "report": report}
```

**D-06 grounding guard (new logic; no codebase analog):**
```python
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


def _allowed_values(metrics: dict) -> set[float]:
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
        admit(c.get("required_h")); admit(c.get("served_h")); admit(c.get("pct"))
        if isinstance(c.get("pct"), (int, float)):         # fraction → percentage (Pitfall 3)
            for y in (c["pct"] * 100, round(c["pct"] * 100, 1)):
                vals.add(float(y))
    for p in (metrics.get("coverage_by_day") or {}).values():
        admit(p)
        if isinstance(p, (int, float)):
            vals.add(float(p * 100))
    return vals


def _grounding_guard(report: str, metrics: dict, *, tol: float = 0.05) -> None:
    allowed = _allowed_values(metrics)
    for tok in _NUM_RE.findall(report):
        v = float(tok.replace(",", ""))
        if not any(abs(v - a) <= tol for a in allowed):
            raise InsightGenerationError(
                f"Ungrounded number {tok!r} not found in run metrics (D-06)"
            )
```

**Metrics dict shape from `serialize_result` (lines 22–45 of `serialize.py`):**
```python
{
    "total_cost": _num(m.total_cost),           # None if NaN (round-2 timeout)
    "total_unmet_hours": _num(m.total_unmet_hours),
    "scheduled_shifts": m.scheduled_shifts,
    "scheduled_members": m.scheduled_members,
    "coverage_by_function": {
        fn: {"required_h": _num(c.required_h),
             "served_h": _num(c.served_h),
             "pct": _num(c.pct)}               # fraction (0.8 = 80%); Pitfall 3
        for fn, c in m.coverage_by_function.items()
    },
    "coverage_by_day": {str(d): _num(p) for d, p in m.coverage_by_day.items()},
}
```

---

### `backend/tests/test_insights_api.py` (NEW)

**Analog:** `backend/tests/test_api.py` — full file (lines 1–123)

**Imports pattern** (mirror `test_api.py` lines 1–23):
```python
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from domain.result import (
    CoverageStat, ScheduleRow, SolveResult, SolverStats, SummaryMetrics,
)
```

**`client` fixture pattern** (lines 46–58 — copy exactly, then also override `get_llm_provider`):
```python
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    from api.deps import get_engine
    from api.main import app

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

**For insight tests: also override `get_llm_provider` (from `test_constraints_api.py` line 93 pattern):**
```python
from api.deps import get_engine, get_llm_provider

app.dependency_overrides[get_engine] = lambda: StubEngine()
app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
```

**`_wait_terminal` helper** (lines 61–68 — copy verbatim):
```python
def _wait_terminal(client, run_id, timeout_s=10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")
```

**`StubEngine` definition** (lines 27–43 — copy verbatim into the new test file):
```python
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
```

**Stub variants for failure / fabrication injection (new, no codebase analog):**
```python
class FailingInsightProvider:
    """Raises on generate_insights — tests criterion 3 (INS-02)."""
    name = "failing-stub"
    def parse_constraints(self, text): return []
    def generate_insights(self, summary): raise RuntimeError("provider down")


class FabricatingInsightProvider:
    """Returns a fabricated number — tests D-06 grounding guard."""
    name = "fabricating-stub"
    def parse_constraints(self, text): return []
    def generate_insights(self, summary): return "Total cost was 99999."


class CountingInsightProvider:
    """Counts generate_insights calls — tests INS-04 cache (sequential only)."""
    name = "counting-stub"
    call_count = 0
    def parse_constraints(self, text): return []
    def generate_insights(self, summary):
        self.call_count += 1
        m = summary["metrics"]
        cost = m.get("total_cost")
        return f"Cost {cost:g} unmet {m.get('total_unmet_hours'):g}."
```

---

## Shared Patterns

### Service raises / router translates
**Source:** `backend/api/routers/runs.py` lines 44–48 and 54–63
**Apply to:** `GET /runs/{run_id}/insights` route
```python
# Unknown run → 404
run = RunRepo(conn).get(run_id)
if run is None:
    raise HTTPException(status_code=404, detail="Run not found")
# Service-level errors → mapped HTTP status (router layer only)
```

### `get_db` dependency injection (per-request connection)
**Source:** `backend/api/deps.py` lines 22–27
**Apply to:** New insight route — take `conn: sqlite3.Connection = Depends(get_db)`
```python
def get_db(settings: Settings = Depends(get_settings)) -> Iterator:
    conn = db.connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

### `get_llm_provider` seam (LLM-03 reuse)
**Source:** `backend/api/deps.py` lines 35–36
**Apply to:** New insight route — take `provider: LLMProvider = Depends(get_llm_provider)`
```python
def get_llm_provider() -> LLMProvider:
    return create_provider("stub")
```

### Parameterized SQL (security — V5 input validation)
**Source:** `backend/store/repositories.py` lines 55–57, 72–84
**Apply to:** New `RunRepo.set_insight` — must use `?` placeholders, never f-string interpolation
```python
self.conn.execute("UPDATE runs SET insight_json=? WHERE id=?", (insight_json, run_id))
```

### `from __future__ import annotations` + module docstring
**Source:** every backend module (e.g. `run_service.py` line 1, `serialize.py` line 1)
**Apply to:** `insight_service.py` and all edited files — module docstring always present

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| D-06 grounding guard (`_grounding_guard` / `_allowed_values`) | utility | transform | No post-hoc numeric verification exists in the codebase; logic is novel. RESEARCH.md Pattern 2 is the reference. |
| Counting / failing / fabricating stub providers for tests | test double | — | No parameterized stub variants exist yet; define inline in `test_insights_api.py`. |

---

## Metadata

**Analog search scope:** `backend/api/`, `backend/llm/`, `backend/services/`, `backend/store/`, `backend/tests/`
**Files read:** 9 source files, 2 planning documents
**Pattern extraction date:** 2026-06-30
