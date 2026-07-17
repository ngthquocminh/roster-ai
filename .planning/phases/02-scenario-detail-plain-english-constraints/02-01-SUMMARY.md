---
phase: 02-scenario-detail-plain-english-constraints
plan: 01
subsystem: api
tags: [backend, fastapi, overrides, api-contract, pydantic]

# Dependency graph
requires:
  - phase: 01-llm-layer-and-overrides
    provides: "POST /constraints, scenario.overrides JSON column, AppliedConstraint/RejectedConstraint schemas"
provides:
  - "GET /scenarios/{scenario_id}/overrides -> list[OverrideOut], 200/404, legacy-safe"
  - "parsed_constraint persisted alongside tool/args in scenario.overrides (D-02)"
  - "docs/API.md documents the new endpoint + OverrideOut model in lockstep with code"
affects: [02-02-frontend-editor-overrides-list, scenario-editor, api-contract]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional response field for legacy-JSON-column read paths (parsed_constraint: str | None = None) to avoid ResponseValidationError 500s on older stored data"
    - "Dedicated GET sub-resource endpoint (not a field bolted onto the parent detail response) when a UI needs the two fetches to resolve/error independently"

key-files:
  created:
    - backend/tests/test_scenarios_api.py
  modified:
    - backend/api/schemas.py
    - backend/api/routers/scenarios.py
    - backend/services/constraint_service.py
    - backend/tests/test_constraints_api.py
    - docs/API.md

key-decisions:
  - "Dedicated GET /scenarios/{scenario_id}/overrides endpoint (Option B), not a field on ScenarioOut — the UI-SPEC requires the scenario-detail fetch and overrides fetch to resolve/error independently, and Option A would silently change GET /scenarios' already-shipped list-row shape."
  - "Overrides returned in the stored dict's natural insertion order (first-applied-first), no server-side re-sort — the zero-extra-code choice, documented as deliberate."
  - "Legacy migration via OverrideOut.parsed_constraint: str | None = None (graceful fallback), not backfill — backfill would require duplicating the six per-tool string templates for near-zero value on local dev DBs."

requirements-completed: [SCEN-03, CONS-02]

coverage:
  - id: D1
    description: "GET /scenarios/{scenario_id}/overrides returns 200 with persisted overrides as list[OverrideOut] ({id, tool, args, parsed_constraint})"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "backend/tests/test_scenarios_api.py#test_overrides"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /scenarios/{scenario_id}/overrides returns 404 for an unknown scenario id"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "backend/tests/test_scenarios_api.py#test_overrides_404"
        status: pass
    human_judgment: false
  - id: D3
    description: "Legacy override (no parsed_constraint key) deserializes with parsed_constraint=null, never 500"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "backend/tests/test_scenarios_api.py#test_overrides_legacy"
        status: pass
    human_judgment: false
  - id: D4
    description: "Empty overrides -> 200 + []"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "backend/tests/test_scenarios_api.py#test_overrides_empty"
        status: pass
    human_judgment: false
  - id: D5
    description: "Idempotent re-submission overwrites the same content-hash override id in place"
    requirement: SCEN-03
    verification:
      - kind: integration
        ref: "backend/tests/test_scenarios_api.py#test_overrides_idempotent"
        status: pass
    human_judgment: false
  - id: D6
    description: "POST /constraints persists parsed_constraint alongside {tool,args} so a reloaded override reads identically to a freshly-applied one"
    requirement: CONS-02
    verification:
      - kind: integration
        ref: "backend/tests/test_constraints_api.py#test_post_constraints_persists_override_to_scenario"
        status: pass
    human_judgment: false
  - id: D7
    description: "docs/API.md documents GET /scenarios/{scenario_id}/overrides and the OverrideOut model in lockstep with code"
    requirement: SCEN-03
    verification:
      - kind: manual_procedural
        ref: "manual diff review of docs/API.md against backend/api/schemas.py + routers/scenarios.py"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 01: Overrides Read Path + parsed_constraint Persistence Summary

**GET /scenarios/{scenario_id}/overrides returning list[OverrideOut] (legacy-safe, unsorted, natural insertion order), with parsed_constraint now persisted alongside tool/args on every applied constraint.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 completed
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- New `GET /scenarios/{scenario_id}/overrides` route returns a scenario's persisted overrides as `list[OverrideOut]`, reusing `scenario_service.get_scenario`'s existing 404 semantics
- `OverrideOut.parsed_constraint` is `str | None = None` so a legacy override (missing the key) deserializes to `null` instead of raising `ResponseValidationError` (500)
- `constraint_service.py`'s persist block now writes `parsed_constraint` alongside `tool`/`args` (additive-only; downstream `run_service.py`/`insight_service.py` readers use explicit key access and are unaffected)
- `docs/API.md` updated in lockstep: new endpoint section + `OverrideOut` data-model table
- Full backend suite green: 142 passed, 6 deselected (the `live` marker, unaffected)

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend contract tests for the overrides read path + parsed_constraint persistence** - `cc57ef5` (test)
2. **Task 2: Implement OverrideOut + GET /scenarios/{id}/overrides + persist parsed_constraint + docs** - `7d2472d` (feat)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `backend/tests/test_scenarios_api.py` - new: 5 contract tests for the overrides read path (200 shape, 404, legacy-no-500, empty, idempotent)
- `backend/tests/test_constraints_api.py` - extended `test_post_constraints_persists_override_to_scenario` to assert the stored overrides JSON carries `parsed_constraint`
- `backend/api/schemas.py` - new `OverrideOut` model (`parsed_constraint: str | None = None`, distinct from the non-optional `AppliedConstraint`)
- `backend/api/routers/scenarios.py` - new `GET /{scenario_id}/overrides` route
- `backend/services/constraint_service.py` - persist block now writes `parsed_constraint` into the stored override dict (D-02)
- `docs/API.md` - new `GET /scenarios/{scenario_id}/overrides` section + `OverrideOut` data-model table

## Decisions Made
- Reused `scenario_service.get_scenario` in the new route (rather than a dedicated query) so 404 semantics stay byte-identical to the existing `GET /scenarios/{scenario_id}` route.
- No server-side re-sort of overrides — returned in the stored dict's natural insertion order, matching the plan's documented Claude's-Discretion decision.
- Did not reuse `AppliedConstraint` for the new response model (its `parsed_constraint: str` is non-optional and would 500 on legacy data per RESEARCH.md Pitfall 2) — added a sibling `OverrideOut` model instead.

## Deviations from Plan

None - plan executed exactly as written. Task 1's tests were written test-first per the plan's instruction ("Do NOT implement the endpoint or schema in this task") and Task 2 turned them green without needing any additional fixes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Backend contract for SCEN-03/CONS-02 is complete and documented; plan 02-02 (frontend Editor/overrides list) can now regenerate `frontend/src/api/schema.d.ts` against the live `/scenarios/{scenario_id}/overrides` OpenAPI path and build `getScenarioOverrides`/`useOverrides` against a real, tested endpoint.
- No blockers.

---
*Phase: 02-scenario-detail-plain-english-constraints*
*Completed: 2026-07-17*

## Self-Check: PASSED

All created/modified files found on disk; all task commit hashes (`cc57ef5`, `7d2472d`, `dda8d49`) found in git log.
