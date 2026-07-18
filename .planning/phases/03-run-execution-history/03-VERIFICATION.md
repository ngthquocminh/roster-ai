---
phase: 03-run-execution-history
verified: 2026-07-18T20:30:00Z
status: human_needed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Start the backend (`uvicorn api.main:app --reload`) and the frontend (`npm run dev`). Open a scenario's Runs tab and click 'Run Scenario'."
    expected: "A new run appears immediately as 'Queued' with no manual refresh (RUN-01); the button then disables with 'A run is already in progress for this scenario.'; the in-flight panel shows the honest 'Solving…' / multi-minute / cannot-be-cancelled copy with NO cancel button and NO progress bar (RUN-03); the run advances to 'Completed' on its own without a manual refresh (RUN-02); reloading mid-flight resumes state from polling; prior runs list with created/started/finished timing (RUN-04); a deep link to /scenarios/<bogus-id>/runs shows the ordinary 'No runs yet' empty state, not a 'Scenario not found' gate; a FAILED run (if available) shows its error text inline and wraps without breaking table columns (RUN-05)."
    why_human: "Requires a live backend, real timers/HTTP polling, and visual/layout judgment (column-width wrap under real browser rendering) that unit tests with mocked hooks and jsdom cannot exercise. Deferred by the plan's own human_verify_mode=end-of-phase checklist (03-05-PLAN.md verification block) and by 03-03's D9 backstop (long/multi-line FAILED error wrap)."
---

# Phase 3: Run Execution & History Verification Report

