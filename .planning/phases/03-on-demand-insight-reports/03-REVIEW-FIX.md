---
phase: 03-on-demand-insight-reports
fixed_at: 2026-06-30T13:45:00Z
review_path: .planning/phases/03-on-demand-insight-reports/03-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-06-30T13:45:00Z
**Source review:** .planning/phases/03-on-demand-insight-reports/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (CR-01, WR-01, WR-02, WR-03)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: StubLLMProvider emits Python dict repr of override args

**Files modified:** `backend/llm/stub.py`, `backend/tests/test_insights_api.py`
**Commit:** 193001d
**Applied fix:** Removed `ov['args']` from the override line in `generate_insights`. The
loop now emits `f"- override applied: {ov['tool']}"` only — no arg values that could be
numeric tokens absent from run metrics. Added `test_insights_succeeds_when_scenario_has_overrides`
regression test that applies a numeric constraint (`at least 4 on Amb Rec`) before
triggering a run, then asserts the insights endpoint returns 200 with `ready=True`. This
covers the combined Phase-2+Phase-3 path that was previously invisible to the suite.
Test suite: 89 passed (88 baseline + 1 new regression test).

---

### WR-01: `_has_column` interpolates table into PRAGMA via f-string without validation

**Files modified:** `backend/store/db.py`
**Commit:** 6c85db1
**Applied fix:** Added `if not table.replace("_", "").isalnum(): raise ValueError(...)` before
the PRAGMA execute. A crafted table name now raises `ValueError` immediately rather than
producing a PRAGMA syntax error or silently bypassing the column-existence check.

---

### WR-02: `InsightOut` schema does not enforce the `ready` field invariant

**Files modified:** `backend/api/schemas.py`
**Commit:** 5287694
**Applied fix:** Added `model_validator(mode="after")` to `InsightOut` that raises
`ValueError` if `ready=True` and `report=None`, or if `ready=False` and `status=None`.
Pydantic now enforces the invariant at serialisation time. Added `model_validator` to
the import from `pydantic`.

---

### WR-03: Unguarded `result["metrics"]` access propagates as uncontrolled 500

**Files modified:** `backend/services/insight_service.py`
**Commit:** 60d7fb8
**Applied fix:** Wrapped the `json.loads(run["result_json"])` and `result["metrics"]`
access in `try/except (json.JSONDecodeError, KeyError)` that re-raises as
`InsightGenerationError`. The route's existing 502 handler now covers malformed or
missing-metrics `result_json` rather than letting a `KeyError` propagate as an
uncontrolled 500.

---

_Fixed: 2026-06-30T13:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
