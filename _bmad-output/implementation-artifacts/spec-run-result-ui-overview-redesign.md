---
title: 'Run result UI: overview-first layout, schedule table, gap statistics, debug-only provenance'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_commit: 'bb1f7af730ab746ab94ec40248cd734aa455f21f'
review_loop_iteration: 0
context:
  - '{project-root}/docs/DOMAIN-MODEL.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The run result page (`ScenarioResults.tsx`) leads with the comparison, renders the candidate schedule as a bullet list of raw IDs, dumps "Unresolved gaps" as one long list of record IDs, and shows the full Decision provenance timeline and a raw Evidence ID list to planners although both are debug data.

**Approach:** Reorder to overview (KPIs + charts + gap statistics) first, then the candidate schedule as a table, then the baseline comparison. Replace the gap list with statistics. Move provenance and the Evidence reference list into a collapsed "Debug details" panel at the bottom (provenance lazily loaded).

## Boundaries & Constraints

**Always:** Derive types from the generated OpenAPI schema (no hand-written API interfaces). Overview/gap numbers come from the candidate `MetricSet` (works with or without a comparison). Show worker/task names via `useWorkerNameMap`/`useTaskNameMap`, falling back to raw IDs; IDs stay copyable (`IdentifierCopyButton`). Text/labels never colour alone (Accessibility Floor). Approval request behaviour, fail-closed pending logic, and stale/unavailable messaging are preserved. Cite `docs/DOMAIN-MODEL.md` rather than re-deriving demand family/unit rules; coverage is in minutes, headcount questions are not answered here.

**Ask First:** Any backend/API change; adding a dependency.

**Never:** No new backend fields. No changes to `ProvenanceTimeline` internals, approvals, progress, or terminal-outcome cards. No recharts/new chart lib (charts are accessible CSS bars). No manual assistive-tech verification work.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Completed + comparison | candidate + comparison | Order: Overview → Candidate schedule table → Comparison → Debug details (Evidence + Provenance) | N/A |
| Comparison unavailable | candidate, `comparison: null` | Same Overview + table; unavailable alert stays; approval button uses result's baseline version; no Comparison section | N/A |
| No gaps | every interval served >= required | Gap card says "No unresolved gaps" with coverage %; no table | N/A |
| Many gaps | 300 under-served intervals | Count, % of intervals, total shortfall hours, size-bucket bars, top-5 worst intervals only | N/A |
| Zero required | required total = 0 | Coverage shows "—", never NaN | N/A |
| Many assignments | 200 rows | Table sorted by worker then start, paginated 25/page with prev/next | N/A |
| No assignments | `[]` | "No assignments" | N/A |
| Name lookup fails | name-map query errors | Raw IDs render | Silent fallback |
| Debug details | page load | Collapsed; provenance not fetched until expanded; then Evidence list plus existing provenance loading/error/retry/timeline states | Retry button as today |

</frozen-after-approval>

## Code Map

