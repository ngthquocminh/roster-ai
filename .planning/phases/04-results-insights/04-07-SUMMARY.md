---
phase: 04-results-insights
plan: 07
subsystem: ui
tags: [react, react-router, tanstack-query, results-view, integration]

# Dependency graph
requires:
  - phase: 04-results-insights
    provides: "useRun/useRunResult/useRunInsights hooks, getRun/getRunResult/getRunInsights api wrappers, and CoverageSummary/WarningsBanner/CoverageByDayTable/DemandVsServedChart/ScheduleTable/InsightPanel result components (plans 04-01..04-06)"
provides:
  - "ResultsView.tsx — the composed Results route, D-12 status-gate branching (loading/error/PENDING/RUNNING/FAILED/COMPLETED) feeding all six result components from one useRun + useRunResult query pair"
  - "App.tsx route swap: runs/:runId now maps to ResultsView; ResultsPlaceholder.tsx retired"
  - "ResultsView.test.tsx: D-12 three-way branch coverage + RES-05 insight-502-isolation integration test"
  - "router.test.tsx updated to assert ResultsView's real loading state instead of the retired placeholder heading"
affects: [results-insights, ui-review, ui-phase-05-if-any]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Route-level composition: one useRun + one gated useRunResult drive branching and feed six presentational children, mirroring RunHistory.tsx's 'one query pair drives everything' precedent"
    - "D-12 status-gate precedence: loading -> error -> PENDING/RUNNING -> FAILED -> COMPLETED (gated further on resultQuery.isLoading/isError/isSuccess so no child ever receives undefined data)"

key-files:
  created:
    - frontend/src/routes/ResultsView.tsx
    - frontend/src/routes/ResultsView.test.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/routes/router.test.tsx
  deleted:
    - frontend/src/routes/ResultsPlaceholder.tsx

key-decisions:
  - "Added an interim honest state for the COMPLETED-but-resultQuery-still-loading/erroring window (centered spinner / ErrorBanner) rather than the plan's minimal null-until-isSuccess sketch — avoids a blank screen between the status resolving COMPLETED and the /result fetch settling, consistent with the project's never-blank-screen (SHELL-04) principle. Does not change the plan's core gate: the results body itself still renders only once resultQuery.isSuccess."
  - "Left frontend/src/components/layout/PlaceholderView.tsx in place even though ResultsPlaceholder.tsx (its only remaining consumer) was retired — out of the plan's files_modified scope; unused but harmless, not a build or lint error."
  - "Mocked @/hooks/useRun and @/hooks/useRunResult at the module boundary in ResultsView.test.tsx (not the underlying api/ wrappers), matching RunHistory.test.tsx's established composition-test convention; InsightPanel is left unmocked so the RES-05 test drives a genuine 502 through its real useRunInsights mutation, with only @/api/insights mocked underneath it."

patterns-established:
  - "Composition route test mocks its own direct hook dependencies but leaves nested components (and their own hooks) real when a cross-section isolation guarantee (RES-05) needs to be proven end-to-end rather than assumed from unit coverage alone."

requirements-completed: [RES-01, RES-02, RES-03, RES-04, RES-05, RES-06]

