---
phase: 03-run-execution-history
reviewed: 2026-07-19T00:00:00Z
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
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-19T00:00:00Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Reviewed the Run Execution & History feature (RUN-01..RUN-05): the trigger
button, the polling list hook, the in-flight panel, the status label, the
history table, the `formatTimestamp`/`runStatus` utilities, and their
composition in `RunHistory.tsx`. XSS is correctly mitigated (text-only
rendering, verified by dedicated tests), no secrets or dangerous APIs are
present, and the `["runs", scenarioId]` query-key contract between
`useRuns`/`useTriggerRun` is byte-identical as documented.

The most significant issue is a genuine gap in the "prevent duplicate
in-flight run submissions" guarantee: the header `TriggerRunButton` disables
correctly, but `RunHistoryTable`'s own empty-state "Run Scenario" CTA — wired
to the exact same mutation — has no disabled/pending guard at all, and the
header button itself has a real (if narrower) race window around the same
guarantee. There's also a latent polling-termination bug in
`isTerminalStatus`'s hardcoded enumeration, plus accessibility and edge-case
gaps below.

## Critical Issues

### CR-01: Table's empty-state "Run Scenario" button has no guard against duplicate submission

**File:** `frontend/src/components/runs/RunHistoryTable.tsx:96-98`
**File:** `frontend/src/routes/RunHistory.tsx:61-65`
**Issue:** `RunHistory.tsx` renders two independent "Run Scenario"
affordances that both call the *same* `trigger.mutate()` from one
`useTriggerRun` instance:

1. The header `TriggerRunButton` (`RunHistory.tsx:52-58`), which disables
   while `trigger.isPending` or `runInProgress` is true
   (`TriggerRunButton.tsx:34`).
2. `RunHistoryTable`'s empty-state CTA:
   ```tsx
   <Button type="button" onClick={onTriggerRun}>
     Run Scenario
   </Button>
   ```
   This button has **no `disabled` prop at all**. `RunHistory.tsx` passes it
   nothing but the callback (`onTriggerRun={() => trigger.mutate()}` at
   `RunHistory.tsx:64`) — `RunHistoryTable` has no visibility into
   `trigger.isPending` or `runInProgress` whatsoever (it only receives
   `runsQuery`).

