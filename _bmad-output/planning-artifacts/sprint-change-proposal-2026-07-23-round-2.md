---
workflow: bmad-correct-course
date: 2026-07-23
project: ShiftMind
trigger: implementation-readiness-report-2026-07-23.md (verdict NEEDS WORK)
mode: batch
scopeClassification: Moderate (backlog reorganization, PO/DEV)
supersedes: sprint-change-proposal-2026-07-23.md (round 1)
status: APPLIED (2026-07-23) — edits made to epics.md, requirements-inventory.md, ARCHITECTURE-SPINE.md, and the PRD addendum
---

# Sprint Change Proposal — 2026-07-23 (Round 2)

## 1. Issue Summary

Round 1 of course correction cleared the 2026-07-22 readiness report's two criticals and four majors, and the re-check on 2026-07-23 confirmed a strong substrate: every required artifact exists, all 24 FRs have story coverage, UX and architecture are closely aligned, and Epics 1–5 form a coherent backward-only dependency sequence.

The re-check returned **NEEDS WORK** on five new findings, two of which are traceable to round 1's own remedies:

- **Critical:** Epic 6 — created by round 1 to absorb the old technical Epic 5 — is itself a mixed technical/release milestone. It bundles system-wide evaluation (6.1), a capability-registry enabler (6.2), and a cross-workflow visual audit (6.3). No planner workflow becomes newly usable at its completion, and FR23 is delivered as an architecture demonstration rather than through a concrete capability outcome.
- **Major:** NFR35 — created by round 1 to give the UX performance gap a home — was written as a placeholder to be fixed at sprint planning and cited by no story. The plan could report every story complete while a canonical acceptance requirement stayed unverified.
- **Major:** Six verification stories (1.9, 3.10, 4.5, 5.7, 6.1, 6.3) are aggregate gates spanning independent subsystems. Story 6.1 alone covered routing, authorization, approvals, grounding, injection, parity, solver edges, recovery, telemetry, accessibility, backup/restore, and rollback.
- **Minor:** Story 2.3 validated stream identity without stating the observable rejection behavior for a mismatched or malformed `Last-Event-ID`.
- **Minor:** Story 1.9's "future-agent projection fixture" could be misread as a dependency on Epic 2.

Still no implementation exists against this backlog and no `sprint-status.yaml` has been generated, so renumbering remains free.

## 2. Impact Analysis

### Epic impact

| Epic | Impact |
|---|---|
| Epic 1 | Story 1.4 and 1.5 gain NFR35 acceptance criteria. Story 1.9 splits into 1.9 (parity and mutation denial) and 1.10 (accessibility and Gate A readiness), and its fixture is renamed. 10 stories. |
| Epic 2 | Gains the evaluation harness as Story 2.2 and the governed capability module as Story 2.6 (FR23), both dissolved out of Epic 6. Old 2.2–2.7 shift to 2.3–2.9. Story 2.4 gains NFR35 and `Last-Event-ID` rejection criteria. 9 stories. |
| Epic 3 | Story 3.5 gains an NFR35 criterion. Story 3.10 splits into 3.10 (correctness), 3.11 (recovery/idempotency), and 3.12 (browser journey). 12 stories. |
| Epic 4 | Story 4.5 splits into 4.5 (approval and audit invariants) and 4.6, which also absorbs old Story 6.3's cross-workflow visual audit — placed here because Epic 4 is where the planner workflow becomes complete. 6 stories. |
| Epic 5 | Story 5.7 splits into 5.7 (rollback) and 5.8 (hosted invariant suite, which also evaluates the Release Gate). 8 stories. |
| Epic 6 | **Dissolved.** No epic 6 exists. |

Dependency direction remains strictly backward-only: 1 → 2 → 3 → 4 → 5. Total: 45 stories across 5 epics (was 41 across 6).

### Artifact impact

