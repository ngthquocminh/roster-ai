---
phase: 01-browser-callable-api-app-shell-scenario-list
plan: 02
subsystem: infra
tags: [npm, supply-chain, package-legitimacy, vite, react-router, tanstack-query, tailwindcss, shadcn, vitest]

# Dependency graph
requires: []
provides:
  - "Human-confirmed supply-chain gate for all 9 install-bound `[SUS]`-flagged npm packages plan 01-03 will install"
  - "Recorded rejection of `msw` (`[SLOP]` verdict) — must not be installed by any plan in this phase"
affects: ["01-03 (npm create vite / npm install / npx shadcn init task, gated on this plan)"]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Blocking human-verify checkpoint as a supply-chain gate, run before any install command (T-1-SC)"]

key-files:
  created: [".planning/phases/01-browser-callable-api-app-shell-scenario-list/01-02-SUMMARY.md"]
  modified: []

key-decisions:
  - "Human approved all 9 install-bound [SUS]-flagged packages (vite, react-router, @tanstack/react-query, tailwindcss, @tailwindcss/vite, shadcn, @vitejs/plugin-react, lucide-react, vitest) after reviewing the name/source-repo table in 01-02-PLAN.md, including the shadcn vs shadcn-ui and react-router vs react-router-dom name traps."
  - "msw remains rejected ([SLOP] verdict: too-new + suspicious-postinstall) and must not appear in frontend/package.json for any plan in this phase; frontend tests mock the typed client module directly with vi.mock instead."

patterns-established: []

requirements-completed: [SHELL-01]

coverage:
  - id: D1
    description: "Human recorded an explicit 'approved' decision for all 9 install-bound [SUS]-flagged npm packages, unblocking plan 01-03's install task"
    requirement: "SHELL-01"
    verification:
      - kind: manual_procedural
        ref: "Human resume-signal response: 'approved' (verbatim, recorded below)"
        status: pass
    human_judgment: true
    rationale: "This is a human-only supply-chain gate by design — the legitimacy protocol requires human sign-off on [SUS]-flagged packages before install; it is never auto-approvable regardless of workflow.auto_advance."

# Metrics
duration: 5min
completed: 2026-07-16
status: complete
---

# Phase 1 Plan 02: Package Legitimacy Human Verification Gate Summary

**Human approved all 9 `[SUS]`-flagged install-bound npm packages after a name/source-repo sanity check; `msw` (`[SLOP]`) stays rejected — plan 01-03's install task is unblocked.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-16
- **Completed:** 2026-07-16
- **Tasks:** 1 completed
- **Files modified:** 0 (this SUMMARY is the only artifact)

## Accomplishments
- Presented the `<what-built>` audit findings and `<how-to-verify>` 9-package name/source-repo table from 01-02-PLAN.md to the human, verbatim, including the `01-RESEARCH.md` `## Package Legitimacy Audit` section.
- Human responded to the `<resume-signal>` with the verbatim decision: **"approved"**.
- No package was named as a name/source-repo mismatch. No install command was run. No `frontend/` directory was created.

## Task Commits

Only one task in this plan, and it produces no source files — its sole output is this SUMMARY, committed as part of the plan-metadata commit (no separate per-task commit was needed since `files_modified: []`).

**Plan metadata:** SUMMARY.md committed alongside this record.

## Files Created/Modified
- `.planning/phases/01-browser-callable-api-app-shell-scenario-list/01-02-SUMMARY.md` - Records the human's verbatim supply-chain-gate decision

## Decisions Made

**Human decision (verbatim resume-signal response): "approved"**

Interpreted, per the plan's `<resume-signal>` contract ("Type 'approved' to unblock plan 01-03's install task, or name any package whose registry page does not match the table above"), as approval of **all 9** install-bound `[SUS]`-flagged packages presented in the table:

| # | Package | Status |
|---|---------|--------|
| 1 | `vite` | Confirmed |
| 2 | `react-router` | Confirmed |
| 3 | `@tanstack/react-query` | Confirmed |
| 4 | `tailwindcss` | Confirmed |
| 5 | `@tailwindcss/vite` | Confirmed |
| 6 | `shadcn` | Confirmed |
| 7 | `@vitejs/plugin-react` | Confirmed |
| 8 | `lucide-react` | Confirmed |
| 9 | `vitest` | Confirmed |

No package was named as a mismatch against its expected source repo (see table above, sourced from `01-02-PLAN.md`'s `<how-to-verify>` section). The two deliberate name traps — `shadcn` (not `shadcn-ui`) and `react-router` (not `react-router-dom`) — were called out explicitly in the material shown to the human and were not flagged as errors.

**`msw` remains `[SLOP]`-rejected.** Not part of the approval set — it was never presented as a package awaiting approval; it is already removed from every recommendation per `01-RESEARCH.md`'s Package Legitimacy Audit (verdict: `SLOP`, reasons: "too-new" + "suspicious-postinstall"). `msw` must not be installed by any plan in this phase; `frontend/package.json` must never contain it. Frontend tests mock the typed client module directly with `vi.mock` instead of using MSW's network-level interception.

`react-router-dom` was checked by the audit but is not an install target — it is superseded by `react-router` per the State of the Art research, and was excluded from the approval table for that reason (not a rejection, simply not being installed).

## Deviations from Plan

None - plan executed exactly as written. This plan's single task is a `checkpoint:human-verify` gate; it was presented to the human by the orchestrator, the human responded with the verbatim decision recorded above, and this executor recorded that decision without re-presenting the checkpoint, without running any install command, and without creating a `frontend/` directory.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 01-03's `npm create vite` / `npm install` / `npx shadcn init` task is unblocked — all 9 install-bound `[SUS]` packages are human-confirmed against the live npm registry.
- `msw` remains off-limits for this phase; any future desire to add it requires a fresh legitimacy check and explicit human sign-off given its `suspicious-postinstall` flag (per `01-RESEARCH.md`).
- No blockers.

---
*Phase: 01-browser-callable-api-app-shell-scenario-list*
*Completed: 2026-07-16*
