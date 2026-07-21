---
phase: quick-260721-0to
plan: 01
subsystem: ui
tags: [react, vitest, error-handling, information-disclosure]
requires: []
provides:
  - Shared fixed product copy for connection, crash, and run failures
  - App-level error surfaces that keep diagnostic objects out of rendered UI
  - Failed-run views that never render persisted backend exceptions
affects: [frontend-errors, run-history, results]
tech-stack:
  added: []
  patterns:
    - Diagnostic errors may be logged or persisted but never used as JSX input
    - User-facing app failures reuse typed USER_ERROR_COPY values
key-files:
  created: []
  modified:
    - frontend/src/lib/errors.ts
    - frontend/src/components/layout/ErrorBanner.tsx
    - frontend/src/components/layout/ErrorBanner.test.tsx
    - frontend/src/components/layout/RootErrorBoundary.tsx
    - frontend/src/routes/router.test.tsx
    - frontend/src/components/editor/OverridesList.test.tsx
    - frontend/src/components/editor/ScenarioHeader.test.tsx
    - frontend/src/components/scenarios/ScenarioTable.test.tsx
    - frontend/src/components/scenarios/CreateScenarioDialog.test.tsx
    - frontend/src/routes/ResultsView.tsx
    - frontend/src/routes/ResultsView.test.tsx
    - frontend/src/components/runs/RunHistoryTable.tsx
    - frontend/src/components/runs/RunHistoryTable.test.tsx
    - frontend/src/routes/RunHistory.test.tsx
key-decisions:
  - "Treat backend/runtime diagnostics as non-display data and render only fixed product copy."
  - "Keep console logging and persisted RunOut.error unchanged for developer/operator diagnosis."
patterns-established:
  - "UI/diagnostic boundary: error objects may reach console logging, never JSX."
  - "Safe-by-default run failures: rendered copy is independent of RunOut.error content or presence."
requirements-completed: []
coverage:
  - id: D1
    description: "Connection and root crash fallbacks render neutral retry/reload guidance without commands, paths, exception text, or developer-tool instructions."
    verification:
      - kind: integration
        ref: "frontend/src/components/layout/ErrorBanner.test.tsx and frontend/src/routes/router.test.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "Results and run-history failed states reuse generic product copy and never render RunOut.error for populated, empty, or null diagnostics."
    verification:
      - kind: integration
        ref: "frontend/src/routes/ResultsView.test.tsx and frontend/src/components/runs/RunHistoryTable.test.tsx"
        status: pass
    human_judgment: false
duration: 20min active
completed: 2026-07-21
status: complete
---

# Quick Task 260721-0to: Prevent Backend Diagnostics in Frontend Summary

**Typed shared product copy now shields connection, crash, and failed-run UI from backend commands, paths, stack traces, and persisted exception messages.**

## Performance

- **Duration:** 20 min active execution
- **Started:** 2026-07-21T00:46:00+07:00
- **Completed:** 2026-07-21T01:07:00+07:00
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments

- Replaced the reported Uvicorn/backend remediation with concise retry/reload product copy shared from `USER_ERROR_COPY`.
- Kept caught error objects available through `console.error` while proving diagnostic-rich inputs never enter the ErrorBanner or root-boundary DOM.
- Removed `RunOut.error` from both failed-run render paths and covered populated, empty, null, and HTML-shaped diagnostic values.
- Audited related frontend error paths; API errors remain thrown into fixed-copy consumers, trigger-run errors use fixed status-based copy, and transcript rejection text remains intentional user-actionable domain feedback.

## Task Commits

1. **Task 1: Replace developer-oriented app error instructions with safe product copy** — `1869317` (`fix(quick-260721-0to): hide app error diagnostics`)
2. **Task 2: Stop failed-run views from rendering persisted backend exceptions** — `d4638e2` (`fix(quick-260721-0to): hide failed-run diagnostics`)

