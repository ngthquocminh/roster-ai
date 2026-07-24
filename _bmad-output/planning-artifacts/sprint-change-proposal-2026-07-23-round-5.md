---
workflow: bmad-correct-course
date: 2026-07-23
project: ShiftMind
trigger: implementation-readiness-report-2026-07-23-rerun-2.md (verdict NEEDS WORK; 0 critical, 2 major, 3 minor)
mode: batch-autonomous (-A)
scopeClassification: Minor (direct planning adjustment, single artifact)
supersedes: sprint-change-proposal-2026-07-23-round-4.md
status: APPLIED (2026-07-23) — autonomous flag authorized the documented direct planning adjustments
---

# Sprint Change Proposal — 2026-07-23 (Round 5)

## 1. Issue Summary

The second readiness rerun again returned **NEEDS WORK**, but with a materially smaller and different defect set than Round 4. Round 4's four majors (FR13 ownership, compound Stories 4.6/5.1/5.8) are resolved and did not reappear. The rerun surfaced two *new* major findings plus three minors, all confined to `epics.md`:

- **MQ-1** — Story 2.5's capability-manifest acceptance criterion cited "FR23 partial" and stated the general manifest contract "is completed and proven in Story 2.6." A story may not defer part of its own acceptance claim to a future story.
- **MQ-2** — Epic 3's Stories 3.2–3.5 carried "As a planner" personas while delivering service-only contracts. The planner-visible **Run optimization** control arrives in Story 3.6 and the Cancel control in Story 3.7, so Story 3.4 in particular promised planner cancellation with no reachable control.
- **MN-1** — Stories 1.4 and 1.5 were unlabelled technical enablers.
- **MN-2** — Stories 1.2, 2.1, 3.2, 5.7 carry high implementation breadth.
- **MN-3** — Stories 1.11 and 5.10 lacked the named evidence artifact and owner used elsewhere.

The report itself concluded the remediation "can be completed entirely in `epics.md`" and that PRD, UX, architecture, FR coverage, and the NFR register require no rework.

### Note on the readiness loop

This is the fourth correct-course round. Rounds 2–4 each resolved the prior report's findings and each triggered a fresh set. The mechanism is visible in the record: every round's remedy was **structural** — decomposing stories, renumbering Epic 5, splitting Story 1.10 — and each restructuring created new story boundaries for the next epic-quality review to assess.

Round 5 therefore deliberately chose the **lowest-churn remedy available** for every finding. No story was renumbered, split, merged, added, or removed. The backlog remains 54 stories. Where the report offered a choice of remedies, the option that changes no story identity was taken.

## 2. Impact Analysis

| Artifact | Impact |
|---|---|
| `epics.md` | Story 2.5 acceptance boundary; FR23 coverage-map pointer; Epic 3 sequencing note; personas/labels on Stories 1.4, 1.5, 3.2, 3.3, 3.4, 3.5; sizing notes on 1.2, 2.1, 3.2, 5.7; evidence criteria on 1.11, 5.10; Story Map |
| `requirements-inventory.md` | No change required — its FR23 pointer already reads "delivered by Epic 2, Story 2.6" and is now consistent with the coverage map |
| PRD, addendum, architecture spine, UX spines | No change |

- FR1–FR24 and NFR1–NFR35 unchanged; no requirement added, removed, weakened, or renumbered.
- FR coverage remains 24/24.
- Story count remains **54**; epic dependency chain remains backward-only `1 → 2 → 3 → 4 → 5`.
- No code, database, infrastructure, or deployment impact.

## 3. Recommended Approach

**Direct Adjustment**, at minimum structural cost. Rollback is not implicated (no implementation exists for these slices) and an MVP review would reopen settled scope.

The one genuine judgement call was MQ-2. The report offered two remedies:

| Option | Effect | Decision |
|---|---|---|
| Reorder Epic 3 — move Story 3.6 after 3.3, merge 3.4 into 3.7 | Renumbers 8 stories, changes story count to 53, cascades into the Story Map, FR13 pointer, `requirements-inventory.md`, and every "54 stories" reference | **Rejected** — highest-churn option, and cross-reference churn is the demonstrated driver of the readiness loop |
| Label Stories 3.2–3.5 as technical enablers and change their persona/outcome statements | Zero renumbering; resolves the actual complaint (stories claiming planner value they do not deliver at their position) | **Selected** |

