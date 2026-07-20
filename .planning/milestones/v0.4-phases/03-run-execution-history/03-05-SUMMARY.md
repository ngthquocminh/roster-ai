---
phase: 03-run-execution-history
plan: 05
subsystem: ui
tags: [react, react-router, tanstack-query, vitest, typescript]

# Dependency graph
requires:
  - phase: 03-run-execution-history (03-02, 03-03, 03-04)
    provides: "useRuns/useTriggerRun hooks, runStatus.ts predicates, and the RunHistoryTable/RunInFlightPanel/TriggerRunButton presentational components this plan composes"
provides:
  - "RunHistory.tsx: the composed /scenarios/:scenarioId/runs route wiring one useRuns + one useTriggerRun pair into the header CTA, in-flight panel, and history table"
  - "App.tsx's 'runs' route now mounts RunHistory instead of RunsPlaceholder"
  - "router.test.tsx assertions updated to the real Run History view; RunsPlaceholder retired"
affects: [phase-04-results-view]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Route-level composition: call each data hook exactly once at the route component, derive every downstream prop (runInProgress, activeRun) from the SAME query response, and pass query objects (not raw arrays) into presentational children — mirrors Editor.tsx's established pattern"

key-files:
  created:
    - frontend/src/routes/RunHistory.tsx
    - frontend/src/routes/RunHistory.test.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/routes/router.test.tsx
  removed:
    - frontend/src/routes/RunsPlaceholder.tsx

key-decisions:
  - "No scenario-existence 404 gate in RunHistory (unlike Editor) — GET /scenarios/{id}/runs returns an empty list rather than 404ing on an unknown scenarioId, so a bogus deep link falls through to RunHistoryTable's ordinary empty state (E4 backstop, T-3-09)."
  - "Removed the router.test.tsx assertion for the retired placeholder's 'This view ships in a later phase…' copy entirely rather than repurposing it — that specific assertion has no real-view analog."

patterns-established: []

requirements-completed: [RUN-01, RUN-02, RUN-03, RUN-04, RUN-05]

coverage:
  - id: D1
    description: "RunHistory composes one useRuns + one useTriggerRun pair, deriving the table rows, in-flight panel's active run, and button's disabled state from a single list response"
    requirement: "RUN-01"
    verification:
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > renders the 'Run History' heading and an enabled 'Run Scenario' button"
        status: pass
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > calls the trigger mutation when the header 'Run Scenario' button is clicked"
        status: pass
    human_judgment: false
  - id: D2
    description: "An active RUNNING/PENDING run shows the in-flight panel; an all-terminal list shows no panel, derived from the same list"
    requirement: "RUN-02"
    verification:
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > shows the in-flight panel when the newest active run is RUNNING"
        status: pass
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > shows no in-flight panel when every run is terminal"
        status: pass
    human_judgment: false
  - id: D3
    description: "TriggerRunButton disables while a run is in progress, derived from the same useRuns list (RUN-03 honesty — no cancel affordance anywhere in the composed view)"
    requirement: "RUN-03"
    verification:
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > disables the button while a run is already in progress, derived from the same list"
        status: pass
    human_judgment: false
  - id: D4
    description: "Prior runs (including a FAILED run with its error text) render in RunHistoryTable within the composed view"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/routes/RunHistory.test.tsx#RunHistory: composition [RUN-01..RUN-04] > renders prior runs in the table"
        status: pass
    human_judgment: false
  - id: D5
    description: "App.tsx's 'runs' route mounts the real RunHistory view in place of RunsPlaceholder; 'runs/:runId' is unchanged; the disabled Results tab and ScenarioLayout are untouched"
    verification:
      - kind: unit
        ref: "frontend/src/routes/router.test.tsx#router: four-route shell (SHELL-03) > mounts the real RunHistory view at /scenarios/:scenarioId/runs"
        status: pass
      - kind: unit
        ref: "frontend/src/routes/router.test.tsx#router: four-route shell (SHELL-03) > mounts the Results placeholder at /scenarios/:scenarioId/runs/:runId"
        status: pass
    human_judgment: false
  - id: D6
    description: "End-to-end browser verification: trigger a run, watch it advance to a terminal state, see prior runs and FAILED error text, without leaving the browser (RUN-01..RUN-05 in the real app against a live backend)"
    verification: []
    human_judgment: true
    rationale: "Deferred to the phase-level end-of-phase human verification checklist per human_verify_mode=end-of-phase; requires a running backend + browser session that this worktree executor does not drive."

# Metrics
duration: 25min
completed: 2026-07-18
status: complete
---

# Phase 3 Plan 5: Run History View Composition Summary