**Phase Goal:** A user can trigger a solve and follow it to a terminal state without leaving the browser.
**Verified:** 2026-07-18T20:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can trigger a run for a scenario and see it appear immediately as `PENDING` | ✓ VERIFIED | `frontend/src/api/runs.ts` `triggerRun()` POSTs `/scenarios/{id}/runs`; `frontend/src/hooks/useTriggerRun.ts` invalidates the byte-identical `["runs", scenarioId]` key on success (asserted in `useTriggerRun.test.tsx`); `RunHistory.tsx` wires `onTrigger={() => trigger.mutate()}` on the header CTA and passes the same callback into the table's empty-state CTA; `RunHistory.test.tsx` asserts the click invokes the mutation exactly once. |
| 2 | User can watch a run advance through `PENDING → RUNNING → COMPLETED/FAILED` without manually refreshing | ✓ VERIFIED | `frontend/src/hooks/useRuns.ts`'s `refetchInterval` predicate calls `hasActiveRun(query.state.data ?? [])`; `useRuns.test.tsx` mounts the real hook and drives the actual wired predicate (read off `query.options.refetchInterval`) against RUNNING (returns interval), all-terminal (returns `false`), and empty (returns `false`) snapshots — proving the self-terminating poll logic, not a reimplementation. |
| 3 | While a run is in flight the user is told honestly it can take minutes and cannot be cancelled — no progress affordance, no abort control | ✓ VERIFIED | `frontend/src/components/runs/RunInFlightPanel.tsx` renders the verbatim UI-SPEC "Solving…" / "This can take a few minutes… It can't be cancelled once started" copy for RUNNING and "Queued" / "next in line" for PENDING; `RunInFlightPanel.test.tsx` and `TriggerRunButton.test.tsx` both assert **no** `/cancel/i`-named control and **no** `progressbar`-role element exists in any rendered state; a repo-wide grep of the `components/runs/`, `hooks/useRuns.ts`, `hooks/useTriggerRun.ts`, and `routes/RunHistory.tsx` sources found no cancel/abort implementation, only the honesty copy and its tests. |
| 4 | User can see prior runs for a scenario with their status and timing (created/started/finished) | ✓ VERIFIED | `frontend/src/components/runs/RunHistoryTable.tsx` renders one row per `RunOut` (Status/Created/Started/Finished columns), newest-first in server order (no client `.sort()`), nullable `started_at`/`finished_at` render `—`; `RunHistoryTable.test.tsx` (11 tests) covers loading/error/empty/populated/nullable-timestamp/overflow states. |
| 5 | A `FAILED` run shows its recorded `error` text rather than appearing merely absent or permanently stuck | ✓ VERIFIED | `RunHistoryTable.tsx` renders `run.error` verbatim (JSX text child only, no `dangerouslySetInnerHTML`) beneath the "Failed" label, with `"Failed — no error details were recorded."` fallback when `error` is null; `RunHistoryTable.test.tsx` asserts both the verbatim case and the null-fallback case, plus an HTML-looking-error-string-renders-as-literal-text negative assertion (XSS mitigation, T-3-05). |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/api/runs.ts` | Typed `listRuns`/`triggerRun` wrappers | ✓ VERIFIED | Two exported functions, routes through shared `./client`, throws `{status, ...error}` on non-2xx, no hand-authored `RunOut` type. |
| `frontend/src/lib/runStatus.ts` | Status vocabulary + terminal/active predicates | ✓ VERIFIED | `RUN_STATUS_META`, `runStatusMeta`, `isTerminalStatus`, `hasActiveRun`, `newestActiveRun` all present, pure (no React import), typed via generated `components["schemas"]["RunOut"]`. |
| `frontend/src/hooks/useRuns.ts` | Self-terminating polling query | ✓ VERIFIED | `useQuery` with `queryKey: ["runs", scenarioId]`, `refetchInterval` predicate using `hasActiveRun`; no `setInterval`. |
| `frontend/src/hooks/useTriggerRun.ts` | Trigger mutation w/ immediate invalidation | ✓ VERIFIED | `useMutation` invalidating exactly `["runs", scenarioId]` on success; error propagates untouched. |
| `frontend/src/components/runs/RunStatusLabel.tsx` | Icon+text status cell (no Badge) | ✓ VERIFIED | Reads `runStatusMeta`, no Badge import. |
| `frontend/src/components/runs/RunHistoryTable.tsx` | Prior-runs read surface | ✓ VERIFIED | Full loading/error/empty/populated/overflow state machine; `solver_status` never rendered (confirmed by grep — no reference in file). |
| `frontend/src/components/runs/TriggerRunButton.tsx` | Presentational trigger CTA | ✓ VERIFIED | 5-prop presentational component, `getErrorStatus`-based 404-vs-other branching, no internal hook. |
| `frontend/src/components/runs/RunInFlightPanel.tsx` | Honest wait panel | ✓ VERIFIED | Renders nothing for null/terminal run; PENDING/RUNNING verbatim copy; no cancel/progress affordance. |
| `frontend/src/routes/RunHistory.tsx` | Composed route | ✓ VERIFIED | Calls `useRuns`/`useTriggerRun` exactly once each, derives `runInProgress`/`activeRun` from the same response, passes into all three children. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `useTriggerRun` onSuccess | `useRuns` query cache | `queryClient.invalidateQueries({queryKey: ["runs", scenarioId]})` vs `useQuery({queryKey: ["runs", scenarioId]})` | ✓ WIRED | Keys are byte-identical string literals in both files; asserted in both hooks' tests. |
| `RunHistory.tsx` | `TriggerRunButton`/`RunInFlightPanel`/`RunHistoryTable` | props derived from one `useRuns()` call | ✓ WIRED | Single `runsQuery` object passed to `RunHistoryTable`; `hasActiveRun(runs)`/`newestActiveRun(runs)` derived from the same `runsQuery.data` feed `TriggerRunButton`/`RunInFlightPanel`. Confirmed by direct file read — no second `useRuns()` call anywhere in the phase's files. |
| `App.tsx` `runs` route | `RunHistory` | `Component: RunHistory` (import swap from `RunsPlaceholder`) | ✓ WIRED | Confirmed by reading `App.tsx`; `runs/:runId` route unchanged (`ResultsPlaceholder`), `RunsPlaceholder.tsx` deleted and no remaining import (`grep` confirms only a stale comment reference in `RunHistory.tsx`'s docstring). |
| `RunHistoryTable` row click | `/scenarios/:scenarioId/runs/:runId` | `useNavigate()` | ✓ WIRED | `onClick`/`onKeyDown` (Enter/Space) call `navigate(...)`, tested via memory-router probe. |
| Backend `RunOut` schema (`backend/api/schemas.py`) | Frontend generated `schema.d.ts` `RunOut` | `openapi-typescript` generation | ✓ WIRED | Both agree: `status: string`, `started_at`/`finished_at`/`solver_status`/`error` all `Optional[str]`/`string | null`. |
| `GET /scenarios/{id}/runs` (backend) | E4 backstop: no scenario-existence gate for unknown `scenarioId` | `RunRepo.list_by_scenario` SQL | ✓ VERIFIED | `store/repositories.py:59-64` runs `SELECT * FROM runs WHERE scenario_id = ? ORDER BY created_at DESC` with no existence pre-check — an unknown `scenario_id` returns `[]`, confirming `RunHistoryTable`'s ordinary empty-state fallthrough (not a 404 gate) is correct as implemented. |

### Prohibitions

| Prohibition | Status | Evidence |
|-------------|--------|----------|
| A COMPLETED run must not be rendered as failure/warning due to `solver_status: "UNKNOWN"` | ✓ VERIFIED (test) | `RunHistoryTable.test.tsx` asserts a COMPLETED+`solver_status:"UNKNOWN"` run renders "Completed" and the DOM never contains "UNKNOWN"; `solver_status` is never read in `RunHistoryTable.tsx`. |
| No cancel affordance anywhere in the trigger/panel/table/view | ✓ VERIFIED (test) | Negative assertions (`queryByRole("button", {name: /cancel/i})` → null) in `TriggerRunButton.test.tsx` and `RunInFlightPanel.test.tsx`; repo grep across `components/runs/`, hooks, and `RunHistory.tsx` finds no cancel/abort implementation. |
| No determinate progress affordance (progress bar/percentage/ETA) | ✓ VERIFIED (test) | Negative `progressbar`-role assertions in the same two test files; only motion is the indeterminate `animate-spin` icon. |
| ScenarioLayout's Results tab must not be enabled; no ResultsView content built | ✓ VERIFIED | `ScenarioLayout.tsx` still renders the Results tab with `disabled`/`aria-disabled="true"` (unchanged in this phase's diff); `runs/:runId` route still mounts `ResultsPlaceholder`. |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|-------------|--------|----------|
| RUN-01 | 03-01, 03-02, 03-04, 03-05 | User can trigger a run for a scenario | ✓ SATISFIED | `triggerRun` + `useTriggerRun` + `TriggerRunButton` + `RunHistory` composition, all tested. |
| RUN-02 | 03-01, 03-02, 03-05 | UI polls run status until terminal, reflects PENDING→RUNNING→COMPLETED/FAILED | ✓ SATISFIED | `useRuns`'s self-terminating `refetchInterval`, unit-tested against the real predicate. |
| RUN-03 | 03-04, 03-05 | Honest in-flight wait, no cancel, no false-progress affordance | ✓ SATISFIED | `RunInFlightPanel` + `TriggerRunButton` copy/negative-assertion tests. |
| RUN-04 | 03-01, 03-03, 03-05 | Prior runs visible with status/timing | ✓ SATISFIED | `RunHistoryTable` full state machine, tested. |
| RUN-05 | 03-03, 03-05 | FAILED run shows recorded error | ✓ SATISFIED | `RunHistoryTable`'s inline FAILED error + null-fallback + XSS-safe rendering, tested. |

**Orphaned requirements check:** REQUIREMENTS.md maps exactly RUN-01..RUN-05 to Phase 3; all 5 appear in at least one plan's `requirements` frontmatter field. No orphans.

**Documentation note (non-blocking):** `.planning/REQUIREMENTS.md`'s checkbox/traceability table currently shows RUN-01/RUN-02/RUN-03 as unchecked/"Pending" while RUN-04/RUN-05 show checked/"Complete" — this is stale bookkeeping (likely mid-phase snapshot from when only 03-01/03-03 had landed), not a functional gap: all five requirements are demonstrably implemented and tested in the current codebase per the table above. Recommend updating REQUIREMENTS.md's checkboxes as part of phase close-out.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` (case-insensitive) across all phase-created files under `frontend/src/api/runs.ts`, `frontend/src/lib/runStatus.ts`, `frontend/src/hooks/useRuns.ts`, `frontend/src/hooks/useTriggerRun.ts`, `frontend/src/components/runs/*.tsx`, and `frontend/src/routes/RunHistory.tsx` returned only benign incidental matches (the word "placeholder" describing UI copy/the retired route name, and doc comments referencing the pre-existing `ResultsPlaceholder`/`RunsPlaceholder` route names) — no debt markers.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All phase-specific unit/component tests pass | `cd frontend && npx vitest run src/api/runs.test.ts src/lib/runStatus.test.ts src/hooks/useRuns.test.tsx src/hooks/useTriggerRun.test.tsx src/components/runs/RunStatusLabel.test.tsx src/components/runs/RunHistoryTable.test.tsx src/components/runs/TriggerRunButton.test.tsx src/components/runs/RunInFlightPanel.test.tsx src/routes/RunHistory.test.tsx src/routes/router.test.tsx` | 10 files, 74 tests passed | ✓ PASS |
| Full frontend suite has no regressions | `cd frontend && npm run test` | 28 files, 175 tests passed | ✓ PASS |
| TypeScript compiles clean (no `RunOut` drift) | `cd frontend && npm run typecheck` | exit 0, no output | ✓ PASS |
| All phase task commits exist in git history | `git log --oneline --all \| grep <18 commit hashes from SUMMARYs>` | all 18 hashes found | ✓ PASS |
| `RunsPlaceholder.tsx` fully retired | `ls frontend/src/routes/RunsPlaceholder.tsx` / repo grep for imports | file absent; no import references remain | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared or found for this phase (frontend UI feature, not a migration/CLI-tooling phase). Skipped.