coverage:
  - id: D1
    description: "ResultsView branches on RunOut.status first (D-12): loading spinner, ErrorBanner on a failed GET /runs/{id}, RunInFlightPanel for PENDING/RUNNING, and a destructive 'Run Failed' Alert (run.error or the reused FAILED_NO_ERROR_COPY) for FAILED — nothing else renders below any of these branches."
    requirement: "RES-01"
    verification:
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx#ResultsView: D-12 status gate [RES-01..RES-06] > PENDING/RUNNING → renders RunInFlightPanel and no results body"
        status: pass
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx#ResultsView: D-12 status gate [RES-01..RES-06] > FAILED (with error) → renders the 'Run Failed' alert with run.error and no results body"
        status: pass
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx#ResultsView: D-12 status gate [RES-01..RES-06] > FAILED (no error) → falls back to RunHistoryTable's exact FAILED_NO_ERROR_COPY"
        status: pass
    human_judgment: false
  - id: D2
    description: "useRunResult is gated on runQuery.data?.status === 'COMPLETED', so GET /runs/{id}/result never fires (and never 409s) before the run completes — the route stays deep-linkable for any run status."
    requirement: "RES-01"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useRunResult.test.tsx (existing coverage of the enabled gate itself)"
        status: pass
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx (useRunResult mocked per-test; PENDING/RUNNING/FAILED cases never supply COMPLETED-only fixture data, exercising the caller-side gate wiring)"
        status: pass
    human_judgment: false
  - id: D3
    description: "On COMPLETED, the body renders in UI-SPEC order: 'Run Results' heading + 'Completed {finished_at}' metadata line, then WarningsBanner -> CoverageSummary -> CoverageByDayTable -> DemandVsServedChart -> ScheduleTable -> InsightPanel, all fed by resultQuery.data."
    requirement: "RES-02"
    verification:
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx#ResultsView: D-12 status gate [RES-01..RES-06] > COMPLETED → renders coverage/chart/schedule/insight sections fed by resultQuery.data"
        status: pass
    human_judgment: true
    rationale: "Automated coverage proves the sections mount with correct data; the plan's own human-check batches full visual/interactive verification (chart bar heights, table scroll, live insight fetch) to end-of-phase per human_verify_mode=end-of-phase — that sign-off has not occurred within this plan's scope."
  - id: D4
    description: "A 502 in InsightPanel leaves the coverage cards, chart, schedule table, and warnings banner mounted and interactive (RES-05) — proven by an integration test that fails the insight fetch and asserts the sibling sections are still present."
    requirement: "RES-05"
    verification:
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx#ResultsView: RES-05 insight failure isolation > a 502 from the insight fetch shows the insight error while coverage/chart/schedule sections remain in the DOM"
        status: pass
    human_judgment: false
  - id: D5
    description: "App.tsx's runs/:runId route maps to ResultsView (no route added/removed); ResultsPlaceholder.tsx is retired; ScenarioLayout.tsx and the Results nav tab are unchanged (still a non-clickable placeholder)."
    requirement: "RES-01"
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit -p tsconfig.app.json && test ! -f src/routes/ResultsPlaceholder.tsx"
        status: pass
      - kind: integration
        ref: "frontend/src/routes/router.test.tsx#router: four-route shell (SHELL-03) > marks the (disabled) Results tab active on /scenarios/:scenarioId/runs/:runId"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 07: Results View Composition Summary

**Composed ResultsView.tsx — the D-12 status-gated route that swaps in for ResultsPlaceholder and wires all six Phase 4 result components (coverage stats, by-day table, demand-vs-served chart, schedule table, insight panel) to one useRun + useRunResult query pair, with an integration test proving the RES-05 502-isolation guarantee.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-20T04:08:33+07:00 (worktree base)
- **Completed:** 2026-07-20T04:15:03+07:00
- **Tasks:** 2
- **Files modified:** 5 (2 created, 2 modified, 1 deleted)

## Accomplishments

- `ResultsView.tsx` branches on `RunOut.status` first (D-12), before any results content renders: loading spinner → `ErrorBanner` on a failed `GET /runs/{id}` → `RunInFlightPanel` (verbatim, Phase 3) for `PENDING`/`RUNNING` → a destructive "Run Failed" `Alert` for `FAILED` → the full results body for `COMPLETED`, gated further on `resultQuery`'s own loading/error/success state.
- `useRunResult(runId, { enabled: runQuery.data?.status === "COMPLETED" })` keeps `GET /runs/{run_id}/result` from ever firing (and 409ing) before the run completes — the route stays deep-linkable for any run status.
- The `COMPLETED` body renders, in order, "Run Results" + "Completed {finished_at}" metadata, `WarningsBanner`, `CoverageSummary`, `CoverageByDayTable`, `DemandVsServedChart`, `ScheduleTable`, and `InsightPanel` — all fed by one `resultQuery.data`.
- `App.tsx`'s `runs/:runId` route now maps to `ResultsView`; `ResultsPlaceholder.tsx` is deleted.
- `ResultsView.test.tsx` proves the D-12 three-way branch (PENDING/RUNNING, FAILED-with-error, FAILED-without-error, COMPLETED) and the RES-05 isolation guarantee: a real 502 from `InsightPanel`'s own `useRunInsights` mutation leaves the coverage stats, by-day table, and schedule table mounted.
- `router.test.tsx`'s placeholder-mount assertion now targets `ResultsView`'s real loading-branch text; the disabled-Results-tab-active test is untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: ResultsView composition + App.tsx route swap + retire ResultsPlaceholder** - `b1249c2` (feat)
2. **Task 2: ResultsView.test.tsx integration + router.test.tsx update** - `2cb1492` (test)

