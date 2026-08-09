---
title: "Sprint Change Proposal: Descope Manual NVDA Screen-Reader Verification"
status: approved
created: 2026-08-09
---

# Sprint Change Proposal: Descope Manual NVDA Screen-Reader Verification

## 1. Issue Summary

`evidence/story-1.11/gate-a-readiness-report.json` recorded `gate_a_passed: false`,
blocking Epic 2. All six AR28 invariants passed; the sole blocker was the
`accessibility_evidence` check (Story 1.10, NFR29), which recorded the manual
NVDA screen-reader pass as `not executed — manual NVDA pass started with NVDA
installed and Speech Viewer active, then cancelled by the user, 2026-08-08`.

The user (Minh, product owner) reported spending 1.5+ days on this single
check and identified it as disproportionately costly given the project's
actual purpose: a CV/portfolio MVP for AI Engineer (secondarily Software
Engineer) hiring, not a commercial product with real users. Per
`_bmad-output/planning-artifacts/briefs/brief-ShiftMind-2026-07-21/brief.md`,
this is explicitly "an AI Engineer portfolio MVP," and "commercial validation
with real planners... [is a] prerequisite for claiming product-market fit" —
i.e. no real users exist today. The user requested NVDA be removed from the
project entirely, and Gate A be resolved so Epic 2 can begin.

Issue type: strategic/scope decision (portfolio-goal alignment), not a
technical failure — the manual pass mechanism itself worked as designed
(Story 1.9/1.10/1.11's evidence machinery correctly recorded an honest `not
executed` rather than a false pass).

## 2. Impact Analysis

**Epic impact:** Contained to Epic 1 (Story 1.10's evidence, Story 1.11's
readiness report) and the shared UX spec. Epics 2–5 are not restructured.

**Root-cause finding:** The NVDA mandate traced to exactly one place in the
planning artifacts — `EXPERIENCE.md`'s Accessibility Floor, "Supported test
matrix (portfolio minimum)" line. Story 1.10's AC and PRD's NFR18/NFR29 are
outcome-level ("screen-reader use" must work) and never mandated a manual
proof method; they required no change. This means Epics 3–5, which also
reference "screen-reader use" in their ACs, do **not** inherit an NVDA-style
manual-verification requirement from this change — only `EXPERIENCE.md`
needed correcting to prevent recurrence.

**Artifacts touched:**
- `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — Accessibility Floor test matrix redefined to automated-only, with the descope rationale stated inline.
- `docs/GATE-A-RUNBOOK.md` — §3 (manual NVDA procedure) removed; sections renumbered; descope note added near the top.
- `docs/ACCESSIBILITY-NVDA-CHECKLIST.md` — deleted.
- `frontend/e2e/manual-nvda.spec.ts` — deleted.
- `frontend/vite.config.ts` — stale comment referencing the deleted spec file removed.
- `evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json` — `nvda_manual_pass` / `manual_screen_reader` fields replaced with an honest `manual_assistive_tech_verification: descoped` record; `policy` binding updated; `passed` flips `false → true` since no field remains recording a `not executed` result.
- `backend/scripts/gate_a_checks.py` — `accessibility_evidence` check description updated to reflect automated-only proof.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — dated note recording the decision and rationale, prepended per the log's existing convention.

**No impact:** PRD (NFR18/20/27/29 text unchanged), Architecture, other epics' story text, the automated accessibility suites themselves (64 jsdom + 20 Playwright browser a11y tests unaffected and remain the accessibility bar).

## 3. Recommended Approach

**Selected: Option 1 — Direct Adjustment.** The NVDA mandate was confined to
one UX-spec line plus Story 1.10's implementation-level evidence; no PRD
rewrite (Option 3) or rollback (Option 2) was needed.

- Effort: Low (documentation, evidence-content, and registry-description edits; no application code changed).
- Risk: Low (automated accessibility coverage — jsdom + Playwright a11y/browser suites — is untouched and remains the recorded bar; the descope is explicit and traceable, not a silent weakening).

Rationale: matches the project's own stated priority (system design,
architecture, AI-agent engineering over frontend/accessibility depth for a
portfolio targeting AI Engineer/SWE hiring) and removes a check whose
effort-to-signal ratio, for that specific goal, was poor.

## 4. Detailed Change Proposals

All four groups below were presented and approved incrementally in
conversation (Incremental mode, per user's explicit preference):

| Group | Change | Status |
|---|---|---|
| A | `EXPERIENCE.md` Accessibility Floor test matrix — remove NVDA, state automated-only bar and descope rationale | Approved & applied |
| B | Delete `ACCESSIBILITY-NVDA-CHECKLIST.md`, `frontend/e2e/manual-nvda.spec.ts`; remove `GATE-A-RUNBOOK.md` §3; renumber; clean `vite.config.ts` comment | Approved & applied |
| C | Rewrite `evidence/story-1.10/…json` semantic fields (descope record, `passed: true`); update `gate_a_checks.py` check description | Approved & applied |
| D | `sprint-status.yaml` dated note; regenerate `evidence/story-1.11/gate-a-readiness-report.json` via the proper pipeline | Approved — execution below |

Verification after Groups A–C: `pytest tests/test_evidence_binding.py
tests/test_evidence_convention.py tests/test_gate_a_readiness.py` → 101
passed, 1 skipped (the one skip is the binding-realism check's own designed
behavior on a dirty tree — expected mid-change, resolves once committed).

## 5. Implementation Handoff

**Scope classification: Minor.** Documentation, evidence-content, and a
check-description edit; no architecture, PRD, or application-code change.
Implemented directly in this session (acting as Developer) rather than
handed off, per the user's request to complete it now.

**Remaining steps (Group D execution):**
1. Commit all Group A–D changes on a clean tree.
2. Run pytest / vitest / Playwright, writing JUnit XML per `GATE-A-RUNBOOK.md`.
3. `scripts/regenerate_evidence.py` to rebind `evidence/story-1.10/…json`'s version/commit bindings (semantic content already hand-edited in Group C, per `EVIDENCE-CONVENTION.md`).
4. `scripts/gate_a_readiness.py` to regenerate `evidence/story-1.11/gate-a-readiness-report.json` — expected `gate_a_passed: true`.
5. Commit evidence separately from code, per convention.

**Success criteria:** `gate_a_passed: true` with all AR28 invariants and the
NFR29 accessibility gate passing on automated evidence alone; zero remaining
NVDA references repo-wide; Epic 2 unblocked.
