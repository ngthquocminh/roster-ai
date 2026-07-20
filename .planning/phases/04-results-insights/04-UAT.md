---
status: resolved
phase: 04-results-insights
source: [04-VERIFICATION.md]
started: 2026-07-20T03:07:47Z
updated: 2026-07-20T05:24:00Z
---

## Current Test

[testing complete]

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
result: pass
verified_by: claude-in-chrome (automated, by user request) against a live
  backend (uv run uvicorn) + frontend (vite dev) with a real triggered run
  (sample_tiny_input.json). Observed directly: coverage cards + by-day table
  render with correct percentages (61.2%, 49.9%, ... confirms the earlier
  CoverageByDayTable fix live); chart renders visible grouped bars
  (Despatch/Pick/Putaways/Receiving); schedule table scrolls internally with
  "Day N, HH:MM-HH:MM" rows matching the by-day table's day range (1-7);
  clicked "Get Insight Report" twice (fresh page load + in-session) and both
  times a real report rendered with zero browser console errors; deep-linking
  the run while RUNNING showed the in-flight "Solving..." panel correctly.
  FAILED-run deep-link was not independently re-driven live (no simple way to
  force a solver failure via the API) — that branch remains covered by
  ResultsView.test.tsx's existing FAILED integration tests (VERIFICATION.md
  items 20-21), not re-verified in the browser this session.
note: |
  No warnings banner appeared because this run produced zero warnings — this
  is correct (WarningsBanner returns null for an empty array) but means test
  1 did not exercise the warnings banner's rendering path; test 2 below
  covers that.

### 2. Long warning string layout (WarningsBanner)
expected: |
  Trigger a run producing a very long warning string; view the results page.
  Text wraps without breaking page layout (no horizontal overflow).
result: pass
verified_by: claude-in-chrome (automated). Traced the backend's degenerate-solve
  warning trigger (backend/engine/cpsat/engine.py:115-122 — a function with
  required hours but zero served hours), built a throwaway fixture (deleted
  after this test) renaming the "Receiving" function to a 147-char name and
  stripping its 3 qualifying Team Member Qualification rows so it goes fully
  unserved, then ran it for real. Backend produced the expected 175-char
  warning string verbatim. Confirmed via direct DOM measurement (not just a
  screenshot): document.documentElement.scrollWidth === clientWidth (1680 ===
  1680, zero page-level horizontal overflow); the warning <p> itself does not
  overflow its own box (scrollWidth ~= clientWidth); computed CSS confirms
  white-space: normal + overflow-wrap: break-word, which guarantees safety
  even for a single unbroken long word, not just this hyphenated string.

### 3. Empty coverage_by_day on a COMPLETED run
expected: |
  Observe a COMPLETED run whose coverage_by_day is empty (if reachable).
  Renders an honest empty/absent state, not a broken or misleading render.
result: pass
verified_by: claude-in-chrome (automated). Reachability confirmed real:
  built a throwaway fixture (deleted after this test) with all demand
  sections (Outbound Workload, Inbound Workload, Indirect Workforce
  Requirement) emptied, ran it for real, backend genuinely returned
  coverage_by_day: {}. CoverageByDayTable renders its header row ("Day |
  Coverage %") with zero body rows (confirmed via DOM: 0 tbody rows) — no
  crash, no misleading data. Judged acceptable as a defensible header-only
  empty-table convention.

### 4. Empty coverage_by_function on a COMPLETED run
expected: |
  Observe a COMPLETED run whose coverage_by_function is empty (if reachable).
  Renders an honest empty/absent chart state.
result: issue
reported: "Confirmed reachable with the same zero-demand fixture as test 3
  (coverage_by_function: {} genuinely returned by the backend). Verified in
  browser: DemandVsServedChart renders a completely blank box — empty axes,
  no bars, no category labels, no text of any kind. No crash, no console
  error, no layout overflow — but no message either, so a user cannot tell
  'no demand for this run' from 'broken/still loading'. Component source
  (DemandVsServedChart.tsx) confirmed: no empty-state branch exists: `data`
  becomes `[]` and Recharts silently draws nothing."
severity: minor

### 5. Long insight report layout (InsightPanel)
expected: |
  Fetch a very long LLM-generated insight report. Report text wraps/scrolls
  within the insight section without breaking page layout.
result: pass
verified_by: claude-in-chrome (automated). Discovered a real, confirmed bug
  during verification and fixed it immediately (by user request, not routed
  through gap-closure): InsightPanel.tsx's ready-state report <p> had
  whitespace-pre-wrap but no overflow-wrap/break-words (unlike this same
  component's error-path AlertDescription a few lines above, which already
  had it). Proved exploitability via live DOM injection: a 300-char unbroken
  token in the rendered element measurably overflowed the document
  (scrollWidth 2846 vs clientWidth 1680). Fixed by adding break-words
  (commit 2a243f0), matching the existing error-path convention; added a
  regression test asserting the class on the rendered element. Re-verified
  post-fix: 236/236 tests pass, clean build. Also noted in passing: the
  backend is actually running a real LLM provider (not the keyless "stub"
  default) — reports came back as full markdown tables, not the stub's
  plain bullet-line format. Not a phase-04 concern, just an observation.

## Summary

total: 5
passed: 4
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-04-4
  truth: "DemandVsServedChart renders an honest empty/absent chart state when coverage_by_function is empty"
  status: resolved
  resolved_by: 04-08-PLAN.md
  reason: "User (via Claude-driven verification) confirmed: chart renders a completely blank box (no bars, no axis labels, no text) with no way to distinguish 'no demand for this run' from broken/loading, against a real zero-demand run"
  severity: minor
  test: 4
  root_cause: "frontend/src/components/results/DemandVsServedChart.tsx has no empty-data branch. toChartData(coverage_by_function) returns [] when the input is {}; that [] is passed straight to Recharts' BarChart, which silently renders empty axes with zero bars and zero category labels — no conditional check for data.length === 0 exists anywhere in the component. Contrast with ScheduleTable.tsx and CoverageByDayTable's sibling components in this same phase, which do have explicit empty-state handling (ScheduleTable renders \"No shifts were scheduled for this run.\"; CoverageByDayTable at least renders its header row)."
  artifacts:
    - path: "frontend/src/components/results/DemandVsServedChart.tsx"
      issue: "No empty-state branch before the ChartContainer/BarChart render; needs an `if (data.length === 0) return <emptyState/>` (or equivalent) guard analogous to ScheduleTable.tsx's empty-state pattern"
  missing:
    - "An explicit empty-state message (e.g. \"No coverage data for this run.\") rendered instead of an empty BarChart when coverage_by_function is {}"
    - "A test asserting the empty-state message renders when coverage_by_function is {} (mirrors ScheduleTable.test.tsx's existing empty-state test)"
  debug_session: ""
