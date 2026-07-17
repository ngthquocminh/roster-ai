---
phase: 02-scenario-detail-plain-english-constraints
plan: 06
subsystem: ui
tags: [frontend, react, react-router, tanstack-query, editor, routing, composition]

# Dependency graph
requires:
  - phase: 02-scenario-detail-plain-english-constraints
    provides: "ScenarioHeader/OverridesList (02-04); ConstraintTranscript/ConstraintInput/ProviderDownBanner (02-05); useScenario/useOverrides/useApplyConstraint hooks (02-03)"
provides:
  - "Editor.tsx — the live /scenarios/:scenarioId route: composes ScenarioHeader, ConstraintTranscript, ConstraintInput, and the 'Applied Overrides' section in the UI-SPEC's fixed vertical order"
  - "Session transcript state (TranscriptEntryData[]) owned in Editor via useState, appended through ConstraintInput's onOutcome callback, never reset on any outcome"
  - "404 gate (E7): a 404 on GET /scenarios/{id} renders only the ScenarioHeader terminal 'Scenario not found' view; transcript/input/overrides never mount and no overrides fetch fires"
  - "App.tsx index route now mounts Editor; EditorPlaceholder.tsx retired"
affects: [02-07-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Editor calls useScenario exactly once and passes the same query-result instance into both ScenarioHeader and useOverrides's enabled gate (scenarioQuery.isSuccess) — avoids a duplicate fetch, per the shared-instance prop contract 02-04/02-05 established"
    - "Route-level integration test mocks @/api/scenarios and @/api/constraints at the module boundary (not msw) so the real useScenario/useOverrides/useApplyConstraint hooks drive genuine TanStack Query state through a real QueryClient — same boundary-mock convention as CreateScenarioDialog.test.tsx"

key-files:
  created:
    - frontend/src/routes/Editor.tsx
    - frontend/src/routes/Editor.test.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/routes/router.test.tsx
  deleted:
    - frontend/src/routes/EditorPlaceholder.tsx

key-decisions:
  - "Task 1 (Editor composition + App.tsx rewire + EditorPlaceholder retirement) had already been implemented and committed (d77d79b) in a prior session before this execution picked up the plan; this run verified that commit against the actual plan requirements (fixed region order, 404 gate, shared useScenario instance, no textarea/transcript reset) rather than re-doing the work, then completed and committed Task 2 (Editor.test.tsx + router.test.tsx update), which was present in the working tree but uncommitted."

requirements-completed: [SCEN-03, CONS-01, CONS-04]

coverage:
  - id: D1
    description: "Opening /scenarios/:scenarioId renders, in fixed vertical order, scenario header → constraint transcript → constraint input → Applied Overrides list"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "frontend/src/routes/Editor.test.tsx — 'Editor: populated [SCEN-03, UI-SPEC Application Structure]'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Editor owns session transcript state; a full apply appends a transcript entry showing parsed_constraint verbatim and clears the textarea"
    requirement: CONS-01
    verification:
      - kind: integration
        ref: "frontend/src/routes/Editor.test.tsx — 'Editor: apply outcome [CONS-01, CONS-02, D-03]'"
        status: pass
    human_judgment: false
  - id: D3
    description: "A clarification_needed outcome appends a transcript entry and preserves the typed textarea text (CONS-04 'rephrase without losing their place')"
    requirement: CONS-04
    verification:
      - kind: integration
        ref: "frontend/src/routes/Editor.test.tsx — 'Editor: clarification outcome [CONS-04]'"
        status: pass
    human_judgment: false
  - id: D4
    description: "A 404 on GET /scenarios/{id} gates the entire Editor — only the 'Scenario not found' terminal view renders, no input/overrides regions, and no overrides fetch fires"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "frontend/src/routes/Editor.test.tsx — 'Editor: 404 gate [E7]'"
        status: pass
    human_judgment: false
  - id: D5
    description: "The Editor mounts at the ScenarioLayout index route, replacing EditorPlaceholder, with the tab-nav chrome unchanged"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "frontend/src/routes/router.test.tsx — 'mounts the Editor at /scenarios/:scenarioId (index)'"
        status: pass
    human_judgment: false
  - id: D6
    description: "The overrides list query is dependent on the scenario detail query's success, and a successful apply invalidates it so newly applied overrides appear without a manual refresh"
    verification: []
    human_judgment: true
    rationale: "The invalidate-on-success wiring lives in useApplyConstraint (02-03, already unit-tested) and useOverrides's enabled flag is exercised structurally in Editor.test.tsx's 404 test (no overrides fetch fires), but an end-to-end 'apply then see the overrides list refetch and grow' assertion was not added at the route-integration layer — routed to human verification in plan 02-07."

duration: ~15min (this session; Task 1 composition was completed and committed in a prior session)
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 06: Editor Route Composition Summary

**Composed the read half (ScenarioHeader/OverridesList) and write half (ConstraintTranscript/ConstraintInput) into the live `/scenarios/:scenarioId` Editor route — session transcript state owned above both regions, 404-gated, mounted in place of `EditorPlaceholder`.**

## Performance

- **Duration:** ~15 min (this session — verification + Task 2 completion; Task 1 was already implemented and committed in a prior session)
- **Tasks:** 2 completed
- **Files modified:** 4 (2 created, 1 modified this session — App.tsx was modified in the prior-session commit; router.test.tsx modified this session; EditorPlaceholder.tsx deleted in the prior-session commit)

## Accomplishments
- `Editor.tsx` composes `ScenarioHeader`, `ConstraintTranscript`, `ConstraintInput`, and an "Applied Overrides" section (`OverridesList`) in the UI-SPEC's mandated fixed vertical order (header → transcript → input → overrides), with `gap-4` (md/16px) spacing between regions
- Calls `useScenario` exactly once and passes that single query-result instance into both `ScenarioHeader` and `useOverrides`'s `enabled` gate (`scenarioQuery.isSuccess`) — no duplicate fetch
- Owns the session transcript (`TranscriptEntryData[]` via `useState`) above both the transcript view and the input; `ConstraintInput`'s `onOutcome` prop appends every submission's outcome, never resetting on rejected/clarification/no-match/503 (CONS-04)
- 404 gate (E7): `scenarioQuery.isError && status === 404` early-returns right after `ScenarioHeader` (which renders the terminal "Scenario not found" view itself) — nothing below it ever renders, and `useOverrides`'s `enabled: false` means no overrides fetch fires either
- `App.tsx`'s index route under `scenarios/:scenarioId` now mounts `Editor`; `EditorPlaceholder.tsx` is deleted and no source file references it (`grep -rl EditorPlaceholder frontend/src` returns nothing)
- `Editor.test.tsx` (route-level integration test, module-boundary-mocked `@/api/scenarios` + `@/api/constraints`) proves: populated fixed-order render with the empty-overrides state and no premature transcript chrome; a full-apply outcome appends the transcript entry and clears the textarea; a clarification outcome appends the entry and preserves the textarea text; a 404 renders only the terminal view with no input/overrides regions and no overrides fetch call
- `router.test.tsx`'s index-route assertion now expects the real Editor surface ("Loading scenario…", the synchronous pre-fetch-settle state) instead of the retired `EditorPlaceholder` copy
- Full frontend suite green: 105/105 tests passing; `tsc --noEmit` clean; `npm run build` succeeds

## Task Commits

1. **Task 1: Editor route composition + wire into App.tsx (retire EditorPlaceholder)**
   - `d77d79b` (feat) — composed Editor.tsx, rewired App.tsx, deleted EditorPlaceholder.tsx (committed in a prior session; verified against plan requirements this session, not re-done)
2. **Task 2: Editor integration test + update route test**
   - `b305bb0` (test) — Editor.test.tsx (4 integration tests) + router.test.tsx index-route assertion update

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `frontend/src/routes/Editor.tsx` - the composed `/scenarios/:scenarioId` route: fixed-order region composition, session transcript state, 404 gate, shared `useScenario` instance
- `frontend/src/routes/Editor.test.tsx` - route-level integration tests: populated render, apply-appends-and-clears, clarification-appends-and-preserves, 404-gates-the-view
- `frontend/src/App.tsx` - index route under `scenarios/:scenarioId` now mounts `Editor` (was `EditorPlaceholder`)
- `frontend/src/routes/router.test.tsx` - index-route assertion updated to expect the Editor surface, not the retired placeholder copy
- `frontend/src/routes/EditorPlaceholder.tsx` - deleted (retired, no longer referenced anywhere)

## Decisions Made
- Task 1's implementation (`Editor.tsx`, `App.tsx` rewire, `EditorPlaceholder.tsx` deletion) was found already committed (`d77d79b`) at the start of this execution — evidently completed in a prior session that did not run through to a plan-complete state (Task 2's files were present in the working tree but uncommitted: `Editor.test.tsx` untracked, `router.test.tsx` modified). Rather than re-implementing Task 1, this session verified the existing composition against every plan requirement (region order, 404 early-return placement, shared `useScenario` instance, `useOverrides`'s dependent `enabled` gate, no transcript reset) by reading the code directly, then ran the full verification suite (`npm test`, `npm run typecheck`, `npm run build`) to confirm it holds, and completed/committed Task 2's already-drafted test files.
- No functional changes were needed to the existing `Editor.tsx` — it already matches the plan's `<action>` and `<acceptance_criteria>` exactly (fixed order, 404 gate, shared query instance, `gap-4` spacing, "Applied Overrides" Heading-role section title).

## Deviations from Plan

None - plan executed exactly as written. The only divergence from the standard single-session flow is procedural (Task 1 was already done and committed from a prior session), not a deviation from the plan's content — the shipped code matches the plan's `<action>`/`<acceptance_criteria>` for both tasks.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The full SCEN-03 + CONS-01..05 Editor surface is live at `/scenarios/:scenarioId`: a user opens a scenario, sees its overrides, types a constraint, and watches the outcome appear in the transcript and (on apply) the durable list.
- The five UI-SPEC backstops (E1/E2/E3 long-text visual wrapping, E4 422 structural-backstop, E5 long-text) and the D6 end-to-end "apply invalidates and overrides list visibly grows" check remain routed to human verification — this is plan 02-07's job per the UI-SPEC's own backstop declaration.
- No blockers.

---
*Phase: 02-scenario-detail-plain-english-constraints*
*Completed: 2026-07-17*

## Self-Check: PASSED

All 4 created/modified source files found on disk (`Editor.tsx`, `Editor.test.tsx`, `App.tsx`, `router.test.tsx`) plus this SUMMARY; `EditorPlaceholder.tsx` confirmed deleted; both task commit hashes (`d77d79b`, `b305bb0`) found in git log.
