---
phase: "01"
plan: "03"
subsystem: run-service-integration
tags: [override-threading, end-to-end, tdd, round-trip, test-02]
dependency_graph:
  requires: [domain.overrides.OverrideCall, engine.base.SolverConfig.overrides, POST /constraints, store.repositories.ScenarioRepo.update_overrides]
  provides: [run_service._execute-overrides-threading, test_constraints_api.round-trip-tests]
  affects: [backend/services/run_service.py, backend/tests/test_constraints_api.py]
tech_stack:
  added: []
  patterns: [tdd-red-green, capturing-engine-stub, thread-safe-config-capture]
key_files:
  created: []
  modified:
    - backend/services/run_service.py
    - backend/tests/test_constraints_api.py
decisions:
  - "CapturingEngine (thread-safe, lock-guarded list) used for RED/GREEN TDD cycle — captures SolverConfig passed to solve() without coupling the test to CP-SAT output"
  - "Baseline test (no constraint -> overrides=[]) uses same CapturingEngine fixture to prove ENG-06 at the service layer"
  - "Task 2 TDD ordering: RED tests written before Task 1 implementation; Task 1's feat commit is the GREEN gate"
metrics:
  duration_min: 8
  completed_date: "2026-06-28"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
status: complete
---

# Phase 01 Plan 03: Override Threading + Round-Trip Test Summary

**One-liner:** run_service._execute now reads scenario['overrides'] JSON into SolverConfig.overrides, closing the NL->override->re-solve vertical slice; verified by a CapturingEngine round-trip test (zero network calls, TEST-02).

## What Was Built

### Task 2 RED: Failing round-trip tests (commit 50c4fa1)

Added to `backend/tests/test_constraints_api.py`:

- `_wait_terminal` helper — polls run until COMPLETED/FAILED (mirrors test_api.py)
- `CapturingEngine` class — thread-safe (lock-guarded `list`) engine stub that records every `SolverConfig` passed to `solve()`; returns a minimal valid `SolveResult` so runs reach COMPLETED
- `_capture_pair` fixture — injects `CapturingEngine` + `StubLLMProvider` via `app.dependency_overrides`; yields `(client, engine)` pair so tests can inspect captured config after the run
- `test_override_is_threaded_into_solver_config` — **RED test**: posts "at least 2 on C Pick", triggers run, asserts `engine.captured_config.overrides` has exactly one `OverrideCall` with correct tool/args/id; FAILS before Task 1 with `got 0 overrides`
- `test_no_constraint_yields_empty_overrides_in_config` — baseline control: no POST /constraints → `config.overrides == []` (ENG-06); passes both before and after Task 1

RED state: 1 failing (threading test), 16 passing.

### Task 1 GREEN: Thread overrides into SolverConfig (commit b83d448)

Modified `backend/services/run_service.py`:

- Added `from domain.overrides import OverrideCall` import
- In `_execute`, before `SolverConfig` construction:
  ```python
  raw = json.loads(scenario["overrides"] or "{}")
  overrides = [OverrideCall(id=k, tool=v["tool"], args=v["args"]) for k, v in raw.items()]
  config = SolverConfig(time_limit_s=float(scenario["time_limit_s"]), overrides=overrides)
  ```
- `json` was already imported at line 11 (no new import needed beyond `OverrideCall`)
- Empty store (`"{}"`) → `[]` → baseline solve identical (ENG-06 preserved)
- Malformed override entries raise inside the existing `except Exception` in `_execute`, marking run FAILED rather than crashing the worker pool (T-01-R1 mitigation)

GREEN state: all 42 tests pass.

## Verification Results

```
42 passed, 1 warning in 2.94s

backend/tests/test_constraints_api.py ... 17 passed
  - 15 from plan 01-02 (POST /constraints endpoint)
  - test_override_is_threaded_into_solver_config PASSED (GREEN after Task 1)
  - test_no_constraint_yields_empty_overrides_in_config PASSED

backend/tests/test_api.py ................... 5 passed (no regression)
backend/tests/test_llm_provider.py .......... 12 passed (no regression)
backend/tests/test_engine_min_workers.py .... 3 passed (no regression)
backend/tests/test_engine_small.py .......... 2 passed (no regression)
backend/tests/test_adapter.py ............... 3 passed (no regression)
```

Task 1 inspection check:
```
cd backend && python -c "import inspect, services.run_service as r; src=inspect.getsource(r._execute); assert 'overrides' in src and 'OverrideCall' in src and 'SolverConfig(' in src; print('ok')"
ok
```

## Success Criteria Met

- ROADMAP success criterion 4 (round trip): the full NL -> override -> re-solve path passes in CI with zero network calls — **PASSED** (`test_override_is_threaded_into_solver_config` confirms override flows from DB through `_execute` into `SolverConfig.overrides`)
- ROADMAP success criterion 2 (end-to-end): override is carried into the solve engine — **PASSED** (CapturingEngine asserts the `OverrideCall` with correct tool/args/id reaches `SolverConfig`; actual honoring proved by plan 01-01's `test_engine_min_workers.py`)
- TEST-02: zero network calls (StubLLMProvider is pure-Python; no Anthropic client imported on the tested path) — **PASSED**
- ENG-06 baseline preserved: no-constraint scenario yields empty overrides in config — **PASSED**
- Threat T-01-R1 (malformed overrides → worker crash): existing `except Exception` in `_execute` catches deserialisation errors — **MITIGATED** (inherits from pre-existing handler)
- Threat T-01-R2 (DOS via override): overrides flow into the soft round-2 penalty path only (per plan 01-01); cannot make solve infeasible — **MITIGATED** (no change to engine safety boundary)

## Deviations from Plan

### Auto-fixed Issues

None.

### TDD Ordering Note

The plan lists Task 1 (auto) before Task 2 (tdd=true). Because Task 2's RED tests need to FAIL before Task 1 is implemented (to demonstrate the missing threading), the actual commit order was:

1. `test(01-03)` 50c4fa1 — RED tests written first (before threading implementation)
2. `feat(01-03)` b83d448 — Task 1 implementation that makes RED tests GREEN

This ordering is the correct TDD sequence: write the test that describes the desired behavior, then implement the behavior.

## TDD Gate Compliance

- RED gate: `test(01-03)` commit 50c4fa1 — 1 failing test (`test_override_is_threaded_into_solver_config`) before implementation
- GREEN gate: `feat(01-03)` commit b83d448 — all 42 tests pass after Task 1 implementation
- REFACTOR gate: No structural changes needed; implementation is minimal and clean

## Known Stubs

- `StubLLMProvider` remains the default production provider (intentional Phase-1 design, documented in 01-02 SUMMARY). Real Claude SDK is Phase 4.
- `CapturingEngine` is a test fixture (not production code); it is defined only in `tests/test_constraints_api.py`.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. The `_execute` change reads from an existing DB column (`scenario["overrides"]`) that is already validated at write time by `constraint_service.parse_and_store` (plan 01-02).

No new threat flags beyond those already in the plan's threat register.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `backend/services/run_service.py` modified with OverrideCall import | FOUND |
| `backend/tests/test_constraints_api.py` has round-trip tests | FOUND |
| Commit 50c4fa1 (Task 2 RED) | FOUND |
| Commit b83d448 (Task 1 feat / GREEN) | FOUND |
| All 42 tests pass | PASSED |