## Files Created/Modified

- `frontend/src/lib/errors.ts` — owns typed connection, unexpected-crash, and run-failure copy.
- `frontend/src/components/layout/ErrorBanner.tsx` — renders fixed connection copy while retaining console diagnostics.
- `frontend/src/components/layout/ErrorBanner.test.tsx` — rejects commands, backend paths, stack traces, and exception text in the DOM.
- `frontend/src/components/layout/RootErrorBoundary.tsx` — renders neutral crash guidance while retaining console diagnostics.
- `frontend/src/routes/router.test.tsx` — verifies route/render exceptions and browser-console guidance are absent.
- `frontend/src/components/editor/OverridesList.test.tsx` — expects safe shared copy from the composed ErrorBanner.
- `frontend/src/components/editor/ScenarioHeader.test.tsx` — expects safe shared copy for non-404 query failures.
- `frontend/src/components/scenarios/ScenarioTable.test.tsx` — expects safe shared copy without stale rows.
- `frontend/src/components/scenarios/CreateScenarioDialog.test.tsx` — preserves single-banner concurrency assertions using safe copy.
- `frontend/src/routes/ResultsView.tsx` — renders fixed failed-run copy independent of `RunOut.error`.
- `frontend/src/routes/ResultsView.test.tsx` — covers diagnostic-rich, null, and empty failed-run errors.
- `frontend/src/components/runs/RunHistoryTable.tsx` — renders the same fixed failed-run copy in history rows.
- `frontend/src/components/runs/RunHistoryTable.test.tsx` — covers diagnostic-rich, null, empty, and HTML-shaped failed-run errors.
- `frontend/src/routes/RunHistory.test.tsx` — verifies the composed route suppresses persisted solver errors.

## Decisions Made

- Centralized all three app-level failure messages in a typed constant so future copy changes cannot reintroduce message-derived rendering at these surfaces.
- Left backend persistence and API schema untouched; diagnostics remain available to operators without exposing them to end users.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated composing-component regression expectations**
- **Found during:** Full frontend test suite after both planned tasks
- **Issue:** Six tests that compose `ErrorBanner` and one route-level run-history test still asserted the retired API-specific or raw backend text.
- **Fix:** Updated those existing tests to assert the shared safe copy and, for run history, explicitly assert the persisted solver error is absent.
- **Files modified:** `OverridesList.test.tsx`, `ScenarioHeader.test.tsx`, `ScenarioTable.test.tsx`, `CreateScenarioDialog.test.tsx`, `RunHistory.test.tsx`
- **Commits:** `1869317`, `d4638e2`

## Issues Encountered

- Git could not create `.git/index.lock` under the executor sandbox (`Permission denied`), so the orchestrator created the two verified atomic commits with repository write permission.
- Lint completed successfully with four pre-existing Fast Refresh warnings in unrelated files (`tabs.tsx`, `DemandVsServedChart.tsx`, `button.tsx`, and `App.tsx`).

## Verification

- Full Vitest suite: **239 passed** across 42 files.
- TypeScript: `tsc --noEmit` passed.
- Lint: `oxlint` passed with only the four pre-existing warnings noted above.
- Source audit: no remaining production render of Uvicorn commands, browser-console instructions, or `RunOut.error`; remaining matches are API throw sites, fixed-copy props, comments, and intentional constraint rejection feedback.

## Known Stubs

None.

## Threat Surface

No new network, authentication, file-access, or schema surface was introduced. The existing backend-to-UI trust boundary is reduced by removing diagnostic data from JSX inputs.

## User Setup Required

None.

## Self-Check: PASSED

- All 14 implementation and regression-test files exist and contain the verified changes.
- Atomic task commits `1869317` and `d4638e2` exist.
- The required summary exists with `status: complete`.
- No unexpected file deletions or whitespace errors were found.

---
*Quick task: 260721-0to*
*Completed: 2026-07-21*
