---
phase: 04-results-insights
verified: 2026-07-20T10:15:00Z
status: human_needed
score: 24/24 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "End-of-phase visual/interactive walkthrough of the composed ResultsView (batched per human_verify_mode=end-of-phase, per 04-07-PLAN.md Task 1's deferred <human-check>)."
    expected: "Run `npm run dev` in frontend/, trigger a run for a scenario to COMPLETED, open /scenarios/{id}/runs/{runId} and confirm: (1) coverage stat cards + (if any) warnings banner + by-day table render; (2) the demand-vs-served chart renders with visible grouped bars (not blank/0-height); (3) the schedule table scrolls with 'Day N, HH:MM–HH:MM' windows whose day numbers match the by-day table; (4) 'Get Insight Report' fetches a report or an honest not-ready/error; (5) deep-linking a PENDING/RUNNING run shows the in-flight panel and a FAILED run shows its error — never a blank screen."
    why_human: "Real Recharts height measurement, table scroll behavior, and a live LLM round trip cannot be verified via grep/unit tests (jsdom cannot measure ResponsiveContainer; per DemandVsServedChart's own test comment)."
  - test: "A single long warning string wraps inside WarningsBanner without breaking the page layout."
    expected: "No horizontal overflow or layout break for a long solver warning string."
    why_human: "Plan 04-04 explicitly tags this truth `verification: backstop` — visual/unverifiable at spec time, same class as Phase 3's long-text backstop items."
  - test: "CoverageByDayTable's rendering when coverage_by_day is empty on a COMPLETED run."
    expected: "An honest empty/absent state, not a broken or misleading render."
    why_human: "Plan 04-04 tags this `verification: backstop` — not confirmed against the engine whether SolveResult.metrics always populates coverage_by_day when scheduling occurs; reachability itself is unconfirmed."
  - test: "DemandVsServedChart's rendering when coverage_by_function is empty on a COMPLETED run."
    expected: "An honest empty/absent state, not a broken or misleading render."
    why_human: "Plan 04-05 tags this `verification: backstop` — same unconfirmed-reachability class as the coverage-by-day empty case."
  - test: "A very long insight report wraps/scrolls within the insight section without breaking the page layout."
    expected: "No horizontal overflow or layout break for a long LLM-generated report."
    why_human: "Plan 04-06 tags this `verification: backstop` — visual/unverifiable at spec time, same class as Phase 3's FAILED-error long-text backstop and E2's warnings long-text."
---

# Phase 04: Results & Insights Verification Report