**RunHistory.tsx composes one useRuns + one useTriggerRun pair into TriggerRunButton, RunInFlightPanel, and RunHistoryTable, and swaps in for RunsPlaceholder at /scenarios/:scenarioId/runs — the point where RUN-01..RUN-05 become true end to end in the browser.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-18T13:09:00Z
- **Completed:** 2026-07-18T13:14:25Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified, 1 removed)

## Accomplishments
- Composed `RunHistory()` route component: calls `useRuns(scenarioId)` and `useTriggerRun(scenarioId)` exactly once each, derives `runInProgress`/`activeRun` via `hasActiveRun`/`newestActiveRun` from the same list response, and passes the single `runsQuery` straight into `RunHistoryTable`
- Wired the header row (`h2` "Run History" + `TriggerRunButton`), the conditional `RunInFlightPanel`, and `RunHistoryTable` in the UI-SPEC's fixed vertical order, mirroring `Editor.tsx`'s composed-route shell (`mx-auto max-w-5xl flex flex-col gap-4 px-6 py-8`)
- Swapped `App.tsx`'s `runs` route `Component` from `RunsPlaceholder` to `RunHistory`; `runs/:runId` left mounting `ResultsPlaceholder` unchanged
- Updated `router.test.tsx`'s `/scenarios/:scenarioId/runs` assertions to target the real view's "Run History" heading and "Run Scenario" button instead of the retired placeholder copy; removed the now-inapplicable "still-placeholder" test
- Retired `RunsPlaceholder.tsx` — nothing imports it after the `App.tsx` swap

## Task Commits

Each task was committed atomically:

1. **Task 1: RunHistory view composition + App.tsx route swap** - `abf1ace` (feat)
2. **Task 2: Update router test + retire RunsPlaceholder (scope guards)** - `5a88e43` (test)

## Files Created/Modified
- `frontend/src/routes/RunHistory.tsx` - Composed Run History route: one useRuns/useTriggerRun pair driving header CTA, in-flight panel, and table
- `frontend/src/routes/RunHistory.test.tsx` - Composition tests: heading/button render, in-flight panel presence/absence, table rendering, trigger wiring, disabled-while-in-progress
- `frontend/src/App.tsx` - `runs` route Component swapped from `RunsPlaceholder` to `RunHistory`
- `frontend/src/routes/router.test.tsx` - `/runs` deep-link assertions updated to the real view; placeholder-copy test removed
- `frontend/src/routes/RunsPlaceholder.tsx` - Deleted (retired)

## Decisions Made
- No scenario-existence 404 gate in `RunHistory` (unlike `Editor`): `GET /scenarios/{id}/runs` returns an empty list rather than 404ing, so a bogus deep-linked `scenarioId` falls through to `RunHistoryTable`'s ordinary empty state (the plan's E4 backstop, threat T-3-09).
- Mocked `@/hooks/useRuns` and `@/hooks/useTriggerRun` at the module boundary in `RunHistory.test.tsx` (rather than `@/api/runs`) since this is a composition test of the route, not an integration test of the hooks — each hook already has dedicated coverage (`useRuns`/`useTriggerRun` are exercised indirectly via `router.test.tsx`'s unmocked-fetch deep-link test, matching `Editor`'s precedent).
- Removed rather than repurposed the router test's assertion on the retired "This view ships in a later phase…" copy — no equivalent real-view assertion exists for that specific string.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- This worktree's `frontend/node_modules` was absent (gitignored, not carried into `git worktree add`). Verified `frontend/package-lock.json` is byte-identical to the main repo's, then created a directory symlink (`frontend/node_modules` -> `../../../../frontend/node_modules`, i.e. the main repo's already-installed `node_modules`) rather than running `npm install`, per the worktree executor instructions. No `package.json`/lockfile changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All of RUN-01..RUN-05 are wired end to end in the composed view; automated coverage (RunHistory.test.tsx, router.test.tsx, plus the child components' own suites from 03-02..03-04) is green — 175/175 tests pass across the full `npm run test` suite, `npm run typecheck` is clean.
- The end-of-phase human verification checklist (browser walk-through against a live backend) in the plan's `<verification>` block is deferred to the phase-level verifier per `human_verify_mode=end-of-phase` — not performed by this executor.
- Phase 4 (Results View) can proceed: the `runs/:runId` route still mounts `ResultsPlaceholder` and the Results tab remains disabled, exactly as this plan's scope guards require.

---
*Phase: 03-run-execution-history*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: frontend/src/routes/RunHistory.tsx
- FOUND: frontend/src/routes/RunHistory.test.tsx
- CONFIRMED REMOVED: frontend/src/routes/RunsPlaceholder.tsx
- FOUND commit: abf1ace
- FOUND commit: 5a88e43
