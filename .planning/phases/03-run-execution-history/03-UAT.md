---
status: testing
phase: 03-run-execution-history
source: [03-VERIFICATION.md]
started: 2026-07-18T20:35:00Z
updated: 2026-07-18T20:35:00Z
---

## Current Test

number: 1
name: Start the backend (`uvicorn api.main:app --reload`) and the frontend (`npm run dev`). Open a scenario's Runs tab and click 'Run Scenario'.
expected: |
  A new run appears immediately as 'Queued' with no manual refresh (RUN-01); the button then disables with 'A run is already in progress for this scenario.'; the in-flight panel shows the honest 'Solving…' / multi-minute / cannot-be-cancelled copy with NO cancel button and NO progress bar (RUN-03); the run advances to 'Completed' on its own without a manual refresh (RUN-02); reloading mid-flight resumes state from polling; prior runs list with created/started/finished timing (RUN-04); a deep link to /scenarios/<bogus-id>/runs shows the ordinary 'No runs yet' empty state, not a 'Scenario not found' gate; a FAILED run (if available) shows its error text inline and wraps without breaking table columns (RUN-05).
awaiting: user response

## Tests

### 1. Start the backend (`uvicorn api.main:app --reload`) and the frontend (`npm run dev`). Open a scenario's Runs tab and click 'Run Scenario'.
expected: A new run appears immediately as 'Queued' with no manual refresh (RUN-01); the button then disables with 'A run is already in progress for this scenario.'; the in-flight panel shows the honest 'Solving…' / multi-minute / cannot-be-cancelled copy with NO cancel button and NO progress bar (RUN-03); the run advances to 'Completed' on its own without a manual refresh (RUN-02); reloading mid-flight resumes state from polling; prior runs list with created/started/finished timing (RUN-04); a deep link to /scenarios/<bogus-id>/runs shows the ordinary 'No runs yet' empty state, not a 'Scenario not found' gate; a FAILED run (if available) shows its error text inline and wraps without breaking table columns (RUN-05).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
