---
phase: 03-run-execution-history
plan: 02
subsystem: ui
tags: [react-query, polling, mutation, typescript, vitest]

# Dependency graph
requires:
  - phase: 03-run-execution-history (plan 01)
    provides: "hasActiveRun/isTerminalStatus predicates in frontend/src/lib/runStatus.ts and listRuns/triggerRun in frontend/src/api/runs.ts"
provides:
  - "useRuns(scenarioId): self-terminating polling list query under [\"runs\", scenarioId]"
  - "useTriggerRun(scenarioId): mutation that invalidates [\"runs\", scenarioId] on success"
affects: [03-03, 03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "refetchInterval as a predicate function of query.state.data (not a fixed number) to implement self-terminating polling driven by a shared domain predicate (hasActiveRun)"

key-files:
  created:
    - frontend/src/hooks/useRuns.ts
    - frontend/src/hooks/useRuns.test.tsx
    - frontend/src/hooks/useTriggerRun.ts
    - frontend/src/hooks/useTriggerRun.test.tsx
  modified: []

key-decisions:
  - "refetchInterval predicate reads query.state.data (React Query v5 Query object) rather than re-deriving state, so the interval always reflects the latest fetched snapshot"
  - "Poll interval is a module-level named constant (RUNS_POLL_INTERVAL_MS = 2000) rather than inlined magic number"
  - "Test for the refetchInterval predicate mounts the real hook and reads the predicate off the QueryClient's query cache (query.options.refetchInterval), then drives it directly with synthetic data via query.setData — proves the actual wired predicate, not a reimplementation"

patterns-established:
  - "Self-terminating polling hook pattern: refetchInterval as (query) => predicate(query.state.data ?? []) ? INTERVAL : false, relying entirely on React Query's own interval lifecycle (no setInterval/clearInterval)"

requirements-completed: [RUN-01, RUN-02]

coverage:
  - id: D1
    description: "useRuns polls GET /scenarios/{id}/runs under [\"runs\", scenarioId] and self-terminates the poll once every run is terminal (or the list is empty)"
    requirement: "RUN-02"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useRuns.test.tsx#refetchInterval predicate (returns interval for RUNNING, false for all-terminal, false for empty)"
        status: pass
    human_judgment: false
  - id: D2
    description: "useTriggerRun triggers a run and invalidates exactly [\"runs\", scenarioId] on success so the new PENDING run appears immediately; errors propagate intact"
    requirement: "RUN-01"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useTriggerRun.test.tsx#mutates via triggerRun(scenarioId) and invalidates exactly the ['runs', scenarioId] key on success"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useTriggerRun.test.tsx#does not invalidate anything, and reports isError with the status intact, when triggerRun rejects"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-18
status: complete
---

# Phase 03 Plan 02: Run Hooks (useRuns / useTriggerRun) Summary

**React Query hooks for the run lifecycle: a self-terminating polling list query (`useRuns`) driven by the shared `hasActiveRun` predicate, and a trigger mutation (`useTriggerRun`) that invalidates the same query key so a newly triggered run appears without waiting for the next poll tick.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-18T09:03:00Z
- **Completed:** 2026-07-18T09:23:33Z
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments
- `useRuns(scenarioId)`: thin `useQuery` wrapper over `listRuns`, `["runs", scenarioId]` key, `refetchInterval` predicate that polls while `hasActiveRun(data)` is true and stops (returns `false`) the instant every run is terminal or the list is empty.
- `useTriggerRun(scenarioId)`: `useMutation` wrapper over `triggerRun`, `onSuccess` invalidates exactly `["runs", scenarioId]` — the byte-identical key contract with `useRuns` that makes RUN-01's "appear immediately" true.
- Both hooks fully TDD'd: RED (failing test importing a non-existent module) committed separately from GREEN (passing implementation) for each task.

## Task Commits

Each task was committed atomically (TDD: test → feat per task):

1. **Task 1: Self-terminating polling list query (useRuns)**
   - `6e3f2ca` test(03-02): add failing test for useRuns self-terminating poll
   - `06d342d` feat(03-02): implement useRuns self-terminating poll hook
2. **Task 2: Trigger-run mutation with immediate refetch (useTriggerRun)**
   - `787afb6` test(03-02): add failing test for useTriggerRun immediate invalidation
   - `e42f6b5` feat(03-02): implement useTriggerRun mutation with immediate invalidation

**Plan metadata:** committed together with this SUMMARY (worktree mode — orchestrator finalizes shared docs after merge).

## Files Created/Modified
- `frontend/src/hooks/useRuns.ts` - `useRuns(scenarioId)`: useQuery(["runs", scenarioId], () => listRuns(scenarioId)) with refetchInterval predicate using hasActiveRun
- `frontend/src/hooks/useRuns.test.tsx` - queryKey/queryFn wiring test + refetchInterval predicate unit tests (RUNNING/all-terminal/empty)
- `frontend/src/hooks/useTriggerRun.ts` - `useTriggerRun(scenarioId)`: useMutation(() => triggerRun(scenarioId)) invalidating ["runs", scenarioId] on success
- `frontend/src/hooks/useTriggerRun.test.tsx` - success-invalidates-exact-key test + rejection-invalidates-nothing/isError test

## Decisions Made
- Poll interval extracted to a named module constant (`RUNS_POLL_INTERVAL_MS = 2000`) rather than a magic number inline, matching the plan's "small named constant" instruction.
- The refetchInterval predicate test mounts the real hook, reads the actual wired predicate off the query cache's `options.refetchInterval`, and drives it directly against synthetic `query.setData(...)` snapshots — this proves the exact function passed to `useQuery`, not a reimplementation that could silently drift from production behavior.
- Avoided the literal strings "setInterval"/"setTimeout" in useRuns.ts's docstring (per the plan's explicit instruction) to keep any downstream negative-assertion grep clean, while still documenting that React Query owns the interval lifecycle.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `useRuns` and `useTriggerRun` are ready for the in-flight panel, run table, and trigger button (later plans in this phase/wave) to consume via the shared `["runs", scenarioId]` key contract.
- No blockers.

---
*Phase: 03-run-execution-history*
*Completed: 2026-07-18*