The empty state (`runs.length === 0`) is exactly the state visible during the
*entire* window between a user's first click and the invalidated
`["runs", scenarioId]` query's refetch resolving with the new run — because
until that refetch lands, `runsQuery.data` is still `[]`. During that whole
window the button stays fully clickable, with no spinner and no disabled
state, so repeated clicks (or a fast double-click, a common user habit) fire
multiple `POST /scenarios/{scenario_id}/runs` calls — `useMutation`'s
`mutate()` does not de-dupe concurrent calls. This directly undermines the
single-active-run invariant the rest of the feature was built to preserve
(`hasActiveRun`, the header's `runInProgress` guard) and can enqueue multiple
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

`hasActiveRun`, `useRuns`'s `refetchInterval` predicate, and
`RunInFlightPanel`'s render guard all rely on this function to decide when to
stop polling. Because it enumerates the two *terminal* literals rather than
the *active* ones, any future/unexpected status string that isn't one of the
four known values (e.g. a backend `CANCELLED` or `TIMED_OUT` state added
later) is silently treated as non-terminal: `hasActiveRun` keeps returning
`true` for that run forever, `useRuns` polls every 2s indefinitely with no way
to stop, and `RunInFlightPanel` renders nothing for it (since `COPY` has no
entry) — so the UI shows no run in progress while quietly polling forever in
the background. No test exercises an "unknown status" case here (the sibling
`runStatusMeta`/`RunStatusLabel` fallback tests only cover *rendering* of an
unknown status, not the polling-termination behavior).
**Fix:** Invert to a safer default — treat "not a known active status" as
terminal, so unknown values stop polling instead of polling forever:

```ts
const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

export function isTerminalStatus(status: string): boolean {
  return !ACTIVE_STATUSES.has(status);
}
```

### WR-02: Header `TriggerRunButton` has a race window where it re-enables before the new run is visible

**File:** `frontend/src/components/runs/TriggerRunButton.tsx:34`
**File:** `frontend/src/routes/RunHistory.tsx:43,52-58`
**Issue:** `disabled = isLoadingList || runInProgress || isPending` combines
`trigger.isPending` (true only while the POST itself is in flight) with
`runInProgress` (derived from `runsQuery.data`, which only reflects the new
PENDING run once the invalidated query's refetch has resolved). Between the
moment the mutation resolves (`isPending` flips back to `false`) and the
moment the invalidated `["runs", scenarioId]` refetch completes
(`runInProgress` flips to `true`), neither guard is active, and
`isLoadingList` (`runsQuery.isLoading`) only reflects the *initial* load, not
this background refetch — so the button is briefly re-enabled and clickable,
allowing a second duplicate trigger in that gap. Narrower than CR-01 (smaller
window, same root cause) but real.
**Fix:** Also gate on the query's fetching state so the button stays disabled
through the full round trip:

```tsx
isLoadingList={runsQuery.isLoading || runsQuery.isFetching}
```

### WR-03: Clickable table row has no interactive ARIA role or accessible name

**File:** `frontend/src/components/runs/RunHistoryTable.tsx:119-129`
**Issue:** Each `TableRow` is made mouse- and keyboard-activatable
(`tabIndex={0}`, `onClick`, `onKeyDown` for Enter/Space) to navigate to the
run detail page, but it keeps the implicit ARIA `row` role with no
`aria-label`/`aria-describedby`. Screen-reader users tabbing through the
table (or browsing it in table-navigation mode) get no indication that
activating a row navigates anywhere — the only way to reach a run's detail
view from this table is effectively invisible to assistive technology.
**Fix:** Add `role="button"` plus a descriptive `aria-label` per row, e.g.:

```tsx
<TableRow
  role="button"
  aria-label={`View run ${run.id} details`}
  tabIndex={0}
  ...
```

## Info

### IN-01: Unchecked `scenarioId as string` casts bypass a real possibly-undefined type

**File:** `frontend/src/routes/RunHistory.tsx:38-40`
**Issue:** `useParams()` types `scenarioId` as `string | undefined`; both
`useRuns(scenarioId as string)` and `useTriggerRun(scenarioId as string)`
silence that with a cast rather than a runtime guard. In the shipped route
tree this route only mounts under `scenarios/:scenarioId/runs`, so it's
defined in practice today, but the cast means a future routing change could
silently call `listRuns(undefined)` (building `/scenarios/undefined/runs`)
with no compiler signal.
**Fix:** Guard explicitly, matching the 404-gate convention used elsewhere
(e.g. `Editor`):

```tsx
const { scenarioId } = useParams<{ scenarioId: string }>();
if (!scenarioId) return null;
```

### IN-02: `formatTimestamp` renders backend UTC time with no timezone indicator

**File:** `frontend/src/lib/formatTimestamp.ts:23-30`
**Issue:** The backend stamps `datetime.now(timezone.utc)`, and this helper
slices the UTC wall-clock portion verbatim (deliberately, to stay
locale/timezone-deterministic for tests). The rendered `"YYYY-MM-DD HH:MM"`
carries no "UTC" marker, so a user outside UTC could reasonably read
Created/Started/Finished as their own local time, which it is not.
**Fix:** Consider a fixed suffix — `` `${date} ${hhmm} UTC` `` — which stays
just as deterministic while removing the implicit-local-time misread.

### IN-03: Empty-string `run.error` is indistinguishable from a missing error

**File:** `frontend/src/components/runs/RunHistoryTable.tsx:135`
**Issue:** `{run.error || FAILED_NO_ERROR_COPY}` treats `run.error === ""`
identically to `null`/`undefined`, substituting the generic fallback copy for
a (theoretically possible) present-but-empty error string.
**Fix:** Use an explicit nullish check if the distinction ever matters:
`{run.error ? run.error : FAILED_NO_ERROR_COPY}` is equivalent to today's
behavior — to actually preserve an empty string, use
`{run.error != null ? run.error : FAILED_NO_ERROR_COPY}` (or confirm/comment
that the backend contract guarantees `error` is never `""`).

---

_Reviewed: 2026-07-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