**Phase Goal:** A user can read a completed run's schedule, coverage, and plain-language insight report.
**Verified:** 2026-07-20T10:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | recharts@3.9.x installed as sole new dep, via shadcn source-copy, gated by a recorded human approval | ✓ VERIFIED | `frontend/package.json:28` `"recharts": "^3.9.2"`; `card.tsx`/`chart.tsx`/`tooltip.tsx` present under `src/components/ui/`; approval recorded in `04-01-SUMMARY.md` "Legitimacy Gate Approval" section; single commit `fa0099e` for the install + version alignment |
| 2 | results.ts exports hand-written `RunResult` (incl. `warnings: string[]`) + `getRunResult`, one cast point | ✓ VERIFIED | `frontend/src/api/results.ts` exists; `results.test.ts` green; `docs/API.md:409` documents `warnings` |
| 3 | insights.ts exports `getRunInsights`, passes `InsightOut` through unmodified, throws `{status,...}` on error | ✓ VERIFIED | `frontend/src/api/insights.ts`; `insights.test.ts` green |
| 4 | runs.ts gains `getRun(runId)` (D-12 status probe) | ✓ VERIFIED | `frontend/src/api/runs.ts`; `runs.test.ts` green |
| 5 | formatShiftWindow converts hour-offsets to 1-indexed, cross-midnight-safe, round-once strings | ✓ VERIFIED | `frontend/src/lib/formatShiftWindow.ts`; `formatShiftWindow.test.ts` green |
| 6 | docs/API.md documents `warnings: string[]` on RunResult | ✓ VERIFIED | `docs/API.md:330,409` |
| 7 | useRun is an ungated query on `['run', runId]` | ✓ VERIFIED | `frontend/src/hooks/useRun.ts`; `useRun.test.tsx` green |
| 8 | useRunResult is a dependent query gated on `enabled`, key `['run', runId, 'result']`, never fetches when disabled | ✓ VERIFIED | `frontend/src/hooks/useRunResult.ts`; `useRunResult.test.tsx` green |
| 9 | useRunInsights is an isolated useMutation with no cache invalidation | ✓ VERIFIED | `frontend/src/hooks/useRunInsights.ts` (no `queryClient`/`invalidateQueries` — confirmed by direct read); `useRunInsights.test.tsx` green |
| 10 | Stat row renders two Cards (Total Cost, Total Unmet Hours), null → "Not computed" + Tooltip, never a currency zero | ✓ VERIFIED | `frontend/src/components/results/CoverageSummary.tsx` — `CostStat`/`UnmetHoursStat` each independently guard null via `NullableStat`; `CoverageSummary.test.tsx` green |
| 11 | Each stat card guards its own value independently (partial-null case) | ✓ VERIFIED | Same file — `CostStat`/`UnmetHoursStat` are separate components, each fed its own prop; test covers the partial case |
| 12 | WarningsBanner renders only when `warnings.length > 0`, one paragraph per string, neutral Alert + TriangleAlert | ✓ VERIFIED | `frontend/src/components/results/WarningsBanner.tsx`; returns `null` for empty array; `variant="default"` + `TriangleAlert`; `WarningsBanner.test.tsx` green |
| 13 | CoverageByDayTable renders 1-indexed "Day N" + `{value}%` or "Not computed", never duplicating the chart's by-function numbers | ✓ VERIFIED | `frontend/src/components/results/CoverageByDayTable.tsx` — `formatCoveragePct` scales the `[0,1]` fraction correctly (fixed in `1409e8f` after code review caught the raw-fraction bug); `CoverageByDayTable.test.tsx` green |
| 14 | DemandVsServedChart renders one grouped-bar pair per function, outline required / solid indigo served, `min-h-[280px]`, null → "Not computed" tooltip | ✓ VERIFIED | `frontend/src/components/results/DemandVsServedChart.tsx` — contains `min-h-[280px]`, `#4F46E5`, null-preserving `*_raw` fields feeding the tooltip formatter; `DemandVsServedChart.test.tsx` green |
| 15 | ScheduleTable renders schedule as a scrollable, server-order table (Member/Task/Function/Shift Window via formatShiftWindow); empty → "No shifts were scheduled for this run." | ✓ VERIFIED | `frontend/src/components/results/ScheduleTable.tsx` — no `.sort(`/`.filter(`, reuses `max-h-[420px] overflow-y-auto` container, empty-state copy present; `ScheduleTable.test.tsx` green |
| 16 | InsightPanel is button-triggered (never auto-fetches), five states (idle/pending/error/not-ready/ready) | ✓ VERIFIED | `frontend/src/components/results/InsightPanel.tsx` — no fetch in a `useEffect`, five distinct JSX branches; `InsightPanel.test.tsx` green |
| 17 | Success branch reads `data.ready`, never `response.status`, to distinguish ready vs not-ready | ✓ VERIFIED | `InsightPanel.tsx:71,77` branches on `insights.data?.ready === false/true`; no `.status ===` readiness branch; test asserts no destructive styling on `ready:false` |
| 18 | A 502 renders distinct destructive block + re-enabled "Try Again"; repeated failures reset to same copy | ✓ VERIFIED | `InsightPanel.tsx:51-69`; `InsightPanel.test.tsx` covers 502 → error copy → retry |
| 19 | Insight failure confined to InsightPanel's own mutation — never unmounts/disables sibling sections | ✓ VERIFIED | `useRunInsights.ts` has zero `queryClient`/`invalidateQueries` usage; `ResultsView.test.tsx` "RES-05 insight failure isolation" integration test asserts sibling sections (`Total Cost`, `Alice`, tables) remain in the DOM after a 502 |
| 20 | ResultsView branches on `RunOut.status` FIRST (D-12): loading/error/PENDING-RUNNING/FAILED/COMPLETED, before any results content | ✓ VERIFIED | `frontend/src/routes/ResultsView.tsx:77-114`; `ResultsView.test.tsx` covers all four branches |
| 21 | `GET /runs/{id}` failure renders ErrorBanner, never a blank screen | ✓ VERIFIED | `ResultsView.tsx:81-83` `runQuery.isError → <ErrorBanner .../>` |
| 22 | On COMPLETED, body renders in order: heading/metadata, WarningsBanner → CoverageSummary → CoverageByDayTable → DemandVsServedChart → ScheduleTable → InsightPanel | ✓ VERIFIED | `ResultsView.tsx:118-145` — exact render order confirmed by direct read |
| 23 | `useRunResult`'s `enabled` wired to `runQuery.data?.status === 'COMPLETED'` — route stays deep-linkable, never 409s early | ✓ VERIFIED | `ResultsView.tsx:73-75` |
| 24 | A 502 in InsightPanel leaves coverage/chart/schedule/warnings mounted and interactive — proven by an integration test | ✓ VERIFIED | `ResultsView.test.tsx` "RES-05 insight failure isolation" test, plus a dedicated CR-01 regression test (cross-run navigation, added after code review) |

