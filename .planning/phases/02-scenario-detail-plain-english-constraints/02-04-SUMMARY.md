---
phase: 02-scenario-detail-plain-english-constraints
plan: 04
subsystem: ui
tags: [frontend, react, editor, overrides, tanstack-query]

# Dependency graph
requires:
  - phase: 02-scenario-detail-plain-english-constraints
    provides: "useScenario/useOverrides query hooks (02-03)"
provides:
  - "ScenarioHeader.tsx — single-record detail header taking a useScenario query-result prop; loading/404-terminal/error/populated states"
  - "OverridesList.tsx — durable overrides list taking a useOverrides query-result prop; loading/empty/error/populated/legacy-fallback states"
  - "toolLabels.ts — fixed TOOL_LABELS map + toolLabel() helper (used by OverridesList's legacy fallback and plan 02-05's rejected-item heading)"
affects: [02-05-constraint-input, 02-06-editor-route]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Both components accept the raw useQuery result object as a prop (scenarioQuery / overridesQuery), not a scenarioId — lets plan 02-06's Editor share one useScenario instance between the header and useOverrides's enabled gate, per 02-PATTERNS.md"
    - "404 discrimination via error.status === 404 (T-02-12), never message text — same T-1-02 convention as CreateScenarioDialog"
    - "Legacy-override fallback renders toolLabel(tool) + comma-joined key=value args, italic + muted + '(legacy entry)' caption, only when parsed_constraint is null/undefined"

key-files:
  created:
    - frontend/src/components/editor/ScenarioHeader.tsx
    - frontend/src/components/editor/ScenarioHeader.test.tsx
    - frontend/src/components/editor/OverridesList.tsx
    - frontend/src/components/editor/OverridesList.test.tsx
    - frontend/src/lib/toolLabels.ts
  modified: []

key-decisions:
  - "ScenarioHeader/OverridesList take the useQuery result object as props (scenarioQuery/overridesQuery) rather than a scenarioId, per the plan's explicit prop-shape guidance — this lets plan 02-06's Editor call useScenario once and pass the same instance into both this header and useOverrides's enabled gate, avoiding a duplicate fetch."
  - "Used a plain Link with buttonVariants() classes for the 404 'Back to Scenarios' action instead of Button asChild + Radix Slot — functionally identical rendered output, avoids introducing an unproven Slot+react-router-Link ref-forwarding combination with no existing repo precedent."

requirements-completed: [SCEN-03, CONS-02]

coverage:
  - id: D1
    description: "ScenarioHeader renders loading spinner, 404-terminal view (with Back to Scenarios link to /), non-404 ErrorBanner, and populated fields (name/fixture/time_limit_s/created_at) driven by a useScenario query-result prop"
    requirement: SCEN-03
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ScenarioHeader.test.tsx (5 tests: loading, 404-terminal, non-404 error x2, populated)"
        status: pass
    human_judgment: false
  - id: D2
    description: "OverridesList renders loading spinner, empty state, ErrorBanner, populated rows with parsed_constraint verbatim (never raw {tool,args} JSON), and the legacy '{Tool Label}: key=value' + '(legacy entry)' fallback when parsed_constraint is missing, in received order keyed by id"
    requirement: CONS-02
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/OverridesList.test.tsx (8 tests: loading, empty, error, populated-verbatim, legacy-fallback x2, zero-one-many x2)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The scenario name / fixture / parsed_constraint / legacy args long-text visual truncation-or-wrap backstops (UI-SPEC E1/E2 long-text) are not automatable at this layer"
    verification: []
    human_judgment: true
    rationale: "UI-SPEC explicitly routes these two backstops to human verification in plan 02-07 — visual truncation/wrapping cannot be asserted from a jsdom test render."

duration: 25min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 04: ScenarioHeader + OverridesList + Tool Label Map Summary

**Read-only Editor surfaces over the plan-02-03 hooks — a 404-resolving scenario detail header and a durable overrides list that renders `parsed_constraint` verbatim with a graceful legacy fallback, never raw `{tool, args}` JSON.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 completed
- **Files modified:** 5 (all created)

