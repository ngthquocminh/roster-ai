---
phase: 04-results-insights
reviewed: 2026-07-20T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - frontend/src/components/results/DemandVsServedChart.tsx
  - frontend/src/components/results/DemandVsServedChart.test.tsx
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** clean

## Summary

This review supersedes the prior broader 04-REVIEW.md, narrowing scope to the two files touched by gap-closure plan 04-08 (UAT gap G-04-4: `DemandVsServedChart` needed an honest empty-state instead of a blank axes-only chart when `coverage_by_function` is `{}`). The other 33 files previously reviewed in this phase are out of scope for this pass and were not re-read.

Diff against base `031f7be` is small and self-contained: an early-return guard on `data.length === 0` rendering an empty-state message, plus one new render test asserting the message appears and no `<svg>` is mounted.

Traced the fix end-to-end:
- `toChartData({})` correctly returns `[]` (pure `Object.entries` map, unit-tested).
- The guard triggers on the *mapped* array length, not the raw prop, so a non-empty map whose entries carry `null` `required_h`/`served_h` still falls through to the real chart (correctly exercised by the existing "mounts without throwing when a function's values are null" test) — this preserves the distinction between "no functions at all" (empty state) and "functions present but values not computed" (chart + "Not computed" tooltip), which is the exact distinction G-04-4 required.
- Checked the backend contract (`backend/domain/result.py:31`, `backend/services/serialize.py:29-33`) to confirm `coverage_by_function` is always serialized as a dict (`default_factory=dict`), never `null` — so `toChartData`'s unguarded `Object.entries(coverageByFunction)` call cannot throw on a real API response; this isn't a residual risk introduced or left open by this change.
- The empty-state JSX (`flex flex-col items-center gap-2 py-16 text-center` wrapper + `text-sm leading-[1.5] text-muted-foreground` message) is byte-for-byte the same pattern used in `ScheduleTable.tsx`'s zero-state guard, matching the stated intent in the code comment ("mirroring ScheduleTable.tsx's zero-state guard").
- The new test correctly scopes its `container.querySelector("svg")` assertion to the isolated render output, and correctly asserts on the exact empty-state copy exported as `EMPTY_COVERAGE_COPY`.

No Critical or Warning issues found. Two Info-level observations below, neither blocking.

## Info

### IN-01: Empty-state markup duplicated across six components

**File:** `frontend/src/components/results/DemandVsServedChart.tsx:84-90`
**Issue:** The `flex flex-col items-center gap-2 py-16 text-center` + `text-sm leading-[1.5] text-muted-foreground` empty-state block is now duplicated verbatim in six files (`DemandVsServedChart.tsx`, `ScheduleTable.tsx`, `RunHistoryTable.tsx`, `ScenarioHeader.tsx`, `OverridesList.tsx`, `ScenarioTable.tsx`). This particular occurrence intentionally mirrors the established convention (per its own code comment), so it isn't a new defect introduced by this change — but the convention itself has never been extracted into a shared component, so any future styling change (e.g. adjusting `py-16` or the text color token) requires six synchronized edits.
**Fix:** Not required for this gap-closure. Consider a shared `<EmptyState message={...} />` component in `components/ui/` the next time one of these six call sites is touched, to collapse the duplication.

### IN-02: Tooltip formatter's non-bar-key branch is currently unreachable

**File:** `frontend/src/components/results/DemandVsServedChart.tsx:117-124`
**Issue:** `formatter`'s `key ? ... : ...` fallback branches (using `name`/`value` directly instead of `chartConfig[key].label`/`*_raw`) can only execute if `isBarKey(name)` is `false`. Since the chart renders exactly two `<Bar>` elements with `dataKey="required_h"` and `dataKey="served_h"`, Recharts will only ever invoke this formatter with `name` equal to one of those two keys, making the fallback dead code today.
**Fix:** No action needed now — it's reasonable defensive code if a third `<Bar>` is ever added — but if it stays permanently unreachable, a one-line comment noting it's forward-looking guard code (rather than tested behavior) would save a future reviewer the trace.

---

_Reviewed: 2026-07-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
