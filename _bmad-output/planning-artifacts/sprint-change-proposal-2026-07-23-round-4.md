---
workflow: bmad-correct-course
date: 2026-07-23
project: ShiftMind
trigger: implementation-readiness-report-2026-07-23-rerun.md (verdict NEEDS WORK; 0 critical, 4 major, 3 minor)
mode: batch-autonomous (-A)
scopeClassification: Moderate (backlog reorganization, PO/DEV)
supersedes: sprint-change-proposal-2026-07-23-round-3.md
status: APPROVED AND APPLIED (2026-07-23) — autonomous flag authorized the documented direct planning adjustments
---

# Sprint Change Proposal — 2026-07-23 (Round 4)

## 1. Issue Summary

The implementation-readiness rerun confirmed that ShiftMind's product and technical planning remain aligned:

- 24/24 functional requirements covered (100%)
- 35 canonical non-functional requirements
- 0 UX-to-PRD or UX-to-architecture blocking conflicts
- 0 critical epic-quality violations

Readiness remains **NEEDS WORK** because the story structure still contains four major defects:

1. **MQ-1 — FR13 forward ownership:** Story 3.5 claims a requirement whose approval-required behavior is explicitly completed by Story 4.1.
2. **MQ-2 — Story 4.6 is compound:** approval accessibility, cross-workflow visual regression, literal-state semantics, and responsive WCAG proof have separate owners and evidence.
3. **MQ-3 — Story 5.1 is compound:** logging/metrics, telemetry privacy, telemetry independence/retention, and alerts/runbooks are independently deliverable.
4. **MQ-4 — Story 5.8 is an aggregate release program:** hosted security, Scenario Data parity/immutability, recovery/continuity, and the aggregate release gate cannot be one story.

The report also records three minor concerns:

- Story 3.1 reserves a disabled Run optimization control that Story 3.6 activates later.
- Story 1.2 does not explicitly own its minimal identity/session persistence.
- Story 1.10 combines viewer accessibility/responsiveness with the aggregate Gate A decision.

These are planning defects, not changes to product scope. No implementation rollback or PRD MVP review is required.

## 2. Impact Analysis

### Epic impact

| Epic | Change | Result |
|---|---|---|
| Epic 1 | Add just-in-time identity schema ownership to Story 1.2. Split Story 1.10 into accessibility/responsiveness and Gate A readiness. | 11 stories |
| Epic 2 | Update the evaluation-harness dependency list for the decomposed proof stories. | 9 stories |
| Epic 3 | Remove the Run optimization placeholder from Story 3.1. Restrict Story 3.5 to optimization progress/recovery. Let Story 3.6 introduce the complete run control and command. | 12 stories |
| Epic 4 | Make Story 4.1 independently own approval-required state/presentation/replay. Replace compound Story 4.6 with Stories 4.6–4.9 and an epic completion gate. | 9 stories |
| Epic 5 | Replace Story 5.1 with four stories, renumber the AWS delivery sequence, replace hosted Story 5.8 with three independent proof stories, and retain the aggregate Release Gate as epic-level definition of done. | 13 stories |

The backlog becomes **54 stories across five epics**. Blocking epic dependencies remain backward-only: `1 → 2 → 3 → 4 → 5`.

### Requirement impact

- FR1–FR24 and NFR1–NFR35 remain unchanged.
- FR13 retains full coverage through two explicit, independently acceptable boundaries:
  - Story 3.5 owns persisted optimization progress states and recovery.
  - Story 4.1 owns approval-required state, presentation, and replay.
- FR coverage remains 24/24.
- No requirement is added, removed, weakened, or renumbered.

### Artifact impact

| Artifact | Impact |
|---|---|
| `epics.md` | Story decomposition, renumbering, coverage ownership, Story Map, and release-evidence ownership |
| `requirements-inventory.md` | FR13 pointer updated to describe independent ownership rather than future completion |
| PRD and addendum | No normative change |
| Architecture spine | No change; existing state machines and aggregate ownership already support the decomposition |
| UX design and experience spines | No change; existing contracts are redistributed into smaller proof stories |
| `sprint-status.yaml` | N/A — no sprint status file exists |

### Technical and timeline impact