## Accomplishments
- `ScenarioHeader.tsx` — renders all four SCEN-03 header states (loading/404-terminal/non-404-error/populated) over a passed-in `useScenario` query-result object; the 404 branch finally resolves Phase 1's bad-deep-link backstop (`E5`/`E7`) with a real terminal "Scenario not found" view and a working "Back to Scenarios" link to `/`
- `OverridesList.tsx` — renders all five SCEN-03/D-01/D-02 list states (loading/empty/error/populated/legacy) over a passed-in `useOverrides` query-result object, copying `ScenarioTable.tsx`'s state-machine and `max-h-[420px] overflow-y-auto` overflow container structurally; `parsed_constraint` is rendered verbatim when present, with the "{Tool Label}: key=value" + "(legacy entry)" fallback for pre-D-02 legacy overrides
- `toolLabels.ts` — the fixed `TOOL_LABELS` map (all five tools) + `toolLabel()` helper, falling back to the raw tool string for any unrecognized value (never a fabricated label)
- Both components TDD'd RED→GREEN: failing tests committed first (import-resolution failures proving the components didn't exist), then minimal implementations made them pass
- Full frontend suite green: 83/83 tests passing; `tsc --noEmit` clean

## Task Commits

Each task was committed atomically (TDD RED→GREEN pairs):

1. **Task 1: ScenarioHeader — single-record detail with loading/404-terminal/error/populated states**
   - RED: `99ec02c` (test) — failing test for all four states
   - GREEN: `1d1a12f` (feat) — implementation, 5/5 tests pass
2. **Task 2: OverridesList + Tool Label Map — durable list with legacy fallback**
   - RED: `03ca5c5` (test) — failing test for all list states + toolLabels.ts added as its dependency
   - GREEN: `1f7223a` (feat) — implementation, 8/8 tests pass

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `frontend/src/components/editor/ScenarioHeader.tsx` - loading/404-terminal/error/populated header over a `useScenario` query-result prop
- `frontend/src/components/editor/ScenarioHeader.test.tsx` - 5 tests covering all four states + non-404-with-no-status edge case
- `frontend/src/components/editor/OverridesList.tsx` - loading/empty/error/populated/legacy-fallback list over a `useOverrides` query-result prop
- `frontend/src/components/editor/OverridesList.test.tsx` - 8 tests covering all list states, legacy fallback (recognized + unrecognized tool), and zero-one-many/ordering
- `frontend/src/lib/toolLabels.ts` - fixed `TOOL_LABELS` map (5 entries) + `toolLabel()` helper

## Decisions Made
- Both components accept the raw `useQuery`/`useOverrides` result object as a prop (`scenarioQuery` / `overridesQuery`) rather than a `scenarioId` string — per the plan's own guidance, this lets plan 02-06's `Editor` call `useScenario` exactly once and pass that same instance into both this header and `useOverrides`'s `enabled` gate (`scenarioQuery.isSuccess`), avoiding a duplicate fetch or a second internal hook call.
- For the 404 "Back to Scenarios" action, used a plain `<Link to="/" className={buttonVariants(...)}>` instead of `<Button asChild><Link .../></Button>` (Radix `Slot` composition). Both render identical DOM/classes; the direct `Link` avoids introducing an untested `Slot` + `react-router` `Link` ref-forwarding combination that has no existing precedent anywhere else in this codebase (`grep asChild` found only Radix-native `DialogPrimitive.Close`/`SelectPrimitive.Icon` usages, never with `react-router`'s `Link`).

## Deviations from Plan

None - plan executed exactly as written. Both tasks followed the plan's `<action>` and `<read_first>` guidance directly against the `ScenarioTable.tsx`/`ErrorBanner.tsx`/`CreateScenarioDialog.tsx` analogs identified in 02-PATTERNS.md, and the exact Copywriting Contract strings from 02-UI-SPEC.md (404 view, empty-state, legacy-fallback caption).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both read-only Editor surfaces are complete and typed against the plan-02-02/02-03 layer: `ScenarioHeader` and `OverridesList`, each accepting a query-result object so plan 02-06 can wire one `useScenario`/`useOverrides` pair per Editor mount without prop-drilling `scenarioId` through multiple internal hook calls.
- `toolLabels.ts`'s `toolLabel()` helper is now available for plan 02-05's `TranscriptEntry` rejected-item heading ("Couldn't apply: {Tool Label}"), reusing the identical fixed map rather than duplicating it.
- Neither component composes into the `/scenarios/:scenarioId` route yet — that wiring, plus `ConstraintInput`/`ConstraintTranscript` composition, is plan 02-06's job.
- No blockers.

---
*Phase: 02-scenario-detail-plain-english-constraints*
*Completed: 2026-07-17*

## Self-Check: PASSED

All 6 created files found on disk (`ScenarioHeader.tsx`, `ScenarioHeader.test.tsx`, `OverridesList.tsx`, `OverridesList.test.tsx`, `toolLabels.ts`, this SUMMARY); all 4 task commit hashes (`99ec02c`, `1d1a12f`, `03ca5c5`, `1f7223a`) found in git log.