- `frontend/src/routes/ScenarioResults.tsx` -- page composition; duplicated candidate blocks and inline provenance section
- `frontend/src/components/run-results/ComparisonSummary.tsx` -- currently holds approval button, version IDs, deltas, diff, constraints, warnings, gaps
- `frontend/src/hooks/useRunProvenance.ts` -- add optional `enabled`
- `frontend/src/hooks/useScenarioProjection.ts` -- `useWorkerNameMap`, `useTaskNameMap` (reuse)
- `frontend/src/lib/formatShiftWindow.ts` -- `formatMinuteWindow` (reuse)
- `frontend/src/components/ui/table.tsx`, `collapsible.tsx` -- reuse
- `frontend/src/routes/ScenarioResultsWorkspace.test.tsx`, `components/run-results/ComparisonSummary.test.tsx`, `test/stateMatrix.tsx` -- tests/fixtures to update

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/lib/coverageStats.ts` (+ `.test.ts`) -- pure `summarizeCoverage(metrics)`: coverage %, unresolved count/total intervals, shortfall minutes, size buckets (<30m, 30–60m, 1–2h, >2h), top-5 worst, per-function required/served/% -- one tested source for all overview numbers
- [x] `frontend/src/components/run-results/RunOverview.tsx` (+ test) -- header with candidate/baseline versions and Request approval (moved from ComparisonSummary, same fail-closed props), KPI tiles (coverage %, unresolved intervals, assignments, workers, cost, overtime), coverage-by-function bars, scheduled-hours-per-day bars, gap statistics card
- [x] `frontend/src/components/run-results/CandidateScheduleTable.tsx` (+ test) -- table (Worker, Task, Shift, Window, Duration), name resolution, sort, pagination
- [x] `frontend/src/components/run-results/ComparisonSummary.tsx` (+ test update) -- drop approval button/versions/gaps; keep diff, metric deltas, constraints, warnings
- [x] `frontend/src/hooks/useRunProvenance.ts` -- `enabled` option
- [x] `frontend/src/features/provenance/DebugDetailsPanel.tsx` (+ test) -- collapsed Collapsible wrapping the Evidence reference list (moved from the page, same `group: record_id` items and "No evidence references" empty text) and existing provenance states/timeline; provenance fetches on first expand
- [x] `frontend/src/routes/ScenarioResults.tsx` -- unify candidate branches; new order; remove inline Evidence section; use panel; update `ScenarioResultsWorkspace.test.tsx` and `stateMatrix.tsx`

**Acceptance Criteria:**
- Given a completed run, when the page renders, then Overview (KPIs, charts, gap stats) precedes the schedule table, which precedes the comparison.
- Given 300 unresolved intervals, when rendered, then no list of 300 IDs appears; only counts, buckets, and top 5.
- Given the page loads, when Debug details is collapsed, then no provenance request is made; when expanded, provenance loads and the existing retry/timeline behaviour works.
- Given comparison unavailable, when rendered, then Overview and table render and Request approval remains fail-closed.
- `npm run typecheck`/`lint`/`test` pass.

## Design Notes

Gap IDs are opaque demand-row IDs with no day/family, so statistics use magnitude (served vs required minutes), not per-ID detail. The server-side unresolved rule is `served < required`; `summarizeCoverage` applies the same rule to the same metrics, so counts match `unresolved_gap_record_ids`. Bars: `role="img"` with an `aria-label` stating the numbers, plus visible text values.

## Verification

**Commands:**
- `cd frontend && npm run test -- --run` -- expected: all pass
- `cd frontend && npx tsc --noEmit && npm run lint` -- expected: clean

**Manual checks (if no CLI):**
- Run dev server, open a completed run's Results: check layout order, table, gap stats, collapsed Debug details.

## Suggested Review Order

**Page composition**

- Single completed branch replaces two duplicated blocks; new order lives here.
  [`ScenarioResults.tsx:59`](../../frontend/src/routes/ScenarioResults.tsx#L59)

- Debug panel always mounted at bottom; evidence falls back to candidate refs.
  [`ScenarioResults.tsx:92`](../../frontend/src/routes/ScenarioResults.tsx#L92)

**Overview and gap statistics**

- One pure source for coverage, gap buckets, and top-5 worst intervals.
  [`coverageStats.ts:38`](../../frontend/src/lib/coverageStats.ts#L38)

- KPIs, CSS-bar charts, gap card; approval controls moved here unchanged.
  [`RunOverview.tsx:24`](../../frontend/src/components/run-results/RunOverview.tsx#L24)

**Schedule table**

- Name-resolved, sorted, paginated table replaces the bullet list.
  [`CandidateScheduleTable.tsx:18`](../../frontend/src/components/run-results/CandidateScheduleTable.tsx#L18)

**Debug-only data**

- Collapsed panel; provenance fetches only after first open.
  [`DebugDetailsPanel.tsx:15`](../../frontend/src/features/provenance/DebugDetailsPanel.tsx#L15)

- `enabled` gate enabling lazy fetch.
  [`useRunProvenance.ts:8`](../../frontend/src/hooks/useRunProvenance.ts#L8)

**Comparison and tests**

- Comparison trimmed to diff, deltas, constraints, warnings.
  [`ComparisonSummary.tsx:22`](../../frontend/src/components/run-results/ComparisonSummary.tsx#L22)

- Route-level expectations: table, names, overview, expand-to-see provenance.
  [`ScenarioResultsWorkspace.test.tsx:1`](../../frontend/src/routes/ScenarioResultsWorkspace.test.tsx#L1)