- No code, infrastructure, database, or deployment rollback is required.
- Total scope does not increase; existing mandatory slices become separately estimable stories.
- Story bookkeeping increases from 45 to 54 stories.
- Delivery risk decreases because each proof story now has one owner, one evidence boundary, and an independently observable completion condition.

## 3. Recommended Approach

### Selected path: Direct Adjustment

Direct backlog adjustment is the lowest-risk path because requirements, architecture, UX, and epic outcomes are already sound. The change decomposes existing work without reopening the MVP or introducing new capabilities.

| Option | Viability | Effort | Risk | Decision |
|---|---|---|---|---|
| Direct Adjustment | Viable | Medium planning effort; no implementation rework | Low | Selected |
| Potential Rollback | Not viable or useful | No completed implementation is implicated | Medium disruption with no benefit | Rejected |
| PRD MVP Review | Not needed | Would reopen settled scope | Medium scope churn | Rejected |

Expected schedule impact is limited to re-estimation and backlog bookkeeping. The implementation sequence remains unchanged.

## 4. Detailed Change Proposals

### 4.1 FR13 ownership boundary

**Artifact:** `epics.md`  
**Sections:** FR Coverage Map, Epic 3 coverage, Epic 4 coverage, Stories 3.5 and 4.1, Story Map

**OLD:**

> FR13: Epic 3 - Persisted progress states and recovery (approval-required state completes in Epic 4, Story 4.1)

**NEW:**

> FR13: Epic 3, Story 3.5 - Persisted optimization progress states and recovery; Epic 4, Story 4.1 - independently owned approval-required state, presentation, and replay

Story 3.5 now accepts queued, running, completed, infeasible, timed-out, cancelled, failed, cancellation-requested, reconnect, budget, and replay behavior without claiming approval behavior. Story 4.1 now independently accepts:

- `ApprovalRequest` persistence;
- the `AgentRun` approval-required transition;
- literal approval-required presentation;
- disconnect/reload replay of the same pending binding and controls.

**Rationale:** Each epic remains independently acceptable for its own user outcome. Epic 3 delivers a complete non-consequential run/recovery workflow; Epic 4 independently adds the consequential pause/decision state.

### 4.2 Story 4.6 decomposition

**Artifact:** `epics.md`  
**Section:** Epic 4 verification stories

**OLD:**

> Story 4.6: Prove the Decision Journey and Cross-Workflow Visual Consistency

One story contained four mandatory execution slices.

**NEW:**

| Story | Owner boundary | Evidence |
|---|---|---|
| 4.6 — Prove Approval-Journey Accessibility | Frontend/Accessibility | `evidence/story-4.6/approval-journey-accessibility.json` plus keyboard/focus/announcement trace |
| 4.7 — Prove Cross-Workflow Visual Consistency | Frontend/Design system | `evidence/story-4.7/cross-workflow-visual-report/` |
| 4.8 — Prove Literal-State Semantics | Frontend/QA | `evidence/story-4.8/literal-state-matrix.json` |
| 4.9 — Prove Responsive WCAG Conformance | Accessibility/QA | `evidence/story-4.9/responsive-wcag-report.json` |

An Epic 4 completion gate requires all four independent stories to pass; no story can mask a failed sibling.

**Rationale:** Each story now has one principal concern, one owner, one evidence artifact, and one independently failing acceptance boundary.

### 4.3 Story 5.1 decomposition and Epic 5 renumbering

**Artifact:** `epics.md`  
**Section:** Epic 5 observability and operations

**OLD:**

> Story 5.1: Operate with Privacy-Safe Logs, Metrics, and Traces

This combined logging/metrics, privacy/leak prevention, telemetry independence/retention, and alert/runbook contracts.

**NEW:**

| Story | Deliverable | Evidence |
|---|---|---|
| 5.1 — Operate with Structured Logs, Metrics, and Correlation | Timings, cost, budgets, correlation, metric-label restrictions | `evidence/story-5.1/log-metric-contract.json` |
| 5.2 — Prevent Telemetry Content and Secret Leaks | Allow-listed metadata and adversarial leak proof | `evidence/story-5.2/telemetry-minimization-report.json` |
| 5.3 — Preserve Operation Across Telemetry Failure and Document Retention | Correctness independence plus current retention/quota policy | `evidence/story-5.3/telemetry-failure-and-policy-report.md` |
| 5.4 — Alert Operators with Tested Runbooks | Severity, destination, deduplication, runbook, and fixture per signal | `evidence/story-5.4/alert-runbook-contract.json` |

