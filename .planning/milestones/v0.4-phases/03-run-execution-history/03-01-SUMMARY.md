---
phase: 03-run-execution-history
plan: 01
subsystem: api
tags: [typescript, openapi-fetch, vitest, lucide-react, react-query-foundation]

# Dependency graph
requires: []
provides:
  - "listRuns/triggerRun thin typed wrappers over GET/POST /scenarios/{scenario_id}/runs"
  - "runStatus.ts single-source status vocabulary (label/icon/color) + terminal/active predicates"
affects: [03-02, 03-03, 03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "runs.ts mirrors scenarios.ts/constraints.ts T-1-02 convention: throw { status: response.status, ...error } on non-2xx, return data on success"
    - "runStatus.ts mirrors toolLabels.ts's fixed-lookup + safe-fallback convention (raw status string as label when unrecognized, never fabricated)"

key-files:
  created:
    - frontend/src/api/runs.ts
    - frontend/src/api/runs.test.ts
    - frontend/src/lib/runStatus.ts
    - frontend/src/lib/runStatus.test.ts
  modified: []

key-decisions:
  - "No getRun/per-run wrapper added — this phase polls only the list endpoint (UI-SPEC Data strategy); per-plan constraint honored exactly."
  - "RunOut typed via indexed access into generated components[\"schemas\"][\"RunOut\"] (@/api/schema), never hand-authored, in both runs.ts and runStatus.ts."

patterns-established:
  - "Pattern: run-status truth (label + icon + color + terminal/active predicates) lives in exactly one pure module (runStatus.ts) that later hooks/table/panel/button all import — prevents visual mapping and polling-stop logic from drifting apart."

requirements-completed: [RUN-01, RUN-02, RUN-04]

coverage:
  - id: D1
    description: "listRuns(scenarioId) issues typed GET /scenarios/{scenario_id}/runs through the shared client and returns RunOut[]; throws { status, ...error } on non-2xx"
    requirement: "RUN-02"
    verification:
      - kind: unit
        ref: "frontend/src/api/runs.test.ts#listRuns"
        status: pass
    human_judgment: false
  - id: D2
    description: "triggerRun(scenarioId) issues typed POST /scenarios/{scenario_id}/runs and returns the created PENDING RunOut; throws { status, ...error } on non-2xx (404 case included)"
    requirement: "RUN-01"
    verification:
      - kind: unit
        ref: "frontend/src/api/runs.test.ts#triggerRun"
        status: pass
    human_judgment: false
  - id: D3
    description: "runStatusMeta maps all four RunOut statuses to the exact UI-SPEC label/icon/color, with spin only on RUNNING, and falls back to a neutral Clock + raw-string label for unrecognized statuses"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/lib/runStatus.test.ts#runStatusMeta"
        status: pass
    human_judgment: false
  - id: D4
    description: "isTerminalStatus/hasActiveRun/newestActiveRun terminal/active predicates, including empty-list, all-terminal, and newest-first-no-resort behavior"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/lib/runStatus.test.ts#isTerminalStatus, #hasActiveRun, #newestActiveRun"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-18
status: complete
---

# Phase 3 Plan 01: Run API Wrappers + Status Vocabulary Summary

**Typed `listRuns`/`triggerRun` wrappers over the run endpoints and a pure `runStatus.ts` module that is the single source of run-status label/icon/color plus the terminal/active predicates driving both polling and rendering.**

## Performance

- **Duration:** ~3 min (wall clock between first and last commit; excludes context-gathering)
- **Started:** 2026-07-18T09:12:19Z
- **Completed:** 2026-07-18T09:13:28Z
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments
- `frontend/src/api/runs.ts` — `listRuns(scenarioId)` and `triggerRun(scenarioId)`, thin wrappers over the shared `client` instance, mirroring `scenarios.ts`'s T-1-02 error convention (`throw { status: response.status, ...error }`).
- `frontend/src/lib/runStatus.ts` — `RUN_STATUS_META`, `runStatusMeta`, `isTerminalStatus`, `hasActiveRun`, `newestActiveRun`; pure, no React/JSX, typed against generated `components["schemas"]["RunOut"]`.
- Both modules fully covered by boundary-mock (runs.ts) and pure-function (runStatus.ts) tests — 19 tests total, all green.

## Task Commits

Each task followed the TDD RED → GREEN cycle with separate commits:

1. **Task 1: Typed run API wrappers (runs.ts)**
   - `3abfa84` (test): add failing test for run API wrappers
   - `17227cb` (feat): implement typed run API wrappers
2. **Task 2: Run-status vocabulary + terminal predicates (runStatus.ts)**
   - `ca62cba` (test): add failing test for run-status vocabulary and terminal predicates
   - `71bf4ed` (feat): implement run-status vocabulary and terminal/active predicates

**Plan metadata:** committed alongside this SUMMARY.

## Files Created/Modified
- `frontend/src/api/runs.ts` - `listRuns`/`triggerRun` thin typed wrappers (RUN-01, RUN-02, RUN-04)
- `frontend/src/api/runs.test.ts` - boundary-mock coverage (`vi.mock("./client")`) mirroring scenarios.test.ts/constraints.test.ts
- `frontend/src/lib/runStatus.ts` - status vocabulary + terminal/active predicates
- `frontend/src/lib/runStatus.test.ts` - pure-function coverage for all four known statuses, the unknown-status fallback, and the newest-first-no-resort case

## Decisions Made
- Kept `runs.ts` to exactly the two endpoints RUN-01/RUN-02/RUN-04 need — no `getRun` wrapper, per the plan's explicit constraint (the run-detail route lands on the Phase-4 `ResultsPlaceholder`).
- Typed `RunOut` via indexed access into generated `components`/`paths` in both new files rather than hand-authoring an interface, consistent with `scenarios.ts`'s established convention and this plan's `must_haves`.

## Deviations from Plan

None - plan executed exactly as written.

One environment-only adjustment (not a code deviation): the worktree had no `frontend/node_modules` (git worktrees don't inherit node_modules, which is gitignored). Verified the worktree's `package-lock.json` is byte-identical to the main repo's, then created a directory symlink `frontend/node_modules → ../../../../frontend/node_modules` to reuse the already-installed main-repo dependencies rather than re-running `npm install` (which would be a Rule-3-excluded package-manager install requiring a legitimacy checkpoint even though no new packages were being added — this plan adds zero new dependencies per its own `success_criteria`). The symlink is outside git tracking (node_modules is gitignored) and does not appear in `git status`.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `frontend/src/api/runs.ts` and `frontend/src/lib/runStatus.ts` are ready for plans 03-02 (polling hook), 03-03 (run history table/in-flight panel), 03-04 (trigger button), and 03-05 (wiring) to import.
- No blockers. `npx vitest run src/api/runs.test.ts src/lib/runStatus.test.ts` and `npm run typecheck` both pass clean.

---
*Phase: 03-run-execution-history*
*Completed: 2026-07-18*

## Self-Check: PASSED

All created files verified present on disk; all four task commit hashes (3abfa84, 17227cb, ca62cba, 71bf4ed) verified in git log.
