---
phase: 03-on-demand-insight-reports
reviewed: 2026-06-30T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - backend/api/routers/runs.py
  - backend/api/schemas.py
  - backend/llm/base.py
  - backend/llm/stub.py
  - backend/services/insight_service.py
  - backend/store/db.py
  - backend/store/repositories.py
  - backend/tests/test_insights_api.py
  - backend/tests/test_llm_provider.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-30
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

The on-demand insight endpoint (vertical slice + negative-path hardening) is well-structured:
the service layer correctly separates the LLM seam from the route, the grounding guard runs
before any write, and the cache short-circuit is correctly placed before the provider call.
The test doubles cover the key failure paths.

One blocker was found: the `StubLLMProvider.generate_insights` implementation renders Python
dict reprs of override args directly into the report, producing numeric tokens (e.g. `n:
4`, `factor: 1.5`) that are not present in the run's metrics. The `_grounding_guard` then
rejects these tokens and returns 502. No test exercises the combined Phase-2+Phase-3 path
(constraints applied → insights requested), so the bug is invisible in the current suite.
In real use, every scenario with at least one numeric constraint arg fails at the insight
step with 502. Three additional warnings address a PRAGMA f-string, a missing schema
invariant, and an unguarded key access.

---

## Critical Issues

### CR-01: `StubLLMProvider.generate_insights` emits Python dict repr of override args — any numeric arg value is absent from metrics and triggers the grounding guard (502 on any constrained scenario)

**File:** `backend/llm/stub.py:260-261`
**Also affects:** `backend/services/insight_service.py:82-88`

`generate_insights` renders each override as:

```python
for ov in summary.get("overrides", []):
    lines.append(f"- override applied: {ov['tool']} {ov['args']}")
```

`{ov['args']}` is the Python `dict.__repr__`, e.g. `{'task_id': 'Pick', 'n': 4}` or
`{'member_id': 'Alice', 'max_hours': 40.0}` or `{'task_id': 'Pick', 'factor': 1.5}`.
The `_NUM_RE` pattern in `_grounding_guard` matches `4`, `40.0`, or `1.5` as numeric
tokens. These values come from the constraint definition, not from the run's metrics dict.
The guard checks each token against `_allowed_values(metrics)` — which derives allowed
values only from `total_cost`, `total_unmet_hours`, `scheduled_shifts`, `scheduled_members`,
and per-function coverage stats. A constraint arg like `n=4` is not present in that set
unless the metric coincidentally has that value. The guard raises `InsightGenerationError`
and the route returns 502.

**No existing test covers this path.** Every test that calls `get_or_generate` creates a
fresh scenario with no applied constraints (`scenario.overrides = "{}"`), so `overrides`
is always `[]` and the override lines are never emitted. Phase 2's primary feature is
applying constraints; Phase 3's primary feature is explaining the resulting run. The
combination breaks silently in production.

The plan (03-01 Task 2) required the stub to ensure "every emitted numeric token is a real
metric value" and cited Research A2 ("spell any small structural count as a word"). Numeric
constraint *args* (like `n`, `max_hours`, `factor`) are not metric values and were not
handled by the spelt-as-word rule.

**Fix — emit only the tool name, omit raw args:**

```python
# backend/llm/stub.py
for ov in summary.get("overrides", []):
    # Omit ov['args'] — constraint arg values (n, max_hours, factor) are not run
    # metrics and will fail the D-06 grounding guard.
    lines.append(f"- override applied: {ov['tool']}")
```

Alternatively, add a companion test that applies a constraint before requesting insights
and assert the response is 200 (would reveal the bug immediately with no code fix):

```python
# backend/tests/test_insights_api.py  (new regression test)
def test_insights_succeeds_when_scenario_has_overrides(client):
    """Insight generation must not 502 when the scenario has numeric constraint args."""
    r = client.post("/scenarios", json={
        "name": "with-override", "fixture": "sample_tiny_input.json", "time_limit_s": 5})
    scenario_id = r.json()["id"]
    # Apply a constraint with a numeric arg before running.
    client.post("/scenarios/parse-constraints", json={
        "scenario_id": scenario_id, "text": "at least 4 on Pick"})
    r = client.post(f"/scenarios/{scenario_id}/runs")
    run_id = r.json()["id"]
    _wait_terminal(client, run_id)
    r = client.get(f"/runs/{run_id}/insights")
    assert r.status_code == 200, r.text
    assert r.json()["ready"] is True
```

---

## Warnings

### WR-01: `_has_column` interpolates `table` into a PRAGMA statement via f-string

**File:** `backend/store/db.py:38-39`

```python
return any(r["name"] == col
           for r in conn.execute(f"PRAGMA table_info({table})"))
```

