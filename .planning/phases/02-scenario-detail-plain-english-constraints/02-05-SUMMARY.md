---
phase: 02-scenario-detail-plain-english-constraints
plan: 05
subsystem: ui
tags: [frontend, react, editor, constraints, outcomes, tanstack-query]

# Dependency graph
requires:
  - phase: 02-scenario-detail-plain-english-constraints
    provides: "useApplyConstraint(scenarioId) mutation hook (02-03); toolLabel() Tool Label Map helper (02-04)"
provides:
  - "TranscriptEntry — renders one submission's applied/rejected/clarification/no-match outcome with four distinct D-04 treatments + D-05 neutral no-match"
  - "ConstraintTranscript — session-log container (D-03); exports TranscriptEntryData, the shared entry type for the Editor's session state (plan 02-06)"
  - "ConstraintInput — Textarea + Apply Constraint form; status-branch (503 vs 422), input-preservation rule, char-limit backstop"
  - "ProviderDownBanner — fixed-copy 503 banner, Alert variant=\"default\", structurally disjoint from the rejection render path"
affects: [02-06-editor-route, scenario-editor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TranscriptEntryData type exported from ConstraintTranscript.tsx (not a separate types file) so ConstraintInput and the future Editor route both import the same shape from one source"
    - "Input-preservation rule evaluated inside ConstraintInput's own .mutate(text, { onSuccess: (data) => {...} }) callback, never inside useApplyConstraint's onSuccess — the clear condition depends on the response BODY, not 'request succeeded' (diverges from CreateScenarioDialog's unconditional-clear analog)"
    - "503 provider-down is structurally disjoint from the 200-body rejection render path — ProviderDownBanner renders directly in ConstraintInput from applyConstraint.error.status, never flows through onOutcome/the transcript, because a 503 throws before any 200 body exists"

key-files:
  created:
    - frontend/src/components/editor/TranscriptEntry.tsx
    - frontend/src/components/editor/TranscriptEntry.test.tsx
    - frontend/src/components/editor/ConstraintTranscript.tsx
    - frontend/src/components/editor/ConstraintTranscript.test.tsx
    - frontend/src/components/editor/ConstraintInput.tsx
    - frontend/src/components/editor/ConstraintInput.test.tsx
    - frontend/src/components/editor/ProviderDownBanner.tsx
  modified: []

key-decisions:
  - "ProviderDownBanner carries a stable data-testid=\"provider-down-banner\" for both its own render assertions and ConstraintInput's 503 test — no equivalent testid existed on ErrorBanner (its analog), added here since this is the banner's first consumer needing to distinguish it from destructive-styled elements in tests."
  - "Rejected-item transcript treatment applies text-destructive to the wrapping div (covering both the 'Couldn't apply: {Tool Label}' heading and the error body in one class application) rather than repeating the class on each <p> — matches UI-SPEC's 'both in text-destructive' requirement with one class, not two."
  - "422 backstop branch renders a data-testid=\"validation-error\" inline message — added purely so the backstop assertion (branch exists, keyed off status) has a stable target without depending on exact copy, since UI-SPEC treats this row as structurally unreachable in the ordinary flow."

requirements-completed: [CONS-01, CONS-02, CONS-03, CONS-04, CONS-05]

coverage:
  - id: D1
    description: "TranscriptEntry renders applied[] items as the parsed_constraint string verbatim with a Check icon (neutral/foreground) — a readable echo, never raw tool-call JSON"
    requirement: CONS-02
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/TranscriptEntry.test.tsx — 'TranscriptEntry: applied [D-04.1, CONS-02]'"
        status: pass
    human_judgment: false
  - id: D2
    description: "TranscriptEntry renders rejected[] items per-item as 'Couldn't apply: {Tool Label}' plus the backend's error string verbatim, both in text-destructive with an X icon"
    requirement: CONS-03
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/TranscriptEntry.test.tsx — 'TranscriptEntry: rejected [D-04.2, CONS-03]'"
        status: pass
    human_judgment: false
  - id: D3
    description: "applied[] and rejected[] both render within one transcript entry, each with its own distinct treatment (E5 mixed/partial-apply)"
    requirement: CONS-03
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/TranscriptEntry.test.tsx — 'TranscriptEntry: mixed applied+rejected [E5 mixed/partial-apply]'"
        status: pass
    human_judgment: false
  - id: D4
    description: "clarification_needed (non-null) renders 'Needs clarification: {text}' in neutral/muted with the rephrase caption; no_constraint_found renders the neutral no-match message + caption"
    requirement: CONS-04
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/TranscriptEntry.test.tsx — clarification_needed and no_constraint_found describe blocks"
        status: pass
    human_judgment: false
  - id: D5
    description: "ConstraintTranscript renders nothing when entries is empty; populated renders one node per entry keyed by id; auto-scrolls a bottom sentinel into view on a new entry"
    requirement: CONS-01
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ConstraintTranscript.test.tsx (empty + populated)"
        status: pass
    human_judgment: false
  - id: D6
    description: "ConstraintInput submits POST /constraints via useApplyConstraint.mutate(text); submit disabled while empty, over 2000 chars, or in flight; in-flight shows spinner + 'Applying…' and disables both textarea and button"
    requirement: CONS-01
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ConstraintInput.test.tsx — empty/submit/in-flight describe blocks"
        status: pass
    human_judgment: false
  - id: D7
    description: "Textarea clears ONLY when applied.length > 0 && clarification_needed === null; every other outcome (rejected-only, clarification, no-match, 503) preserves the typed text"
    requirement: CONS-04
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ConstraintInput.test.tsx — 'ConstraintInput: input-preservation [CONS-04, generalized rule]' (4 tests) + 'ConstraintInput: provider-down [D-04.4, CONS-05]'"
        status: pass
    human_judgment: false
  - id: D8
    description: "A 503 renders ProviderDownBanner (Alert default variant), never destructive styling — the 503-vs-422 branch keys off response.status only, never error message text"
    requirement: CONS-05
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ConstraintInput.test.tsx — 'ConstraintInput: provider-down [D-04.4, CONS-05]' + 'ConstraintInput: 422 backstop [UI-SPEC E4/422, structural]'"
        status: pass
    human_judgment: false
  - id: D9
    description: "Character counter '{n}/2000' appears past 1,800 characters and submit disables past 2,000 (client-side backstop against a guaranteed 422)"
    requirement: CONS-01
    verification:
      - kind: unit
        ref: "frontend/src/components/editor/ConstraintInput.test.tsx — 'ConstraintInput: char-limit backstop [UI-SPEC E4/long-text]' (2 tests)"
        status: pass
    human_judgment: false
  - id: D10
    description: "Long-text visual wrapping (2000-char submission, long rejected[].error string) — backstop, no automated visual evidence at spec time"
    verification: []
    human_judgment: true
    rationale: "Visual wrapping behavior is not assertable via RTL/jsdom (no real layout engine); routed to human verification in plan 02-07 per the plan's own backstop declaration."

duration: ~35min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 05: Constraint Input + Session Transcript + Provider-Down Banner Summary

**The Editor's write half — TranscriptEntry/ConstraintTranscript render all five POST /constraints outcomes (applied, rejected, mixed, clarification, no-match) with genuinely distinct D-04/D-05 treatments, and ConstraintInput submits via useApplyConstraint while honestly distinguishing a 503 provider outage from a validation rejection and preserving the user's text on every non-full-success outcome.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2 completed (both TDD, RED→GREEN pairs)
- **Files modified:** 7 (all created)

## Accomplishments
- `TranscriptEntry` renders one submission's outcome: `applied[]` items as the `parsed_constraint` string verbatim with a neutral `Check` icon (CONS-02); `rejected[]` items as "Couldn't apply: {Tool Label}" + the backend's `error` string verbatim, both `text-destructive` with an `X` icon (CONS-03); a mixed `applied[]`+`rejected[]` response rendering both sections in one entry (E5); `clarification_needed` as a neutral/muted question + rephrase caption (CONS-04); `no_constraint_found` as the neutral no-match message + caption (D-05)
- `ConstraintTranscript` is the D-03 session-log container: renders nothing (not even empty-state chrome) until the first submission, exports `TranscriptEntryData` (the shared entry shape `ConstraintInput` builds and the future Editor route will hold as session `useState`), auto-scrolls a bottom sentinel into view on a new entry, scrolls internally past a fixed height
- `ConstraintInput` submits via `useApplyConstraint(scenarioId).mutate(text, {...})`; whole-form disables while in flight (spinner + "Applying…"); a live "{n}/2000" counter appears past 1,800 characters and submit disables past 2,000; the Input-preservation rule clears the textarea **only** when `applied.length > 0 && clarification_needed === null` — rejected-only, clarification, no-match, and 503 all leave the typed text in place
- `ProviderDownBanner` is a fixed-copy `Alert variant="default"` (never `destructive`) rendered directly by `ConstraintInput` on a `503` — structurally disjoint from the transcript's rejection path, since a 503 throws before any 200 body exists and is never wrapped in a `TranscriptEntryData`
- Both tasks TDD'd RED→GREEN: implementation files were moved aside, tests written and confirmed failing on missing-module errors, implementations restored, tests confirmed green
- Full frontend suite green: 101/101 tests passing; `tsc --noEmit` clean; no `dangerouslySetInnerHTML` in either new component file

## Task Commits

Each task was committed atomically (TDD RED→GREEN pairs):

1. **Task 1: TranscriptEntry (four outcome treatments + no-match) and the ConstraintTranscript container**
   - RED: `1628763` (test) — failing tests for both components
   - GREEN: `a49625d` (feat) — implementations, 7/7 tests pass
2. **Task 2: ConstraintInput (form + status-branch + input-preservation + char-limit) and ProviderDownBanner**
   - RED: `b866794` (test) — failing test for ConstraintInput
   - GREEN: `b0d07e9` (feat) — implementations, 11/11 tests pass

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `frontend/src/components/editor/TranscriptEntry.tsx` - one submission's applied/rejected/clarification/no-match outcome render (D-04/D-05)
- `frontend/src/components/editor/TranscriptEntry.test.tsx` - applied/rejected/mixed/clarification/no-match coverage
- `frontend/src/components/editor/ConstraintTranscript.tsx` - D-03 session-log container; exports `TranscriptEntryData`
- `frontend/src/components/editor/ConstraintTranscript.test.tsx` - empty/populated coverage
- `frontend/src/components/editor/ConstraintInput.tsx` - Textarea + Apply Constraint form, status-branch, input-preservation, char-limit
- `frontend/src/components/editor/ConstraintInput.test.tsx` - empty/submit/in-flight/503/422/preservation/char-limit coverage (11 tests)
- `frontend/src/components/editor/ProviderDownBanner.tsx` - fixed-copy 503 banner, `Alert variant="default"`

## Decisions Made
- `ProviderDownBanner` carries `data-testid="provider-down-banner"` — no analog component had one; added since it's the first component whose test needs to positively assert "this is NOT a destructive-variant element" rather than just matching text.
- Rejected-item styling applies `text-destructive` to the wrapping `<div>` (covering the "Couldn't apply" heading and the error body together) rather than repeating the class on both `<p>` elements — one class satisfies UI-SPEC's "both in text-destructive" requirement.
- The 422 structural-backstop branch renders `data-testid="validation-error"` so the backstop test has a stable, copy-independent assertion target (UI-SPEC explicitly notes this path is visually unreachable via client-side gating in the ordinary flow).
- Used `crypto.randomUUID()` (with a `Date.now()`-based fallback) for fresh transcript-entry ids inside `ConstraintInput` — no existing repo convention for client-generated ids; `crypto.randomUUID` is the standard Web API and matches the session-only, non-persisted nature of transcript entries (D-03).

## Deviations from Plan

None - plan executed exactly as written. Both tasks followed the plan's `<action>`/`<read_first>` guidance directly against the `ErrorBanner`/`alert.tsx`/`CreateScenarioDialog`/`toolLabels.ts` analogs identified in `02-PATTERNS.md`, and the divergence the plan explicitly calls out (gating the textarea-clear on the response body inside `ConstraintInput`'s own `.mutate` callback, not inside `useApplyConstraint`) was followed as specified rather than copying `CreateScenarioDialog`'s unconditional clear.