### Human Verification Required

### 1. End-to-end browser walkthrough (RUN-01..RUN-05 against a live backend)

**Test:** Start the backend and `npm run dev`. Open a scenario's Runs tab. Click "Run Scenario".
**Expected:** A run appears immediately as "Queued" without a manual refresh; the button disables with the in-progress caption; the in-flight panel shows the honest "Solving…" copy with no cancel button and no progress bar; the run advances to "Completed" on its own; reloading mid-flight resumes from polling; prior runs list with timing; a bogus `scenarioId` deep link shows the ordinary empty state.
**Why human:** Requires a live backend, real HTTP polling over wall-clock time, and a real browser session — none of which the mocked-hook unit tests exercise end-to-end. This is the plan's own `human_verify_mode=end-of-phase` checklist item (03-05-PLAN.md).

### 2. Long/multi-line FAILED error text wraps without breaking table column widths

**Test:** Trigger or otherwise produce a FAILED run whose `error` text is long or multi-line; view it in the Run History table.
**Expected:** The error text wraps within its cell; the Status/Created/Started/Finished column widths stay stable (do not widen or shift).
**Why human:** A genuine visual layout/wrap check under real browser rendering — the `table-fixed` + `whitespace-pre-wrap break-words` CSS is present and correct by inspection, but jsdom text-content assertions cannot prove visual wrap behavior. Flagged explicitly as a backstop in 03-03-PLAN.md's `must_haves.truths` (`verification: backstop`) and reported as `human_judgment: true` in 03-03-SUMMARY.md's coverage (D9).

### Gaps Summary

No gaps found. All 5 ROADMAP success criteria, all plan-level must-have truths, artifacts, and key links are verified present, substantive, and wired, backed by 74 phase-specific tests (175 in the full suite) and a clean typecheck. The only open items are two explicitly-flagged human-verification backstops (live end-to-end browser walkthrough, and visual text-wrap under real rendering) that the plans themselves deferred to end-of-phase human review rather than claiming as automated — this is honest self-reporting, not a gap being papered over. A non-blocking documentation staleness note (REQUIREMENTS.md checkbox state for RUN-01/02/03) is recorded for phase close-out.

---
_Verified: 2026-07-18T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
