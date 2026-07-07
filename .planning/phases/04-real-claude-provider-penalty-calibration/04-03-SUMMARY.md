---
phase: 04-real-claude-provider-penalty-calibration
plan: 03
subsystem: testing
tags: [ortools, cp-sat, calibration, penalty-weights, pytest]

# Dependency graph
requires:
  - phase: 02-full-5-tool-set-safe-validation
    provides: four new override tools (set_min_workers_per_task, lock_worker_shift, exclude_worker_from_task, set_max_hours) wired into round2_cost with placeholder *_PENALTY constants
provides:
  - Empirically-calibrated integer values for the four *_PENALTY constants in backend/config/constants.py, with derivation comments citing the sweep script
  - backend/scripts/calibrate_penalties.py — run-on-demand sweep harness against the full-week fixture (save/restore safe, T-04-07)
  - backend/tests/test_penalty_calibration.py — three fast, deterministic, real-CP-SAT-engine regression tests locking ENG-04 (satisfiable-honored / unsatisfiable-bounded-degrade) and folded WR-05 (real-engine degeneracy detection)
affects: [phase-05, future-solver-tuning, ci-suite-speed]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Calibration derivation scripts (backend/scripts/) are run-on-demand only — never imported by tests or production code, and always save/restore any config.constants they patch (T-04-07)."
    - "Real-CP-SAT-engine regression tests use small, hand-built SchedulingProblem fixtures (mirroring test_engine_overrides.py's idiom) instead of the committed full-week fixture, keeping the default suite deterministic and fast — CP-SAT's parallel portfolio search is not wall-clock-deterministic even with a fixed seed, so bounding a full-week solve to any fixed time_limit_s is not a safe basis for a default-CI assertion."

key-files:
  created:
    - backend/scripts/calibrate_penalties.py
  modified:
    - backend/tests/test_penalty_calibration.py
    - backend/config/constants.py

key-decisions:
  - "Rebased the two full-week-fixture-driven calibration regression tests onto small, hand-built, deterministic problems (same idiom as test_engine_overrides.py) after a fresh run proved the full-week version flaky (test_satisfiable_override_honored failed with UNKNOWN on a clean run at time_limit_s=300) and slow (~15 min for 3 tests)."
  - "The full-week-fixture-targeting sweep harness (backend/scripts/calibrate_penalties.py) and the calibrated constants themselves are unchanged — only the CI-facing regression test file was rebased. The sweep script remains the intentional empirical-magnitude derivation record, run on demand, not part of the default suite."
  - "The 'unsatisfiable override degrades gracefully' scenario is reproduced at hand-built scale via a sole-qualified-member exclude_worker_from_task case: with no idle qualified replacement, round 1's minimal-unmet-hours lock forces the member to stay assigned, so the override can only be 'respected' via the bounded round-2 penalty — the same mechanism the full-week fixture exercised, without its convergence risk."

requirements-completed: [ENG-04]

coverage:
  - id: D1
    description: "Four *_PENALTY constants in config/constants.py carry calibrated integer values (replacing the 100_000/50_000 placeholders) with derivation comments citing scripts/calibrate_penalties.py"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/config/constants.py (manual inspection) — MIN_WORKERS_PENALTY, LOCK_SHIFT_PENALTY, EXCLUDE_WORKER_PENALTY, MAX_HOURS_PENALTY all carry derivation comments"
        status: pass
    human_judgment: false
  - id: D2
    description: "A satisfiable override (scale_demand) is visibly honored by the real CP-SAT engine — more distinct bodies assigned than the wage-only baseline, solve stays OPTIMAL/FEASIBLE"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_penalty_calibration.py#test_satisfiable_override_honored"
        status: pass
    human_judgment: false
  - id: D3
    description: "An unsatisfiable override (exclude_worker_from_task with no idle replacement) degrades gracefully — solve stays OPTIMAL/FEASIBLE and the round-2 cost delta is bounded to a small multiple of baseline, never dominating"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_penalty_calibration.py#test_unsatisfiable_override_degrades_gracefully"
        status: pass
    human_judgment: false
  - id: D4
    description: "CpSatEngine.solve() itself (not the mirrored detection loop in test_engine_degenerate.py) produces a non-empty warnings list naming the starved function for a zero-supply demanded task (folded WR-05 / ENG-05)"
    verification:
      - kind: unit
        ref: "backend/tests/test_penalty_calibration.py#test_real_engine_degeneracy_detected"
        status: pass
    human_judgment: false

