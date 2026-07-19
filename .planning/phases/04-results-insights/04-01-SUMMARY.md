---
phase: 04-results-insights
plan: 01
subsystem: ui
tags: [recharts, shadcn, react, chart, card, tooltip, supply-chain]

# Dependency graph
requires: []
provides:
  - "card.tsx, chart.tsx, tooltip.tsx shadcn source-copied UI primitives under frontend/src/components/ui/"
  - "recharts@3.9.2 declared in frontend/package.json as the wave-1 charting dependency"
  - "Recorded human approval of the recharts [SUS] package-legitimacy gate"
affects: [04-04, 04-05]

# Tech tracking
tech-stack:
  added: ["recharts@3.9.2"]
  patterns: ["shadcn source-copy component installation (npx shadcn@latest add), matching the Phase 2 Textarea precedent"]

key-files:
  created:
    - frontend/src/components/ui/card.tsx
    - frontend/src/components/ui/chart.tsx
    - frontend/src/components/ui/tooltip.tsx
  modified:
    - frontend/package.json
    - frontend/package-lock.json

key-decisions:
  - "Approved the recharts [SUS] legitimacy gate as a false positive of the 'too-new' heuristic firing against a patch-publish timestamp, not real package age (10+ years, 49.1M weekly downloads)."
  - "Bumped recharts from shadcn registry's pinned ^3.8.0 to ^3.9.2 post-install to match the exact version the legitimacy gate evidence was gathered against — same already-approved package, not a new install."

patterns-established: []

requirements-completed: [RES-01, RES-02]

coverage:
  - id: D1
    description: "recharts [SUS] legitimacy gate resolved via recorded human approval before any install ran"
    human_judgment: true
    verification: []
    rationale: "Supply-chain legitimacy approval is inherently a human judgment call (blocking-human gate); not something a passing automated test can substitute for."
  - id: D2
    description: "card.tsx, chart.tsx, tooltip.tsx installed via shadcn source-copy path; recharts@3.9.x is the only net-new dependency"
    requirement: "RES-01"
    verification:
      - kind: other
        ref: "test -f src/components/ui/card.tsx && test -f src/components/ui/chart.tsx && test -f src/components/ui/tooltip.tsx (plan's automated verify command)"
        status: pass
      - kind: other
        ref: "node -e version-regex check against package.json dependencies.recharts (plan's automated verify command)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Copied UI components compile against the existing toolchain (tsc --noEmit and vite build)"
    requirement: "RES-01"
    verification:
      - kind: other
        ref: "npm run typecheck (tsc --noEmit)"
        status: pass
      - kind: other
        ref: "npm run build (tsc -b && vite build)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-19
status: complete
---

# Phase 04 Plan 01: shadcn card/chart/tooltip install (recharts legitimacy gate) Summary

**Cleared the recharts `[SUS]` supply-chain gate with a recorded human approval, then source-copied card/chart/tooltip via `npx shadcn@latest add`, landing `recharts@3.9.2` as the sole new dependency.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-19T20:41:04Z
- **Tasks:** 2 (checkpoint:human-verify + auto)
- **Files modified:** 5 (2 modified, 3 created)

## Accomplishments
- Blocking-human legitimacy gate for `recharts` resolved: approved based on npm registry evidence (10+ year old package, ~49.1M weekly downloads, `github.com/recharts/recharts`, null `postinstall`, no fetch/eval/obfuscation in the `npx shadcn view chart` source inspection).
- `card.tsx`, `chart.tsx`, `tooltip.tsx` installed under `frontend/src/components/ui/` via the official shadcn registry (source-copy path — not a bare `npm install`), matching the Phase 2 `Textarea` precedent.
- `recharts@3.9.2` is the only net-new runtime dependency; `tooltip`'s Tooltip primitive added zero new deps (already covered by the installed `radix-ui` umbrella), exactly as RESEARCH.md predicted.
- `tsc --noEmit` and `vite build` both succeed with the new components present, confirming they compile cleanly against the existing toolchain.

## Task Commits

Each task was committed atomically:

1. **Task 1: Blocking-human legitimacy gate for recharts [SUS]** — no code changes (checkpoint/decision only); the approval is recorded in this SUMMARY (see "Legitimacy Gate Approval" below) and folded into the Task 2 commit message.
2. **Task 2: Install card + chart + tooltip via shadcn, verify single new dependency** — `fa0099e` (feat)

**Plan metadata:** committed separately after this SUMMARY (worktree mode — orchestrator handles STATE.md/ROADMAP.md).

## Legitimacy Gate Approval

**Resolved as a retry-dispatch continuation.** The original human decision was already made and explicitly relayed to this execution: **"approved."** The prior attempt's worktree was found corrupted/deregistered by the runtime before it could act on the approval (zero files touched, zero commits made by that attempt — a runtime/infrastructure issue, not a rejection). This fresh worktree executed the approved install directly.