The report explicitly sanctions the second: *"If service-only sequencing must remain, label Stories 3.2–3.5 clearly as technical enablers and change their persona/outcome statements accordingly."* It also resolves MN-1 through the same mechanism.

## 4. Detailed Changes Applied

### 4.1 MQ-1 — Story 2.5 acceptance boundary

**OLD** (Story 2.5, second criterion):
> **And** the handler calls the scenario-read use case rather than repositories or a second source-data interpretation. (FR5, FR23 partial — the general manifest contract is completed and proven in Story 2.6)

**NEW:**
> **And** the handler calls the scenario-read use case rather than repositories or a second source-data interpretation. (FR5, AR5)

Its `**Given**` was narrowed from "the inspect capability manifest" to "the scheduling inspect capability manifest", and a scoping line was added before the criteria:

> Acceptance boundary: FR5 and the scheduling inspect capability only. The general `CapabilityManifestV1` contract and its add/remove conformance proof are wholly owned by Story 2.6; nothing in this story depends on Story 2.6 to complete.

Story 2.6's `Unblocks` line now asserts sole FR23 ownership. The FR Coverage Map changed from *"Epic 2 - ... (conformance proven in Story 2.6, beside the Story 2.5 registry it validates)"* to **"Epic 2, Story 2.6 - Versioned governed capability-module extensibility, wholly owned and proven there."**

**Rationale:** FR5 and FR23 now have separate, complete, non-forward ownership.

### 4.2 MQ-2 — Epic 3 verticality

An epic-level sequencing note was added stating that Epic 3's planner-visible slices are Story 3.1 and Stories 3.6 onward, that Stories 3.2–3.5 are deliberate service-only contracts, and that no story depends on a later story to complete its own acceptance boundary.

Four stories were relabelled and re-personed:

| Story | New title | New persona | Declared outcome |
|---|---|---|---|
| 3.2 | Produce a Deterministic Candidate from an Immutable Snapshot `[TE]` | As the scheduling platform | None at this position; consumed by 3.6 and 3.8 |
| 3.3 | Lease Solver Jobs with Fencing `[TE]` | As the scheduling platform | None at this position |
| 3.4 | **Provide the Safe Cancellation Command** `[TE]` | As the scheduling platform | Command contract only; Cancel control delivered by 3.7 |
| 3.5 | Persist Literal Run State and Replay Progress `[TE]` | As the scheduling platform | None at this position; progress surface delivered by 3.7 |

Story 3.4's title changed from "Cancel Queued and Running Work" — the old title was itself the planner-value claim the report objected to. Acceptance criteria were not weakened; each story states how it is accepted (seeded/API-level tests).

**Rationale:** No story now claims planner-visible value it does not deliver, and the sequencing is declared rather than implicit.

### 4.3 MN-1 — Unlabelled enablers

Stories 1.4 and 1.5 became `[Technical Enabler]`, persona changed from "As a planner or governed agent tool" to "As the scenario platform", each declaring the consuming story (1.7 and 2.8 respectively).

### 4.4 MN-2 — Sizing

A **Sizing note** was added to Stories 1.2, 2.1, 3.2, and 5.7 naming the specific cross-stack concerns to break into implementation tasks before sprint commitment, with the instruction not to split into separate stories unless each slice stays independently testable without a forward dependency. Deliberately not decomposed here — inventing task lists at epic level is the churn that fuels the loop; this is sprint-planning work.

### 4.5 MN-3 — Gate evidence

Stories 1.11 and 5.10 each gained a criterion naming a persisted evidence artifact, its required version bindings, and an accountable owner:

- `evidence/story-1.11/gate-a-readiness-report.json` — owner Product/QA
- `evidence/story-5.10/rollback-drill-report.json` — owner Operations/QA

### 4.6 Story Map