**Score:** 24/24 truths verified (0 present-but-behavior-unverified)

### Code Review Findings — Closure Verification

`04-REVIEW.md` (standard depth, 35 files) found 1 critical + 2 warnings + 1 info. All four independently confirmed fixed and committed in this codebase (not merely claimed):

| Finding | Fix Commit | Verified |
|---|---|---|
| CR-01: InsightPanel shows stale/wrong-run report across navigation (no `key`, mutation state not keyed by `runId`) | `d548d9d` | ✓ `ResultsView.tsx:143` now renders `<InsightPanel key={runId} runId={runId as string} />`; a dedicated regression test ("CR-01 regression — insight report must not leak across runs") in `ResultsView.test.tsx` navigates r1→r2 and asserts r1's report is gone |
| WR-01: `ResultsView.test.tsx` fixture used percent-scale values instead of `[0,1]` fraction scale, never asserted rendered percentage | `1409e8f` | ✓ `ResultsView.test.tsx:120-123,236-237` now uses `pct: 0.95`/`1.0`, `coverage_by_day: {"0": 0.95, "1": 1.0}`, and asserts `"95%"`/`"100%"` text |
| WR-02: WarningsBanner used raw warning string as React list key | commit in `d548d9d`/`1409e8f` range (confirmed by direct read) | ✓ `WarningsBanner.tsx:31-33` now keys by index `key={i}` |
| IN-01: DemandVsServedChart.test.tsx fixtures use percent-scale `pct` (no functional impact, drift only) | Not separately tracked (info-level, non-functional) | Not re-verified — info-level, explicitly noted by reviewer as having no functional impact since `pct` is never read by the chart |

