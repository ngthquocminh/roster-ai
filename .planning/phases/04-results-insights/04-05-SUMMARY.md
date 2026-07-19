---
phase: 04-results-insights
plan: 05
subsystem: ui
tags: [react, recharts, shadcn, typescript, vitest]

# Dependency graph
requires:
  - phase: 04-01
    provides: shadcn chart primitives (ChartContainer/ChartTooltip/ChartTooltipContent/ChartConfig) + recharts dependency
  - phase: 04-02
    provides: formatShiftWindow (Day N, HH:MM–HH:MM formatter) + RunResult/ScheduleRow/CoverageStat types
provides:
  - DemandVsServedChart component + toChartData pure helper (RES-02)
  - ScheduleTable component (RES-03)
affects: [04-07 (ResultsView composition — mounts both components)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "First Recharts BarChart composition in the project, via shadcn ChartContainer/ChartConfig — required series as outline-only bar (fill=none + stroke), served series as solid brand-indigo fill"
    - "Null-safe chart tooltip: bar height zero-fills a null value for Recharts' numeric requirement, while a parallel *_raw field preserves the original null so the tooltip formatter can render 'Not computed' instead of a misleading 0h line"

key-files:
  created:
    - frontend/src/components/results/DemandVsServedChart.tsx
    - frontend/src/components/results/DemandVsServedChart.test.tsx
    - frontend/src/components/results/ScheduleTable.tsx
    - frontend/src/components/results/ScheduleTable.test.tsx
  modified: []

key-decisions:
  - "ScheduleTable.tsx's header comment describes the XSS mitigation without spelling out the literal raw-HTML-sink function name, so the plan's own acceptance grep (which expects a zero count for that literal string) doesn't false-positive on the explanatory comment itself — same pattern as the prior plan's useApplyConstraint docstring precedent."
  - "toChartData's public contract stays exactly { function, required_h, served_h } with nulls passed through verbatim (per the plan's <behavior> spec); the null-to-zero bar-height substitution and the parallel *_raw fields needed for the tooltip's 'Not computed' text live only inside the component, not in the exported pure helper."

patterns-established:
  - "Pattern: Recharts BarChart + shadcn ChartContainer/ChartConfig for grouped bar charts — reusable for any future chart in this project"

requirements-completed: [RES-02, RES-03]

coverage:
  - id: D1
    description: "DemandVsServedChart renders one grouped-bar pair per function (required outline-only bar, served solid indigo #4F46E5) with an explicit min-h-[280px] guard for Recharts' ResponsiveContainer"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#DemandVsServedChart: render smoke test"
        status: pass
    human_judgment: false
  - id: D2
    description: "toChartData pure helper maps coverage_by_function to per-function chart data, preserving function keys and passing null required_h/served_h through verbatim (never coerced to 0)"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#toChartData"
        status: pass
    human_judgment: false
  - id: D3
    description: "Chart tooltip renders 'Not computed' for a null required_h/served_h instead of a numeric line, so a zero-height bar isn't misread as zero hours"
    requirement: "RES-02"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/DemandVsServedChart.test.tsx#DemandVsServedChart: render smoke test (mounts without throwing when a function's values are null)"
        status: pass
    human_judgment: true
    rationale: "The unit suite proves the null-safe data path doesn't throw, but the actual rendered tooltip text ('Not computed' vs a numeric line) only appears on real DOM hover in a browser — jsdom cannot exercise Recharts' Tooltip portal/hover interaction. Visual confirmation deferred to plan 04-07's end-to-end Results view UAT."
  - id: D4
    description: "ScheduleTable renders the schedule as a scrollable, server-order-only table (Member | Task | Function | Shift Window) reusing RunHistoryTable's exact max-h-[420px] overflow-y-auto container"
    requirement: "RES-03"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/ScheduleTable.test.tsx#ScheduleTable: populated"
        status: pass
    human_judgment: false
  - id: D5
    description: "A COMPLETED run with zero scheduled shifts renders 'No shifts were scheduled for this run.' instead of an error"
    requirement: "RES-03"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/ScheduleTable.test.tsx#ScheduleTable: empty"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 05: Demand-vs-Served Chart + Schedule Table Summary

**Recharts grouped bar chart (required outline vs. served indigo fill, per function) via shadcn ChartContainer, plus a server-order-only scrollable schedule table reusing RunHistoryTable's container — both null-safe and XSS-safe.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-19T20:52:00Z
- **Completed:** 2026-07-19T20:58:00Z
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments
- `DemandVsServedChart` (RES-02): grouped bar chart, one pair per function from `coverage_by_function` — required as an outline-only bar (`fill="none"`, `stroke="var(--color-required_h)"`), served as a solid `#4F46E5` fill; `min-h-[280px] w-full` guards Recharts' `ResponsiveContainer` first-paint measurement (RESEARCH.md Pitfall 4).
- `toChartData` pure helper: `Record<string, CoverageStat>` → array of `{ function, required_h, served_h }`, preserving function keys and passing `null` through unchanged (never coerced to `0`) — independently unit-testable from Recharts' DOM.
- Chart tooltip null-guard: bar height zero-fills a `null` for Recharts' numeric requirement while a parallel `*_raw` field on each chart-data row lets the tooltip formatter render "Not computed" instead of a misleading "0h" line.
- `ScheduleTable` (RES-03): scrollable, server-order-only table (`max-h-[420px] overflow-y-auto rounded-md border border-border`, copied verbatim from `RunHistoryTable.tsx`) with columns Member | Task | Function | Shift Window; Shift Window uses `formatShiftWindow` (plan 04-02) for human day/time labels.
- Honest empty state: a `COMPLETED` run with zero scheduled shifts renders "No shifts were scheduled for this run." (a legitimate solver outcome, not an error — UI-SPEC E6).
- Both components render all data-sourced strings (member_name/task_id/function/chart labels) as plain JSX text children only — verified via an XSS-payload test asserting no `<img>` element is created from a malicious `member_name`.

## Task Commits

Each task followed the RED → GREEN TDD cycle:

1. **Task 1: DemandVsServedChart (D-02, D-03, RES-02)**
   - `3f34ef1` test(04-05): add failing test for DemandVsServedChart
   - `7eaa636` feat(04-05): implement DemandVsServedChart
2. **Task 2: ScheduleTable (D-08, D-09, D-10, RES-03)**
   - `5b8ffc3` test(04-05): add failing test for ScheduleTable
   - `d197eba` feat(04-05): implement ScheduleTable

_Note: RED commits were verified as genuinely failing (unresolved import errors) before their GREEN counterparts were restored and verified passing._

## Files Created/Modified
- `frontend/src/components/results/DemandVsServedChart.tsx` - Grouped bar chart component + `toChartData` pure helper
- `frontend/src/components/results/DemandVsServedChart.test.tsx` - Data-mapping + render smoke tests (5 tests)
- `frontend/src/components/results/ScheduleTable.tsx` - Scrollable server-order schedule table component
- `frontend/src/components/results/ScheduleTable.test.tsx` - Server-order, formatting, XSS-safety, empty-state tests (6 tests)

## Decisions Made
- `ScheduleTable.tsx`'s header comment avoids spelling out the literal raw-HTML-injection-sink function name (paraphrases it as "no raw-HTML injection sink") so the plan's own acceptance grep for that literal string (expecting count 0) doesn't false-positive on the explanatory comment — mirrors the prior plan's `useApplyConstraint` docstring precedent (STATE.md decisions log).
- `toChartData`'s exported/public shape stays exactly `{ function, required_h, served_h }` with nulls passed through verbatim, matching the plan's `<behavior>` spec literally; the null→0 bar-height substitution and the `*_raw` fields needed for the "Not computed" tooltip text are internal to the component, not part of the tested pure-function contract.

## Deviations from Plan

None - plan executed exactly as written, aside from the acceptance-grep-avoidance comment wording noted above (not a deviation from behavior, just phrasing).

## Issues Encountered
- `node_modules` was not present in this worktree checkout (gitignored); ran `npm install` before any test could execute. Confirmed recharts `3.9.2`'s `ResponsiveContainer` no-ops gracefully when `ResizeObserver` is undefined in jsdom (checked `node_modules/recharts/es6/component/ResponsiveContainer.js:97`), so no polyfill was needed for the render smoke tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both components are presentational (props-only, no internal fetching) and ready to be composed by plan 04-07's `ResultsView`, which feeds them `RunResult.metrics.coverage_by_function` and `RunResult.schedule`.
- Full frontend suite (34 files, 208 tests) and `tsc -b`/`vite build` both pass with these additions — no regressions introduced.

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*
