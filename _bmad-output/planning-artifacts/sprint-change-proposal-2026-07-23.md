---
workflow: bmad-correct-course
date: 2026-07-23
project: ShiftMind
trigger: implementation-readiness-report-2026-07-22.md (verdict NOT READY)
mode: batch
scopeClassification: Moderate (backlog reorganization, PO/DEV)
status: APPROVED (2026-07-23) — all edits applied to epics.md, requirements-inventory.md (new), PRD addendum, ARCHITECTURE-SPINE.md, and EXPERIENCE.md
supersededBy: sprint-change-proposal-2026-07-23-round-2.md — the Epic 6 created by this round (Section 4.4) was dissolved by round 2; story numbering here is historical
---

# Sprint Change Proposal — 2026-07-23

## 1. Issue Summary

The implementation-readiness assessment (2026-07-22, `implementation-readiness-report-2026-07-22.md`) returned **NOT READY** for Phase 4 story execution. Product intent is not in question: all 24 PRD FRs have concrete story coverage, UX and architecture are strongly aligned, and acceptance criteria are detailed and testable. The blocking condition is **backlog structure**:

- **CQ-1 (critical):** Epic 5 is a technical milestone ("the product team" as beneficiary; infra/eval/telemetry layers) rather than a user-value epic.
- **CQ-2 (critical):** Story 3.4 requires approval-required behavior and the `ApprovalRequest` aggregate, which Epic 4 introduces — a forward dependency.
- **MQ-1:** Story 3.1 exposes an active Run optimization control before Story 3.5 implements the command.
- **MQ-2:** Stories 1.4, 1.5, 2.2, 3.3, 5.9 each bundle multiple independently risky concerns.
- **MQ-3:** Visual-system consolidation (Story 5.2) lands after four UI-heavy epics.
- **MQ-4:** No canonical numbered NFR catalogue; PRD (23 unnumbered) and epics (34 numbered) diverge.
- **Minors NQ-1–NQ-3** and three UX-alignment gaps (`last verified` contract, internal performance thresholds, UX traceability/AT matrix).

No implementation has started from this backlog and no `sprint-status.yaml` exists, so restructuring and renumbering now carries near-zero migration cost.

## 2. Impact Analysis

### Epic impact

| Epic | Impact |
|---|---|
| Epic 1 | Gains one enabler story (design tokens/primitives, from MQ-3) and splits Stories 1.4 and 1.5 (MQ-2). Stories renumbered 1.1–1.9. |
| Epic 2 | Splits Story 2.2 into persistence vs live replay (MQ-2). Stories renumbered 2.1–2.7. |
| Epic 3 | Story 3.4 restricted to `AgentRun`/`ScheduleRun` (CQ-2); Story 3.1 loses the active Run optimization control (MQ-1); Story 3.3 splits (MQ-2). Stories renumbered 3.1–3.10. |
| Epic 4 | Story 4.1 explicitly introduces the `ApprovalRequest` state machine and approval-required transitions deferred from 3.4. No renumbering. |
| Epic 5 | Restructured (CQ-1): becomes **Epic 5 — Reliable Hosted Planner Workspace** (observability, AWS provisioning, deployment, backup/restore, mixed-version rollout, rollback proof; old 5.9 split per MQ-2). |
| Epic 6 (new) | **Evidence-Gated Release and Governed Growth**: release evaluation gating (old 5.3), governed capability module as a marked Technical Enabler for FR23 (old 5.1), and a slimmed cross-workflow visual regression/consistency audit (residue of old 5.2). |

Dependency direction remains strictly backward-only: 1 → 2 → 3 → 4 → 5 → 6.

### Artifact impact

- **epics.md** — primary artifact; all structural edits in Section 4.
- **New: requirements-inventory.md** — canonical numbered NFR catalogue with provenance (MQ-4).
- **PRD addendum** — one paragraph adopting the inventory as normative and declaring the UX-derived accessibility/responsive constraints normative.
- **ARCHITECTURE-SPINE.md** — define `ScenarioProjectionV1.projection_generated_at` semantics (UX `last verified` gap).
- **UX EXPERIENCE.md** — add FR-21 and FR1–FR3 rows to the source-coverage table; name the supported browser/assistive-technology matrix.
- **Technical impact:** none yet — no code implements this backlog; no rollback needed.

## 3. Recommended Approach

**Direct Adjustment (Option 1).** Modify the epic/story structure in place; no scope reduction, no rollback.

