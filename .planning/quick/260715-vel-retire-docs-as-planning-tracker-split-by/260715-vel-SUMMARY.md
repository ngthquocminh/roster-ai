---
phase: quick-260715-vel
plan: 01
subsystem: docs
tags: [docs, gsd-planning, api-reference, design-doc]

# Dependency graph
requires: []
provides:
  - "docs/ split by lifecycle owner: .planning/ owns planning lifecycle, docs/ owns reference (API.md/design.md) + origin (vision.md)"
  - "docs/API.md documents the shipped LLM layer (POST /constraints, GET /runs/{id}/insights) with contracts verified against backend code"
  - "docs/design.md trimmed to durable 'why' + shipped LLM-layer design folded in as a numbered section"
  - "docs/README.md ownership-boundary statement"
  - "docs/archive/ holding the two superseded Phase 1-2 plan docs, history preserved via git mv"
affects: [docs, gsd-onboarding, gsd-map-codebase]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docs/ vs .planning/ ownership split: one owner per audience, stated in docs/README.md and docs/design.md's header"

key-files:
  created:
    - docs/README.md
    - docs/archive/phase-1-engine.md (moved via git mv, re-headered)
    - docs/archive/phase-2-backend.md (moved via git mv, re-headered)
  modified:
    - docs/API.md
    - docs/design.md
    - docs/vision.md
    - README.md
    - .planning/PROJECT.md
  deleted:
    - docs/PLAN.md

key-decisions:
  - "docs/PLAN.md deleted outright (not archived) — pure duplication of .planning/STATE.md+ROADMAP.md+MILESTONES.md; confirmed zero loss (its 5 deferred follow-ups already in .planning/todos/pending/, its phases 4/5 already in PROJECT.md) before deleting"
  - "docs/vision.md kept at its original path, not moved to archive/ — it's a deliberately permanent origin snapshot, not a rotting tracker; only its self-deprecation sentence was removed"
  - "Shipped LLM-layer design folded into docs/design.md as new §4, renumbering old §4 (Later phases) to §5 and old §5 (Open decisions) to §6"
  - "PROJECT.md's false ADR claim corrected by removing the docs/decisions/ string entirely rather than stating 'it doesn't exist' — avoids the same false claim resurfacing as a different kind of misdirection"

requirements-completed: []

coverage:
  - id: D1
    description: "docs/PLAN.md deleted after confirming zero loss; docs/archive/phase-{1,2}-*.md created via git mv with history preserved"
    verification:
      - kind: other
        ref: "test ! -f docs/PLAN.md && test -f docs/archive/phase-1-engine.md && test -f docs/archive/phase-2-backend.md && git log --oneline --follow -- docs/archive/phase-1-engine.md (2 commits, history preserved)"
        status: pass
    human_judgment: false
  - id: D2
    description: "docs/vision.md unchanged except its one self-deprecation sentence removed"
    verification:
      - kind: other
        ref: "git diff 94cf788~1 94cf788 --stat -- docs/vision.md → 1 file changed, 1 deletion(-)"
        status: pass
    human_judgment: false
  - id: D3
    description: "docs/README.md states the one-owner-per-audience boundary"
    verification:
      - kind: other
        ref: "docs/README.md (manual read)"
        status: pass
    human_judgment: true
    rationale: "Prose quality/clarity of the ownership statement is a judgment call, not something a grep can verify"
  - id: D4
    description: "docs/API.md documents POST /constraints and GET /runs/{run_id}/insights with contracts verified against backend/api/routers/{constraints,runs}.py and backend/api/schemas.py (including 200+ready=false not-ready case and 502 failure code), plus LLM_PROVIDER"
    verification:
      - kind: other
        ref: "grep -q 'POST /constraints' && grep -q 'runs/{run_id}/insights' && grep -q 'LLM_PROVIDER' && grep -q 'insight_json' && grep -q '502' && grep -q 'no_constraint_found' && grep -q 'clarification_needed' docs/API.md — all pass"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/design.md: no phase map/status claims, provider diagram fixed (stub+Gemini+OpenRouter), AWS deploy claim, shipped LLM-layer numbered section, §1/§3/§6 intact, ownership rule stated"
    verification:
      - kind: other
        ref: "grep -q 'OpenRouter' && grep -q 'to_override_call' && grep -q 'ROADMAP.md' && grep -q 'CloudFront' && ! grep -qi 'Render' && ! grep -qi 'Gemini later' && ! grep -q '← *current*' && ! grep -q 'Phase map' && grep -q 'gsd-map-codebase' docs/design.md — all pass"
        status: pass
    human_judgment: false
  - id: D6
    description: "PROJECT.md Context makes no false ADR/tracker claims; zero dangling markdown links to deleted/moved files in README.md, docs/, PROJECT.md, STATE.md, CLAUDE.md; historical/generated artifacts left untouched"
    verification:
      - kind: other
        ref: "! grep -rEn link-regex ... && ! grep -rn 'docs/decisions' ... && grep -q 'vision.md' PROJECT.md && grep -q 'docs/README.md' README.md — all pass; git diff --stat HEAD -- backend/ empty"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-15
