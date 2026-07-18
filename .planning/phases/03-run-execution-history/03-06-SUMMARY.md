---
phase: 03-run-execution-history
plan: 06
subsystem: ui
tags: [react, typescript, vitest, timestamp-formatting, table-layout]

# Dependency graph
requires:
  - phase: 03-run-execution-history (plan 05)
    provides: RunHistoryTable component, RunOut schema, TimestampCell scaffold
provides:
  - Pure formatTimestamp(value) utility shortening ISO-8601 UTC timestamps to fixed-width "YYYY-MM-DD HH:MM"
  - RunHistoryTable's Created/Started/Finished columns routed through formatTimestamp
  - Regression test pinning the real 32-char microsecond+offset backend timestamp format
affects: [run-execution-history, results-view]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Deterministic regex-slice formatting (no toLocale*) mirroring runStatus.ts/toolLabels.ts fallback discipline"]

key-files:
  created:
    - frontend/src/lib/formatTimestamp.ts
    - frontend/src/lib/formatTimestamp.test.ts
  modified:
    - frontend/src/components/runs/RunHistoryTable.tsx
    - frontend/src/components/runs/RunHistoryTable.test.tsx

key-decisions:
  - "formatTimestamp implemented via regex slice of the leading YYYY-MM-DDTHH:MM group, not toLocaleString/toLocaleDateString, to keep jsdom tests deterministic across host timezones"
  - "Created column now routes through the same TimestampCell/formatTimestamp path as Started/Finished, unifying all three timestamp cells on one formatting function"

patterns-established:
  - "Fixed-width lib utilities (formatTimestamp) mirror runStatus.ts: pure function, module docstring citing the gap/requirement it closes, defensive fallback to raw input on unrecognized shape, never throws"

requirements-completed: [RUN-04]

coverage:
  - id: D1
    description: "formatTimestamp shortens ISO-8601 UTC timestamps (both +00:00-offset and Z-suffixed forms, including microsecond precision) to fixed-width 'YYYY-MM-DD HH:MM', with defensive fallback for unrecognized/empty input"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/lib/formatTimestamp.test.ts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Run History table's Created/Started/Finished cells render the short formatted timestamp (not the raw 32-char microsecond+offset string), with nullable started_at/finished_at still showing the muted '—' placeholder"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: timestamp formatting [gap G-03-1/RUN-04]"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-18
status: complete
---

# Phase 3 Plan 6: Fix Run History Timestamp Overflow (gap G-03-1) Summary

**Pure `formatTimestamp` utility shortens ISO-8601 UTC timestamps to fixed-width "YYYY-MM-DD HH:MM", wired into all three Run History table timestamp columns to close the column-overflow regression (RUN-04).**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-07-18T16:20:12Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- New `frontend/src/lib/formatTimestamp.ts` — deterministic, regex-based ISO timestamp shortener with a total (never-throw) fallback, unit-tested against the real 32-char microsecond+offset backend format, the Z-suffixed form, a fractional-second offset form, and unrecognized/empty input
- `RunHistoryTable`'s `TimestampCell` now renders `formatTimestamp(value)` instead of the raw ISO string; the Created column (previously rendering `{run.created_at}` verbatim) now routes through the same `TimestampCell` component as Started/Finished
- New regression test using the exact real backend timestamp shapes captured in the gap diagnosis, asserting the short form renders and the raw microsecond fraction/UTC offset never appear in the rendered table text
- Full frontend suite (181 tests, 29 files) and `tsc --noEmit` both pass with zero regressions

## Task Commits

Each task was committed atomically, following RED/GREEN TDD gates:

1. **Task 1: Add formatTimestamp utility**
   - `2eff8d5` (test) — failing test for formatTimestamp (RED)
   - `8bd0617` (feat) — formatTimestamp implementation (GREEN)
2. **Task 2: Route Run History timestamp cells through formatTimestamp**
   - `eba8883` (test) — failing regression test using the real 32-char backend format (RED)
   - `1074f28` (feat) — wired TimestampCell/Created column through formatTimestamp (GREEN)

_Note: both tasks are `tdd="true"`; each has a distinct test→feat commit pair as required._

## Files Created/Modified
- `frontend/src/lib/formatTimestamp.ts` - Pure `formatTimestamp(value: string): string` utility; regex-slices the leading `YYYY-MM-DDTHH:MM` from an ISO-8601 UTC timestamp, falls back to raw input on unrecognized shape
- `frontend/src/lib/formatTimestamp.test.ts` - 5 unit tests: real 32-char microsecond+offset format, Z-suffixed format, fractional-second offset, unrecognized input fallback, empty-string passthrough
- `frontend/src/components/runs/RunHistoryTable.tsx` - `TimestampCell` renders `formatTimestamp(value)`; Created cell now uses `<TimestampCell value={run.created_at} />` instead of raw `{run.created_at}`
- `frontend/src/components/runs/RunHistoryTable.test.tsx` - New `describe` block asserting the real backend timestamp format renders shortened with raw noise (`.702354`, `+00:00`) absent; all 11 pre-existing tests still pass unchanged

## Decisions Made
- Implemented `formatTimestamp` via regex slicing rather than `Date`/`toLocaleString` APIs, per the plan's explicit determinism requirement — avoids host-timezone-dependent jsdom test flakiness and avoids any instant-shifting, since the backend's leading date+time portion is already UTC wall-clock.
- Routed the Created column through the same `TimestampCell` component as Started/Finished (rather than calling `formatTimestamp` inline in three places), keeping one formatting path for all three columns as the plan specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The worktree's `frontend/node_modules` was missing (gitignored, not carried into `git worktree add`); a directory symlink to the main repo's already-installed `frontend/node_modules` was created (package-lock.json confirmed byte-identical) rather than running a fresh `npm install`, per the parallel-execution setup instructions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Gap G-03-1 (RUN-04) is closed: the Run History table's Created/Started/Finished columns render legibly within their fixed `w-[22%]` column widths for the real backend timestamp format, with no cell overflow or horizontal scroll. No blockers for downstream phases (ResultsView, Phase 4) — `formatTimestamp` is a general-purpose lib utility any future view rendering backend timestamps can reuse.

---
*Phase: 03-run-execution-history*
*Completed: 2026-07-18*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 5 commit hashes (2eff8d5, 8bd0617, eba8883, 1074f28, 8418e73) confirmed in `git log`.