## Files Created/Modified

- `frontend/src/routes/ResultsView.tsx` - Composed Results route: D-12 status gate, feeds six result components from one query pair
- `frontend/src/routes/ResultsView.test.tsx` - Integration coverage for the D-12 branch and RES-05 502-isolation
- `frontend/src/App.tsx` - `runs/:runId` now maps to `ResultsView`; `ResultsPlaceholder` import removed
- `frontend/src/routes/router.test.tsx` - Placeholder-mount assertion updated to `ResultsView`'s loading state
- `frontend/src/routes/ResultsPlaceholder.tsx` - Deleted (retired; superseded by `ResultsView`)

## Decisions Made

- Added an interim honest loading/error state for the `COMPLETED`-but-`resultQuery`-still-settling window (a centered spinner and `ErrorBanner`, mirroring `useRun`'s own loading/error branches) rather than the plan's minimal "gate on `isSuccess`, else null" sketch — avoids a blank screen between the run resolving `COMPLETED` and the `/result` fetch settling, consistent with the project's SHELL-04 never-blank-screen principle. The core plan requirement (body renders only once `resultQuery.isSuccess`) is unchanged.
- Left `frontend/src/components/layout/PlaceholderView.tsx` in place — its only remaining consumer (`ResultsPlaceholder.tsx`) was retired, but the file itself is outside this plan's `files_modified` scope; it is unused but harmless (no build/lint error), so removal was deferred rather than expanding scope.
- Mocked `@/hooks/useRun`/`@/hooks/useRunResult` at the module boundary in `ResultsView.test.tsx` (matching `RunHistory.test.tsx`'s composition-test convention) while leaving `InsightPanel` unmocked so the RES-05 test drives a real 502 through its own `useRunInsights` mutation (only `@/api/insights` mocked underneath it) — this proves cross-section isolation end-to-end rather than assuming it from `InsightPanel`'s own unit coverage.

## Deviations from Plan

None beyond the loading/error interim-state addition already documented above under Decisions Made (Rule 2 — missing critical functionality: an honest non-blank interim state for a `COMPLETED` run whose result fetch is still in flight or fails).

## Issues Encountered

- `frontend/node_modules` did not exist in this git worktree (each worktree needs its own `npm install` since `node_modules` is gitignored and not shared across worktrees). Ran `npm install` from `frontend/` before any `tsc`/`vitest`/`build` verification could execute — resolved cleanly (565 packages, 0 vulnerabilities), no `package.json`/`package-lock.json` changes.
- `screen.getByRole("table")` in the first draft of the RES-05 isolation test failed with a multiple-elements error, since both `CoverageByDayTable` and `ScheduleTable` render a `<table>` once the `COMPLETED` body is mounted — switched to `getAllByRole("table").length > 0`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All six Phase 4 result components (04-01..04-06) are now composed and live at the run-detail route; `npx tsc --noEmit -p tsconfig.app.json`, the full `npx vitest run` suite (234 tests, 42 files), and `npm run build` (`tsc -b && vite build`) all pass clean from this worktree.
- The plan's `<human-check>` (visual verification of chart bars, table scrolling, live insight fetch, and deep-linking each run status) is explicitly batched to end-of-phase per `human_verify_mode=end-of-phase` and has not been performed within this plan's scope — flagged in `coverage` D3 above as `human_judgment: true`.
- No blockers for the remaining Phase 4 waves or an end-of-phase human-check pass.

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*
