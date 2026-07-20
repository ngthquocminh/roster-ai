---
phase: 04-results-insights
plan: 08
subsystem: ui
tags: [react, recharts, vitest, testing-library, empty-state]

# Dependency graph
requires:
  - phase: 04-results-insights
    provides: DemandVsServedChart.tsx (RES-02 grouped bar chart), ScheduleTable.tsx's established zero-state pattern
provides:
  - DemandVsServedChart honest empty-state for zero-demand (coverage_by_function={}) COMPLETED runs
  - Regression test locking the empty-state / populated / null-values behavior split
affects: [results-insights UAT closure]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Zero-length-map empty-state guard mirrored verbatim from ScheduleTable.tsx (data.length === 0 early return, same wrapper/typography classes) — now established across two sibling results components"]

key-files:
  created: []
  modified:
    - frontend/src/components/results/DemandVsServedChart.tsx
    - frontend/src/components/results/DemandVsServedChart.test.tsx

key-decisions:
  - "Empty-state guard keys off toChartData(...).length === 0 (mapped-data length), never a null-value check, so a function with null required_h/served_h still renders its bar — matching the plan's explicit prohibition"
  - "Empty-state early return placed immediately after toChartData(...), before the chartData null-coalescing map and ChartContainer/BarChart render, so an empty run never reaches Recharts"

requirements-completed: [RES-02]

coverage:
  - id: D1
    description: "DemandVsServedChart renders an honest empty-state message (\"No coverage data for this run.\") instead of a blank chart box when coverage_by_function is {}"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#DemandVsServedChart: empty > renders the empty-state copy instead of a chart for empty coverage_by_function"
        status: pass
    human_judgment: false
  - id: D2
    description: "Populated coverage_by_function still renders the grouped required-vs-served bar chart unchanged (no regression to RES-02)"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#DemandVsServedChart: render smoke test > mounts without throwing given populated coverage_by_function"
        status: pass
    human_judgment: false
  - id: D3
    description: "A non-empty coverage_by_function with null required_h/served_h still renders the chart — empty-state fires only on zero-length map, never on null hours"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#DemandVsServedChart: render smoke test > mounts without throwing when a function's values are null"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 08: DemandVsServedChart empty-state gap closure Summary

**Added an honest "No coverage data for this run." empty-state to DemandVsServedChart, gated strictly on mapped-data length so a zero-demand COMPLETED run no longer renders a blank axes-only chart box (closes UAT gap G-04-4).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-20T05:00:00Z (approx)
- **Completed:** 2026-07-20T05:08:25Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- `DemandVsServedChart.tsx` now returns a centered `EMPTY_COVERAGE_COPY` ("No coverage data for this run.") block — reusing `ScheduleTable.tsx`'s exact `flex flex-col items-center gap-2 py-16 text-center` / `text-sm leading-[1.5] text-muted-foreground` classes — when `toChartData(coverage_by_function).length === 0`, instead of proceeding to `ChartContainer`/`BarChart`.
- The guard is placed immediately after `toChartData(...)`, before the existing `chartData` null-coalescing map, so it can never fire on null field values — only on a genuinely empty function map.
- Added a `describe("DemandVsServedChart: empty", ...)` block to `DemandVsServedChart.test.tsx` asserting the empty-state copy renders and no `<svg>` chart is drawn, following TDD RED→GREEN (test committed failing, then implementation committed to make it pass).
- Confirmed no regression: all 6 tests in the file pass (2 `toChartData` unit tests unaffected, 1 new empty-state test, 2 pre-existing populated/null-value smoke tests, 1 empty-array `toChartData` unit test), and the full frontend suite (237 tests across 42 files) passes.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1 (RED): add failing test for DemandVsServedChart empty-state** - `092a38b` (test)
2. **Task 1 (GREEN): add empty-state to DemandVsServedChart** - `d52a71a` (feat)

**Plan metadata:** committed separately by the orchestrator/executor after this SUMMARY.

## Files Created/Modified
- `frontend/src/components/results/DemandVsServedChart.tsx` - Added `EMPTY_COVERAGE_COPY` constant and an early-return empty-state branch gated on `data.length === 0`, positioned before the existing `chartData` map and `ChartContainer`/`BarChart` render.
- `frontend/src/components/results/DemandVsServedChart.test.tsx` - Added `screen` import and a new `describe("DemandVsServedChart: empty", ...)` block asserting the empty-state copy renders and no `<svg>` is present for `coverage_by_function={{}}`.

## Decisions Made
- Empty-state guard keys off `toChartData(coverage_by_function).length === 0` (the same zero-length-map condition `ScheduleTable.tsx` uses), never a null-value check — preserving the existing "values are null" smoke test's requirement that a function with null hours still renders its bar.
- Reused `ScheduleTable.tsx`'s exact wrapper/typography classes verbatim so the two components' empty states read as one visual system, per the plan's `key_links` requirement.

## Deviations from Plan

None - plan executed exactly as written. (One environment-setup step was needed to run tests inside the isolated git worktree — see Issues Encountered below — but it made no code changes and is not a deviation from the plan's scope.)

## Issues Encountered
- The worktree's `frontend/` had no `node_modules` (git worktrees don't carry `node_modules`, which is gitignored). Since `frontend/package.json` and `frontend/package-lock.json` are byte-identical to the main checkout, created a directory junction (`frontend/node_modules` → main checkout's `frontend/node_modules`, Windows `mklink /J`) to reuse the already-installed dependencies without a fresh `npm install`. This is a local filesystem link only, not a repo change, and is excluded from git status (node_modules is gitignored) — confirmed via `git status --short` showing no node_modules entry before either commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- G-04-4 is closed: DemandVsServedChart now distinguishes "no demand for this run" from broken/loading for a zero-demand COMPLETED run.
- No blockers for the remaining phase 04 UAT re-check (manual verification against a real zero-demand run's `coverage_by_function: {}` response is still recommended per the plan's `<verification>` section, but is out of scope for this automated executor).

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*
