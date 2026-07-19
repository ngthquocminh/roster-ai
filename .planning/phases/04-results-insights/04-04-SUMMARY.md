---
phase: 04-results-insights
plan: 04
subsystem: ui
tags: [react, shadcn, tailwind, vitest, testing-library, tooltip, card, table]

# Dependency graph
requires:
  - phase: 04-results-insights
    provides: "plan 04-01's Card/Tooltip shadcn primitives and results.ts's RunResult type; plan 04-02's ScheduleTable/formatShiftWindow day-indexing convention this plan's CoverageByDayTable must match"
provides:
  - "WarningsBanner — renders SolveResult.warnings[] verbatim above the stat row, or nothing when empty"
  - "CoverageSummary — two-Card stat row (Total Cost, Total Unmet Hours) with independent per-card null-safe 'Not computed' + Tooltip handling"
  - "CoverageByDayTable — 1-indexed by-day coverage breakdown table"
affects: ["04-07 (ResultsView composition — mounts all three components in WarningsBanner → CoverageSummary → CoverageByDayTable order)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Presentational-only components receiving already-fetched RunResult fields as props, never fetching themselves (RunInFlightPanel precedent)"
    - "Per-field null guard at the point of render (never a top-level gate), rendering literal 'Not computed' instead of a fabricated zero or em dash"
    - "1-indexed day labels via Number(dayKey) + 1, matching formatShiftWindow's day math"

key-files:
  created:
    - frontend/src/components/results/WarningsBanner.tsx
    - frontend/src/components/results/WarningsBanner.test.tsx
    - frontend/src/components/results/CoverageSummary.tsx
    - frontend/src/components/results/CoverageSummary.test.tsx
    - frontend/src/components/results/CoverageByDayTable.tsx
    - frontend/src/components/results/CoverageByDayTable.test.tsx
  modified: []

key-decisions:
  - "WarningsBanner deliberately deviates from ErrorBanner's fixed-copy convention: solver warnings are already display-ready, non-user-controlled text, so they render verbatim as plain JSX text (no dangerouslySetInnerHTML anywhere)."
  - "CoverageSummary's null guard renders a literal 'Not computed' string wrapped in a Tooltip, never `value ?? 0` and never a bare em dash — the same never-hide-solver-limitations principle as RunInFlightPanel's honest wait copy."
  - "CoverageByDayTable reuses RunHistoryTable's Table/TableHeader/TableBody composition but drops the scroll container, row-click navigation, and loading/error/empty state machine — this table renders synchronously from an already-loaded RunResult."

patterns-established:
  - "Nullable numeric metric rendering: guard at the exact render point per-field, never once at a parent gate — established here for CoverageSummary/CoverageByDayTable, to be reused by DemandVsServedChart (04-05/04-06) for coverage_by_function nulls."

requirements-completed: [RES-01, RES-06]

coverage:
  - id: D1
    description: "WarningsBanner renders SolveResult.warnings[] verbatim above the stat row (Alert variant=default + TriangleAlert, title 'Heads up'), or nothing at all when the array is empty"
    requirement: "RES-06"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/WarningsBanner.test.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "CoverageSummary renders Total Cost (Intl.NumberFormat USD) and Total Unmet Hours ('{value} h', one decimal) as the Display-type stat row, with each card independently guarding a null metric as 'Not computed' + explanatory Tooltip"
    requirement: "RES-01"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/CoverageSummary.test.tsx"
        status: pass
    human_judgment: false
  - id: D3
    description: "CoverageByDayTable renders one row per coverage_by_day key as 1-indexed 'Day N' with '{value}%' or 'Not computed' for a null day"
    requirement: "RES-01"
    verification:
      - kind: unit
        ref: "frontend/src/components/results/CoverageByDayTable.test.tsx"
        status: pass
    human_judgment: false
  - id: D4
    description: "A single long warning string wraps inside WarningsBanner without breaking page layout (visual backstop, same class as Phase 3's FAILED-error long-text backstop)"
    verification: []
    human_judgment: true
    rationale: "UI-SPEC backstop — visual wrap behavior cannot be asserted at spec/unit-test time; requires human visual verification once ResultsView (04-07) composes this component into the real page."
  - id: D5
    description: "CoverageByDayTable's rendering when coverage_by_day is empty on a COMPLETED run (unverified reachability against the real engine)"
    verification: []
    human_judgment: true
    rationale: "UI-SPEC backstop — not confirmed against the engine whether SolveResult.metrics always populates coverage_by_day when scheduling occurs; genuine unknown, not an oversight."

duration: 25min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 04: Coverage Cluster (WarningsBanner, CoverageSummary, CoverageByDayTable) Summary

**Three presentational components — coverage-honesty warnings banner, null-safe cost/unmet-hours stat cards, and a 1-indexed by-day breakdown table — built TDD (RED/GREEN per task) against already-fetched RunResult fields.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-20T03:51:00Z
- **Completed:** 2026-07-20T04:16:00Z
- **Tasks:** 3
- **Files modified:** 6 (all created)

## Accomplishments
- WarningsBanner renders the solver's `warnings[]` verbatim above the stat row (or nothing when empty), using a neutral `Alert variant="default"` + `TriangleAlert` icon — no severity color, matching UI-SPEC's "caveat, not error" framing (D-06/RES-06).
- CoverageSummary renders the two-Card stat row with `Intl.NumberFormat` currency and one-decimal-hour formatting, and an independent per-card null guard rendering literal "Not computed" + a `Tooltip` explaining the solver's time limit — never a misleading `$0.00` or plain `0` (D-04/D-07/RES-01).
- CoverageByDayTable renders one row per `coverage_by_day` key as 1-indexed "Day N" (matching `formatShiftWindow`'s day math used by the schedule table in a later plan), with per-day null values rendering "Not computed" (plain text, no tooltip) (D-05/RES-01).

## Task Commits

Each task was committed atomically, TDD RED → GREEN per task:

1. **Task 1: WarningsBanner (D-06, RES-06)** - `bb717f2` (test) → `3697899` (feat)
2. **Task 2: CoverageSummary stat row (D-04, D-07, RES-01)** - `1862c28` (test) → `e7bfb8d` (feat)
3. **Task 3: CoverageByDayTable (D-05, RES-01)** - `054d0c5` (test) → `1f72c68` (feat)

## Files Created/Modified
- `frontend/src/components/results/WarningsBanner.tsx` - conditional coverage-honesty caveat banner, plain-JSX-text-only
- `frontend/src/components/results/WarningsBanner.test.tsx` - empty/one/many-warning coverage
- `frontend/src/components/results/CoverageSummary.tsx` - two-Card stat row with independent null guards
- `frontend/src/components/results/CoverageSummary.test.tsx` - populated/null/partial/both-null coverage
- `frontend/src/components/results/CoverageByDayTable.tsx` - 1-indexed by-day breakdown table
- `frontend/src/components/results/CoverageByDayTable.test.tsx` - populated + null-day coverage

## Decisions Made
- Followed PATTERNS.md's WarningsBanner/CoverageSummary/CoverageByDayTable pattern blocks closely; used UI-SPEC's exact copy ("Heads up" title, tooltip copy string) where PATTERNS.md's illustrative snippet differed (e.g. PATTERNS.md's example title "Coverage caveat" was superseded by UI-SPEC's authoritative "Heads up").
- CoverageSummary composes a shared internal `NullableStat` helper consumed by both `CostStat` and `UnmetHoursStat`, so the null-guard/Tooltip logic exists in exactly one place rather than being duplicated per stat.

## Deviations from Plan

None - plan executed exactly as written. All three tasks followed their `<action>` specs; TDD RED was verified by moving each implementation file out before running its test (confirmed import-resolution failure), then restoring it and confirming green, before making the two-commit test→feat sequence.

## Issues Encountered
- The worktree's `frontend/` had no `node_modules` (gitignored, not present after worktree creation). Created a Windows directory junction (`mklink /J`) from the worktree's `frontend/node_modules` to the main repo's `frontend/node_modules` so `npx vitest`/`npx tsc` could resolve dependencies without a full reinstall. This is a local filesystem link only — nothing committed, no `package.json`/lockfile changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All three components are ready for composition into `ResultsView` (plan 04-07), which mounts them in the order WarningsBanner → CoverageSummary → CoverageByDayTable per D-06's caveat-before-numbers rule.
- `npx tsc --noEmit -p tsconfig.app.json` passes with zero errors across the new files.
- Two backstop items (long-text wrap, empty-`coverage_by_day` reachability) are deferred to human visual verification once ResultsView composes real data — documented in `coverage` D4/D5 above, not silently dropped.

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*