## TDD Gate Compliance

Both tasks show the required RED→GREEN commit sequence in git log:
- Task 1: `test(02-05)` at `1628763` before `feat(02-05)` at `a49625d`
- Task 2: `test(02-05)` at `b866794` before `feat(02-05)` at `b0d07e9`

No REFACTOR commits were needed — both GREEN implementations passed on the first attempt with no cleanup required.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The Editor's write surface is complete: `ConstraintInput` submits, `ConstraintTranscript`/`TranscriptEntry` render every outcome distinctly, `ProviderDownBanner` honestly separates provider-down from validation.
- Plan 02-06 (Editor route) can now compose `ScenarioHeader` (02-04), `OverridesList` (02-04), `ConstraintTranscript`/`ConstraintInput` (this plan) into the full `/scenarios/:scenarioId` view: hold `TranscriptEntryData[]` as session `useState`, pass `appendEntry` as `ConstraintInput`'s `onOutcome` prop, and wire `useScenario`/`useOverrides` (02-03) through to `ScenarioHeader`/`OverridesList`.
- Backstops (long-text wrapping in the transcript, the 2000-char submission, the visually-unreachable 422 state) are routed to human verification in plan 02-07 per the plan's own declaration — no automated visual evidence exists at this layer.
- No blockers.

---
*Phase: 02-scenario-detail-plain-english-constraints*
*Completed: 2026-07-17*

## Self-Check: PASSED

All 7 created source files found on disk (`TranscriptEntry.tsx`, `TranscriptEntry.test.tsx`, `ConstraintTranscript.tsx`, `ConstraintTranscript.test.tsx`, `ConstraintInput.tsx`, `ConstraintInput.test.tsx`, `ProviderDownBanner.tsx`) plus this SUMMARY; all 4 task commit hashes (`1628763`, `a49625d`, `b866794`, `b0d07e9`) found in git log.
