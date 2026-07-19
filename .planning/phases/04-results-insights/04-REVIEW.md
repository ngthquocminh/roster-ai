---
phase: 04-results-insights
reviewed: 2026-07-20T05:05:00Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - docs/API.md
  - frontend/package-lock.json
  - frontend/package.json
  - frontend/src/App.tsx
  - frontend/src/api/insights.test.ts
  - frontend/src/api/insights.ts
  - frontend/src/api/results.test.ts
  - frontend/src/api/results.ts
  - frontend/src/api/runs.test.ts
  - frontend/src/api/runs.ts
  - frontend/src/components/results/CoverageByDayTable.test.tsx
  - frontend/src/components/results/CoverageByDayTable.tsx
  - frontend/src/components/results/CoverageSummary.test.tsx
  - frontend/src/components/results/CoverageSummary.tsx
  - frontend/src/components/results/DemandVsServedChart.test.tsx
  - frontend/src/components/results/DemandVsServedChart.tsx
  - frontend/src/components/results/InsightPanel.test.tsx
  - frontend/src/components/results/InsightPanel.tsx
  - frontend/src/components/results/ScheduleTable.test.tsx
  - frontend/src/components/results/ScheduleTable.tsx
  - frontend/src/components/results/WarningsBanner.test.tsx
  - frontend/src/components/results/WarningsBanner.tsx
  - frontend/src/components/ui/card.tsx
  - frontend/src/components/ui/chart.tsx
  - frontend/src/components/ui/tooltip.tsx
  - frontend/src/hooks/useRun.test.tsx
  - frontend/src/hooks/useRun.ts
  - frontend/src/hooks/useRunInsights.test.tsx
  - frontend/src/hooks/useRunInsights.ts
  - frontend/src/hooks/useRunResult.test.tsx
  - frontend/src/hooks/useRunResult.ts
  - frontend/src/lib/formatShiftWindow.test.ts
  - frontend/src/lib/formatShiftWindow.ts
  - frontend/src/routes/ResultsView.test.tsx
  - frontend/src/routes/ResultsView.tsx
  - frontend/src/routes/router.test.tsx
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-20T05:05:00Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

This is a retry of a review that timed out mid-run. The previously-confirmed bug
(`CoverageByDayTable` rendering the raw `coverage_by_day` fraction with a bare
`%` instead of scaling by 100) is already fixed in commit `1409e8f` — verified
the fix is correct: `formatCoveragePct` multiplies by 100, rounds to one
decimal, and strips a trailing `.0`, matching the `CoverageByDayTable.test.tsx`
expectations (`0.612 → "61.2%"`, `0.88 → "88%"`).

Per the retry instructions, I specifically hunted for the same class of bug
(wire-contract fraction/percentage confusion) elsewhere in the reviewed files.
`docs/API.md` documents both `coverage_by_day` and `coverage_by_function.pct`
as fractions in `[0, 1]`. `DemandVsServedChart` never renders `pct` at all (it
only plots `required_h`/`served_h` in hours), so there is no second production
scaling bug of that class in this file set — confirmed via `grep` for
`.pct`/`* 100`/`toFixed` across `frontend/src`.

However, I found and reproduced (with a throwaway rerender test, since
deleted) a real, unrelated correctness bug in `InsightPanel`/`useRunInsights`:
navigating between two different runs' results pages without a full remount
(the normal React Router behavior when only the `:runId` path param changes)
leaves the previous run's cached LLM insight report displayed under the new
run's heading, with no indication it is stale. I also found that
`ResultsView.test.tsx`'s `RUN_RESULT` fixture uses percent-scale values
(`95`, `100`) for `coverage_by_day`/`coverage_by_function.pct` instead of the
real fraction scale (`0.95`, `1.0`) documented in `docs/API.md`, and never
asserts on the rendered percentage text — so this integration test would not
have caught the original `CoverageByDayTable` bug, nor would it catch a
regression of it.

`npx tsc --noEmit -p tsconfig.app.json` and `npx oxlint src` were both run
directly (not relying on any executor self-report) and came back clean; the
full Phase 4 test subset (104 tests) passes. None of that gives the
`InsightPanel` staleness bug coverage — it is a cross-render lifecycle issue,
not a type or lint issue, and no test in the suite rerenders a results-view
component with a changed `runId` while already-fetched mutation state exists.

## Critical Issues

### CR-01: InsightPanel shows a stale/wrong-run insight report when navigating between runs without a full remount

**File:** `frontend/src/components/results/InsightPanel.tsx:26-27`, `frontend/src/hooks/useRunInsights.ts:21-25`, `frontend/src/routes/ResultsView.tsx:138`

