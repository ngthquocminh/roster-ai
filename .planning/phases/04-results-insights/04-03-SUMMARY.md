---
phase: 04-results-insights
plan: 03
subsystem: ui
tags: [tanstack-query, react, hooks, vitest]

# Dependency graph
requires:
  - phase: 04-results-insights (plan 02)
    provides: frontend/src/api/results.ts (getRunResult), frontend/src/api/insights.ts (getRunInsights), frontend/src/api/runs.ts (getRun)
provides:
  - useRun(runId) — ungated status-probe query on ['run', runId]
  - useRunResult(runId, { enabled }) — dependent query on ['run', runId, 'result'], gated on run COMPLETED
  - useRunInsights(runId) — isolated mutation-as-fetch over getRunInsights, no cache invalidation
affects: [04-06-insight-panel, 04-07-results-view]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dependent-query gate: useRunResult's enabled option mirrors useOverrides.ts exactly, keeping the deep-linkable Results route from ever hitting the pre-COMPLETED /result 409"
    - "Isolated mutation-as-fetch: useRunInsights is a bare useMutation with no useQueryClient/onSuccess, so an insight 502 has no code path to reach the ['run', ...] query cache"

key-files:
  created:
    - frontend/src/hooks/useRun.ts
    - frontend/src/hooks/useRun.test.tsx
    - frontend/src/hooks/useRunResult.ts
    - frontend/src/hooks/useRunResult.test.tsx
    - frontend/src/hooks/useRunInsights.ts
    - frontend/src/hooks/useRunInsights.test.tsx
  modified: []

key-decisions:
  - "useRun and useRunResult follow useScenario/useOverrides's ungated-then-enabled-gated pair shape exactly, including the query-key prefix-extension convention (['run', runId] -> ['run', runId, 'result'])"
  - "useRunInsights deliberately omits useTriggerRun's queryClient/onSuccess invalidation step entirely (not just leaves it empty) — the hook has no reference to the shared query client at all, making cache coupling structurally impossible, not just avoided by convention"

patterns-established:
  - "Mutation-as-fetch for button-triggered isolated reads: model as useMutation (not useQuery+enabled:false+refetch) when isPending/isError/mutate retry semantics are needed and the result must never touch another query's cache"

requirements-completed: [RES-04, RES-05]

coverage:
  - id: D1
    description: "useRun(runId) — ungated useQuery on ['run', runId] over getRun, the first fetch in the Results dependent-query chain"
    requirement: "RES-04"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useRun.test.tsx#queries getRun(id) under the ['run', id] key immediately, with no enabled gate"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useRun.test.tsx#surfaces isError on a failed fetch"
        status: pass
    human_judgment: false
  - id: D2
    description: "useRunResult(runId, { enabled }) — dependent useQuery on ['run', runId, 'result'] over getRunResult, gated so it never fires before the caller marks the run COMPLETED"
    requirement: "RES-04"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useRunResult.test.tsx#does not call getRunResult while enabled is false (dependent query stays idle, never 409s)"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useRunResult.test.tsx#queries getRunResult(id) under the ['run', id, 'result'] key once enabled is true"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useRunResult.test.tsx#surfaces isError on a failed fetch when enabled"
        status: pass
    human_judgment: false
  - id: D3
    description: "useRunInsights(runId) — isolated useMutation over getRunInsights with isIdle/isPending/isError/error/data/mutate, no query-cache invalidation, so a 502 cannot touch the run/result cache"
    requirement: "RES-05"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useRunInsights.test.tsx#starts isIdle, then mutate() drives isPending -> isSuccess with data set"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useRunInsights.test.tsx#lands isError with error.status === 502 on a thrown 502, and a second mutate() re-runs"
        status: pass
      - kind: unit
        ref: "frontend/src/hooks/useRunInsights.test.tsx#never calls queryClient.invalidateQueries, on success or on failure (RES-05 isolation)"
        status: pass
    human_judgment: false