The underlying scaling bug (`CoverageByDayTable` rendering a raw `[0,1]` fraction with a bare `%`, e.g. `61%` → `"0.61%"`) is independently confirmed fixed: `formatCoveragePct` in `CoverageByDayTable.tsx` multiplies by 100 before formatting, and both `CoverageByDayTable.test.tsx` and the `ResultsView.test.tsx` integration fixture now use fraction-scale input.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `frontend/src/components/ui/card.tsx`, `chart.tsx`, `tooltip.tsx` | shadcn source-copied primitives | ✓ VERIFIED | Exist, compile, consumed downstream |
| `frontend/src/api/results.ts` | hand-written `RunResult` + `getRunResult` | ✓ VERIFIED | Exists, exactly one `as RunResult` cast |
| `frontend/src/api/insights.ts` | `getRunInsights` | ✓ VERIFIED | Exists, passes `InsightOut` through unmodified |
| `frontend/src/lib/formatShiftWindow.ts` | day/time formatter | ✓ VERIFIED | Exists, tested |
| `frontend/src/hooks/useRun.ts`, `useRunResult.ts`, `useRunInsights.ts` | the three query/mutation hooks | ✓ VERIFIED | All exist, all tested green |
| `frontend/src/components/results/WarningsBanner.tsx`, `CoverageSummary.tsx`, `CoverageByDayTable.tsx` | coverage cluster | ✓ VERIFIED | All exist, tested, fixed post-review |
| `frontend/src/components/results/DemandVsServedChart.tsx`, `ScheduleTable.tsx` | visuals | ✓ VERIFIED | Both exist, tested |
| `frontend/src/components/results/InsightPanel.tsx` | on-demand insight panel | ✓ VERIFIED | Exists, five states, tested, `key`-fixed for CR-01 |
| `frontend/src/routes/ResultsView.tsx` | composed route | ✓ VERIFIED | Exists, live at `runs/:runId`, `ResultsPlaceholder.tsx` deleted |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `App.tsx` route table | `ResultsView` | `runs/:runId` Component mapping | ✓ WIRED | `App.tsx:55` maps `runs/:runId` to `ResultsView`; `ResultsPlaceholder` import removed; file deleted |
| `ResultsView` | `useRun`/`useRunResult` | direct hook calls | ✓ WIRED | `ResultsView.tsx:72-75` |
| `useRunResult` | `getRunResult` | gated `enabled` | ✓ WIRED | `enabled: runQuery.data?.status === "COMPLETED"` |
| `ResultsView` | six result components | props from `resultQuery.data` | ✓ WIRED | `ResultsView.tsx:128-143` — all six fed real fields |
| `InsightPanel` | `useRunInsights` | direct hook call | ✓ WIRED | `InsightPanel.tsx:27` |
| `ScenarioLayout.tsx` | (unchanged) | — | ✓ VERIFIED UNCHANGED | No diff for this file in phase 04 commits (confirmed by plan's own acceptance criterion and no matching commits touch it) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Frontend type-checks cleanly (bare `npm run typecheck` is a known no-op per orchestrator note; used the real check) | `cd frontend && npx tsc --noEmit -p tsconfig.app.json` | no output, exit 0 | ✓ PASS |
| Full frontend test suite (run once, not filtered per-truth) | `cd frontend && npx vitest run` | `Test Files 42 passed (42)`, `Tests 235 passed (235)` | ✓ PASS |
| Targeted coverage/warnings regression tests | `npx vitest run src/components/results/CoverageByDayTable.test.tsx src/components/results/WarningsBanner.test.tsx` | `2 passed`, `5 passed` | ✓ PASS |
| No debt markers in phase-modified files | `grep -rnE "TBD|FIXME|XXX"` across `components/results/`, `routes/ResultsView.tsx`, `api/*.ts`, `lib/formatShiftWindow.ts`, hooks, ui primitives | no matches | ✓ PASS |
| No raw-HTML injection sink in phase components | `grep -rn dangerouslySetInnerHTML components/results/ routes/ResultsView.tsx` | only comment/test-name mentions, no live usage | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| RES-01 | 04-01, 04-04, 04-07 | Coverage summary cards for a completed run | ✓ SATISFIED | `CoverageSummary.tsx` + `ResultsView.tsx` composition |
| RES-02 | 04-01, 04-05, 04-07 | Demand-vs-served chart for a completed run | ✓ SATISFIED | `DemandVsServedChart.tsx` + composition |
| RES-03 | 04-02, 04-05, 04-07 | Schedule as a readable table | ✓ SATISFIED | `ScheduleTable.tsx` + `formatShiftWindow.ts` + composition |
| RES-04 | 04-02, 04-03, 04-06, 04-07 | On-demand insight report, branches on `ready` not status | ✓ SATISFIED | `InsightPanel.tsx` branches on `data.ready`; `insights.ts` passes body through unmodified |
| RES-05 | 04-02, 04-03, 04-06, 04-07 | Insight failure isolated from rest of results view | ✓ SATISFIED | `useRunInsights.ts` (no invalidation) + `ResultsView.test.tsx` integration proof, incl. CR-01 fix |
| RES-06 | 04-02, 04-04 | Degenerate-solve warnings surfaced, not dropped | ✓ SATISFIED | `WarningsBanner.tsx`; `docs/API.md` documents `warnings` |

No orphaned requirements — all 6 RES-* IDs from `.planning/REQUIREMENTS.md`'s Phase 4 row are declared across plan frontmatter (04-01, 04-02, 04-03, 04-04, 04-05, 04-06, 04-07) and all six are satisfied.

### Anti-Patterns Found

None blocking. No `TBD`/`FIXME`/`XXX`/`TODO`/placeholder markers in phase-modified files; no `dangerouslySetInnerHTML` usage (comments and a test name reference the sink by name only, to assert its absence). One minor process note (not a code anti-pattern): `04-01-SUMMARY.md` documents that a bare `npm install recharts@^3.9.2` was run post-shadcn-install to bump the resolved version from the registry's pinned `^3.8.0` to the vetted `3.9.2` — this is a literal instance of the plan's own prohibited phrase ("must not be added via a bare `npm install recharts`"), though the summary's argument that this is a version bump of an already-source-copied package (not a new/different install) rather than a new supply-chain entry point is reasonable and the change landed in the same Task 2 commit (`fa0099e`), not a separate out-of-band step. Flagged as informational, not a gap — the resulting `package.json`/`package-lock.json` state is a single dependency (`recharts@^3.9.2`), matching the plan's actual `must_have` truth.

### Human Verification Required

1. **End-of-phase visual/interactive walkthrough of ResultsView** (deferred from `checkpoint:human-verify` per `human_verify_mode=end-of-phase`, `04-07-PLAN.md` Task 1)
   **Test:** Run `npm run dev`, trigger a scenario run to COMPLETED, open `/scenarios/{id}/runs/{runId}`.
   **Expected:** Coverage cards + warnings banner + by-day table render; chart shows visible grouped bars (not blank/0-height); schedule table scrolls with matching day numbers; "Get Insight Report" fetches a report or an honest not-ready/error; deep-linking PENDING/RUNNING/FAILED runs shows the correct branch, never a blank screen.
   **Why human:** Real Recharts height measurement and a live LLM round trip are outside jsdom/unit-test reach.

2. **Long warning string layout (WarningsBanner)** — `04-04-PLAN.md`, `verification: backstop`
   **Test:** Trigger a run producing a very long warning string; view the results page.
   **Expected:** Text wraps without breaking page layout.
   **Why human:** Visual layout, explicitly tagged non-inferable at spec time.

3. **Empty `coverage_by_day` on a COMPLETED run** — `04-04-PLAN.md`, `verification: backstop`
   **Test:** Observe a COMPLETED run whose `coverage_by_day` is empty (if reachable).
   **Expected:** An honest empty/absent state, not a broken render.
   **Why human:** Reachability itself is unconfirmed against the engine; not testable from the frontend alone.

4. **Empty `coverage_by_function` on a COMPLETED run** — `04-05-PLAN.md`, `verification: backstop`
   **Test:** Observe a COMPLETED run whose `coverage_by_function` is empty (if reachable).
   **Expected:** An honest empty/absent chart state.
   **Why human:** Same unconfirmed-reachability class as item 3.

5. **Long insight report layout (InsightPanel)** — `04-06-PLAN.md`, `verification: backstop`
   **Test:** Fetch a very long LLM-generated insight report.
   **Expected:** Report text wraps/scrolls without breaking page layout.
   **Why human:** Visual layout, explicitly tagged non-inferable at spec time.

### Gaps Summary

No gaps. All 24 derived must-have truths across the phase's 7 plans are VERIFIED against the actual codebase (not SUMMARY claims): artifacts exist, are substantive (no stubs), are wired end-to-end (route → hooks → components → props), and the full 235-test frontend suite plus a targeted `tsc --noEmit` pass cleanly. The phase's own code review (`04-REVIEW.md`) found and the codebase independently confirms fixed: a critical cross-run stale-insight-report bug (CR-01, fixed via `key={runId}` + regression test) and a coverage-percentage fraction/percentage scaling bug (fixed via `formatCoveragePct`, with both the unit test and the integration test fixture corrected to real wire-contract fraction values). The only open items are five explicitly-deferred/backstop human-verification checks that the plans themselves flagged as unverifiable by grep/unit test at spec time — none are code gaps.

---

_Verified: 2026-07-20T10:15:00Z_
_Verifier: Claude (gsd-verifier)_
