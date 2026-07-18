---
status: diagnosed
phase: 03-run-execution-history
source: [03-VERIFICATION.md]
started: 2026-07-18T20:35:00Z
updated: 2026-07-19T02:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Start the backend (`uvicorn api.main:app --reload`) and the frontend (`npm run dev`). Open a scenario's Runs tab and click 'Run Scenario'.
expected: A new run appears immediately as 'Queued' with no manual refresh (RUN-01); the button then disables with 'A run is already in progress for this scenario.'; the in-flight panel shows the honest 'Solving…' / multi-minute / cannot-be-cancelled copy with NO cancel button and NO progress bar (RUN-03); the run advances to 'Completed' on its own without a manual refresh (RUN-02); reloading mid-flight resumes state from polling; prior runs list with created/started/finished timing (RUN-04); a deep link to /scenarios/<bogus-id>/runs shows the ordinary 'No runs yet' empty state, not a 'Scenario not found' gate; a FAILED run (if available) shows its error text inline and wraps without breaking table columns (RUN-05).
result: issue
reported: "the run status layout is broken due to the time format is long"
severity: major

## Summary

total: 1
passed: 0
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-03-1
  truth: "Prior runs list shows created/started/finished timing legibly, within the table's fixed column widths, without breaking layout (RUN-04)"
  status: failed
  reason: "User reported: the run status layout is broken due to the time format is long"
  severity: major
  test: 1
  root_cause: "RunHistoryTable.tsx renders created_at/started_at/finished_at verbatim (no formatting) inside whitespace-nowrap cells within a table-fixed layout with w-[22%] column widths. The backend's _now() emits full microsecond+UTC-offset ISO-8601 strings (e.g. 2026-07-18T15:53:53.702354+00:00, 32 chars) which overflow the 22%-wide cells and force the whole table into horizontal scroll (overflow-y-auto promotes overflow-x to auto per CSS spec once content overflows). No timestamp-formatting utility exists in frontend/src, and RunHistoryTable.test.tsx's fixtures use short Z-suffixed timestamps that never modeled the real 32-char length — so no existing test caught it."
  artifacts:
    - path: "frontend/src/components/runs/RunHistoryTable.tsx"
      issue: "TimestampCell (lines ~47-52) passes non-null timestamp values through unformatted; Created/Started/Finished cells (lines ~138-146) are whitespace-nowrap inside table-fixed w-[22%] columns (lines ~107-114); wrapper div (line ~106) sets overflow-y-auto only"
    - path: "frontend/src/components/runs/RunHistoryTable.test.tsx"
      issue: "All timestamp fixtures use short Z-suffixed strings (e.g. 2026-07-18T10:00:00Z), never the real 32-char microsecond+offset format the backend actually emits"
  missing:
    - "Format the displayed timestamp in TimestampCell to a shorter, fixed-width representation instead of rendering the raw ISO string verbatim"
    - "Add a RunHistoryTable.test.tsx fixture using the real 32-character microsecond+offset timestamp format to lock in the fix"
  debug_session: ".planning/debug/run-status-layout-broken-time.md"