status: complete
---

# Quick Task 260715-vel: Retire docs/ as a planning tracker, split by lifecycle owner Summary

**Deleted the duplicate docs/PLAN.md tracker, archived the two Phase 1-2 plan docs via `git mv`, fixed design.md's inverted LLM-provider diagram and wrong deploy target, added the missing LLM-layer endpoints to API.md, corrected PROJECT.md's false ADR claim, and swept every dangling link the split created.**

## Performance

- **Duration:** ~12 min (across 3 task commits)
- **Started:** 2026-07-15T15:44:41Z (first task commit)
- **Completed:** 2026-07-15T15:51:06Z (final task commit)
- **Tasks:** 3
- **Files modified:** 9 (1 deleted, 2 moved, 1 created, 5 modified)

## Accomplishments

- `docs/PLAN.md` deleted after verifying every item it tracked (5 deferred follow-ups, 2 future phases) already lives in `.planning/`
- `docs/phase-1-engine.md` and `docs/phase-2-backend.md` archived to `docs/archive/` via `git mv`, history preserved (`git log --follow` confirms 2 commits each), re-headered as historical records pointing to `design.md`/`API.md`/`.planning/`
- `docs/vision.md` frozen in place (unchanged path) with its single self-deprecation sentence removed — it's a permanent origin snapshot now
- `docs/README.md` created, stating the one-owner-per-audience boundary that the retired tracker violated
- `docs/API.md` gained full documentation for `POST /constraints` and `GET /runs/{run_id}/insights`, both verified line-by-line against `backend/api/routers/constraints.py`, `runs.py`, and `schemas.py` — including the real `200 + ready=false` not-ready shape (not `409`, unlike `/result`) and the real `502` insight-failure code
- `docs/design.md` trimmed to "why": removed the phase map and all phase-status claims, fixed the §2 provider diagram (was inverted — named a provider that was never built; now correctly shows stub default + Gemini + OpenRouter), fixed the Deploy claim (was Docker Compose + a free-tier PaaS host; actual shipped target is AWS), and folded the shipped LLM-layer design in as a new numbered §4 (Protocol seams, `to_override_call` translation boundary, `OverrideCall` content-hash seam, soft-only overrides, five tools, scenario-ID validation, D-06 grounding guard, cached on-demand insights)
- `.planning/PROJECT.md`'s Context section no longer claims a nonexistent `docs/decisions/` ADR directory or calls the deleted tracker current; points to `docs/vision.md` as the origin snapshot
- Full link sweep across `README.md`, `docs/`, `PROJECT.md`, `STATE.md`, `CLAUDE.md` — fixed README.md's Layout tree block and Documentation list (both named the deleted tracker); zero dangling links remain

## Task Commits

Each task was committed atomically:

1. **Task 1: Retire the tracker, archive the phase docs, freeze vision.md, write the ownership boundary** - `94cf788` (docs)
2. **Task 2: Make docs/ tell the truth — API.md gains the LLM layer, design.md is trimmed to "why"** - `bf26802` (docs)
3. **Task 3: Fix PROJECT.md's false Context claims, then sweep every dangling link the split created** - `0729b21` (docs)

_No test/feat/refactor split — this is a docs-only quick task, no `tdd="true"` tasks._

## Files Created/Modified

