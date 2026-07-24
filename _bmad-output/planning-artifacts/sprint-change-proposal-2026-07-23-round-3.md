---
workflow: bmad-correct-course
date: 2026-07-23
project: ShiftMind
trigger: implementation-readiness-report-2026-07-23.md (verdict NEEDS WORK; 0 critical, 2 major)
mode: batch-autonomous (-A)
scopeClassification: Moderate (backlog proof decomposition, PO/DEV)
supersedes: sprint-change-proposal-2026-07-23-round-2.md
status: APPROVED AND APPLIED (2026-07-23) — autonomous flag authorized the documented direct adjustments
---

# Sprint Change Proposal — 2026-07-23 (Round 3)

## 1. Issue Summary

The post-Round-2 implementation-readiness check retained complete functional coverage and found no critical defect:

- 24/24 FRs covered (100%)
- 35 NFRs extracted
- 5 epics and 45 stories reviewed
- 0 critical issues

Formal readiness remains **NEEDS WORK** because:

1. **MQ-1 — oversized proof/operations stories:** Stories 4.6, 5.1, and 5.8 combine independently ownable evidence domains, allowing a nominal story completion to hide partial proof.
2. **MQ-2 — missing explicit hosted FR24 proof:** Epic 5 says it hardens FR1–FR22, while the hosted invariant suite does not explicitly re-prove Scenario Data viewer/agent parity and mutation denial through CloudFront, ALB, API, and generated-client boundaries.

The same assessment records three minor epic-quality concerns and document-governance warnings: future activation points are described too absolutely as backward-only dependencies; technical-enabler labels are inconsistent in Epic 5; and reconciled PRD, UX, and architecture frontmatter dates still show 2026-07-22.

## 2. Impact Analysis

### Epic and story impact

| Area | Impact |
|---|---|
| Epic 4 / Story 4.6 | Story ID and unified release gate remain intact, but execution is divided into four mandatory owned slices: approval-journey accessibility, visual regression, literal-state semantics, and responsive/WCAG conformance. |
| Epic 5 scope | Hosted hardening is corrected from FR1–FR22 to FR1–FR24; FR23 remains covered by its governed-capability conformance suite. |
| Epic 5 / Story 5.1 | Four mandatory evidence slices separate telemetry contracts, minimization/leak resistance, provider independence/policies, and alerts/runbooks. |
| Epic 5 / Story 5.8 | Adds explicit hosted FR24 parity/version/identifier and negative mutation-path acceptance evidence; four mandatory slices separate authority/security, Scenario Data parity/immutability, recovery, and aggregate thresholds. |
| Story map and dependency summary | Stories 5.2–5.4 are consistently labelled technical enablers; the summary distinguishes non-blocking activation points from blocking dependency direction. |

### Artifact impact

- `epics.md` — substantive edits described above.
- PRD, PRD addendum, architecture spine, UX design spine, and UX experience spine — frontmatter `updated` refreshed to 2026-07-23 only; normative content remains unchanged.
- Requirements inventory — no edit. FR/NFR IDs and precedence remain frozen.
- Sprint status — no edit. No epic/story IDs were added, removed, or renumbered.
- Product scope, architecture, UX flows, and code — no change.

## 3. Recommended Approach

**Direct Adjustment (Option 1), using mandatory proof slices rather than further story renumbering.**

The readiness report explicitly allows either story splits or named subtasks/checklists with separate owners and evidence. Mandatory slices close the sizing defect while preserving the 45 frozen story IDs and the unified story-level release gates.

- **Effort:** Low to medium — backlog/evidence-contract edits only.
- **Risk:** Low — no implementation or product contract changes.
- **Timeline impact:** One readiness re-check before sprint planning.
- **MVP impact:** None. No scope reduction, rollback, or strategic replan is warranted.

Rollback is not viable or useful because no implemented behavior caused the issue. MVP review is unnecessary because the report confirms full FR coverage and aligned product/UX/architecture contracts.

## 4. Detailed Change Proposals

### 4.1 Story 4.6 — separate proof ownership

**OLD**

> One story acceptance block jointly covers the approval journey, cross-workflow visual regression, every literal state, responsive behavior, WCAG, zoom, text spacing, contrast, and reduced motion.

**NEW**

> Preserve all acceptance criteria and require four independently owned, independently evidenced slices:
> 4.6-A approval-journey accessibility; 4.6-B cross-workflow visual regression; 4.6-C literal-state semantics; 4.6-D responsive and WCAG conformance. Story completion requires all four artifacts; no passing slice masks a failed or missing sibling.

**Rationale:** Keeps the unified end-to-end gate while making estimation, ownership, failure diagnosis, and completion evidence reliable.

### 4.2 Story 5.1 — separate operations evidence

**OLD**

> One story jointly owns structured logs/metrics, OTel/Logfire minimization, leak tests, provider failure behavior, quotas/retention, alerts, and runbooks.

**NEW**

> Preserve all acceptance criteria and require four independently owned, independently evidenced slices:
> 5.1-A logs/metrics/correlation; 5.1-B telemetry minimization/leak resistance; 5.1-C telemetry independence/quotas/retention; 5.1-D alerts/runbooks. Story completion requires all four artifacts.

