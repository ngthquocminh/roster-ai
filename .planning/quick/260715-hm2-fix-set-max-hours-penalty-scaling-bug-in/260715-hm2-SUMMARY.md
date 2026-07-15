---
phase: quick-260715-hm2
plan: 01
subsystem: engine
tags: [cp-sat, or-tools, penalty-calibration, builder]

requires: []
provides:
  - "set_max_hours override penalty corrected from ~$100,000/hour-over-cap to the documented $1,000/hour-over-cap"
affects: [engine, constraints]

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - backend/engine/cpsat/builder.py
    - backend/tests/test_engine_overrides.py

key-decisions:
  - "Used integer floor division (// C.VOL_SCALE) rather than float division to keep round2_cost expression in exact integer cents-space, matching the pattern of the other three penalty coefficients."

patterns-established: []

requirements-completed: []

coverage:
  - id: D1
    description: "maxh_terms coefficient in round2_cost divides out VOL_SCALE so set_max_hours penalty matches documented $1,000/hour-over-cap rate"
    verification:
      - kind: unit
        ref: "backend/tests/test_engine_overrides.py::test_set_max_hours_honored"
        status: pass
    human_judgment: false
  - id: D2
    description: "test_set_max_hours_honored docstring corrected to describe the fixed penalty math"
    verification:
      - kind: unit
        ref: "backend/tests/test_engine_overrides.py::test_set_max_hours_honored"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-15
status: complete
---

# Quick Task 260715-hm2: Fix set_max_hours penalty scaling bug Summary

**Divided `C.VOL_SCALE` out of the `maxh_terms` coefficient in `round2_cost` so `set_max_hours` costs $1,000/hour-over-cap as documented, not ~$100,000/hour.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-15T05:38:00Z
- **Completed:** 2026-07-15T05:49:50Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed the `maxh_terms` penalty coefficient in `backend/engine/cpsat/builder.py`'s `round2_cost` expression from `C.MAX_HOURS_PENALTY * sum(maxh_terms)` to `(C.MAX_HOURS_PENALTY // C.VOL_SCALE) * sum(maxh_terms)`, with an inline comment explaining why this term alone needs the extra division (its `over` IntVar is the only VOL_SCALE-scaled variable among the four override penalty terms).
- Corrected the stale docstring in `test_set_max_hours_honored` that described the old buggy formula ("penalty=MAX_HOURS_PENALTY * 4h * VOL_SCALE") to state the corrected math (penalty = (MAX_HOURS_PENALTY / VOL_SCALE) * 4h = $4,000).

## Task Commits

Each task was committed atomically as a single combined commit (both tasks touch the same logical fix):

1. **Task 1 + Task 2: Fix round2_cost coefficient + correct test docstring** - `5bf1689` (fix)

## Files Created/Modified
- `backend/engine/cpsat/builder.py` - `round2_cost` maxh_terms coefficient now divides `C.VOL_SCALE` out; added explanatory inline comment
- `backend/tests/test_engine_overrides.py` - `test_set_max_hours_honored` docstring now describes the corrected $4,000 penalty math instead of the old buggy formula

## Decisions Made
- Used integer floor division (`// C.VOL_SCALE`) rather than float division to keep `round2_cost` in exact integer cents-space, matching the pattern of the other three penalty coefficients (`MIN_WORKERS_PENALTY`, `LOCK_SHIFT_PENALTY`, `EXCLUDE_WORKER_PENALTY`). `100_000 // 100 == 1000` with no rounding loss since both constants are clean multiples of 100.

## Deviations from Plan

None - plan executed exactly as written. `backend/config/constants.py` was not modified, matching the plan's instruction that its constant and doc comment already describe the correct intended formula.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `set_max_hours` overrides now cost the documented $1,000/hour-over-cap, matching `config/constants.py`'s intended calibration.
- Full test suite (`test_engine_overrides.py` + `test_constraints_api.py`, 42 tests) passes.
- No follow-up work identified from this fix.

---
*Phase: quick-260715-hm2*
*Completed: 2026-07-15*

## Self-Check: PASSED

- FOUND: backend/engine/cpsat/builder.py
- FOUND: backend/tests/test_engine_overrides.py
- FOUND: SUMMARY.md
- FOUND commit: 5bf1689