- `docs/PLAN.md` - deleted (pure duplication of `.planning/STATE.md`+`ROADMAP.md`+`MILESTONES.md`)
- `docs/archive/phase-1-engine.md` - moved from `docs/phase-1-engine.md` (git mv), re-headered as archived historical record with fixed sibling links (`../design.md`)
- `docs/archive/phase-2-backend.md` - moved from `docs/phase-2-backend.md` (git mv), re-headered, fixed sibling links (`../design.md`, `../API.md`)
- `docs/vision.md` - removed 1 sentence (self-deprecation); every other byte unchanged
- `docs/README.md` - new; states the one-owner-per-audience boundary
- `docs/API.md` - added `POST /constraints` + `GET /runs/{run_id}/insights` endpoint docs, `ConstraintParseResponse`/`InsightOut` data models, `LLM_PROVIDER`+LLM env vars in Configuration, broadened intro/status-code-summary beyond "Phase 2"
- `docs/design.md` - removed phase map/status claims; fixed §2 provider diagram and Deploy claim; folded shipped LLM-layer design in as new §4 (renumbered old §4→§5, §5→§6); fixed §3.1 repo-layout tree; stated the design.md-vs-`.planning/codebase` ownership rule in the header
- `README.md` - Layout tree block and Documentation list updated to drop the deleted tracker, add `docs/README.md` and `docs/archive/`, keep `docs/vision.md` at its unchanged path
- `.planning/PROJECT.md` - Context section corrected: no ADR directory claim, no "PLAN.md is current" claim, added a pointer to `docs/vision.md` as the origin snapshot

## Decisions Made

- **`docs/PLAN.md` deleted, not archived** — it was pure duplication with zero unique content once confirmed against `.planning/`; archiving it would have kept a second, now-frozen copy of information `.planning/` already owns forever.
- **`docs/vision.md` stays at its original path** — per the plan's explicit instruction, it's a deliberately permanent origin snapshot whose value grows over time, unlike the phase docs whose value dropped to zero once `design.md` absorbed their durable content.
- **Renumbered `docs/design.md`'s sections** (old §4→§5, §5→§6) to make room for the new shipped-LLM-layer §4 as a first-class numbered section, per the retired tracker's own documented "when it ships, fold the durable design into design.md" rule.
- **PROJECT.md's ADR correction avoids naming the specific `docs/decisions/` path** — states "no ADR directory exists" and lists where decisions actually live, rather than naming and negating the specific wrong path, so the string `docs/decisions` doesn't reappear anywhere in a live document.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PROJECT.md's ADR correction initially still contained the literal string `docs/decisions/`**
- **Found during:** Task 3, during self-verification of the automated verify gate
- **Issue:** My first edit to PROJECT.md's Context section corrected the false claim by writing "There is no ADR directory (`docs/decisions/` does not exist)" — technically accurate, but this still leaves the literal substring `docs/decisions` in a live document, which the plan's own verify gate (`! grep -rn 'docs/decisions' .planning/PROJECT.md README.md docs/`) is designed to catch regardless of context.
- **Fix:** Reworded to state "No ADR directory exists in this repo" without naming the specific (nonexistent) path, so the false-claim string doesn't reappear even in a corrective context.
- **Files modified:** `.planning/PROJECT.md`
- **Verification:** Re-ran the exact verify-gate command from the plan; passes.
- **Committed in:** `0729b21` (Task 3 commit — caught before commit, not a separate fix commit)

---

**Total deviations:** 1 auto-fixed (1 bug, caught pre-commit during self-verification)
**Impact on plan:** No scope creep — same correction, worded to actually satisfy the plan's own verify gate.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `docs/` is now clean: `API.md`, `design.md`, `vision.md`, `README.md`, `archive/` — no lifecycle tracking duplication, no false claims found during the link sweep.
- Two prose mentions of `docs/PLAN.md` remain, both reviewed and intentionally left: `docs/README.md`'s explanatory sentence about why the split happened, and `.planning/STATE.md`'s "migrated out of docs/PLAN.md at the v0.3/v0.4 boundary" note under Pending Todos — both are factual, non-link, historical/explanatory prose, not dangling references.
- `.planning/config.json` and `.planning/milestones/v0.3-ROADMAP.md` were confirmed as false-positive matches (GSD plan filenames like `01-01-PLAN.md`) and correctly left untouched — these files are outside the swept scope (README.md, docs/, PROJECT.md, STATE.md, CLAUDE.md) per the plan.
- No blockers for future work. This was a pure docs/ + PROJECT.md correction; `git diff --stat HEAD -- backend/` confirmed empty at every step.

---
*Phase: quick-260715-vel*
*Completed: 2026-07-15*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`docs/README.md`, `docs/archive/phase-{1,2}-*.md`,
`docs/vision.md`, `docs/API.md`, `docs/design.md`, `README.md`, `.planning/PROJECT.md`, this SUMMARY);
`docs/PLAN.md` confirmed absent. All three task commits (`94cf788`, `bf26802`, `0729b21`) confirmed present
in `git log`.
