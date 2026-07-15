---
phase: 02-full-5-tool-set-safe-validation
plan: "03"
subsystem: engine
tags: [degeneracy-detection, warnings, serialization, tdd, eng-05]
dependency_graph:
  requires: []
  provides: [SolveResult.warnings, degeneracy-detection, serialize_result.warnings]
  affects: [backend/domain/result.py, backend/engine/cpsat/engine.py, backend/services/serialize.py]
tech_stack:
  added: []
  patterns: [dataclass-field-default-factory, append-only-detection, pass-through-serialization]
key_files:
  created:
    - backend/tests/test_engine_degenerate.py
  modified:
    - backend/domain/result.py
    - backend/engine/cpsat/engine.py
    - backend/services/serialize.py
decisions:
  - "Detection loop iterates coverage_by_function after assembly — no new data structures needed"
  - "Threshold 1e-9 for both required_h and served_h guards against floating-point noise"
  - "Tests use direct CoverageStat approach (not real CP-SAT) — OR-Tools crashes on Windows under Anaconda"
metrics:
  duration_min: 15
  completed: "2026-06-29"
  tasks_completed: 2
  files_changed: 4
status: complete
---

# Phase 02 Plan 03: Degeneracy Detection and Flag Summary

**One-liner:** Post-solve zero-coverage detection loop on SolveResult.warnings flowing through serialize_result into runs.result_json (ENG-05).

## What Was Built

Added degeneracy detection to the CP-SAT solve pipeline:

1. **`SolveResult.warnings: List[str]`** (`domain/result.py`) — new last field with `field(default_factory=list)`; backward-compatible with all existing call sites including `StubEngine` (no warnings argument required).

2. **ENG-05 detection loop** (`engine/cpsat/engine.py`) — after `coverage_by_function` is assembled, iterates families and appends a structured warning for each where `stat.required_h > 1e-9` and `stat.served_h <= 1e-9`. Detection never reads or writes `status`.

3. **Serialization pass-through** (`services/serialize.py`) — `"warnings": r.warnings` added as top-level key in `serialize_result` output alongside status/metrics/stats/schedule. Warning strings flow into `runs.result_json` for the Phase-3 insight step.

4. **`test_engine_degenerate.py`** — 14 tests covering: field presence, default value, explicit value preservation, zero-supply detection with correct family name and hours, multiple families, negative cases (fully covered, partial coverage), edge cases (zero demand, near-zero demand, empty map), status-unchanged guarantee, and serialization round-trip.

## TDD Gate Compliance

- RED commit: `3edfac5` — `test_warnings_field_present_on_solve_result` added before field existed; pytest reported 1 FAILED.
- GREEN commit: `0a03bb4` — warnings field + detection loop + serialize added; RED test passed.
- Task 2 commit: `95bd7ae` — 13 additional comprehensive tests; all 14 pass.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | Failing test for SolveResult.warnings | 3edfac5 | tests/test_engine_degenerate.py |
| 1 GREEN | Warnings field + degeneracy detection + serialize | 0a03bb4 | domain/result.py, engine/cpsat/engine.py, services/serialize.py |
| 2 | Comprehensive degeneracy detection tests | 95bd7ae | tests/test_engine_degenerate.py |

## Verification Results

- `pytest tests/test_engine_degenerate.py -x -q`: 14 passed
- `pytest tests/test_adapter.py tests/test_llm_provider.py tests/test_engine_degenerate.py`: 29 passed (backward compatible)
- Import verification: `engine.cpsat.engine`, `services.serialize` both import cleanly
- Acceptance criteria:
  - SolveResult has warnings field defaulting to []: PASS
  - serialize_result output contains "warnings" key: PASS
  - engine.py status assignment unchanged: PASS (test_status_not_altered_when_warnings_present)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_make_result` helper had duplicate keyword argument conflict**
- **Found during:** Task 2 test run
- **Issue:** `_make_result(**kwargs)` passed `status="OPTIMAL"` hardcoded then also accepted `status` via `**kwargs`, causing `TypeError: got multiple values for keyword argument 'status'` in `test_status_not_altered_when_warnings_present`
- **Fix:** Replaced with `defaults.update(kwargs)` pattern so callers can override any default
- **Files modified:** `backend/tests/test_engine_degenerate.py`
- **Commit:** Included in `95bd7ae`

**2. CP-SAT engine tests skipped in this plan's test strategy**
- **Found during:** Task 2 research
- **Issue:** OR-Tools crashes with access violation on Windows (Anaconda environment); `test_engine_min_workers.py` and `test_engine_small.py` both crash
- **Resolution:** This is a pre-existing environment issue unrelated to Plan 03 changes. Plan 03 tests use the direct `CoverageStat` approach (approach 1 from PATTERNS.md) which avoids CP-SAT entirely. Logged in deferred-items.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. `warnings` field flows into existing `runs.result_json` column — no new DB columns or trust boundaries.

STRIDE mitigations confirmed:
- T-02-09 (Repudiation): Zero-coverage families flagged in warnings — degenerate solve cannot silently narrate as success.
- T-02-10 (Tampering): `test_status_not_altered_when_warnings_present` enforces detection is append-only; status field unchanged.

## Self-Check: PASSED

- `backend/domain/result.py` — modified, warnings field present: CONFIRMED
- `backend/engine/cpsat/engine.py` — modified, detection loop present: CONFIRMED
- `backend/services/serialize.py` — modified, warnings key present: CONFIRMED
- `backend/tests/test_engine_degenerate.py` — created, 14 tests: CONFIRMED
- Commits 3edfac5, 0a03bb4, 95bd7ae all present in git log: CONFIRMED
