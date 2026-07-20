---
phase: 04-results-insights
plan: 06
subsystem: ui
tags: [react, tanstack-query, useMutation, insight-report, RES-04, RES-05]

# Dependency graph
requires:
  - phase: 04-results-insights (plan 04-03)
    provides: useRunInsights mutation hook (isolated, no cache invalidation) + insights.ts api wrapper
provides:
  - InsightPanel.tsx — button-triggered five-state insight report panel (idle/pending/error/not-ready/ready)
  - InsightPanel.test.tsx — coverage of all five states, the ready-not-status guard, and the 502 retry
affects: [04-07 (ResultsView composes InsightPanel as the bottom section)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mutation-driven five-state render branch (isIdle/isPending/isError/data.ready) composed from RunInFlightPanel's Alert shape + ErrorBanner's distinct-error-styling precedent"

key-files:
  created:
    - frontend/src/components/results/InsightPanel.tsx
    - frontend/src/components/results/InsightPanel.test.tsx
  modified: []

key-decisions:
  - "Error-state 'Try Again' button uses the outline variant (not destructive) — the Alert above it already carries the destructive-styled error copy; the button itself is a neutral retry affordance, consistent with D-13's 'calm rather than punitive' framing."
  - "Not-ready state renders as a plain <p>, not an Alert — reinforcing structurally (not just by copy) that ready:false is a normal state, not an error condition."

patterns-established:
  - "InsightPanel state-branch pattern: exactly one of five JSX blocks renders per mutation lifecycle state, keyed off useMutation's isIdle/isPending/isError/isSuccess + data.ready — never response.status."

requirements-completed: [RES-04, RES-05]

coverage:
  - id: D1
    description: "InsightPanel idle state shows heading, body copy, and 'Get Insight Report' button; never auto-fetches on mount"
    requirement: RES-04
    verification:
      - kind: unit
        ref: "frontend/src/components/results/InsightPanel.test.tsx#InsightPanel: idle [UI-SPEC E7/empty] > shows the 'Get Insight Report' button before any click"
        status: pass
    human_judgment: false
  - id: D2
    description: "Success branch reads data.ready (never response.status) to distinguish ready vs not-ready — a ready:false 200 renders the honest fallback copy with zero destructive/alert styling"
    requirement: RES-04
    verification:
      - kind: unit
        ref: "frontend/src/components/results/InsightPanel.test.tsx#InsightPanel: not-ready [UI-SPEC E7/edge, RES-04 guard] > renders the not-ready copy and shows NO destructive/error styling"
        status: pass
      - kind: unit
        ref: "frontend/src/components/results/InsightPanel.test.tsx#InsightPanel: ready [UI-SPEC E7/populated, RES-04] > renders the report text after a { ready:true, report } resolution"
        status: pass
    human_judgment: false
  - id: D3
    description: "A 502 renders a distinct destructive-styled inline Alert plus a re-enabled 'Try Again' button that re-invokes the mutation (D-13 retry)"
    requirement: RES-05
    verification:
      - kind: unit
        ref: "frontend/src/components/results/InsightPanel.test.tsx#InsightPanel: error [UI-SPEC E7/error, D-13] > renders the 502 error copy plus a re-enabled Try Again button, and a second click re-invokes the fetch (retry)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The LLM report string renders as a plain JSX text child (whitespace-pre-wrap) only — no dangerouslySetInnerHTML sink"
    requirement: RES-04
    verification:
      - kind: unit
        ref: "grep -c dangerouslySetInnerHTML frontend/src/components/results/InsightPanel.tsx (returns 0)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A very long insight report wraps/scrolls within the insight section without breaking the page layout"
    verification: []
    human_judgment: true
    rationale: "Visual backstop only, unverifiable at spec time — same backstop class as Phase 3's FAILED-error long-text and E2's warnings long-text; requires a human to eyeball the rendered layout with a long report string."

duration: 22min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 06: InsightPanel Summary

**On-demand five-state insight report panel that branches strictly on the response body's `ready` field (never HTTP status), with an isolated 502 error state and D-13 retry that never touches the rest of the results page**

## Performance

- **Duration:** 22 min
- **Started:** 2026-07-19T20:44:00Z
- **Completed:** 2026-07-19T21:06:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `InsightPanel({ runId })` renders exactly one of five states driven by `useRunInsights(runId)`'s mutation lifecycle: idle (heading + body + "Get Insight Report" button), pending (disabled "Generating…" button), error (destructive Alert + re-enabled "Try Again"), not-ready (`ready:false` honest fallback copy, zero error styling), and ready (`ready:true` report text, `whitespace-pre-wrap`)
- Readiness branch structurally reads `data.ready` — no `response.status` / `.status ===` branch exists anywhere in the component (RES-04 hard rule)
- Report string renders as a plain JSX text child only — `dangerouslySetInnerHTML` count is 0 (T-04-01 mitigation)
- 5 test cases across 4 describe blocks cover idle, ready, not-ready (with an explicit assertion that no `role="alert"` element and no destructive-error copy appears), and the 502-then-retry-recovers flow
- Full frontend suite (229 tests across 41 files) stays green after this addition — no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: InsightPanel five-state component (D-11, D-13, RES-04, RES-05)** - `990133a` (feat)
2. **Task 2: InsightPanel.test.tsx — all five states + branch-on-ready + isolation** - `c9d9cbf` (test)

**Plan metadata:** committed together with this SUMMARY (see final commit)

## Files Created/Modified
- `frontend/src/components/results/InsightPanel.tsx` - Five-state insight panel component, consumes `useRunInsights`
- `frontend/src/components/results/InsightPanel.test.tsx` - Coverage for idle/ready/not-ready/error states plus the ready-not-status guard and 502 retry

## Decisions Made
- The error-state "Try Again" button uses the `outline` Button variant rather than `destructive` — the Alert directly above it already carries the destructive visual treatment (border-destructive/40, destructive AlertTitle text via the `variant="default"` Alert composed per the plan's pattern block), so the button stays a neutral, calm retry affordance per D-13's "no cumulative counter, calm not punitive" framing. This mirrors ConstraintInput/ProviderDownBanner's precedent of pairing a distinct error block with a plain-styled action.
- Not-ready renders as a bare `<p>`, not wrapped in any `Alert` — this was a deliberate structural choice (not just a copy choice) so the RES-04 guard is provable by the ABSENCE of `role="alert"` in the DOM, not just by string matching.

## Deviations from Plan

None — plan executed exactly as written. `npm install` was required once (no `node_modules` present in this freshly-created worktree) to run `tsc`/`vitest`; this is routine environment setup, not a plan deviation, and produced no `package.json`/`package-lock.json` diff (lockfile was already in sync).

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `InsightPanel` is ready for composition into `ResultsView` (plan 04-07) as the bottom section, per the UI-SPEC's Application Structure item 6.
- `useRunInsights` (plan 04-03) already guarantees no cache coupling; this plan's tests further confirm the isolation is visible at the render layer (a 502 here never invalidates or touches any other query's DOM output, since InsightPanel touches nothing outside its own local JSX tree).
- No blockers for 04-07.

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: frontend/src/components/results/InsightPanel.tsx
- FOUND: frontend/src/components/results/InsightPanel.test.tsx
- FOUND: .planning/phases/04-results-insights/04-06-SUMMARY.md
- FOUND: 990133a (feat: InsightPanel component)
- FOUND: c9d9cbf (test: InsightPanel.test.tsx)
- FOUND: 10d9572 (docs: plan metadata commit)