- **epics.md** — primary artifact: Epic 6 removed, Epic 2 restructured and renumbered, five proof stories split, NFR35 added as a numbered requirement and cited by four stories, new Release Gate and Story Map sections.
- **requirements-inventory.md** — NFR35 finalized (placeholder removed) and given a normative measurement protocol; FR23 pointer retargeted to Epic 2.
- **ARCHITECTURE-SPINE.md** — new **AD-26** allocating NFR35's four thresholds to AD-4, AD-6, and AD-21; capability map row added.
- **PRD addendum** — paragraph recording that NFR35 is final and binding, not deferred.
- **EXPERIENCE.md / DESIGN.md** — no change needed; the supported browser/assistive-technology matrix added in round 1 already scopes the accessibility claim, which was the standing warning.
- **Technical impact:** none — no code implements this backlog.

## 3. Recommended Approach

**Direct Adjustment (Option 1).** No scope reduction, no rollback. Every finding is addressable by restructuring `epics.md` plus three small contract edits; the FR set, MVP scope, architecture decisions, and acceptance-criteria content are all preserved.

Rollback was considered and rejected: nothing has been implemented, so there is nothing to revert. MVP review was considered and rejected: the readiness report found the requirements sound and the coverage complete — the defect is in backlog shape, not product scope.

- **Effort:** Medium. **Risk:** Low. **Timeline impact:** one revision cycle plus a readiness re-check.

## 4. Detailed Change Proposals

### 4.1 Critical — Dissolve Epic 6

The readiness report's remedy was to "treat evaluation and visual regression as definitions of done attached to the epics they protect" and to rehome FR23 in a concrete capability outcome or the earliest registry-owning slice. Applied literally:

| Old | New home | Why there |
|---|---|---|
| Story 6.1 (evaluation gating) | Split three ways: the harness and report version-binding become **Story 2.2** (a technical enabler, since Story 2.1's spike already proves deterministic model doubles); per-slice suites already live in each epic's proof stories and now cite the harness explicitly; the aggregate thresholds become the **Release Gate** section, evaluated by Story 5.8. | Evaluation is needed from the first agent slice onward, not at the end. Only the aggregates genuinely cannot be measured by one story. |
| Story 6.2 (capability module, FR23) | **Story 2.6**, immediately after Story 2.5 establishes the application-owned registry. | This is "the earliest registry-owning slice." FR23's coverage moves from Epic 6 to Epic 2. |
| Story 6.3 (visual audit) | **Story 4.6**, merged with old Story 4.5's approval-journey accessibility criteria. Per-component visual fixtures remain owned by Story 1.6 and by each UI story. | Epic 4 is the point at which the planner workflow is complete, so a cross-workflow audit has a real subject. |

A short note replaces Epic 6 in the Epic List explaining that release evaluation is a definition of done rather than an epic, so a future reader does not re-create it.

**New Release Gate section** holds only what no single story can measure: deterministic-first CI, report version binding, golden-dataset size (NFR28), tool-routing percentages, the NFR35 roll-up, and the release-blocking regression list (NFR29) — each with a named evidence owner.

### 4.2 Major — Close NFR35

**Finalized, no longer a placeholder.** The four thresholds stand at their round-1 defaults (2 s / 2 s / 5 s / 5 s), now stated as final rather than provisional. The gap the readiness report identified was not that the numbers were wrong — it was that a number with no measurement method and no owning story cannot be accepted or refuted.

**New normative measurement protocol** in `requirements-inventory.md` fixes fixture scale (largest Gate A fixture at full size), environment (CI reference runner, not hosted AWS), warm/cold conditions, the run rule (three runs, all must pass — a deterministic rule rather than a percentile, because three samples cannot support a percentile claim), clock boundaries (server-side measures exclude network and render; client-observed measures run to event receipt), and evidence format.

**NFR35 added to `epics.md`'s numbered register** and cited by four story acceptance criteria: Story 1.4 (group-window load), Story 1.5 (evidence-target resolution), Story 2.4 (SSE reconnect replay), Story 3.5 (first persisted run event). Each criterion names the fixture, the clock boundary, the run rule, and states that a miss blocks acceptance of that story.

**New AD-26** allocates the thresholds to components — the scenario read service (AD-4) owns the two read measures, the persisted workflow boundary (AD-6) owns first-event latency, the SSE contract (AD-21) owns replay — and restates that these are never customer objectives (NFR17).

### 4.3 Major — Split aggregate proof stories

Acceptance-criteria text is preserved and redistributed; only the boundaries change.

| Old story | New stories | Seam |
|---|---|---|
| 1.9 Prove Viewer Integrity and Accessibility | **1.9 Prove Viewer Parity and Mutation Denial** (ACs 1–2) · **1.10 Prove Scenario Data Accessibility and Gate A Readiness** (ACs 3–5) | Correctness/security vs accessibility |
| 3.10 Prove Repair Correctness and Recovery | **3.10 Prove Repair Correctness** (ACs 1–2) · **3.11 Prove Recovery and Idempotency** (AC 3 + regression gate) · **3.12 Prove the Repair Browser Journey** (AC 4 + Epic 3 visual states) | Correctness vs recovery vs accessibility |
| 4.5 Prove Approval, Audit, and Provenance Invariants | **4.5 Prove Approval and Audit Invariants** (ACs 1–4) · **4.6 Prove the Decision Journey and Cross-Workflow Visual Consistency** (AC 5 + old 6.3) | Backend invariants vs journey/visual audit |
| 5.7 Prove Rollback and the AWS Invariant Suite | **5.7 Prove Rollback** (AC 1) · **5.8 Prove the Hosted Invariant Suite** (AC 2 + Release Gate evaluation) | Rollback vs hosted proof |
| 6.1 Gate Releases with Versioned Evaluation | Dissolved per Section 4.1 | — |

### 4.4 Minor findings

- **Story 2.4** gains an explicit criterion: a malformed `Last-Event-ID`, one referencing a different stream, or one carrying an impossible sequence is rejected with a stable non-disclosing problem response that reveals no other stream's existence, position, or content; no events replay from the mismatched stream; and the browser recovers from its own persisted cursor or labelled polling without duplicating or dropping visible activity.
- **Story 1.9** now compares against "the shared `ScenarioProjectionV1` contract fixture" and states explicitly that AgentRuntime and agent capabilities are not required, removing the false Epic 2 dependency reading.

### 4.5 Standing warnings (no edit required)

Both readiness warnings were reviewed and deliberately left as-is:

1. Pagination versus virtualization stays implementation-tunable. This is safe because the semantic, accessibility, deterministic-order, exact-target, and bounded-navigation contracts remain mandatory in UX-DR14, UX-DR16, UX-DR24, and Story 1.8 — the tunable part is the rendering strategy, not the contract.
2. The accessibility claim stays scoped to the declared portfolio matrix (latest Chrome and Edge on Windows, NVDA, keyboard, zoom/text spacing, reduced motion), already recorded in `EXPERIENCE.md` and referenced by the PRD addendum. It must not be presented as broader cross-platform conformance.

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization plus small contract edits. PRD goals, MVP scope, and architecture decisions all stand.

| Recipient | Responsibility |
|---|---|
| Developer agent (backlog editor) | Applied — all Section 4 edits are in `epics.md`, `requirements-inventory.md`, `ARCHITECTURE-SPINE.md`, and the PRD addendum. |
| Product Owner (Minh) | Confirm the NFR35 thresholds are acceptable as final rather than provisional, and that dissolving Epic 6 into definitions of done matches your intent for release governance. |
| Readiness re-check | Re-run `bmad-check-implementation-readiness`; target: the critical and both majors cleared, both minors closed, 100% FR coverage retained, and no new epic-structure defect introduced by this round. |

**Success criteria:** no epic is a mixed technical/release milestone; every FR is delivered inside a user-value epic; NFR35 is final, measurable, allocated to components, and cited by the stories that own it; no proof story spans independent security, correctness, recovery, accessibility, and deployment subsystems; every story remains satisfiable from prior stories alone.

**Next step:** re-run the readiness check, then sprint planning and story creation.