`[TE]` labels added for 1.4, 1.5, 3.2–3.5; Story 3.4 renamed to "Cancellation command"; Story 3.7 renamed to "Monitor/cancel/reopen runs". The trailing note now states the general no-forward-dependency rule and the specific enabler→consumer pairs.

## 5. Verification Performed

| Check | Result |
|---|---|
| Story count | 54 — unchanged |
| BDD block integrity | 160 `**Given**` / 160 `**When**` / 160 `**Then**` — matched |
| Forward-reference language (`completed and proven in Story`, `FR23 partial`, `completes in Story`) | Zero occurrences |
| Story renumbering | None; Epic 3 remains 3.1–3.12 |
| Cross-references to Stories 3.2–3.5 elsewhere in the document | None outside the Story Map and coverage map, both updated |
| `requirements-inventory.md` FR23/FR13 pointers | Already consistent; no edit required |

## 6. Change Navigation Checklist

- [x] 1.1–1.3 Trigger identified, categorized as planning-structure defects, evidence captured from the rerun report.
- [x] 2.1–2.3 All epics remain viable and independently valuable; epic scope and order unchanged.
- [N/A] 2.4–2.5 No epic obsolete, added, or reprioritized.
- [x] 3.1–3.3 PRD achievable unchanged; architecture and UX contracts unaffected.
- [x] 3.4 `requirements-inventory.md` verified consistent. No `sprint-status.yaml` exists.
- [x] 4.1 Direct Adjustment selected; low effort, low risk.
- [N/A] 4.2–4.3 Rollback and MVP review not implicated.
- [x] 5.1–5.5 Issue, impact, path, and handoff documented.
- [x] 6.1–6.3 Proposal checked against readiness evidence and the modified artifact; `-A` recorded as autonomous approval.
- [N/A] 6.4 No sprint status file.
- [x] 6.5 Next steps defined below.

## 7. Implementation Handoff

**Scope classification: Minor.** A single planning artifact changed, with no story identity, count, scope, or requirement affected. This does not require PO backlog reorganization — Round 4 already completed that.

| Recipient | Responsibility |
|---|---|
| Product Owner | Note that Stories 1.4, 1.5, 3.2–3.5 are now explicitly enablers — estimate them as service contracts, not demoable slices |
| Developer | Implement each story against its own stated acceptance boundary and declared outcome; do not reintroduce planner-facing scope into the Epic 3 enablers |
| QA/Evaluation | Add the two new evidence artifacts (`story-1.11`, `story-5.10`) to release-evidence routing |

### Success criteria

1. Story 2.5 is independently acceptable for FR5 with no FR23 claim. ✔ applied
2. Story 2.6 wholly owns FR23. ✔ applied
3. No Epic 3 story claims planner value it does not deliver at its position. ✔ applied
4. Stories 1.4, 1.5, 3.2–3.5 are labelled and personed as enablers. ✔ applied
5. Stories 1.11 and 5.10 name evidence artifacts, version bindings, and owners. ✔ applied
6. A fresh readiness run reports no major story-structure or forward-ownership defect. — pending rerun

### Recommended guard for the next readiness run

If the rerun returns NEEDS WORK on **newly-generated** story-structure findings rather than on MQ-1/MQ-2, that is evidence the epic-quality review is operating below its useful resolution, not evidence of a real backlog defect. In that case the correct action is to accept the backlog and proceed to sprint planning, recording the residual findings as sprint-time guidance — not to run a sixth correct-course round. Structural churn has a cost and the backlog is already at 24/24 FR coverage, 54/54 BDD coverage, zero criticals, and zero unresolved contradictions with PRD, UX, or architecture.

## 8. Workflow Completion Record

- **Issue addressed:** MQ-1 (Story 2.5 forward acceptance dependency), MQ-2 (Epic 3 verticality), MN-1/MN-2/MN-3.
- **Change scope:** Minor.
- **Artifacts modified:** `epics.md` only.
- **Routed to:** Product Owner / Developer / QA-Evaluation.
- **Approval:** `-A` autonomous execution flag.
- **Next action:** rerun implementation readiness; on a READY verdict proceed to sprint planning.