Existing Epic 5 delivery stories are renumbered:

| OLD | NEW |
|---|---|
| 5.2 AWS edge/identity/network | 5.5 |
| 5.3 AWS data/runtime | 5.6 |
| 5.4 Immutable deploys | 5.7 |
| 5.5 Backup/restore | 5.8 |
| 5.6 Mixed-version rollout | 5.9 |
| 5.7 Rollback | 5.10 |

**Rationale:** Operational telemetry transport success can no longer substitute for privacy, failure independence, or operational-response readiness.

### 4.4 Hosted invariant-suite decomposition

**Artifact:** `epics.md`  
**Section:** Epic 5 hosted proof stories and Release Gate

**OLD:**

> Story 5.8: Prove the Hosted Invariant Suite

The story combined hosted security/authority, Scenario Data parity/immutability, recovery/continuity, and aggregate release thresholds.

**NEW:**

| Story | Deliverable | Evidence |
|---|---|---|
| 5.11 — Prove Hosted Security and Authority | Cross-site denial, retry, stale approval, grounding, injection, audit, telemetry independence | `evidence/story-5.11/hosted-security-authority-report.json` |
| 5.12 — Prove Hosted Scenario Data Parity and Immutability | Viewer/agent projection parity and deployed mutation denial | `evidence/story-5.12/hosted-scenario-parity-mutation-denial.json` |
| 5.13 — Prove Hosted Recovery and Continuity | Worker recovery, replay, backup/restore, evidence reconciliation, rollback | `evidence/story-5.13/hosted-recovery-restore-rollback-report.json` |

The aggregate Release Gate is not a story. After Stories 5.11–5.13 pass, Evaluation/QA evaluates it as Epic 5's final definition of done and writes:

`evidence/epic-5/release-gate-report.json`

**Rationale:** Security, parity, and recovery must pass independently. Aggregate routing or dataset thresholds cannot compensate for a failed zero-tolerance invariant.

### 4.5 Remove Story 3.1's forward UI coupling

**Artifact:** `epics.md`  
**Sections:** Stories 3.1 and 3.6

**OLD:**

> the Run optimization slot renders disabled with accessible sequencing copy until the compute command exists

**NEW:**

> this story introduces no Run optimization control or required placeholder

Story 3.6 now introduces the control, accessible sequencing copy, command contract, and enabled/disabled states together.

**Rationale:** Story 3.1 delivers a complete draft experience without acceptance scaffolding owned by a future story.

### 4.6 Clarify Story 1.2 schema ownership

**Artifact:** `epics.md`  
**Section:** Story 1.2 acceptance criteria

**OLD:**

Identity persistence ownership was implied.

**NEW:**

> Story 1.2 creates only the minimal application-user, membership, application-session, and one-user enforcement structures and constraints it requires; invitations, role administration, additional memberships, and future identity structures are not created early.

**Rationale:** This preserves just-in-time schema ownership and the architecture's aggregate boundary.

### 4.7 Split Story 1.10

**Artifact:** `epics.md`  
**Section:** Epic 1 proof stories

**OLD:**

> Story 1.10: Prove Scenario Data Accessibility and Gate A Readiness

**NEW:**

- Story 1.10 — Prove Scenario Data Accessibility and Responsiveness
- Story 1.11 — Confirm Gate A Readiness [Technical Enabler]

**Rationale:** Accessibility/responsive proof and the aggregate go/no-go gate are separately estimable and independently reviewable.

### 4.8 Update the canonical requirements pointer

**Artifact:** `requirements-inventory.md`  
**Section:** Functional Requirements pointer

**OLD:**

> FR13's approval-required state completes in Epic 4, Story 4.1

**NEW:**

> FR13 has two independently acceptable ownership boundaries: Story 3.5 owns optimization progress/recovery behavior, while Story 4.1 owns approval-required state, presentation, and replay.

**Rationale:** The canonical traceability pointer must not preserve the forward-completion language removed from the backlog.

## 5. Change Navigation Checklist

### Section 1 — Understand the Trigger and Context