- **Rationale:** The readiness report states the requirements and architecture "do not need wholesale redesign" and that "a focused backlog and contract-governance revision should be sufficient." All 15 findings are addressable by restructuring `epics.md` plus small contract/documentation edits. MVP scope, FR set, and acceptance-criteria content are preserved.
- **Effort:** Medium (one focused backlog revision plus three small doc edits).
- **Risk:** Low — renumbering is free while no sprint status or implementation references story IDs.
- **Timeline impact:** One revision cycle plus a readiness re-check before Phase 4.

## 4. Detailed Change Proposals

All edits target `_bmad-output/planning-artifacts/epics.md` unless stated otherwise. Acceptance-criteria *content* is preserved wherever a story moves or splits — only structure, framing, and the specific defects below change.

### 4.1 CQ-2 — Remove Story 3.4's forward dependency on Epic 4

**Story 3.4 (new number 3.5), AC 1:**

OLD:
> **Given** an agent run, schedule run, and optional approval pause
> **When** each aggregate transitions
> **Then** it follows its separate closed architecture state machine and emits one monotonic persisted event with stable reason/resource version
> **And** adapters may project a combined timeline but never merge stored status types. (FR13, AR7)

NEW:
> **Given** an agent run and a schedule run
> **When** each aggregate transitions
> **Then** each follows its separate closed architecture state machine and emits one monotonic persisted event with stable reason/resource version; shared closed status enums and contracts may declare the approval-required literal, but no acceptance in this story exercises approval behavior or the ApprovalRequest aggregate
> **And** adapters may project a combined timeline but never merge stored status types. (FR13 — approval-required presentation completes in Epic 4, AR7)

**Story 4.1, append to AC 1:**

> **And** this story introduces `ApprovalRequest` persistence and the agent-run approval-required transitions deferred from Epic 3.

**FR Coverage Map, FR13 line:**

OLD: `FR13: Epic 3 - Persisted progress states and recovery`
NEW: `FR13: Epic 3 - Persisted progress states and recovery (approval-required state completes in Epic 4, Story 4.1)`

**Rationale:** Story 3.4 must be completable from prior stories only (CQ-2 remediation, verbatim from the readiness report).

### 4.2 MQ-1 — Defer the active Run optimization control to Story 3.5

**Story 3.1, AC 2:**

OLD:
> **Then** the Draft card shows resolved entities, constraints/objectives, locks, expected versions, consequences, and “Draft — no baseline change”
> **And** revise, reject, and Run optimization are separate controls from Send and approval. (FR10, UX-DR9, UX-DR35)

NEW:
> **Then** the Draft card shows resolved entities, constraints/objectives, locks, expected versions, consequences, and “Draft — no baseline change”
> **And** revise and reject are separate active controls from Send and approval, while the Run optimization slot renders disabled with accessible sequencing copy until the compute command exists. (FR10, UX-DR9, UX-DR35)

**Story 3.5 (new number 3.6), append to AC 1:**

> **And** this story activates the Draft card's Run optimization control introduced as a disabled slot in Story 3.1.

**Rationale:** A visible control without its complete command path is not an independently complete increment (MQ-1).

### 4.3 MQ-2 — Split oversized stories at contract boundaries

Each split preserves the existing AC text, redistributed as listed. Backward-only ordering is preserved.

| Old story | New stories | Seam |
|---|---|---|
| 1.4 Serve One Normalized Scenario Projection | **1.4 Serve the Normalized Scenario Read Contract** (ACs 1, 2 minus exact-target sentence, 4) and **1.5 Resolve Exact Evidence Targets** (AC 3 plus the exact-target lookup clause of AC 2) | Read contract vs exact-target behavior |
| 1.5 Inspect Scenario Data Read-Only | **1.7 Open the Read-Only Scenario Data Workspace** (ACs 1, 4, and the semantic-table/read-only core of AC 2) and **1.8 Control Scenario Data Tables** (sorting/filtering/counts/bounded navigation/identifier copy from AC 2, plus AC 3 column chooser) | Basic read-only workspace vs advanced table controls |
| 2.2 Create and Revisit Durable Conversations | **2.2 Persist Conversations Durably** (ACs 1, 2, 3) and **2.3 Replay Conversation Events Live** (AC 4: SSE, `Last-Event-ID`, heartbeats) | Durable persistence vs live replay |
| 3.3 Lease and Recover Solver Jobs Safely | **3.3 Lease Solver Jobs with Fencing** (ACs 1, 2, 3) and **3.4 Cancel Queued and Running Work** (AC 4 plus the cancellation-race clause) | Leasing/fencing vs cancellation |
| 5.9 Prove Mixed-Version Safety and Rollback | **5.6 Roll Out Compatible Mixed Versions** (ACs 1, 2) and **5.7 Prove Rollback and the AWS Invariant Suite** (ACs 3, 4) | Mixed-version rollout vs rollback proof |