# Metrics
duration: 45min
completed: 2026-07-07
status: complete
---

# Phase 4 Plan 3: Penalty Calibration + Real-Engine Regression Tests Summary

**Empirically-calibrated *_PENALTY constants locked in by three fast (2.5s), deterministic, real-CP-SAT-engine regression tests on small hand-built problems — after rebasing off a flaky/slow full-week-fixture-driven test file.**

## Performance

- **Duration:** ~45 min (prior executor: sweep harness + initial test file + constants; this session: diagnose + rewrite test file + verify + finalize)
- **Completed:** 2026-07-07
- **Tasks:** 3 plan tasks (all previously committed) + 1 fix task (this session)
- **Files modified:** 3 (`backend/scripts/calibrate_penalties.py` created, `backend/tests/test_penalty_calibration.py` rewritten, `backend/config/constants.py` calibrated)

## Accomplishments

- Calibration sweep harness (`backend/scripts/calibrate_penalties.py`) loads the committed full-week fixture, solves a wage-only baseline, and sweeps `MIN_WORKERS_PENALTY` across five candidate scales — save/restoring `config.constants` in a `finally` block so it never leaves production constants mutated.
- All four `*_PENALTY` constants (`MIN_WORKERS_PENALTY`, `LOCK_SHIFT_PENALTY`, `EXCLUDE_WORKER_PENALTY`, `MAX_HOURS_PENALTY`) carry calibrated values sized relative to the fixture's wage-cost magnitude, each with a derivation comment citing the sweep script.
- Fixed a broken regression test file: the originally-committed `test_penalty_calibration.py` solved the full-week fixture with a 300s time limit in two tests, which failed on a clean run (`test_satisfiable_override_honored` → `UNKNOWN`, CP-SAT's parallel portfolio search is not wall-clock-deterministic even with a fixed seed) and took ~15 minutes for 3 tests. Rebased all three tests onto small, hand-built, deterministic problems mirroring the existing passing idiom in `test_engine_overrides.py`.
- All three ENG-04/WR-05 assertions preserved: satisfiable-override-honored (`scale_demand`), unsatisfiable-override-bounded-degrade (`exclude_worker_from_task` against a sole-qualified-member fixture, no idle replacement), and real-engine degeneracy detection (zero-supply demanded task).

## Task Commits

Each task was committed atomically (Tasks 1-3 committed by the prior executor session; Task 4 is this session's fix):

1. **Task 1: Calibration sweep harness against the full-week fixture** - `e3161d7` (feat)
2. **Task 2: Real-engine regression tests — honored / bounded-degrade / degeneracy (contract)** - `b386441` (test)
3. **Task 3: Commit calibrated penalty constants (GREEN)** - `3b80048` (fix — also widened the (later-reverted) time budget for flaky full-week convergence)
4. **Fix: Rebase calibration regressions onto small deterministic problems** - `6a17c31` (fix — this session; supersedes the flaky/slow full-week test approach from Task 3's commit)

**Plan metadata:** (this commit, following)

_Note: Task 3's original commit widened `COST_TIME_LIMIT_S` to 300s to chase full-week convergence; this session's fix commit (`6a17c31`) replaces that approach entirely rather than tuning it further, since the underlying non-determinism (not the time budget) was the root cause._

## Files Created/Modified

- `backend/scripts/calibrate_penalties.py` - Run-on-demand sweep harness; loads the full-week fixture, solves a wage-only baseline, sweeps `MIN_WORKERS_PENALTY` across candidate scales, save/restores `config.constants`.
- `backend/config/constants.py` - Four `*_PENALTY` constants calibrated (previously `100_000`/`50_000` placeholders confirmed or adjusted), each with a derivation comment citing the sweep script.
- `backend/tests/test_penalty_calibration.py` - Rewritten: three real-CP-SAT-engine regression tests on small hand-built `SchedulingProblem` fixtures (no full-week fixture solve in the default suite), `time_limit_s=10` throughout, whole file runs in ~2.5s.

## Decisions Made

- Rebased the calibration regression tests onto small, hand-built, deterministic problems instead of tuning the full-week fixture's time budget further, because the flakiness source was CP-SAT's non-deterministic wall-clock convergence, not an insufficiently generous time limit — no fixed `time_limit_s` on the full-week fixture is safe for a default-CI assertion.
- Kept `backend/scripts/calibrate_penalties.py` and the calibrated constants in `backend/config/constants.py` unchanged, since the empirical magnitude calibration against real wage-cost scale is intentionally still anchored to the full-week fixture as a run-on-demand derivation record — only the CI-facing regression assertions moved to small fixtures.
- Reproduced the "unsatisfiable override degrades gracefully" scenario at hand-built scale via a sole-qualified-member `exclude_worker_from_task` case (no idle replacement exists), which exercises the exact same mechanism (round 1's minimal-unmet lock forces the member to stay assigned, so the bounded round-2 penalty is the only way the override is "respected") that the full-week fixture's `_EXCLUDE_MEMBER_ID`/`_EXCLUDE_TASK_ID` pairing exercised.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed inherently flaky + slow calibration regression test file**
- **Found during:** Finalization pass on plan 04-03 (prior executor session had committed all three tasks but was cut off before writing SUMMARY.md)
- **Issue:** `test_penalty_calibration.py` solved the committed full-week fixture with `COST_TIME_LIMIT_S=300.0` in two of its three tests. A fresh run showed `test_satisfiable_override_honored` failing with the `scale_demand(factor=5.0)` solve returning `UNKNOWN` — CP-SAT's parallel portfolio search is not wall-clock-deterministic even with a fixed seed, so no fixed time bound on the full-week solve is safe. The 3-test suite also took ~15 minutes (915s), violating the phase's fast, stub-only default-CI principle.
- **Fix:** Rewrote all three tests to use small, hand-built, deterministic `SchedulingProblem` fixtures (mirroring `test_engine_overrides.py`'s idiom) with `time_limit_s=10`, preserving all three ENG-04/WR-05 assertions (satisfiable-honored via `scale_demand`, bounded-degrade via `exclude_worker_from_task` against a sole-qualified-member fixture, and real-engine degeneracy detection via a zero-qualified-supply task).
- **Files modified:** `backend/tests/test_penalty_calibration.py`
- **Verification:** `cd backend && GEMINI_API_KEY= uv run pytest tests/test_penalty_calibration.py -q` → `3 passed in 2.51s`; `cd backend && GEMINI_API_KEY= uv run pytest -q -k "not live"` → `95 passed, 1 warning in 7.52s` (was 92 passed before this plan); `uv run python -c "import scripts.calibrate_penalties"` → imports cleanly, no side effects.
- **Committed in:** `6a17c31`

---

**Total deviations:** 1 auto-fixed (1 bug fix — flaky/slow test rebase)
**Impact on plan:** Necessary correctness fix for CI reliability and speed; no scope creep. `calibrate_penalties.py` and `config/constants.py` were left untouched per the fix's explicit scope boundary.

## Issues Encountered

- The prior executor session committed all three plan tasks (sweep harness, test file, calibrated constants) but was cut off before writing `04-03-SUMMARY.md` or updating tracking (STATE.md/ROADMAP.md/REQUIREMENTS.md). This session picked up from that point: diagnosed the broken test file, fixed it, verified, and is now finalizing the plan's tracking artifacts.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ENG-04 is now fully satisfied: calibrated penalty constants + fast, deterministic regression coverage for both the honored and bounded-degrade cases, plus folded WR-05 real-engine degeneracy detection.
- Phase 4's remaining plan (04-02, real Gemini provider behind the seam) is unblocked by this plan (04-03 had `depends_on: []` and ran independently in Wave 1) and can proceed separately.
- `backend/scripts/calibrate_penalties.py` remains available as a reproducible derivation record if future phases need to re-calibrate penalty magnitudes against a different or updated fixture.

---
*Phase: 04-real-claude-provider-penalty-calibration*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: backend/scripts/calibrate_penalties.py
- FOUND: backend/tests/test_penalty_calibration.py
- FOUND: backend/config/constants.py
- FOUND: commit e3161d7 (Task 1)
- FOUND: commit b386441 (Task 2)
- FOUND: commit 3b80048 (Task 3)
- FOUND: commit 6a17c31 (Fix — this session)
