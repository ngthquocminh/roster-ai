---
phase: 02-full-5-tool-set-safe-validation
plan: "04"
subsystem: constraint-api
tags: [validation, tdd, test-03, mixed-multi-tool, partial-apply, stub-driven]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [test_unknown_task_rejected, test_scale_demand_bad_factor, test_rejection_error_names_ref, test_mixed_valid_invalid_multi_tool, test_mixed_valid_oob_multi_tool]
  affects:
    - backend/tests/test_constraints_api.py
tech_stack:
  added: []
  patterns: [tdd-green-at-write-time, idempotent-resubmit-persistence-check, mixed-applied-rejected-criterion-5]
key_files:
  created: []
  modified:
    - backend/tests/test_constraints_api.py
decisions:
  - "TEST-03 tests pass at write time (GREEN immediate) — implementation pre-exists from plan 02-02; same deviation pattern as 02-02 Task 3"
  - "Non-persistence verified via idempotent re-submit: post invalid -> post again -> still rejected, never in applied[]"
  - "Criterion-5 persistence check: applied id is stable across re-submits (idempotent override_id hash proves the valid entry was stored)"
metrics:
  duration_min: 2
  completed_date: "2026-06-29"
  tasks_completed: 2
  files_changed: 1
status: complete
---

# Phase 02 Plan 04: TEST-03 Validation Suite Summary

**One-liner:** Five new stub-driven tests — unknown task/member refs rejected with token+valid-options in error, mixed valid/invalid and valid/OOB multi-tool calls yield applied[]+rejected[] in one 200 response with only valid fragment persisted (criterion 5).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Unknown-reference + out-of-bounds rejection tests | 35c308c | tests/test_constraints_api.py |
| 2 | Mixed valid/invalid multi-tool tests (criterion 5) | 142c982 | tests/test_constraints_api.py |

## What Was Built

### test_constraints_api.py — TEST-03 section (plan 02-04)

Five new test functions appended under two new comment sections:

#### Task 1: Unknown-ref + OOB rejection tests

**`test_unknown_task_rejected`**
Posts `"scale GHOST_TASK_NONEXISTENT demand by 2.0x"` to exercise the `scale_demand` unknown-task rejection path. Asserts:
- 200, `rejected[0].error` contains `"GHOST_TASK_NONEXISTENT"`, `applied == []`
- Re-submit: still rejected, still no applied entry (non-persistence proof via idempotent re-submit)

**`test_scale_demand_bad_factor`**
Posts `"boost C Pick volume by 0x"` (factor=0.0, which is <= 0). Asserts:
- 200, `rejected[0].error` contains `"factor"`, `applied == []`
- Re-submit: still rejected (never persisted)
- Distinct from the pre-existing `test_scale_demand_bad_factor_rejected` by using an alternate phrasing and adding the non-persistence check

**`test_rejection_error_names_ref`**
Posts two requests — unknown task and unknown member — and asserts the rejection error string contains:
1. The offending token (`BAD_TASK_REF`, `BAD_MEMBER_REF`)
2. A listing of valid options (`"Valid tasks:"` / `"Valid members:"`)

This exercises the `_resolve_task` / `_resolve_member` error template in `constraint_service.py` which emits `f"Unknown task {token!r}. Valid tasks: {valid_names}"`.

#### Task 2: Mixed valid/invalid multi-tool tests (criterion 5)

**`test_mixed_valid_invalid_multi_tool`**
Posts `"at least 2 on C Pick and exclude XYZ_NONEXISTENT_MEMBER from C Pick"`:
- Fragment 1: `set_min_workers_per_task` on C Pick → valid → `applied[0]`
- Fragment 2: `exclude_worker_from_task` with unknown member → `rejected[0]`
- Asserts: 200, `len(applied)==1`, `len(rejected)==1`, `"XYZ_NONEXISTENT_MEMBER"` in error
- Persistence check: re-submit returns same `applied[0].id` (idempotent), rejected fragment still rejected

**`test_mixed_valid_oob_multi_tool`**
Posts `"at least 3 on C Pick and boost C Pick volume by 0x"`:
- Fragment 1: `set_min_workers_per_task` → valid → `applied[0]`
- Fragment 2: `scale_demand` with factor=0 → out-of-bounds → `rejected[0]`
- Asserts: 200, `len(applied)==1`, `len(rejected)==1`, `"factor"` in error
- Persistence check: re-submit returns same `applied[0].id`, rejected fragment still rejected

### Updated module docstring

Added `Exercises (plan 02-04 — TEST-03 validation suite)` block listing all five new test behaviors for future orientation.

## Verification

```
pytest tests/test_constraints_api.py -x -q -k "rejected or bad_factor or zero_rejected or names_ref"
4 passed, 30 deselected, 1 warning

pytest tests/test_constraints_api.py -x -q -k "mixed"
3 passed, 33 deselected, 1 warning

pytest tests/test_constraints_api.py -x -q
36 passed, 1 warning

pytest -x -q
80 passed, 1 warning
```

All must-have truths satisfied:
- Unknown task references rejected at 200 naming the token and listing valid options (VAL-02/VAL-03)
- Unknown member references rejected at 200 naming the token and listing valid options (VAL-02/VAL-03)
- scale_demand factor<=0 rejected naming `factor` (VAL-01)
- set_max_hours=0 rejected naming `max_hours` (VAL-01 — covered by pre-existing test from 02-02)
- Mixed valid+unknown-ref: `applied[]+rejected[]` in one 200, only valid persisted (criterion 5/T-02-11)
- Mixed valid+OOB: `applied[]+rejected[]` in one 200, only valid persisted (criterion 5/T-02-11)
- All tests stub-driven via `app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()` — zero network calls (TEST-01 invariant preserved)

## Deviations from Plan

### Deviation 1: Tests GREEN at write time (sequence artifact — same as 02-02 Task 3)

**Found during:** Task 1 and Task 2
**Issue:** Both tasks have `tdd="true"` requiring a RED (failing) phase before GREEN. However, the full five-tool service implementation and validation logic were already completed in plan 02-02. All five new test functions pass immediately when written — there is no RED phase.
**Fix:** Tests accurately describe the required behavior and pass against the existing implementation. Documented here rather than artificially deferring implementation.
**Files modified:** No additional change — tests are correct and pass.
**Commit pattern:** Single commit per task (no separate RED/GREEN commits) matching the deviation pattern recorded in 02-02 SUMMARY.

### Pre-existing tests covered by plan artifact list

Plan 02-04 `artifacts_this_phase_produces` listed `test_unknown_member_rejected` and `test_max_hours_zero_rejected` as artifacts of this plan, but both were added in plan 02-02 with those exact names. These were not re-added; the plan list was written assuming 02-02 had not yet run. The new tests added here cover the same acceptance criteria via distinct named functions with non-persistence checks.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes. All additions are test-only. T-02-11 (mixed multi-tool persistence) and T-02-12 (live LLM in CI) are both mitigated as planned.

## Known Stubs

None — tests use StubLLMProvider which is the production stub (no placeholder data).

## Self-Check

| Item | Status |
|------|--------|
| backend/tests/test_constraints_api.py | FOUND |
| test_unknown_task_rejected | FOUND |
| test_scale_demand_bad_factor | FOUND |
| test_rejection_error_names_ref | FOUND |
| test_mixed_valid_invalid_multi_tool | FOUND |
| test_mixed_valid_oob_multi_tool | FOUND |
| Commit 35c308c (Task 1) | FOUND |
| Commit 142c982 (Task 2) | FOUND |
| pytest 80 passed | PASSED |

## Self-Check: PASSED
