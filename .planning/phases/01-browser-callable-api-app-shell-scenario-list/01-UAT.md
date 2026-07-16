---
status: passed
phase: 01-browser-callable-api-app-shell-scenario-list
source: [01-VERIFICATION.md]
started: 2026-07-16T15:32:46Z
updated: 2026-07-16T15:45:00Z
---

## Current Test

number: (none — all 5 items resolved)
name: —
awaiting: none

## Tests

### 1. Real-browser DevTools CORS round trip
expected: |
  Run `cd backend && uv run uvicorn api.main:app --reload` and `cd frontend && npm run dev`.
  Open http://localhost:5173 in a real browser with DevTools open. Console shows no CORS
  error; Network tab shows GET /scenarios as a genuine cross-origin request that succeeds
  (status 200, access-control-allow-origin header present).
result: [pass] — user confirmed CORS works in a real browser.

### 2. Live create-scenario round trip
expected: |
  With both servers running, click "New scenario", enter a name, pick a backend-offered
  fixture, submit. The dialog closes and the new scenario appears as a new row in the table
  without a manual page refresh (react-query invalidation refetch).
result: [pass] — user confirmed create-scenario worked (new row appeared).

### 3. Visual backstop — long scenario name
expected: |
  Type a 200+ character scenario name into the Name field of the create dialog. It renders
  acceptably (wraps or scrolls) and does not break the modal layout.
result: |
  [pass-after-fix] — Originally FAILED: a long name widened the table and forced the whole
  grid into horizontal scroll. Fixed in ScenarioTable.tsx (table-fixed layout + `truncate`
  on the name/fixture cells + `title` for the full value on hover). Re-verified in a real
  browser: long names truncate with an ellipsis, the Fixture/Created columns stay visible,
  and there is no horizontal scroll.

### 4. Visual backstop — long fixture filename
expected: |
  Select or view a fixture with a long filename in the fixture Select's trigger and option
  list. It renders acceptably (truncates or wraps) and does not overflow the trigger or list.
result: |
  [pass-after-fix] — Originally FAILED: a long fixture name blew out the create-dialog width.
  Fixed in CreateScenarioDialog.tsx (`min-w-0` on the form / fixture-field / Select trigger so
  the trigger's built-in line-clamp can take effect; `truncate` on the option text). Re-verified
  in a real browser: the long fixture truncates with an ellipsis inside the trigger and the
  dialog keeps its normal centered width.

### 5. Concurrent failure with backend down — single banner
expected: |
  Stop the backend process, then load Home so both the scenarios and fixtures queries fail
  concurrently. Exactly one backend-unreachable ErrorBanner is visible on the page, not two.
result: [pass] — user confirmed exactly one banner.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

Two visual gaps found during UAT (tests 3 and 4) were fixed and re-verified in a real browser
during the same session — no outstanding gaps remain:

- Long scenario name forced horizontal table scroll → fixed (table-fixed + truncate). ScenarioTable.tsx.
- Long fixture name overflowed the create dialog → fixed (min-w-0 + truncate). CreateScenarioDialog.tsx.
