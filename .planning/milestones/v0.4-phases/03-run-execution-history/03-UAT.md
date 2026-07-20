---
status: complete
phase: 03-run-execution-history
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md, 03-05-SUMMARY.md, 03-06-SUMMARY.md]
started: 2026-07-19T09:20:00Z
updated: 2026-07-19T09:40:00Z
---

## Current Test

[testing complete]

## Tests

### 1. End-to-end run lifecycle walkthrough
expected: |
  Start the backend (`uvicorn api.main:app --reload`) and the frontend (`npm run dev`). Open a scenario's Runs tab.

  Click the header "Run Scenario" button. A new run appears immediately as "Queued" with no manual refresh (RUN-01). The header button disables while the run is in progress; if the table's empty-state "Run Scenario" button was visible before triggering, it is disabled too — clicking either repeatedly should not fire duplicate run requests (RUN-01, RUN-03).

  The in-flight panel shows the honest "Solving…" / multi-minute copy with NO cancel button and NO progress bar (RUN-03). The run advances to "Completed" (or "Failed") on its own without a manual refresh (RUN-02). Reloading mid-flight resumes state from polling.

  Prior runs list with Created/Started/Finished timing, now shown as a short fixed-width timestamp (e.g. "2026-07-19 09:20") instead of the raw microsecond+offset string — no cell overflow, no whole-table horizontal scroll (RUN-04, retest of gap G-03-1).

  A deep link to /scenarios/<bogus-id>/runs shows the ordinary "No runs yet" empty state, not a "Scenario not found" gate.

  A FAILED run (if available) shows its error text inline, wrapping without breaking table columns (RUN-05).
result: pass
coverage_id: D6 (03-05)

### 2. FAILED run — long error text wrap
expected: A run that fails with a long or multi-line error message wraps the error text inside its table cell instead of breaking the table's fixed column widths or forcing horizontal scroll.
result: pass
coverage_id: D9 (03-03)

### 3. listRuns/triggerRun typed API wrappers
expected: listRuns(scenarioId) issues typed GET /scenarios/{scenario_id}/runs through the shared client and returns RunOut[]; throws { status, ...error } on non-2xx
result: pass
source: automated
coverage_id: D1 (03-01)

### 4. triggerRun typed POST wrapper
expected: triggerRun(scenarioId) issues typed POST /scenarios/{scenario_id}/runs and returns the created PENDING RunOut; throws { status, ...error } on non-2xx (404 case included)
result: pass
source: automated
coverage_id: D2 (03-01)

### 5. runStatusMeta label/icon/color mapping
expected: runStatusMeta maps all four RunOut statuses to the exact UI-SPEC label/icon/color, with spin only on RUNNING, and falls back to a neutral Clock + raw-string label for unrecognized statuses
result: pass
source: automated
coverage_id: D3 (03-01)

### 6. Terminal/active run predicates
expected: isTerminalStatus/hasActiveRun/newestActiveRun terminal/active predicates, including empty-list, all-terminal, and newest-first-no-resort behavior
result: pass
source: automated
coverage_id: D4 (03-01)

### 7. useRuns self-terminating poll
expected: useRuns polls GET /scenarios/{id}/runs under ["runs", scenarioId] and self-terminates the poll once every run is terminal (or the list is empty)
result: pass
source: automated
coverage_id: D1 (03-02)

### 8. useTriggerRun invalidation
expected: useTriggerRun triggers a run and invalidates exactly ["runs", scenarioId] on success so the new PENDING run appears immediately; errors propagate intact
result: pass
source: automated
coverage_id: D2 (03-02)

### 9. RunStatusLabel status mappings
expected: RunStatusLabel renders the four run-status icon+text mappings (Queued/Running/Completed/Failed) with an honest fallback for unknown statuses, and never imports a Badge component
result: pass
source: automated
coverage_id: D1 (03-03)

### 10. RunHistoryTable newest-first rendering
expected: RunHistoryTable renders every run for a scenario newest-first (server order, no client re-sort) with Status/Created/Started/Finished columns, keyed by run.id
result: pass
source: automated
coverage_id: D2 (03-03)

