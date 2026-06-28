---
phase: "01"
plan: "01"
subsystem: engine
tags: [overrides, cp-sat, domain-seam, soft-constraint, tdd]
dependency_graph:
  requires: []
  provides: [domain.overrides.OverrideCall, engine.base.SolverConfig.overrides, MIN_WORKERS_PENALTY, cpsat-shortfall-penalty]
  affects: [engine/cpsat/builder.py, engine/cpsat/engine.py, engine/base.py, config/constants.py]
tech_stack:
  added: []
  patterns: [frozen-dataclass-domain-type, content-hash-id, soft-penalty-slack-term, scaled-integer-objective]
key_files:
  created:
    - backend/domain/overrides.py
    - backend/tests/test_engine_min_workers.py
  modified:
    - backend/engine/base.py
    - backend/engine/cpsat/builder.py
    - backend/engine/cpsat/engine.py
    - backend/config/constants.py
decisions:
  - "MIN_WORKERS_PENALTY = 100_000 scaled cents: large enough to beat one full shift's wage cost (32_000) per shortfall unit, deferred to Phase 4 (ENG-04) for empirical calibration"
  - "override_id() uses sorted-key JSON canonical so key order is irrelevant (D-05 stability)"
  - "CpSatBuilder stores self.coverage_terms before _build_objectives so shortfall penalty reuses per-(task,hour) body-count expressions without rebuilding them (D-02)"
metrics:
  duration_min: 7
  completed_date: "2026-06-28"
  tasks_completed: 2
  files_created: 2
  files_modified: 4
status: complete
---

# Phase 01 Plan 01: Engine Override Seam Summary

**One-liner:** CP-SAT shortfall penalty (`set_min_workers_per_task`) as soft round-2 term via `OverrideCall` domain seam, content-hash id, and `MIN_WORKERS_PENALTY = 100_000` scaled constant.

## What Was Built

### Task 1: OverrideCall domain seam + SolverConfig.overrides + penalty constant (commit 01f4846)

- **`backend/domain/overrides.py`** (NEW): Pure-domain module (stdlib only — no solver/web/llm imports, ENG-01). Contains:
  - `OverrideCall` frozen dataclass with fields `id: str`, `tool: str`, `args: dict[str, Any]`
  - `override_id(tool, args) -> str` content-hash helper: `"ov_" + sha256(tool + sorted-key-JSON(args))[:8]` (D-05)
- **`backend/engine/base.py`** (MOD): Added `overrides: list[OverrideCall] = field(default_factory=list)` to `SolverConfig`. No change to `SchedulerEngine` Protocol or `solve()` signature (ENG-02).
- **`backend/config/constants.py`** (MOD): Added `MIN_WORKERS_PENALTY: int = 100_000`. Placed in the integer-scaling block alongside `VOL_SCALE`/`HOUR_SCALE`/`COST_SCALE`. Comment flags Phase-4 calibration.

### Task 2: CP-SAT shortfall penalty + engine tests (commits efd4539 RED, c7d1532 GREEN)

**TDD RED** (commit efd4539): `backend/tests/test_engine_min_workers.py` with three failing tests:
1. `test_min_workers_override_honored` — override n=2 must place >= 2 bodies on Pick per demanded hour, strictly more than no-override baseline (1 body)
2. `test_no_regression_empty_overrides` — `overrides=[]` must produce identical status/cost/schedule as default `SolverConfig()`
3. `test_no_supply_override_stays_feasible` — override on no-qualified-supply task must not make solve infeasible

**TDD GREEN** (commit c7d1532):
- **`backend/engine/cpsat/engine.py`** (MOD): `CpSatBuilder(problem, overrides=config.overrides).build()`
- **`backend/engine/cpsat/builder.py`** (MOD):
  - `__init__` now accepts `overrides: list[OverrideCall] | None = None`; stores `self.overrides` and `self.coverage_terms`
  - `build()` stores `self.coverage_terms = coverage_terms` BEFORE calling `_build_objectives` (D-02 reuse)
  - `_build_objectives`: for each `set_min_workers_per_task` override, per demanded hour `h` for that task, creates `short = NewIntVar(0, n)`, adds `sum(bodies) + short >= n`, collects shortfall_terms; `round2_cost = sum(cost_terms) + MIN_WORKERS_PENALTY * sum(shortfall_terms)` — ONLY in round2_cost, never round1_unmet (D-03)

## Verification Results

```
5 passed in 0.67s
backend/tests/test_engine_min_workers.py ... 3 passed
backend/tests/test_engine_small.py ......... 2 passed
```

Manual read-check: `round2_cost` (line 347) is the only assignment touched by the shortfall penalty; `round1_unmet` (line 318) is unchanged from pre-existing code.

## Success Criteria Met

- ROADMAP success criterion 2 (engine half): override re-solves schedule that visibly honors it, soft round-2 only — **PASSED** (test asserts 2 bodies vs 1-body baseline)
- ROADMAP success criterion 3: no-override scenario re-solves identically — **PASSED** (test asserts byte-identical)
- ENG-01: `domain/overrides.py` imports nothing from engine/web/llm — **PASSED**
- ENG-02: `SolverConfig.overrides` default `[]`; `solve()` signature unchanged — **PASSED**
- ENG-03: override visibly honored in schedule — **PASSED**
- ENG-06: no-override baseline is identical — **PASSED**

## Deviations from Plan

None — plan executed exactly as written.

The system Python environment (Anaconda, OR-Tools 9.15) segfaults on CP-SAT — this is a pre-existing environment issue documented in `backend/pyproject.toml`. All test runs used the uv venv at `backend/.venv/` with pinned ortools==9.11.4210 as specified.

## TDD Gate Compliance

- RED gate: `test(01-01)` commit efd4539 — failing tests written before implementation
- GREEN gate: `feat(01-01)` commit c7d1532 — implementation makes all tests pass
- REFACTOR gate: No structural changes needed; code is minimal and clean

## Known Stubs

None — this plan implements real engine behavior with the actual CP-SAT solver. No placeholders, no hardcoded empty values.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. All changes are internal to the CP-SAT model construction (in-process). The `OverrideCall.args` boundary (T-01-E2) is handled by:
- `int(ov.args["n"])` coercion in builder
- Unknown `task_id` yields empty `coverage_terms` → constant penalty, not crash

No new threat flags beyond those already in the plan's threat register.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `backend/domain/overrides.py` exists | FOUND |
| `backend/tests/test_engine_min_workers.py` exists | FOUND |
| Commit 01f4846 (Task 1 feat) | FOUND |
| Commit efd4539 (Task 2 RED test) | FOUND |
| Commit c7d1532 (Task 2 GREEN impl) | FOUND |
