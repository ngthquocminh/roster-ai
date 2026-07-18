---
phase: 03-run-execution-history
reviewed: 2026-07-18T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - frontend/src/App.tsx
  - frontend/src/api/runs.test.ts
  - frontend/src/api/runs.ts
  - frontend/src/components/runs/RunHistoryTable.test.tsx
  - frontend/src/components/runs/RunHistoryTable.tsx
  - frontend/src/components/runs/RunInFlightPanel.test.tsx
  - frontend/src/components/runs/RunInFlightPanel.tsx
  - frontend/src/components/runs/RunStatusLabel.test.tsx
  - frontend/src/components/runs/RunStatusLabel.tsx
  - frontend/src/components/runs/TriggerRunButton.test.tsx
  - frontend/src/components/runs/TriggerRunButton.tsx
  - frontend/src/hooks/useRuns.test.tsx
  - frontend/src/hooks/useRuns.ts
  - frontend/src/hooks/useTriggerRun.test.tsx
  - frontend/src/hooks/useTriggerRun.ts
  - frontend/src/lib/formatTimestamp.test.ts
  - frontend/src/lib/formatTimestamp.ts
  - frontend/src/lib/runStatus.test.ts
  - frontend/src/lib/runStatus.ts
  - frontend/src/routes/RunHistory.test.tsx
  - frontend/src/routes/RunHistory.tsx
  - frontend/src/routes/router.test.tsx
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-18T00:00:00Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Reviewed the Run Execution & History feature (RUN-01..RUN-05): the trigger
button, the polling list hook, the in-flight panel, the history table, and
their composition in `RunHistory.tsx`. The code is generally careful — XSS is
correctly mitigated (text-only rendering, verified by tests), no secrets or
dangerous APIs are present, the `["runs", scenarioId]` query-key contract
between `useRuns`/`useTriggerRun` is consistent, and the loading/error/empty
state machine mirrors existing patterns in the codebase.

The most significant issue is a genuine gap in the "prevent duplicate
in-flight run submissions" guarantee that the header `TriggerRunButton`
implements correctly but that `RunHistoryTable`'s own empty-state CTA does
not — the two "Run Scenario" affordances are wired to the same mutation but
only one of them respects `trigger.isPending`/`runInProgress`. There's also a
narrower defensive-coding smell in `isTerminalStatus` that hardcodes the two
terminal literals rather than deriving "terminal" from "not one of the known
active statuses," which would silently break polling termination if the
backend ever introduces a new terminal status value.

## Critical Issues

### CR-01: Table's empty-state "Run Scenario" button is not guarded against duplicate submission while a trigger is in flight

**File:** `frontend/src/components/runs/RunHistoryTable.tsx:96-98`
**File:** `frontend/src/routes/RunHistory.tsx:61-65`

**Issue:**
`RunHistory.tsx` renders two independent "Run Scenario" affordances that both
call the *same* `trigger.mutate()` (from one `useTriggerRun` instance):

1. The header `TriggerRunButton` (`RunHistory.tsx:52-58`), which correctly
   disables while `trigger.isPending` or `runInProgress` is true
   (`TriggerRunButton.tsx:34`: `disabled = isLoadingList || runInProgress || isPending`).
2. `RunHistoryTable`'s empty-state CTA (`RunHistoryTable.tsx:96-98`):
   ```tsx
   <Button type="button" onClick={onTriggerRun}>
     Run Scenario
   </Button>
   ```
   This button has **no `disabled` prop at all**, and `RunHistory.tsx` passes
   it nothing but the callback (`onTriggerRun={() => trigger.mutate()}` at
   `RunHistory.tsx:64`) — `trigger.isPending` is never threaded through.

The empty state (`runs.length === 0`) is exactly the state that's visible
during the entire window between a user's first click and the invalidated
`["runs", scenarioId]` query's refetch resolving with the new PENDING run —
because until that refetch lands, `runsQuery.data` is still `[]`, so
`runInProgress` (derived from that same data in `RunHistory.tsx:43`) is still
`false` and the empty state keeps rendering. During that entire window the
table's button remains fully clickable with no spinner, no "Starting…" text,
and no disabled state, so a user (or an automated test/double-click) can fire
multiple `POST /scenarios/{id}/runs` calls before the first one's result is
visible anywhere. This directly undermines the "disabled-in-progress"
guarantee the header button implements (UI-SPEC E1) and can enqueue multiple
redundant runs against the single-worker solve pool.