# Metrics
duration: 3min
completed: 2026-07-20
status: complete
---

# Phase 04 Plan 03: Results/Insights Query Hooks Summary

**Three TanStack Query hooks (useRun, useRunResult, useRunInsights) implementing D-12's gated dependent-query chain and RES-05's structurally isolated insight mutation, each following an in-repo analog exactly.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-20T03:55:00+07:00
- **Completed:** 2026-07-20T03:57:40+07:00
- **Tasks:** 2
- **Files modified:** 6 (all new)

## Accomplishments
- `useRun(runId)`: ungated `useQuery` on `["run", runId]` — the first, always-resolving fetch in the Results status chain (D-12).
- `useRunResult(runId, { enabled })`: dependent `useQuery` on `["run", runId, "result"]`, gated by `enabled` so it never fires before the run is `COMPLETED`, keeping the deep-linkable route from ever hitting the pre-`COMPLETED` 409.
- `useRunInsights(runId)`: `useMutation` over `getRunInsights` with no `queryClient`/invalidation reference at all — a 502 there is structurally unable to touch the `["run", ...]` cache (RES-05), while `isIdle`/`isPending`/`isError`/`mutate()` gives the D-13 retry affordance for free.

## Task Commits

Each task followed RED -> GREEN TDD:

1. **Task 1: useRun + useRunResult** — `1f8b149` (test, RED) -> `aaa4a4b` (feat, GREEN)
2. **Task 2: useRunInsights** — `a5e0acf` (test, RED) -> `2a9d934` (feat, GREEN)

## TDD Gate Compliance

Both tasks show a `test(...)` commit (RED, tests failing on missing hook import) followed by a `feat(...)` commit (GREEN, all tests passing) — no REFACTOR commit was needed (no cleanup required after either GREEN pass).

## Files Created/Modified
- `frontend/src/hooks/useRun.ts` — ungated `useQuery(["run", runId])` over `getRun`
- `frontend/src/hooks/useRun.test.tsx` — asserts immediate fetch and isError propagation
- `frontend/src/hooks/useRunResult.ts` — gated `useQuery(["run", runId, "result"])` over `getRunResult`, `enabled` option
- `frontend/src/hooks/useRunResult.test.tsx` — asserts no fetch while `enabled:false`, fetch + isError while `enabled:true`
- `frontend/src/hooks/useRunInsights.ts` — `useMutation` over `getRunInsights`, no cache write
- `frontend/src/hooks/useRunInsights.test.tsx` — asserts idle/pending/success transition, 502 isError + retry, and zero `invalidateQueries` calls

## Decisions Made
- Followed 04-PATTERNS.md's prescribed code blocks for all three hooks verbatim (structure), with header comments explaining the D-12 gate and RES-05 isolation rationale (mirroring `useOverrides.ts`/`useTriggerRun.ts`'s existing header-comment convention).
- `useRunInsights.ts`'s header comment was worded to avoid the literal tokens `queryClient`/`invalidateQueries` appearing anywhere in the file (even in prose), satisfying the plan's grep-based acceptance criterion (`grep -c "invalidateQueries\|queryClient"` == 0) while still documenting the deliberate omission.

## Deviations from Plan

None — plan executed exactly as written. One environment-only adjustment (not a code deviation): the git worktree this plan executed in had no `frontend/node_modules` (worktrees don't carry `node_modules`, which is gitignored); a directory junction to the main checkout's `frontend/node_modules` was created locally to run `vitest`/`tsc`. This is a local dev-environment link only, not a repo change — nothing was added to git, and no lockfile or dependency changed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `useRun`, `useRunResult`, and `useRunInsights` are ready for consumption: `useRunResult`'s `enabled` is meant to be wired by `ResultsView` (plan 04-07) to `runQuery.data?.status === "COMPLETED"`; `useRunInsights` is meant to be consumed by `InsightPanel` (plan 04-06).
- No blockers for downstream plans in this wave.

---
*Phase: 04-results-insights*
*Completed: 2026-07-20*