### 4.4 CQ-1 + MQ-3 — Restructure Epic 5 and pull the visual foundation into Epic 1

**New Epic 1 story (number 1.6), placed before the Scenario Data workspace stories — marked `[Technical Enabler]`:**

> ### Story 1.6: Establish ShiftMind Design Tokens and Shared Primitives [Technical Enabler]
>
> As a product engineer,
> I want the ShiftMind visual tokens and shared workspace primitives established before the first data UI,
> So that every later story implements its visual contract once instead of retrofitting consistency.
>
> Acceptance criteria are relocated from old Story 5.2 AC 1 (token consolidation against `DESIGN.md`, inherited tokens unchanged — UX-DR30, UX-DR33) plus a new criterion: the shared Status badge, Inline alert, Skeleton, Empty state, Reconnect banner, Evidence link, and quiet highlight primitives exist as reusable components with visual-regression fixtures (UX-DR23, UX-DR34), and each subsequent UI story implements its component-specific visual contract in that story.

**Epic 5 — reframed:**

OLD (title/outcome):
> ### Epic 5: Production-Shaped Trust and Governed Growth
> The product team can add a new capability without changing the core loop and can deploy, evaluate, observe, recover, restore, and roll back the complete ShiftMind portfolio proof...

NEW:
> ### Epic 5: Reliable Hosted Planner Workspace
> The planner can sign in to the hosted ShiftMind workspace and trust it: it is reproducibly deployed, diagnosable by the portfolio operator without privacy leaks, and provably recovers accepted work through backup, restore, and tested rollback.
>
> **FRs covered:** none new (hardens FR1–FR22 outcomes in the hosted environment)

Epic 5 stories (renumbered): 5.1 Operate with Privacy-Safe Logs, Metrics, and Traces (old 5.4, amended per NQ-3 below); 5.2 Provision AWS Edge, Identity, and Network Boundaries (old 5.5); 5.3 Provision AWS Data and Least-Privilege Runtime (old 5.6); 5.4 Deploy Immutable API, Worker, and Web Releases (old 5.7); 5.5 Demonstrate Backup and Restore (old 5.8); 5.6 and 5.7 from the old-5.9 split (Section 4.3). Observability placed first so old 5.7's run-identifier search proof (NFR22) no longer forward-depends on old 5.4.

**New Epic 6:**

> ### Epic 6: Evidence-Gated Release and Governed Growth
> Every release the planner receives is gated by reproducible versioned evidence, and new agent capabilities cannot bypass the governance, budget, or evaluation contract.
>
> **FRs covered:** FR23

Epic 6 stories: 6.1 Gate Releases with Versioned Deterministic Evaluation (old 5.3); 6.2 Add and Remove a Governed Capability Module [Technical Enabler] (old 5.1); 6.3 Audit Cross-Workflow Visual Consistency (residue of old 5.2: ACs 2–4 — visual regression across the completed workflow and the release-blocking accessibility sweep; token/primitive work now lives in Story 1.6).

**FR Coverage Map:** `FR23: Epic 6 - Versioned governed capability-module extensibility`.

**Rationale:** Implements the readiness report's CQ-1 remediation: production/recovery work reframed as an observable planner/operator outcome; FR23 explicitly classified as a governed-extensibility enabler; visual foundation moved ahead of the UI-heavy epics (MQ-3).

### 4.5 MQ-4 — Canonical requirements inventory

Create `_bmad-output/planning-artifacts/requirements-inventory.md` as the single canonical catalogue:

- FR1–FR24 verbatim from the PRD.
- NFR1–NFR34 with the numbering already used in `epics.md` (IDs frozen), each row carrying a provenance tag: `PRD` (with the PRD's ordinal position), `UX`, `ARCH`, or `SPEC`.
- UX-DR1–UX-DR35 and AR1–AR28 referenced by pointer, not duplicated.
- Proposed **NFR35 (internal demonstration thresholds, non-SLO):** initial Scenario Data group window, exact evidence-target resolution, first persisted run event after acknowledgement, and SSE reconnect replay each have an internal portfolio acceptance threshold recorded before implementation acceptance; default placeholders to be fixed at sprint planning. (Addresses UX-alignment issue 2 without creating a customer SLO, consistent with NFR17.)

Amend the PRD addendum with one paragraph: the inventory is the normative requirement register; the PRD's unnumbered NFR section defers to it; the UX-derived accessibility/responsive constraints (WCAG 2.2 AA, 200% zoom, text spacing, reduced motion, 44×44 targets, phone read-only triage) are adopted as normative MVP requirements (readiness recommendation 7). Update `epics.md` to cite the inventory as its requirements source.

### 4.6 Minor findings (NQ-1–NQ-3)

- **NQ-1:** Reframe verification stories 1.9 (old 1.6), 3.10 (old 3.9), and 4.5 personas from “As a planner, I want … tested” to “As the product team, we want … proven before release,” keeping every acceptance criterion unchanged.
- **NQ-2:** Mark Stories 1.1, 2.1, and 6.2 with `[Technical Enabler]` in their titles, each stating the user-value story it unblocks (1.3, 2.2, and governed capability growth respectively). Story 1.6 (new) is created with the marker.
- **NQ-3:** In Story 5.1 (old 5.4) AC 4, replace “emit actionable signals” with: “emit alerts with a defined minimum contract — severity, destination, deduplication key, and a linked runbook entry — and each release-blocking signal class has a test asserting that contract.”

### 4.7 Cross-artifact contract edits (UX-alignment issues)

- **ARCHITECTURE-SPINE.md (AR4/AR20 vicinity):** add — `ScenarioProjectionV1` carries a server-owned `projection_generated_at` (UTC) defined as the time the projection response was generated from the immutable fixture version; the UX “last verified” timestamp renders this field and is never client-derived.
- **UX EXPERIENCE.md:** add FR-21 and FR1–FR3 rows to the source-requirement coverage table; add a supported-matrix note (proposed minimum for the portfolio: latest Chrome and Edge on Windows with NVDA, keyboard-only, at 100%/200% zoom — adjust if you want Safari/VoiceOver in scope).

### 4.8 Resulting story map (34 stories, was 29)

| Epic | Stories |
|---|---|
| 1 — Inspectable Single-Site Scenario Workspace | 1.1 Fixture history [TE] · 1.2 Sign in · 1.3 Fixture catalogue · 1.4 Scenario read contract · 1.5 Exact evidence targets · 1.6 Design tokens/primitives [TE] · 1.7 Scenario Data workspace · 1.8 Table controls · 1.9 Integrity/accessibility proof |
| 2 — Grounded Conversational Investigation | 2.1 AgentRuntime boundary [TE] · 2.2 Durable conversations · 2.3 Live event replay · 2.4 Governed inspect capability · 2.5 Evidence grounding · 2.6 Evidence jump/return · 2.7 Clarify/refuse/fail safely |
| 3 — Governed and Recoverable Schedule Repair | 3.1 Reversible draft · 3.2 Deterministic candidate · 3.3 Job leasing/fencing · 3.4 Cancellation · 3.5 Literal run state/replay · 3.6 Explicit bounded optimization · 3.7 Monitor/reopen runs · 3.8 Candidate/baseline comparison · 3.9 Model-outage continuity · 3.10 Repair correctness proof |
| 4 — Exact Baseline Decision and Decision Record | 4.1–4.5 unchanged (4.1 gains ApprovalRequest introduction) |
| 5 — Reliable Hosted Planner Workspace | 5.1 Privacy-safe observability · 5.2 AWS edge/identity/network · 5.3 AWS data/runtime · 5.4 Immutable deploys · 5.5 Backup/restore · 5.6 Mixed-version rollout · 5.7 Rollback + AWS proof suite |
| 6 — Evidence-Gated Release and Governed Growth | 6.1 Versioned evaluation gating · 6.2 Governed capability module [TE] · 6.3 Cross-workflow visual audit |

Old Story 3.6 (Monitor/Cancel/Reopen) sheds nothing; the cancellation *command* work stays in 3.4 while 3.7 keeps the Runs UI Cancel control it renders.

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization plus small cross-artifact contract edits; no strategic replan (PRD goals, MVP, architecture decisions all stand).

| Recipient | Responsibility |
|---|---|
| Developer agent (backlog editor) | Apply Sections 4.1–4.4, 4.6, 4.8 to `epics.md`; create `requirements-inventory.md` (4.5); apply the two doc edits in 4.7. |
| Product Owner (Minh) | Confirm the Epic 5/6 framing, the NFR35 placeholder thresholds, and the browser/AT matrix choice. |
| Readiness re-check | Re-run `bmad-check-implementation-readiness` after edits; target: both criticals cleared, majors resolved, 100% FR coverage retained. |

**Success criteria:** readiness re-check no longer reports CQ-1/CQ-2/MQ-1–MQ-4; every story satisfiable from prior stories only; every active UI control has its complete command path in the same or an earlier story; one canonical NFR numbering resolvable from every artifact.

**Next step after approval:** apply the edits, then re-run the readiness check before starting sprint planning / story creation.