**Issue:** `ResultsView` mounts at the route `scenarios/:scenarioId/runs/:runId`
(`frontend/src/App.tsx:55`). React Router does **not** remount the matched
route component when only a path param changes (e.g. the user goes back to
run history and opens a different completed run, or the app later grows a
"next run" / "previous run" link) — it re-renders the same `ResultsView`
instance with a new `runId`. `InsightPanel` is rendered as
`<InsightPanel runId={runId as string} />` with no `key`, so it also is not
remounted; its `useRunInsights(runId)` hook returns a `useMutation` object
whose internal state (`data`, `isSuccess`, etc.) is **not** keyed by `runId` —
unlike `useRun`/`useRunResult`, which use TanStack Query with `runId` baked
into the query key and therefore correctly reset per run. Because
`useRunInsights` never calls `.reset()` when `runId` changes, a previously
fetched `{ ready: true, report: "..." }` for run A remains `isSuccess: true`
after the component re-renders for run B, so `InsightPanel` immediately
renders run A's report text under run B's "Insight Report" heading —
attributing one run's LLM-generated cost/coverage narrative to a completely
different run, with no visual indication it's stale.

Reproduced directly: rendering `<InsightPanel runId="r1" />`, successfully
fetching an insight, then `rerender(<InsightPanel runId="r2" />)` (simulating
the exact re-render React Router performs on a param-only navigation) leaves
`"REPORT FOR R1"` still in the DOM with zero fetches issued for `r2`.

**Fix:** Force a remount on run change (simplest, matches the "structurally
isolated" intent already documented for this component), or reset the
mutation explicitly:

```tsx
// frontend/src/routes/ResultsView.tsx
<InsightPanel key={runId} runId={runId as string} />
```

or, inside `InsightPanel.tsx`:

```tsx
import { useEffect } from "react";
// ...
const insights = useRunInsights(runId);
useEffect(() => {
  insights.reset();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [runId]);
```

Add a regression test (rerendering `InsightPanel` with a new `runId` after a
successful fetch, asserting the previous report is no longer shown and the
idle "Get Insight Report" button reappears) so this can't silently regress.

## Warnings

### WR-01: `ResultsView.test.tsx`'s `RUN_RESULT` fixture uses percent-scale numbers for fraction fields, and never asserts the rendered percentage

**File:** `frontend/src/routes/ResultsView.test.tsx:119-124`

**Issue:** `docs/API.md` documents `coverage_by_function.pct` and
`coverage_by_day` as fractions in `[0, 1]` (`"pct": 0.354`,
`"coverage_by_day": {"0": 0.61, ...}`), matching `CoverageStat.pct` and the
already-fixed `formatCoveragePct` scaling logic. This test's fixture instead
uses percent-scale values:

```ts
coverage_by_function: {
  Pick: { required_h: 40, served_h: 38, pct: 95 },
  Receiving: { required_h: 10, served_h: 10, pct: 100 },
},
coverage_by_day: { "0": 95, "1": 100 },
```

Fed through the real `CoverageByDayTable`/`formatCoveragePct` code path, `95`
renders as `"9500%"` and `100` as `"10000%"` — but the test only asserts
`screen.getByText("Day 1")` (the label), never the percentage cell text. This
means the fixture is silently contract-inconsistent, and this integration
test provides zero regression coverage for the exact class of bug this file
was fixing (it would pass identically whether `formatCoveragePct` scales
correctly, doesn't scale at all, or scales by the wrong factor). `pct` isn't
rendered by `DemandVsServedChart` so that half is inert, but the
`coverage_by_day` half is live and asserted against a label only, not a value.

**Fix:** Use fraction-scale values matching the real contract, and assert the
rendered percentage text:

```ts
coverage_by_day: { "0": 0.95, "1": 1.0 },
// ...
expect(screen.getByText("95%")).toBeInTheDocument();
expect(screen.getByText("100%")).toBeInTheDocument();
```

### WR-02: `WarningsBanner` uses the raw warning string as the React list key

**File:** `frontend/src/components/results/WarningsBanner.tsx:31-33`

**Issue:** `warnings.map((warning) => <p key={warning}>{warning}</p>)` keys
each row by its own text content. `SolveResult.warnings` is backend-generated
prose (e.g. per-family "has real demand but zero served hours" lines) — if
the solver ever emits the identical warning string twice in one run's
`warnings` array (plausible if two independent code paths produce the same
templated sentence for the same condition), React will warn about duplicate
keys in the console and is not guaranteed to keep both `<p>` elements
distinct/stable across re-renders.

**Fix:** Key by index instead, since this list is never reordered or
filtered client-side:

```tsx
{warnings.map((warning, i) => (
  <p key={i}>{warning}</p>
))}
```

## Info

### IN-01: `DemandVsServedChart.test.tsx` also uses out-of-contract `pct` values, with no functional effect

**File:** `frontend/src/components/results/DemandVsServedChart.test.tsx:17-18,55-56`

**Issue:** Fixtures use `pct: 80`, `pct: 100` (percent-scale) rather than the
documented `[0, 1]` fraction scale. This has no functional impact today since
`toChartData`/`DemandVsServedChart` never read `pct` (only `required_h` /
`served_h` are used), so it's not a live bug — but it's the same fixture-data
drift pattern as WR-01, and would become a real gap the moment any future
change starts rendering `pct` from this chart's data.

**Fix:** Use fraction-scale `pct` values in these fixtures for contract
consistency with `docs/API.md`, even though they're currently unused by the
component under test.

---

_Reviewed: 2026-07-20T05:05:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