### 11. RunHistoryTable loading/error/empty states
expected: RunHistoryTable's loading/error/empty states mirror ScenarioTable/OverridesList (centered spinner, ErrorBanner, "No runs yet" + inline Run Scenario button)
result: pass
source: automated
coverage_id: D3 (03-03)

### 12. Nullable timestamp placeholder
expected: Nullable started_at/finished_at render a "—" placeholder rather than a blank or broken cell
result: pass
source: automated
coverage_id: D4 (03-03)

### 13. FAILED row inline error text
expected: A FAILED row renders run.error verbatim beneath the Failed label; a null error renders the defensive "Failed — no error details were recorded." fallback
result: pass
source: automated
coverage_id: D5 (03-03)

### 14. solver_status never leaks into DOM
expected: A COMPLETED run with solver_status UNKNOWN still renders "Completed"; solver_status is never present in the rendered DOM
result: pass
source: automated
coverage_id: D6 (03-03)

### 15. Error text renders as literal text (XSS)
expected: run.error and all cell text render only as JSX text children — an HTML-looking error string renders as literal text with no element created from it (T-3-05 XSS mitigation)
result: pass
source: automated
coverage_id: D7 (03-03)

### 16. Row click/keyboard navigation
expected: One run renders identical chrome to many (no row-count label); row click/Enter/Space navigates to /scenarios/:scenarioId/runs/:runId
result: pass
source: automated
coverage_id: D8 (03-03)

### 17. TriggerRunButton state coverage
expected: TriggerRunButton covers idle/loading-initial/submitting/in-progress/error-404/error-other states, calls onTrigger once on click, and renders no cancel control or progressbar in any state
result: pass
source: automated
coverage_id: D1 (03-04)

### 18. RunInFlightPanel honest copy
expected: RunInFlightPanel renders the honest PENDING "Queued"/RUNNING "Solving…" copy verbatim, renders nothing for null or terminal-status runs, and offers no cancel control or progressbar
result: pass
source: automated
coverage_id: D2 (03-04)

### 19. RunHistory composition — trigger wiring
expected: RunHistory composes one useRuns + one useTriggerRun pair, deriving the table rows, in-flight panel's active run, and button's disabled state from a single list response
result: pass
source: automated
coverage_id: D1 (03-05)

### 20. RunHistory composition — in-flight panel visibility
expected: An active RUNNING/PENDING run shows the in-flight panel; an all-terminal list shows no panel, derived from the same list
result: pass
source: automated
coverage_id: D2 (03-05)

### 21. RunHistory composition — button disable honesty
expected: TriggerRunButton disables while a run is in progress, derived from the same useRuns list (RUN-03 honesty — no cancel affordance anywhere in the composed view)
result: pass
source: automated
coverage_id: D3 (03-05)

### 22. RunHistory composition — prior runs render
expected: Prior runs (including a FAILED run with its error text) render in RunHistoryTable within the composed view
result: pass
source: automated
coverage_id: D4 (03-05)

### 23. Router mounts real RunHistory view
expected: App.tsx's "runs" route mounts the real RunHistory view in place of RunsPlaceholder; "runs/:runId" is unchanged; the disabled Results tab and ScenarioLayout are untouched
result: pass
source: automated
coverage_id: D5 (03-05)

### 24. formatTimestamp shortens ISO timestamps
expected: formatTimestamp shortens ISO-8601 UTC timestamps (both +00:00-offset and Z-suffixed forms, including microsecond precision) to fixed-width "YYYY-MM-DD HH:MM", with defensive fallback for unrecognized/empty input
result: pass
source: automated
coverage_id: D1 (03-06)

### 25. RunHistoryTable renders short formatted timestamps
expected: Run History table's Created/Started/Finished cells render the short formatted timestamp (not the raw 32-char microsecond+offset string), with nullable started_at/finished_at still showing the muted "—" placeholder
result: pass
source: automated
coverage_id: D2 (03-06)

## Summary

total: 25
passed: 25
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-03-1
  truth: "Prior runs list shows created/started/finished timing legibly, within the table's fixed column widths, without breaking layout (RUN-04)"
  status: resolved
  resolved_by: 03-06-PLAN.md
  resolved_at: 2026-07-19
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