**Rationale:** Prevents transport success from being mistaken for privacy, product-independence, or operational-response completeness.

### 4.3 Epic 5 and Story 5.8 — hosted FR24 and proof decomposition

**Epic 5 scope — OLD**

> **FRs covered:** none new (hardens FR1–FR22 outcomes in the hosted environment)

**Epic 5 scope — NEW**

> **FRs covered:** none new (hardens FR1–FR24 outcomes in the hosted environment; FR23 remains proven by the governed-capability conformance suite)

**Story 5.8 — NEW acceptance evidence**

> For the same immutable hosted fixture version, compare the deployed viewer/API projection with the allow-listed agent inspection projection through CloudFront, ALB, API, and generated-client boundaries. Values, stable identifiers, ordering, evidence targets, fixture version, and baseline version must match exactly. The browser exposes no mutation controls; no supported scenario upload/create/edit/delete/import endpoint exists; conventional POST/PUT/PATCH/DELETE probes fail without changing source data. Any parity or denial failure blocks release.

**Story 5.8 — NEW execution slices**

> 5.8-A hosted security/authority; 5.8-B hosted Scenario Data parity/immutability; 5.8-C hosted recovery/continuity; 5.8-D aggregate Release Gate. Each has a named owner and required evidence artifact; every slice must pass independently.

**Rationale:** Closes the hosted-topology gap without duplicating FR24 or creating a new feature story.

### 4.4 Minor governance corrections

- Replace “dependency direction is strictly backward-only” with a precise statement: blocking dependencies are backward-only, while Stories 3.1 and 3.5 contain documented non-blocking activation points completed by Stories 3.6 and 4.1.
- Mark infrastructure Stories 5.2, 5.3, and 5.4 as `[Technical Enabler]` in both headings and the story map.
- Refresh the PRD, addendum, architecture, DESIGN, and EXPERIENCE frontmatter dates to 2026-07-23.

## 5. Checklist Record

| Checklist item | Status | Finding |
|---|---|---|
| 1.1–1.3 Trigger/context/evidence | [x] | Trigger is the 2026-07-23 readiness assessment; MQ-1/MQ-2 supply concrete evidence. |
| 2.1–2.5 Epic impact/order | [x] | Epics remain viable and ordered; Epic 5 scope/proof wording changes only. No epic added, removed, or resequenced. |
| 3.1 PRD conflicts | [x] | None. FR24 already exists and MVP remains achievable. |
| 3.2 Architecture conflicts | [x] | None. AD-4 already specifies shared normalized projection and no mutation path. |
| 3.3 UX conflicts | [x] | None. UX already requires Scenario Data parity/read-only behavior and the relevant accessibility states. |
| 3.4 Other artifacts | [x] | Evidence paths/checkpoints added; document dates refreshed. No sprint-status structural change. |
| 4.1 Direct adjustment | [x] Viable | Low-risk planning correction; selected. |
| 4.2 Rollback | [N/A] | Nothing implemented to roll back. |
| 4.3 MVP review | [N/A] | Product scope and 24/24 FR coverage remain sound. |
| 4.4 Recommended path | [x] | Direct adjustment with mandatory proof slices. |
| 5.1–5.5 Proposal/handoff | [x] | Issue, impact, edits, MVP effect, owners, and next step documented. |
| 6.1–6.2 Final review | [x] | Edits checked against the report and canonical contracts. |
| 6.3 User approval | [x] | Autonomous `-A` invocation recorded as approval to apply the batch correction. |
| 6.4 Sprint status | [N/A] | No epic/story IDs changed; no status update required. |
| 6.5 Handoff | [x] | PO/DEV and readiness re-check responsibilities defined below. |

## 6. Implementation Handoff

**Scope classification: Moderate** — backlog proof decomposition and hosted coverage clarification; no fundamental replan.

| Recipient | Responsibility |
|---|---|
| Product Owner / Developer | Carry the mandatory slice owner, artifact, and checkpoint fields into story tasking without weakening their all-slices-pass rule. |
| Frontend / Accessibility / Design system | Produce Story 4.6’s four independent reports. |
| Platform / Security / Reliability / Operations | Produce Story 5.1’s four independent observability reports. |
| Security / Backend / Frontend / QA / Evaluation | Produce Story 5.8’s security, parity/mutation-denial, recovery, and aggregate gate reports. |
| Readiness re-check | Re-run implementation readiness; target: 0 critical, 0 major, 24/24 FR coverage, hosted FR24 proof explicit, and no new dependency defect. |

### Success criteria

- Stories 4.6, 5.1, and 5.8 cannot be completed without every named slice’s owner and passing evidence artifact.
- Epic 5 explicitly hardens FR24.
- Hosted browser/API tests prove viewer/agent parity, exact identifier/version preservation, no mutation controls, no supported mutation endpoint, and no mutation from conventional write probes.
- Blocking dependency language matches the documented future activation points.
- FR/NFR identifiers, story IDs, MVP scope, architecture, and UX contracts remain unchanged.
