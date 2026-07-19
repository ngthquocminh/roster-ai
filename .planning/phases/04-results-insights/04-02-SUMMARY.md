---
phase: 04-results-insights
plan: 02
subsystem: api
tags: [typescript, openapi-fetch, react-query-prep, tanstack-query, vitest]

# Dependency graph
requires:
  - phase: 04-results-insights (plan 01)
    provides: shadcn card/chart primitives, frontend scaffolding for Results route
provides:
  - Hand-written RunResult TypeScript interface + getRunResult() wrapper (single-cast-point deviation for the untyped /runs/{run_id}/result endpoint)
  - getRunInsights() wrapper over the already-typed InsightOut response
  - getRun() added to runs.ts for D-12's non-COMPLETED deep-link status probe
  - formatShiftWindow() hour-offset -> "Day N, HH:MM" formatter (1-indexed, cross-midnight-safe)
  - docs/API.md RunResult model + example JSON now document the warnings field
affects: [04-03 (hooks), 04-04 (coverage/warnings components), 04-05 (schedule table), 04-06 (insight panel), 04-07 (results route composition)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single hand-written TypeScript interface + one 'as X' cast point for a backend response with no FastAPI response_model (documented deviation, mirrors formatTimestamp.ts's single-explanatory-comment precedent)"
    - "1-indexed 'Day N' display convention (Math.floor(totalMinutes/1440)+1) applied uniformly across the schedule-window formatter, shared with the coverage-by-day table's convention in a later plan"

key-files:
  created:
    - frontend/src/api/results.ts
    - frontend/src/api/results.test.ts
    - frontend/src/api/insights.ts
    - frontend/src/api/insights.test.ts
    - frontend/src/lib/formatShiftWindow.ts
    - frontend/src/lib/formatShiftWindow.test.ts
  modified:
    - frontend/src/api/runs.ts
    - frontend/src/api/runs.test.ts
    - docs/API.md

key-decisions:
  - "RunResult is hand-written (not codegen'd) because GET /runs/{run_id}/result has no FastAPI response_model — schema.d.ts resolves the response to an unknown-indexed record; the interface is sourced field-for-field from backend/services/serialize.py, with exactly one 'as RunResult' cast in results.ts"
  - "getRunInsights never inspects the 'ready' field — it returns the InsightOut body unmodified so the caller (a later plan's InsightPanel) branches on ready, never on HTTP status code"
  - "formatShiftWindow rounds once in total minutes (not independently in hours/minutes) to avoid a 23.999h -> '24:00' rendering bug, and uses 1-indexed day numbering matching docs/API.md's own worked example"

patterns-established:
  - "Boundary-mock API wrapper tests (vi.mock('./client')) extended to results.ts and insights.ts, matching runs.test.ts's existing convention exactly"

requirements-completed: [RES-03, RES-04, RES-05, RES-06]

coverage:
  - id: D1
    description: "results.ts exports a hand-written RunResult interface (with warnings: string[]) and getRunResult(runId) wrapper, with exactly one 'as RunResult' cast point"
    requirement: "RES-06"
    verification:
      - kind: unit
        ref: "frontend/src/api/results.test.ts#getRunResult"
        status: pass
    human_judgment: false
  - id: D2
    description: "getRunInsights(runId) resolves the typed InsightOut body unmodified (never inspects ready) and throws {status, ...error} with status 502 on provider/grounding failures"
    requirement: "RES-04"
    verification:
      - kind: unit
        ref: "frontend/src/api/insights.test.ts#getRunInsights"
        status: pass
    human_judgment: false
  - id: D3
    description: "getRunInsights isolates a 502 failure as a distinguishable thrown status, satisfying the failure-isolation contract insight consumers rely on"
    requirement: "RES-05"
    verification:
      - kind: unit
        ref: "frontend/src/api/insights.test.ts#getRunInsights > rejects with an error carrying status === 502"
        status: pass
    human_judgment: false
  - id: D4
    description: "getRun(runId) added to runs.ts, resolving RunOut for any run status (PENDING/RUNNING/COMPLETED/FAILED) without throwing"
    verification:
      - kind: unit
        ref: "frontend/src/api/runs.test.ts#getRun"
        status: pass
    human_judgment: false
  - id: D5
    description: "formatShiftWindow(startH, endH) formats hour-offset floats as 1-indexed 'Day N, HH:MM–HH:MM', cross-midnight as 'Day N, HH:MM – Day M, HH:MM', rounding once to avoid a 24:00 boundary bug"
    requirement: "RES-03"
    verification:
      - kind: unit
        ref: "frontend/src/lib/formatShiftWindow.test.ts#formatShiftWindow"
        status: pass
    human_judgment: false
  - id: D6
    description: "docs/API.md's RunResult model table and example JSON document the warnings: string[] field"
    requirement: "RES-06"
    verification:
      - kind: other
        ref: "docs/API.md RunResult table 'warnings' row + example JSON 'warnings': []"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-19
status: complete
---

# Phase 04 Plan 02: Typed Results/Insights Read Contract Summary

**Hand-written RunResult TypeScript type (single-cast-point deviation for the untyped `/result` endpoint) plus `getRunInsights`, `getRun`, and a rounding-safe `formatShiftWindow` hour-offset formatter — the read contract plans 04-03..04-07 build against.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-20T03:19:48+07:00 (base commit)
- **Completed:** 2026-07-20T03:33:47+07:00
- **Tasks:** 3
- **Files modified:** 8 (6 new, 2 modified... plus docs/API.md = 3 modified)

## Accomplishments
- `results.ts` exports a hand-written `RunResult` interface (status, metrics, stats, schedule, `warnings: string[]`) and `getRunResult(runId)`, sourced field-for-field from `backend/services/serialize.py`, with exactly one `as RunResult` cast — closing the codegen gap left by the endpoint having no FastAPI `response_model`
- `insights.ts` exports `getRunInsights(runId)`, returning the already-typed `InsightOut` body unmodified so callers branch on `ready`, never on HTTP status; throws `{status, ...error}` on error (502 distinguishable)
- `runs.ts` gains `getRun(runId)` over `GET /runs/{run_id}`, resolving `RunOut` for any run status — the D-12 deep-link status probe — and its header comment no longer claims no per-run wrapper exists
- `formatShiftWindow.ts` converts hour-offset floats to 1-indexed "Day N, HH:MM–HH:MM" strings, correctly handling cross-midnight shifts and the 23.999h rounding boundary
- `docs/API.md`'s `RunResult` model table and example JSON now document the `warnings` field, closing the doc/code drift flagged in CONTEXT.md

## Task Commits

Each task was committed atomically:

1. **Task 1: results.ts — hand-written RunResult type + getRunResult + docs/API.md warnings fix** - `00ea23f` (feat)
2. **Task 2: insights.ts (getRunInsights) + runs.ts getRun** - `08555b4` (feat)
3. **Task 3: formatShiftWindow hour-offset formatter** - `9303645` (feat)

_All three tasks were TDD-tagged; tests were authored alongside (not as separate RED commits) since each wrapper/formatter is small enough that test-then-implementation collapsed into a single commit per task without losing the verification loop — every commit's test suite was run green before committing._

## Files Created/Modified
- `frontend/src/api/results.ts` - Hand-written `RunResult`/`CoverageStat`/`ScheduleRow` interfaces + `getRunResult(runId)` wrapper (one cast point, documented deviation)
- `frontend/src/api/results.test.ts` - Boundary-mock tests: success body (incl. warnings), empty-warnings preservation, 409, 404
- `frontend/src/api/insights.ts` - `getRunInsights(runId)` wrapper, passes `InsightOut` through unmodified
- `frontend/src/api/insights.test.ts` - Boundary-mock tests: ready:true, ready:false pass-through, 502, 404
- `frontend/src/api/runs.ts` - Added `getRun(runId)`; updated header comment (no longer claims no per-run wrapper)
- `frontend/src/api/runs.test.ts` - Added `getRun` tests: non-terminal status, COMPLETED, 404
- `frontend/src/lib/formatShiftWindow.ts` - `formatDayTime`/`formatShiftWindow`; round-once-in-minutes, 1-indexed day, cross-midnight branch
- `frontend/src/lib/formatShiftWindow.test.ts` - Same-day, second-day, cross-midnight, rounding-boundary, hour-0 cases
- `docs/API.md` - `RunResult` model table + example JSON now include `warnings: string[]`

## Decisions Made
- Followed RESEARCH.md's Code Example 2 and PATTERNS.md's assignment verbatim for `RunResult`'s shape — no deviation from the researched field list.
- Kept the `warnings` field typed as always-present `string[]` (never `undefined`), per RESEARCH.md's Open Question 1 recommendation, rather than making it optional to hedge against hypothetical pre-warnings-era cached rows (none exist in this dev DB; the field has been on `SolveResult` since Phase 2).
- `getRunInsights`'s test suite explicitly asserts the `ready: false` body passes through without throwing, directly encoding RES-04's hard rule ("never on HTTP status code") as a regression test rather than leaving it as an implicit convention.

## Deviations from Plan

None - plan executed exactly as written. The one intentional "deviation" (hand-written `RunResult` type, single cast point) is itself the plan's explicit, researched instruction, not an unplanned discovery — documented in `results.ts`'s header comment as directed.

## Issues Encountered
- The worktree had no `frontend/node_modules` (git worktrees don't share installed dependencies with the main checkout). Since `package.json`/`package-lock.json` are byte-identical to the main repo's, a Windows directory junction (`mklink /J`) to the main repo's `frontend/node_modules` was created instead of a fresh `npm install`, avoiding a slow reinstall of an unchanged dependency tree. This is local-environment plumbing only — no repo file was added or modified, and the junction itself is git-ignored (confirmed via `git check-ignore`).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The typed read contract (`getRunResult`, `getRunInsights`, `getRun`, `formatShiftWindow`) is in place and fully unit-tested; plan 04-03 (hooks: `useRun`, `useRunResult`, `useRunInsights`) can now be built directly against these wrappers without any further API-layer work.
- Full frontend suite (`npx vitest run`) is green: 32 test files, 197 tests passed, including this plan's 21 new/updated tests.
- `tsc --noEmit` passes with zero errors across the frontend.
- No blockers for 04-03 onward.

---
*Phase: 04-results-insights*
*Completed: 2026-07-19*

## Self-Check: PASSED

All created files verified present on disk; all three task commit hashes (`00ea23f`, `08555b4`, `9303645`) verified present in git log.
