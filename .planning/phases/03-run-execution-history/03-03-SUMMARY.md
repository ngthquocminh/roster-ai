---
phase: 03-run-execution-history
plan: 03
subsystem: ui
tags: [react, typescript, vitest, lucide-react, react-router, run-history]

# Dependency graph
requires:
  - phase: 03-run-execution-history (plan 03-01)
    provides: runStatusMeta / RUN_STATUS_META (lib/runStatus.ts) — single status vocabulary this plan's components consume
provides:
  - RunStatusLabel — reusable icon+text run-status cell (no Badge), consumed by RunHistoryTable
  - RunHistoryTable — full run-history read surface (loading/error/empty/populated/overflow) with FAILED inline error
affects: [03-04 (trigger run button), 03-05 (RunHistory view composing runsQuery + these components)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Icon+text status convention (no Badge) generalized from TranscriptEntry into a reusable RunStatusLabel component"
    - "runsQuery prop pattern (UseQueryResult<T[]>) — component never calls its own hook, mirrors OverridesList"

key-files:
  created:
    - frontend/src/components/runs/RunStatusLabel.tsx
    - frontend/src/components/runs/RunStatusLabel.test.tsx
    - frontend/src/components/runs/RunHistoryTable.tsx
    - frontend/src/components/runs/RunHistoryTable.test.tsx
  modified: []

key-decisions:
  - "Empty-state 'Run Scenario' button is a plain Button + onTriggerRun callback (like ScenarioTable's onCreateScenario), not the stateful TriggerRunButton from 03-04, to avoid a cross-plan coupling."
  - "FAILED error fallback uses run.error || FAILED_NO_ERROR_COPY (not ??) so an empty string as well as null/undefined routes to the defensive copy."
  - "Status cell overrides TableCell's default whitespace-nowrap with whitespace-normal (via twMerge) so the FAILED error paragraph beneath the status label can wrap; table-fixed + explicit TableHead widths keep column widths stable regardless of error length."

patterns-established:
  - "RunStatusLabel: the reusable status-cell shape any future run-status display (e.g. the in-flight panel or a run detail header in later plans) should reuse rather than reinventing icon+text markup."

requirements-completed: [RUN-04, RUN-05]

coverage:
  - id: D1
    description: "RunStatusLabel renders the four run-status icon+text mappings (Queued/Running/Completed/Failed) with an honest fallback for unknown statuses, and never imports a Badge component"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunStatusLabel.test.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "RunHistoryTable renders every run for a scenario newest-first (server order, no client re-sort) with Status/Created/Started/Finished columns, keyed by run.id"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: populated"
        status: pass
    human_judgment: false
  - id: D3
    description: "RunHistoryTable's loading/error/empty states mirror ScenarioTable/OverridesList (centered spinner, ErrorBanner, 'No runs yet' + inline Run Scenario button)"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: loading/error/empty"
        status: pass
    human_judgment: false
  - id: D4
    description: "Nullable started_at/finished_at render a '—' placeholder rather than a blank or broken cell"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: populated (nullable timestamps)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A FAILED row renders run.error verbatim beneath the Failed label; a null error renders the defensive 'Failed — no error details were recorded.' fallback"
    requirement: "RUN-05"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: FAILED inline error"
        status: pass
    human_judgment: false
  - id: D6
    description: "A COMPLETED run with solver_status UNKNOWN still renders 'Completed'; solver_status is never present in the rendered DOM"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: solver_status never rendered"
        status: pass
    human_judgment: false
  - id: D7
    description: "run.error and all cell text render only as JSX text children — an HTML-looking error string renders as literal text with no element created from it (T-3-05 XSS mitigation)"
    requirement: "RUN-05"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: HTML-looking error"
        status: pass
    human_judgment: false
  - id: D8
    description: "One run renders identical chrome to many (no row-count label); row click/Enter/Space navigates to /scenarios/:scenarioId/runs/:runId"
    requirement: "RUN-04"
    verification:
      - kind: unit
        ref: "frontend/src/components/runs/RunHistoryTable.test.tsx#RunHistoryTable: zero-one-many / populated (navigation)"
        status: pass
    human_judgment: false
  - id: D9
    description: "A long or multi-line FAILED error string wraps inside its cell without breaking the table's column widths (backstop — visual wrap, not asserted by DOM structure alone)"
    requirement: "RUN-05"
    verification: []
    human_judgment: true
    rationale: "UI-SPEC marks this a backstop: a genuine visual-wrap check (table-fixed columns + whitespace-pre-wrap break-words) that cannot be proven by jsdom text assertions alone — routes to human verification at end-of-phase per plan's own verification section."

# Metrics
duration: 9min
completed: 2026-07-18
status: complete
---

# Phase 03 Plan 03: Run Status Label & Run History Table Summary

**RunStatusLabel (icon+text, no Badge) and RunHistoryTable (loading/error/empty/populated read surface with inline FAILED errors) built TDD, both consuming the shared runStatusMeta vocabulary from 03-01.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-18T16:17:11+07:00 (worktree base)
- **Completed:** 2026-07-18T16:25:30+07:00
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments
- `RunStatusLabel` — a single reusable icon+text status cell reading `runStatusMeta`, replacing any Badge/pill idiom for the four run statuses (PENDING/RUNNING/COMPLETED/FAILED), with an honest fallback for unrecognized statuses.
- `RunHistoryTable` — the full run-history read surface: loading spinner, `ErrorBanner` on fetch error, "No runs yet" empty state with an inline "Run Scenario" trigger, and a populated `table-fixed` table (Status/Created/Started/Finished) scrolling past ~10 rows.
- RUN-05 satisfied: a `FAILED` row shows `run.error` verbatim and wrapped directly beneath its status label, with a defensive "Failed — no error details were recorded." fallback when `error` is null.
- `solver_status` is never read or rendered anywhere in this surface — a `COMPLETED` run with `solver_status: "UNKNOWN"` still renders the neutral "Completed" treatment, verified by a negative DOM assertion.
- Row click / Enter / Space navigates to `/scenarios/:scenarioId/runs/:runId`, mirroring `ScenarioTable`'s exact interaction pattern.

## Task Commits

Each task was executed as a full TDD RED → GREEN cycle:

1. **Task 1: Reusable status cell (RunStatusLabel)**
   - `022b8ac` (test) — failing test for the four statuses + unknown fallback
   - `b4405ec` (feat) — RunStatusLabel implementation, all 5 tests green
2. **Task 2: Run history table with inline failure text (RunHistoryTable)**
   - `aae8a82` (test) — failing test for the full state machine + RUN-05 + T-3-05
   - `5fa77d4` (feat) — RunHistoryTable implementation, all 11 tests green

**Plan metadata:** committed as part of this SUMMARY (worktree mode — orchestrator merges and records the final metadata commit).

## Files Created/Modified
- `frontend/src/components/runs/RunStatusLabel.tsx` - icon+text run-status cell (no Badge), reads `runStatusMeta`
- `frontend/src/components/runs/RunStatusLabel.test.tsx` - 5 tests: four statuses + unknown fallback + spin assertion
- `frontend/src/components/runs/RunHistoryTable.tsx` - run history table taking a `runsQuery` prop; full state machine + RUN-05 inline error
- `frontend/src/components/runs/RunHistoryTable.test.tsx` - 11 tests: loading/error/empty/populated/timestamps/FAILED error (+null fallback)/solver_status-hidden/XSS-escaping/zero-one-many/navigation

## Decisions Made
- Empty-state "Run Scenario" button is a plain `Button` + `onTriggerRun` callback (mirrors `ScenarioTable`'s `onCreateScenario`), not the stateful `TriggerRunButton` from plan 03-04 — avoids a cross-plan coupling since 03-03 and 03-04 are both Wave 2 (parallel, not sequenced).
- `run.error || FAILED_NO_ERROR_COPY` (not `??`) so an empty-string error also routes to the defensive fallback copy, not just `null`/`undefined`.
- Status `TableCell` overrides the base component's `whitespace-nowrap` with `whitespace-normal` (via `cn`/`twMerge`) so the FAILED error paragraph beneath the label can wrap onto multiple lines; `table-fixed` plus explicit `TableHead` widths (34%/22%/22%/22%) keep all four column widths stable regardless of error text length.

## Deviations from Plan

None — plan executed exactly as written. Both tasks followed the plan's TDD RED → GREEN sequence, and the resulting components/tests match the plan's `<action>` and `<acceptance_criteria>` blocks directly (state machine copied from `ScenarioTable`/`OverridesList` as instructed, `RunStatusLabel` generalized from `TranscriptEntry`'s icon+text convention as instructed).

## Issues Encountered
- Worktree `frontend/node_modules` was missing (gitignored, not carried by `git worktree add`). Verified `frontend/package-lock.json` was byte-identical to the main repo's, then created a directory symlink (`node_modules` → main repo's `frontend/node_modules`) instead of running `npm install`, per this plan's worktree instructions. An initial `mklink` invocation via a mixed bash/cmd path produced a malformed symlink target; recreated with a clean Windows-native path and verified `node_modules/.bin/vitest` resolved correctly before running any tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `RunStatusLabel` and `RunHistoryTable` are ready to be composed by plan 03-05's `RunHistory` view, which owns the single `useRuns()` query instance and passes its `UseQueryResult` down as the `runsQuery` prop to this plan's table (and to the in-flight panel).
- Plan 03-04's `TriggerRunButton` can be passed into `RunHistoryTable`'s `onTriggerRun` callback once available — the empty-state button is already wired to accept it without further changes to this plan's files.
- No blockers. The one open item is the UI-SPEC-flagged backstop (long/multi-line FAILED error wrap without breaking column widths) — deferred to end-of-phase human verification per the plan's own `<verification>` section, not a gap introduced by this plan.

---
*Phase: 03-run-execution-history*
*Completed: 2026-07-18*