**Fix:** Thread the mutation's pending/in-progress state into
`RunHistoryTable` and disable its CTA the same way the header button does:
```tsx
// RunHistoryTable.tsx
export function RunHistoryTable({
  runsQuery,
  scenarioId,
  onTriggerRun,
  triggerDisabled, // new
}: {
  runsQuery: UseQueryResult<RunOut[], unknown>;
  scenarioId: string;
  onTriggerRun?: () => void;
  triggerDisabled?: boolean;
}) {
  // ...
  <Button type="button" disabled={triggerDisabled} onClick={onTriggerRun}>
    Run Scenario
  </Button>
```
```tsx
// RunHistory.tsx
<RunHistoryTable
  runsQuery={runsQuery}
  scenarioId={scenarioId as string}
  onTriggerRun={() => trigger.mutate()}
  triggerDisabled={trigger.isPending || runInProgress}
/>
```

## Warnings

### WR-01: `isTerminalStatus` hardcodes terminal literals instead of deriving from known active statuses

**File:** `frontend/src/lib/runStatus.ts:42-44`

**Issue:**
```ts
export function isTerminalStatus(status: string): boolean {
  return status === "COMPLETED" || status === "FAILED";
}
```
`hasActiveRun`/`useRuns`'s `refetchInterval` predicate, and
`RunInFlightPanel`'s render guard, all depend on this function returning
`true` for every status that should stop polling. Because it enumerates the
two known terminal values rather than checking against the known *active*
values (`PENDING`/`RUNNING`), any future backend status that isn't one of the
four current literals (e.g. a new `CANCELLED` terminal state) is silently
treated as **non-terminal** — `hasActiveRun` would keep reporting `true`
forever for that run, `useRuns` would poll indefinitely, and
`RunInFlightPanel` would render nothing (since `COPY` has no entry for it)
while polling never terminates. This is a real latent bug with no test
coverage for an "unknown-but-terminal" status.

**Fix:** Invert the check so new unknown statuses default to terminal
(safer default — stop polling rather than poll forever) or explicitly
enumerate known active statuses:
```ts
const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

export function isTerminalStatus(status: string): boolean {
  return !ACTIVE_STATUSES.has(status);
}
```

### WR-02: Race window on the header `TriggerRunButton` between mutation success and query invalidation resolving

**File:** `frontend/src/components/runs/TriggerRunButton.tsx:34`
**File:** `frontend/src/routes/RunHistory.tsx:43,52-58`

**Issue:** `disabled = isLoadingList || runInProgress || isPending` uses
`trigger.isPending` (true only while the POST is in flight) and
`runInProgress` (derived from `runsQuery.data`, only becomes true once the
invalidated query's refetch resolves with the new PENDING/RUNNING run).
Between the moment `trigger.mutate()` resolves (`isPending` flips to
`false`) and the moment the invalidated `["runs", scenarioId]` refetch
completes and updates `runsQuery.data` (`runInProgress` flips to `true`),
neither guard is active and `isLoadingList` is also `false` (it only reflects
the *initial* load, not background refetches) — so the button is briefly
re-enabled and clickable again, allowing a second duplicate submission in
that gap. This is a narrower instance of the same underlying issue as CR-01.

**Fix:** Also gate on `runsQuery.isFetching` (which is `true` for the
invalidation-triggered background refetch, not just the initial load) so the
button stays disabled through the whole round trip:
```tsx
isLoadingList={runsQuery.isLoading || runsQuery.isFetching}
```

## Info

### IN-01: Clickable table rows lack an accessible role/name for their action

**File:** `frontend/src/components/runs/RunHistoryTable.tsx:119-130`

**Issue:** Each `TableRow` is made keyboard-interactive (`tabIndex={0}`,
`onKeyDown` for Enter/Space) and mouse-interactive (`onClick`) to navigate to
the run detail page, but it keeps the implicit ARIA `row` role with no
`aria-label`/`aria-describedby` indicating that activating it navigates
somewhere. Screen-reader users tabbing through the table have no indication
these rows are actionable beyond the (currently 404-only) `ResultsPlaceholder`
destination.

**Fix:** Add a descriptive `aria-label` per row, e.g.
`aria-label={`View run ${run.id} details`}`, or wrap the row's semantics with
`role="button"` alongside the existing `tabIndex`/`onKeyDown`.

### IN-02: Async error text has no live region

**File:** `frontend/src/components/runs/TriggerRunButton.tsx:56-58`

**Issue:** The error message (`"This scenario no longer exists."` /
`"Couldn't start the run. Try again."`) appears asynchronously after a failed
mutation but is a plain `<p>` with no `role="alert"`/`aria-live` attribute, so
assistive technology may not announce it when it appears.

**Fix:** Add `role="alert"` to the error `<p>`:
```tsx
{errorMessage && (
  <p role="alert" className="text-xs leading-[1.5] text-destructive">
    {errorMessage}
  </p>
)}
```

---

_Reviewed: 2026-07-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