SQLite PRAGMA statements do not support parameterised arguments for object names, so the
f-string is the only mechanism available. However, the function signature accepts any
`str` with no validation. Python's `sqlite3.execute()` rejects multi-statement input (no
semicolon injection), but a crafted `table` value could still produce a PRAGMA syntax
error or bypass the column-existence check (e.g. `table = "x) SELECT 'insight_json'
--"` would produce `PRAGMA table_info(x) SELECT ...` which `execute()` would reject as
multi-statement — but the outcome is an uncaught `OperationalError` rather than a clear
`ValueError`). The function is private and today only called with the literal `"runs"`,
so the immediate risk is low. If the function is ever promoted to a shared utility or
called from migrated code with a table name read from config, the risk materialises.

**Fix:**

```python
def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table!r}")
    return any(
        r["name"] == col
        for r in conn.execute(f"PRAGMA table_info({table})")
    )
```

---

### WR-02: `InsightOut` schema does not enforce the `ready` ↔ field invariant — a 200 response with `ready=True` and `report=None` is schema-valid

**File:** `backend/api/schemas.py:34-39`

```python
class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None    # present when ready=True (INS-01)
    status: Optional[str] = None    # present when ready=False (D-07)
    reason: Optional[str] = None    # present when ready=False (D-07)
```

The comments describe an invariant (`report` non-None when `ready=True`; `status` non-None
when `ready=False`) but Pydantic does not enforce it. A caller that dereferences
`body["report"]` on a `ready=True` response would raise `TypeError: string indices must
be integers` if a future code path returns `ready=True` without setting `report`. The
invariant is currently maintained by `get_or_generate`, but the schema provides no
safety net if the service is extended.

**Fix:**

```python
from pydantic import model_validator

class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def check_ready_fields(self) -> "InsightOut":
        if self.ready and self.report is None:
            raise ValueError("report must be set when ready=True")
        if not self.ready and self.status is None:
            raise ValueError("status must be set when ready=False")
        return self
```

---

### WR-03: Unguarded `result["metrics"]` access in `get_or_generate` — `KeyError` from malformed `result_json` propagates as an uncontrolled 500

**File:** `backend/services/insight_service.py:129-130`

```python
result = json.loads(run["result_json"])
metrics = result["metrics"]
```

The route's exception handlers catch `LookupError` (→ 404) and `InsightGenerationError`
(→ 502) but not `KeyError`. If `result_json` is stored without a `"metrics"` key —
through DB corruption, a manual write, or a future change to `serialize_result` — the
`KeyError` propagates and FastAPI returns an uncontrolled 500 Internal Server Error
rather than a semantically correct 502. `json.JSONDecodeError` from malformed JSON has
the same effect. Both conditions are "the insight pipeline encountered bad data" and
should yield 502.

**Fix:**

```python
try:
    result = json.loads(run["result_json"])
    metrics = result["metrics"]
except (json.JSONDecodeError, KeyError) as exc:
    raise InsightGenerationError(
        f"result_json is malformed or missing 'metrics': {exc}"
    ) from exc
```

---

## Info

### IN-01: `conn.commit()` at the end of `init_db` is a no-op — `executescript` commits its own transaction and `ALTER TABLE` auto-commits in autocommit mode

**File:** `backend/store/db.py:56-59`

`conn.executescript(_SCHEMA)` issues an implicit `COMMIT` before running and manages its
own transaction internally (per the Python sqlite3 docs). After it returns, the connection
is in autocommit mode. The subsequent `ALTER TABLE` DDL statement also auto-commits
immediately. The final `conn.commit()` therefore operates on an empty transaction. This
is harmless but may mislead contributors into believing the schema changes and the ALTER
TABLE are batched in a single transaction guarded by the explicit commit.

**Fix:** add a comment, or commit only after the ALTER TABLE:

```python
conn.executescript(_SCHEMA)                        # commits its own transaction
if not _has_column(conn, "runs", "insight_json"):
    conn.execute("ALTER TABLE runs ADD COLUMN insight_json TEXT")
    conn.commit()                                   # commit the ALTER TABLE
```

---

### IN-02: `CountingInsightProvider.generate_insights` applies `:g` format directly to potentially-`None` values — would raise `TypeError` instead of the expected `InsightGenerationError` on a degenerate solve

**File:** `backend/tests/test_insights_api.py:228-229`

```python
cost = m.get("total_cost")
return f"Cost {cost:g} unmet {m.get('total_unmet_hours'):g}."
```

`serialize_result` coerces NaN/Inf metric values to `None`. If a future test variant uses
an engine that produces a degenerate solve (e.g. a timed-out solve where `cost_objective`
is NaN → `total_cost=None`), the `:g` format raises `TypeError: unsupported format
character` rather than surfacing through the 502 path. The confusion is compounded by the
fact that `StubLLMProvider.generate_insights` already handles this correctly (lines 247-248
of `stub.py`). Mirror that pattern:

```python
cost = m.get("total_cost")
unmet = m.get("total_unmet_hours")
cost_s = f"{cost:g}" if cost is not None else "not available"
unmet_s = f"{unmet:g}" if unmet is not None else "not available"
return f"Cost {cost_s} unmet {unmet_s}."
```

---

_Reviewed: 2026-06-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