- [x] 1.1 Triggering artifact identified: implementation-readiness rerun, with findings in Stories 3.1, 3.5, 4.6, 5.1, 5.8, 1.2, and 1.10.
- [x] 1.2 Core problem categorized: planning decomposition and ownership defects, not a technical limitation or new stakeholder requirement.
- [x] 1.3 Evidence captured: 24/24 FR coverage, zero criticals, four majors, three minors, and exact cited story text.

### Section 2 — Epic Impact Assessment

- [x] 2.1 All current epics remain viable and independently valuable.
- [x] 2.2 Existing epic scope is retained; only story decomposition and trace ownership change.
- [x] 2.3 All future epics reviewed; renumbering is contained to Epic 5 plus cross-reference updates.
- [N/A] 2.4 No epic becomes obsolete and no new epic is needed.
- [N/A] 2.5 Epic order and priority remain unchanged.

### Section 3 — Artifact Conflict and Impact Analysis

- [x] 3.1 PRD remains achievable with no requirement or MVP modification.
- [x] 3.2 Architecture already supports the separate aggregate/state/evidence boundaries; no update required.
- [x] 3.3 UX contracts remain unchanged and are redistributed into smaller proof stories.
- [x] 3.4 `requirements-inventory.md` trace wording and Epic 5 evidence ownership require updates. No sprint-status file exists.

### Section 4 — Path Forward Evaluation

- [x] 4.1 Direct Adjustment: viable; medium planning effort; low risk.
- [N/A] 4.2 Rollback: no implementation rollback is implicated.
- [N/A] 4.3 PRD MVP Review: product scope remains sound.
- [x] 4.4 Selected Direct Adjustment for the smallest sustainable correction.

### Section 5 — Proposal Components

- [x] 5.1 Issue summary completed.
- [x] 5.2 Epic and artifact impact documented.
- [x] 5.3 Recommended path and alternatives documented.
- [x] 5.4 MVP unchanged; sequencing and renumbering recorded.
- [x] 5.5 Moderate PO/DEV handoff defined.

### Section 6 — Final Review and Handoff

- [x] 6.1 All applicable checklist sections completed.
- [x] 6.2 Proposal checked against the readiness evidence and modified artifacts.
- [x] 6.3 `-A` recorded as autonomous approval for the direct adjustments.
- [N/A] 6.4 No `sprint-status.yaml` exists to update.
- [x] 6.5 Next steps and success criteria defined below.

## 6. Implementation Handoff

### Scope classification

**Moderate** — backlog reorganization and traceability updates requiring Product Owner/Developer coordination. No fundamental product or architecture replan is required.

### Handoff recipients

| Recipient | Responsibility |
|---|---|
| Product Owner | Confirm estimates, ownership, and sequencing for the 54-story map; maintain the Epic 4 and Epic 5 completion gates as non-story definitions of done |
| Developer | Implement each story only against its own acceptance and evidence boundary; do not recombine the decomposed slices during execution |
| QA/Evaluation | Update report routing and evidence paths for Stories 4.6–4.9 and 5.11–5.13; evaluate the aggregate Epic 5 Release Gate only after its three hosted proof stories pass |

### Success criteria

1. FR13 is reported as two independent ownership boundaries without “completes in a future epic” language.
2. Stories 4.6–4.9 are separately estimable, ownable, implementable, and acceptable.
3. Stories 5.1–5.4 are separately estimable, ownable, implementable, and acceptable.
4. Stories 5.11–5.13 pass independently before the aggregate Epic 5 Release Gate is evaluated.
5. Story 3.1 contains no required Run optimization placeholder.
6. Story 1.2 explicitly owns its minimal identity/session persistence.
7. Accessibility/responsiveness and Gate A readiness are separate Epic 1 stories.
8. A fresh implementation-readiness run reports no major story-structure or forward-ownership defect.

## 7. Workflow Completion Record

- **Issue addressed:** FR13 forward ownership plus oversized Stories 4.6, 5.1, and 5.8, with the three readiness minor concerns.
- **Change scope:** Moderate.
- **Artifacts modified:** `epics.md`, `requirements-inventory.md`.
- **Proposal produced:** this Round 4 document.
- **Routed to:** Product Owner / Developer / QA-Evaluation.
- **Approval:** `-A` autonomous execution flag.
- **Next action:** rerun implementation readiness against the updated planning bundle.
