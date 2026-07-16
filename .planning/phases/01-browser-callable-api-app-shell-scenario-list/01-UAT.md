---
status: testing
phase: 01-browser-callable-api-app-shell-scenario-list
source: [01-VERIFICATION.md]
started: 2026-07-16T15:32:46Z
updated: 2026-07-16T15:32:46Z
---

## Current Test

number: 1
name: Real-browser DevTools CORS round trip
expected: |
  With the backend running at http://127.0.0.1:8000 and the frontend dev server at
  http://localhost:5173, opening the app in a real browser loads the scenario list with
  no CORS error in the console, and the Network tab shows the cross-origin GET /scenarios
  request completing with status 200 and an access-control-allow-origin header present.
awaiting: user response

## Tests

### 1. Real-browser DevTools CORS round trip
expected: |
  Run `cd backend && uv run uvicorn api.main:app --reload` and `cd frontend && npm run dev`.
  Open http://localhost:5173 in a real browser with DevTools open. Console shows no CORS
  error; Network tab shows GET /scenarios as a genuine cross-origin request that succeeds
  (status 200, access-control-allow-origin header present).
result: [pending]
why_human: Backend CORS is fully proven by backend/tests/test_cors.py (13/13) and curl; a browser's actual CORS enforcement/reporting is not observable from pytest or jsdom.

### 2. Live create-scenario round trip
expected: |
  With both servers running, click "New scenario", enter a name, pick a backend-offered
  fixture, submit. The dialog closes and the new scenario appears as a new row in the table
  without a manual page refresh (react-query invalidation refetch).
result: [pending]
why_human: The invalidate-on-success contract is proven by unit test against a mocked API boundary (CreateScenarioDialog.test.tsx), but a live network round trip against a real backend was not exercised.

### 3. Visual backstop — long scenario name
expected: |
  Type a 200+ character scenario name into the Name field of the create dialog. It renders
  acceptably (wraps or scrolls) and does not break the modal layout.
result: [pending]
why_human: Declared `verification: backstop` in 01-07-PLAN.md — a visual check with no assertable spec-time width, deferred to execution-time human judgment.

### 4. Visual backstop — long fixture filename
expected: |
  Select or view a fixture with a long filename in the fixture Select's trigger and option
  list. It renders acceptably (truncates or wraps) and does not overflow the trigger or list.
result: [pending]
why_human: Declared `verification: backstop` in 01-07-PLAN.md — same reasoning as test 3.

### 5. Concurrent failure with backend down — single banner
expected: |
  Stop the backend process, then load Home so both the scenarios and fixtures queries fail
  concurrently. Exactly one backend-unreachable ErrorBanner is visible on the page, not two.
result: [pending]
why_human: The single-banner decision logic (Home.tsx: showFixturesOnlyBanner = fixturesQuery.isError && !scenariosQuery.isError) is unit-tested with mocked rejections, but a live check with the backend actually stopped was not performed.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