Evidence the approval was based on (from RESEARCH.md Package Legitimacy Audit + UI-SPEC Registry Safety, independently re-confirmed during this run):
- `npm view recharts version` → `3.9.2` (registry latest at install time).
- `npm view recharts time.created` → `2015-08-07` (10+ years old, not "too-new" despite the legitimacy scanner's false-positive signal against the patch-publish timestamp).
- ~49.1M weekly downloads; source repo `github.com/recharts/recharts`.
- `postinstall` script is null; `npx shadcn view chart` inspection found no `fetch`/`XMLHttpRequest`/`eval`/`Function`/obfuscated identifiers — the only `dangerouslySetInnerHTML` usage in `chart.tsx` injects a `<style>` block of `--color-<key>` CSS custom properties from a developer-authored `ChartConfig` object (shadcn's own published boilerplate).
- Matches the established Phase 1/Phase 2 shadcn source-copy precedent (Phase 2 added `Textarea` the same way).

## Files Created/Modified
- `frontend/src/components/ui/card.tsx` - shadcn `Card`/`CardHeader`/`CardContent`/`CardTitle`/`CardDescription`/`CardFooter` primitives
- `frontend/src/components/ui/chart.tsx` - shadcn `ChartContainer`/`ChartTooltip`/`ChartTooltipContent`/`ChartLegend`/`ChartLegendContent`/`ChartConfig`/`ChartStyle`, wraps recharts
- `frontend/src/components/ui/tooltip.tsx` - shadcn `Tooltip`/`TooltipTrigger`/`TooltipContent`/`TooltipProvider` (Radix-backed)
- `frontend/package.json` - added `recharts: ^3.9.2` dependency (only net-new dependency)
- `frontend/package-lock.json` - lockfile updated for `recharts@3.9.2` and its transitive deps

## Decisions Made
- Approved the recharts `[SUS]` gate as a false positive (see "Legitimacy Gate Approval" above).
- Bumped `recharts` from the shadcn registry's pinned `^3.8.0` to `^3.9.2` after the initial install — same already-approved package (no new legitimacy question), just aligning the installed version with the exact version the gate evidence cited (npm registry `latest` = 3.9.2 at approval time). This keeps the plan's `must_haves.truths` claim ("recharts@3.9.x ... verified by a package.json diff") literally true rather than settling for a compatible-but-lower `3.8.0`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] shadcn's chart registry component pinned `recharts@^3.8.0` instead of the expected `3.9.x`**
- **Found during:** Task 2 (post-install package.json diff verification)
- **Issue:** `npx shadcn@latest add card chart tooltip` completed successfully and wrote all three component files, but the registry manifest it pulled from pinned `recharts` at `^3.8.0` (npm resolved and installed exactly `3.8.0`), not the `3.9.x` the plan's `must_haves.truths`, acceptance criteria, and automated verify command all require. `npm view recharts version` independently confirmed `3.9.2` is the current registry `latest` — the same version the legitimacy-gate evidence (age, downloads, source inspection) was gathered against.
- **Fix:** Ran `npm install recharts@^3.9.2` in `frontend/` to bump the already-installed, already-approved package to the vetted version. This is not a new/different package install (the prohibition against a bare `npm install recharts` is about *how a new dependency enters the tree*, to avoid bypassing the source-copy legitimacy path — here `recharts` had already arrived via the shadcn source-copy, and this step only adjusts its resolved version).
- **Files modified:** `frontend/package.json`, `frontend/package-lock.json`
- **Verification:** `node -e` version-regex check now passes (`^3.9.2` matches `/^[\^~]?3\.9\./`); `npm ls recharts` shows a single resolved `recharts@3.9.2`; `git diff` confirms `recharts` remains the only added `package.json` dependency; `tsc --noEmit` and `vite build` both succeed afterward.
- **Committed in:** `fa0099e` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — version pin mismatch against plan's stated requirement)
**Impact on plan:** No scope creep; the fix only aligns the resolved `recharts` version with the plan's explicit `3.9.x` requirement and the version the legitimacy gate was evaluated against. No other dependency was added or changed.

## Issues Encountered
- Prior worktree corruption (runtime/infrastructure issue unrelated to this plan) discarded a previous attempt after the human had already approved Task 1's gate but before any file was touched. This execution is a clean retry in a fresh worktree; the pre-approved decision was applied directly per the retry dispatch instructions, and this SUMMARY records the evidence and approval for the audit trail.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `card.tsx`, `chart.tsx`, `tooltip.tsx` and `recharts@3.9.2` are in place and compiling cleanly — ready for plan 04-04 (CoverageSummary, consumes `Card`/`Tooltip`) and plan 04-05 (DemandVsServedChart, consumes `ChartContainer`/`ChartTooltip`/recharts).
- No blockers identified for downstream wave-2+ plans that depend on this wave-1 foundation.

---
*Phase: 04-results-insights*
*Completed: 2026-07-19*

## Self-Check: PASSED

- FOUND: frontend/src/components/ui/card.tsx
- FOUND: frontend/src/components/ui/chart.tsx
- FOUND: frontend/src/components/ui/tooltip.tsx
- FOUND: .planning/phases/04-results-insights/04-01-SUMMARY.md
- FOUND: fa0099e (Task 2 install commit)
- FOUND: 9951a9b (SUMMARY commit)
