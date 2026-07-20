---
status: testing
phase: 04-results-insights
source: [04-VERIFICATION.md]
started: 2026-07-20T03:07:47Z
updated: 2026-07-20T03:07:47Z
---

## Current Test

number: 1
name: End-of-phase visual/interactive walkthrough of ResultsView
expected: |
  Run `npm run dev` in `frontend/`, trigger a scenario run to COMPLETED, open
  `/scenarios/{id}/runs/{runId}` and confirm: (1) coverage stat cards +
  warnings banner (if any) + by-day table render; (2) the demand-vs-served
  chart renders with visible grouped bars (not blank/0-height); (3) the
  schedule table scrolls with "Day N, HH:MM-HH:MM" windows whose day numbers
  match the by-day table; (4) "Get Insight Report" fetches a report or an
  honest not-ready/error state; (5) deep-linking a PENDING/RUNNING run shows
  the in-flight panel and a FAILED run shows its error — never a blank
  screen.
awaiting: user response

## Tests

### 1. End-of-phase visual/interactive walkthrough of ResultsView
expected: |
  Run `npm run dev` in `frontend/`, trigger a scenario run to COMPLETED, open
  `/scenarios/{id}/runs/{runId}` and confirm: (1) coverage stat cards +
  warnings banner (if any) + by-day table render; (2) the demand-vs-served
  chart renders with visible grouped bars (not blank/0-height); (3) the
  schedule table scrolls with "Day N, HH:MM-HH:MM" windows whose day numbers
  match the by-day table; (4) "Get Insight Report" fetches a report or an
  honest not-ready/error state; (5) deep-linking a PENDING/RUNNING run shows
  the in-flight panel and a FAILED run shows its error — never a blank
  screen.
result: [pending]

### 2. Long warning string layout (WarningsBanner)
expected: |
  Trigger a run producing a very long warning string; view the results page.
  Text wraps without breaking page layout (no horizontal overflow).
result: [pending]

### 3. Empty coverage_by_day on a COMPLETED run
expected: |
  Observe a COMPLETED run whose coverage_by_day is empty (if reachable).
  Renders an honest empty/absent state, not a broken or misleading render.
result: [pending]

### 4. Empty coverage_by_function on a COMPLETED run
expected: |
  Observe a COMPLETED run whose coverage_by_function is empty (if reachable).
  Renders an honest empty/absent chart state.
result: [pending]

### 5. Long insight report layout (InsightPanel)
expected: |
  Fetch a very long LLM-generated insight report. Report text wraps/scrolls
  within the insight section without breaking page layout.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
