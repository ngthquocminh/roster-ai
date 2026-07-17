---
phase: 02-scenario-detail-plain-english-constraints
plan: 02
subsystem: api
tags: [frontend, api-client, openapi-typescript, codegen, shadcn, vitest]

# Dependency graph
requires:
  - phase: 02-scenario-detail-plain-english-constraints
    provides: "GET /scenarios/{scenario_id}/overrides -> list[OverrideOut] (02-01)"
provides:
  - "Regenerated frontend/src/api/schema.d.ts containing paths[\"/scenarios/{scenario_id}/overrides\"]"
  - "getScenario(scenarioId) and getScenarioOverrides(scenarioId) typed wrappers in scenarios.ts"
  - "applyConstraint(body) typed wrapper (new constraints.ts) with the status-attach error convention"
  - "constraints.test.ts unit coverage: success + 503/422 status-attach rejects"
  - "Textarea shadcn primitive (frontend/src/components/ui/textarea.tsx)"
affects: [02-03-frontend-hooks, 02-05-constraint-input, scenario-editor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Status-attach error convention (T-1-02) extended to getScenario/getScenarioOverrides/applyConstraint: throw {status: response.status, ...error} on every wrapper, never branch on message text"
    - "Request/response types derived only via indexed access into generated `paths` — no hand-authored payload interfaces"

key-files:
  created:
    - frontend/src/api/constraints.ts
    - frontend/src/api/constraints.test.ts
    - frontend/src/components/ui/textarea.tsx
  modified:
    - frontend/src/api/schema.d.ts
    - frontend/src/api/scenarios.ts

key-decisions:
  - "constraints.test.ts mirrors scenarios.test.ts's vi.mock(\"./client\") boundary-mock pattern verbatim (not msw) — the established repo convention for this test surface."
  - "Textarea added via `npx shadcn add textarea` from the official registry (source-file copy), verified to add zero new package.json dependencies."

requirements-completed: [SCEN-03, CONS-01, CONS-05]

coverage:
  - id: D1
    description: "schema.d.ts regenerated from the live backend OpenAPI schema and contains paths[\"/scenarios/{scenario_id}/overrides\"]"
    requirement: SCEN-03
    verification:
      - kind: other
        ref: "grep -c '/scenarios/{scenario_id}/overrides' frontend/src/api/schema.d.ts -> 1"
        status: pass
    human_judgment: false
  - id: D2
    description: "getScenario and getScenarioOverrides call the typed client with the scenario_id path param and throw {status: response.status, ...error} on failure"
    requirement: SCEN-03
    verification:
      - kind: unit
        ref: "frontend/src/api/scenarios.test.ts (existing suite, unaffected/still green)"
        status: pass
      - kind: other
        ref: "npm run typecheck (tsc --noEmit) — derived types resolve against regenerated schema"
        status: pass
    human_judgment: false
  - id: D3
    description: "applyConstraint POSTs /constraints, resolves to the full ConstraintParseResponse on 200, and throws {status: response.status, ...error} on failure — status distinguishes 503 (provider down) from 422 (validation)"
    requirement: CONS-01
    verification:
      - kind: unit
        ref: "frontend/src/api/constraints.test.ts#applyConstraint (success + status===503 + status===422)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Textarea component sourced from the official shadcn registry into frontend/src/components/ui/textarea.tsx, no new npm dependency"
    requirement: CONS-05
    verification:
      - kind: other
        ref: "git diff frontend/package.json (empty) + file exists and exports Textarea"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 02: Typed Client Regeneration + Constraint/Overrides Wrappers Summary

**Regenerated `schema.d.ts` against the D-01 overrides endpoint, added `getScenario`/`getScenarioOverrides`/`applyConstraint` typed wrappers (all status-attaching on error), unit-tested `applyConstraint`'s 503-vs-422 discrimination, and pulled in the shadcn `Textarea` primitive.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 completed
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- `npm run codegen` regenerated `frontend/src/api/schema.d.ts` against the live backend (D-01 already on `main`), adding `paths["/scenarios/{scenario_id}/overrides"]`
- `scenarios.ts` gained `getScenario(scenarioId)` and `getScenarioOverrides(scenarioId)`, both following the existing `createScenario` status-attach error convention (`throw { status: response.status, ...error }`)
- New `frontend/src/api/constraints.ts` with `applyConstraint(body)` — request type derived via indexed access into `paths["/constraints"]["post"]["requestBody"]`, resolves to the full `ConstraintParseResponse` on success, throws the status-attached error shape on failure
- New `frontend/src/api/constraints.test.ts` covers the success path and both `503` (provider down) and `422` (validation) reject cases — the exact discriminator CONS-05's UI branch will use downstream
- `frontend/src/components/ui/textarea.tsx` added via `npx shadcn add textarea` (official registry, source-copy — zero new `package.json` dependencies), matching `input.tsx`'s composition shape
- Full frontend suite green: 61/61 tests passing; `tsc --noEmit` clean; re-running `npm run codegen` a second time produced byte-identical output (no drift)

## Task Commits

Each task was committed atomically:

1. **Task 1: Regenerate schema.d.ts and add the three typed endpoint wrappers** - `314bc61` (feat)
2. **Task 2: Wrapper unit test + add the shadcn Textarea primitive** - `e75ecaf` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `frontend/src/api/schema.d.ts` - regenerated; gains `paths["/scenarios/{scenario_id}/overrides"]["get"]`
- `frontend/src/api/scenarios.ts` - added `getScenario`, `getScenarioOverrides`
- `frontend/src/api/constraints.ts` - new: `applyConstraint` wrapper
- `frontend/src/api/constraints.test.ts` - new: unit coverage for `applyConstraint`
- `frontend/src/components/ui/textarea.tsx` - new: shadcn `Textarea` primitive

## Decisions Made
- Mirrored `scenarios.test.ts`'s exact `vi.mock("./client")` boundary-mock pattern in `constraints.test.ts` rather than introducing any new test-mocking approach — keeps the client-boundary-mock convention singular across the API layer.
- Confirmed via `git diff frontend/package.json` that the shadcn CLI's `add textarea` introduced no new dependency, satisfying the plan's registry-safety acceptance check without additional tooling.

## Deviations from Plan

None - plan executed exactly as written. `npm run codegen` picked up the D-01 backend change on the first run (already merged to `main` per plan 02-01), so no backend re-verification step was needed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The typed HTTP surface for SCEN-03/CONS-01/CONS-05 is complete and unit-tested: `getScenario`, `getScenarioOverrides`, and `applyConstraint` are all available with the status-attach error convention downstream hooks and components rely on.
- `Textarea` is available for plan 02-05's `ConstraintInput` component.
- No blockers. Plan 02-03 (frontend hooks: `useScenario`, `useOverrides`, `useApplyConstraint`) can now build directly on these wrappers.

---
*Phase: 02-scenario-detail-plain-english-constraints*
*Completed: 2026-07-17*

## Self-Check: PASSED

All created/modified files found on disk; both task commit hashes (`314bc61`, `e75ecaf`) found in git log.
