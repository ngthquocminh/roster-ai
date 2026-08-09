---
title: "Sprint Change Proposal: Epics 2–5 Portfolio Scope Audit and Local/Hosted Split"
status: approved
created: 2026-08-09
supersedes_scope: none
related: sprint-change-proposal-2026-08-09.md
---

# Sprint Change Proposal: Epics 2–5 Portfolio Scope Audit and Local/Hosted Split

## 1. Issue Summary

Epic 1 closed on 2026-08-09 with Gate A passing, after a prior correct-course
descoped manual NVDA screen-reader verification that had cost 1.5+ days for a
poor effort-to-signal ratio (`sprint-change-proposal-2026-08-09.md`). The
product owner (Minh) requested the same lens be applied to the four remaining
epics before Epic 2 begins.

ShiftMind is a CV/portfolio MVP targeting AI Engineer roles (secondarily
Software Engineer). It has no real users and is not a commercial product. The
capabilities that serve that goal are system design, architecture, and
AI-agent engineering — safe tool-use, grounding, orchestration, reasoning, and
performance. Frontend-QA depth and operational/SRE maturity do not serve it.

Issue type: strategic/scope decision (portfolio-goal alignment). No technical
failure triggered it.

Two secondary findings emerged during the audit and are documented as root
causes in §2, because both are *method* mandates that no requirement actually
asks for — the same failure shape as the NVDA mandate.

## 2. Root-Cause Findings

### Root cause 1 — "visual-regression fixtures" is a process artifact

No PRD NFR, no UX-DR, and no architecture AD mandates screenshot baselines.
The mandate entered through `implementation-readiness-report-2026-07-22:352`
("Retain only cross-workflow visual regression and final consistency auditing
in the production-hardening work") and was hardened by
`sprint-change-proposal-2026-07-23-round-3.md:74`, which split the old compound
Story 4.6 into four slices — one of which (4.6-B, latterly Story 4.7) was
defined by its *method* rather than by an outcome.

The substantive rules it stood in for are all DOM-assertable: UX-DR32 (no
color-only status, no confidence gauge/glow/pulse), UX-DR31/UX-DR34 (no
page-level horizontal overflow; exact-target highlight only).

Evidence the method was never actually adopted: Story 1.6's dev log
(`1-6-establish-shiftmind-design-tokens-and-shared-primitives.md:86`) records
an explicit refusal to install a screenshot runner — Playwright was absent from
the architecture spine's Stack table and AR27 forbids adding an unlocked
dependency before its gate — and shipped a deterministic **state fixture
catalogue** instead, deferring the runner to "1.10 / 3.12 / 4.7". The repo
today contains Playwright (46 e2e tests) and zero `toHaveScreenshot`, Percy, or
Chromatic references. Story 3.12-AC2 and the whole of Story 4.7 were the unpaid
bill for a method nobody selected.

### Root cause 2 — Story 4.9-AC1 still mandated manual accessibility checks

> **When** automated **and manual** accessibility checks run at supported
> sizes, 100% and 200% zoom… (`epics.md:1329`, pre-change)

This contradicted `EXPERIENCE.md:196` as amended on 2026-08-09. The prior
correct-course fixed the root spec line but did not sweep `epics.md`; its
impact analysis stated "Epics 3–5 … do not inherit an NVDA-style
manual-verification requirement," which was true of the *screen-reader* wording
but missed this literal `manual … checks` mandate.

Counter-check performed: every AC in Epics 2–5 mentioning keyboard,
screen-reader, reduced-motion, or zoom was read individually. **2.8-AC4,
3.12-AC1, 4.4-AC2, and 4.6** are all outcome-level and already satisfied by the
existing axe/jsdom/Playwright suites — they were reworded to name the automated
suite, adding no work. 4.9-AC1 was the only true manual mandate remaining.

## 3. Impact Analysis

**Epic impact:** Epics 2 and 3 keep every story; two stories simplified in each.
Epic 4 loses three stories to consolidation and one to a cut. The old Epic 5 is
split into a new Epic 5 (local, portfolio milestone) and Epic 6 (hosted), with
four of its thirteen stories cut outright.

**Story count:** 54 → 47 across the plan; 43 remaining → **32 to the portfolio
milestone**, with 5 deferred to hosting.

**Milestone impact:** the PRD's two-gate cutline becomes three gates. Gate B
now completes the portfolio MVP in a reproducible *local* environment; Gate C
adds the hosted proof and may be deferred in full.

**Artifacts touched:**

- `_bmad-output/planning-artifacts/epics.md` — story edits, Epic 5/6 split, Release Gate re-anchor, Epic List, Story Map, AR28, totals.
- `_bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md` — MVP goal 5, §4.10 delivery cutline (Gate B/Gate C), §8.1 MVP acceptance statement.
- `.../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-24 marked `[DEFERRED]` with a scope note; three new Deferred-table entries with revisit triggers.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — dated decision note; Epic 4 story list; Epic 5 replaced; Epic 6 added.

**No impact:** every agent invariant (grounding, safe tool-use, approval
fail-closed, idempotency, recovery, injection refusal, three-way authority
partition); all FR normative text; NFR35's four thresholds — AD-26 already
scoped them to the CI reference environment "never on the hosted AWS
topology," so the split costs no performance coverage. NFR10's telemetry
independence remains proven by Story 3.9-AC3.

## 4. Recommended Approach

**Selected: Hybrid of Option 1 (Direct Adjustment) and Option 3 (MVP scope
review).** Epics 2–4 are direct story/AC adjustments. The Epic 5 split is an
MVP-scope resequencing.

- Effort: Low (planning-artifact edits only; no application code changed).
- Risk: Low-to-moderate. The moderate component is the milestone resequencing,
  which touches the PRD's acceptance statement and one adopted architecture
  decision. It is recorded explicitly here rather than applied silently.

Rationale for preferring the split over descoping AWS: the product owner
proposed it, and it is structurally cleaner than the descope originally
recommended. Descoping would have contradicted PRD goal 5 and required
**retiring** AD-17 `[ADOPTED]` and AD-24. The split **retires nothing** — AD-17
stays adopted and binds Epic 6; AD-24 is marked deferred with a revisit trigger.
Nothing is removed, only resequenced, and the option to build the hosted epic
later for its own infrastructure signal is preserved.

## 5. Detailed Change Proposals

Presented and approved in conversation across three rounds (Incremental mode,
per the user's stated preference to approve section by section).

### Epic 2 — Grounded Conversational Investigation (9 → 9)

| Story | Change |
|---|---|
| 2.1–2.7, 2.9 | KEEP as-is. Core AI-engineering surface. |
| **2.8** | SIMPLIFY. AC1+AC2 merged into one jump-and-return criterion; the "ordinary user filters preserved separately for restoration" clause dropped. AC3 retained for its non-disclosure invariant. AC4 reduced to focus-target/focus-return proven by the Epic 1 automated suite; **the "full locator is never entrusted to a model-generated URL" invariant was explicitly preserved** (AR15). |

### Epic 3 — Governed and Recoverable Schedule Repair (12 → 12)

| Story | Change |
|---|---|
| 3.1–3.6, 3.8–3.11 | KEEP as-is. |
| **3.7** | SIMPLIFY. AC2 reduced to the shared loading/empty/alert primitives. **AC4 cut** (tablet/phone read-only triage) — its one real clause, API permission enforced independently of viewport, is already covered by FR3/NFR1. |
| **3.12** | SIMPLIFY. **AC2 cut** (visual-regression fixtures — root cause 1). AC1 refocused on one end-to-end draft → run → reconnect → comparison test asserting run-ID survival and exact evidence targeting; a second AC names the automated accessibility suite and states that no manual assistive-technology verification is required. |

### Epic 4 — Exact Baseline Decision and Decision Record (9 → 6)

| Story | Change |
|---|---|
| 4.1, 4.3 | KEEP as-is. |
| **4.2** | KEEP + one AC absorbed from the former 4.6: NFR19 (Approve as baseline stays distinct from Run optimization), disabled stale actions, dialog focus restoration, consequence-specific accessible name — proven by the automated suite. |
| **4.4** | AC2 reworded from "keyboard and screen-reader accessible" to the semantics the Epic 1 automated suite asserts. No scope change. |
| **4.5** | AC3 restated from S3-specific to the object-storage evidence adapter, provable locally. **Removes an accidental Epic 4 → Epic 5 dependency.** |
| **4.6 (new)** | Consolidates former 4.6, 4.7, 4.8, 4.9 into *Prove Workflow State Semantics and Automated Accessibility*. Three ACs: the literal-state matrix (no color-only status, no confidence gauge/glow/pulse/invented ETA), automated WCAG 2.2 AA at 100%/200% zoom with text spacing and reduced motion, and one bound evidence artifact `evidence/story-4.6/state-semantics-and-accessibility.json`. "and manual" struck (root cause 2). Proof method stated as automated-only. |
| **4.7** | **CUT** (root cause 1). |
| 4.8, 4.9 | Merged into the new 4.6. |
| Epic 4 Completion Gate | Removed; its independence requirement is now internal to Story 4.6's third AC. |

### Epic 5 → Epic 5 (local) + Epic 6 (hosted)

**New Epic 5: Demonstrable Local Planner Workspace — the portfolio milestone (Gate B), 4 stories**

| Story | Origin |
|---|---|
| 5.1 Instrument Agent Runs for Latency, Budget, and Cost | old 5.1, slimmed — metric-label cardinality rules and the standalone `log-metric-contract.json` gate dropped; NFR22 run-ID correlation absorbed from old 5.7-AC3 |
| 5.2 Prevent Content and Secret Leaks | old 5.2, slimmed — Logfire-specific channel enumeration generalized |
| 5.3 Run ShiftMind Reproducibly from One Command **[TE]** | **new** — one-command start, seeded fixtures, deterministic model doubles with no credential required, dependency pinning (AR27, from old 5.6-AC3), and a locally built content-addressed image digest |
| 5.4 Publish the Portfolio Walkthrough | **new** — thesis, authority partition, the Wednesday journey with real output, links to evaluation and gate evidence, plus explicit limitations (NFR17, NFR34, absorbing old 5.3's retention documentation) |

**New Epic 6: Reliable Hosted Planner Workspace — Gate C, 5 stories**

| Story | Origin |
|---|---|
| 6.1 Provision AWS Edge, Identity, and Network Boundaries [TE] | old 5.5 |
| 6.2 Provision AWS Data and Least-Privilege Runtime [TE] | old 5.6, AC3 narrowed to deployed image digests |
| 6.3 Deploy Immutable API, Worker, and Web Releases [TE] | old 5.7, AC3 removed (now 5.1's) — **the SSE-through-CloudFront/ALB proof is deliberately retained** |
| 6.4 Prove Hosted Invariants, Parity, and Mutation Denial | old 5.11 + 5.12 merged, reduced to a smoke-level re-proof with the acceptance boundary stated explicitly |
| 6.5 Provide Backups and a Tested Rollback Path | old 5.8-AC1 + old 5.10, reduced |

**Cut outright, with the reason recorded in the architecture spine's Deferred table:**

| Cut | Rationale |
|---|---|
| old 5.3 | NFR10 independence already proven by Story 3.9-AC3; the retention write-up folded into new 5.4 |
| old 5.4 (alerts/runbooks) | 12 signal classes × severity/destination/dedup/runbook + a contract test each, for a single-operator portfolio with no paging destination |
| old 5.9 (mixed-version rollout) | One API task and one worker task are replaced, not rolled; no concurrent prior version exists to stay compatible with, and no user to strand |
| old 5.10 restore/drill portion, old 5.13 | Rehearsed disaster-recovery restore and hosted recovery re-proof; dependencies cut. Automated backups retained in 6.5 |

### Release Gate

Re-anchored from *"After Stories 5.11–5.13 pass"* — i.e. after AWS — to a
**Gate B / Gate C** column. All six original thresholds are locally measurable;
only backup/restore and rollback moved to Gate C, and the blocking-regressions
row was trimmed accordingly. The image-binding row now names Story 5.3's local
digest as its source.

**Deliberately not done:** the gate was *not* promoted into an owned story.
Doing so would have re-litigated the round-2/round-3 decision that release
evaluation is a definition of done attached to the epic it protects, not an
epic or story of its own. It remains a checklist section.

**Recorded caveat:** the 50-case golden-dataset floor was set when thirteen
Epic 5 stories were expected to contribute. The hosted stories now in Epic 6
contribute infrastructure assertions rather than agent-behavior cases, so the
floor must be re-verified against the actual contribution of Stories 2.9,
3.10–3.12, and 4.5–4.6 when Epic 2's harness lands. If it does not hold, lower
the threshold with a recorded rationale — never pad the dataset to reach it.

### Deferred Requirements section (added during application)

A post-edit ownership sweep found that cutting the stories above orphaned
requirements that no remaining story claimed. Leaving them silent would be the
same defect class this project's evidence machinery exists to catch, so a
**Deferred Requirements** table was added to `epics.md` before the FR Coverage
Map, recording each with rationale and a revisit trigger:

| Requirement | Clause deferred | Revisit trigger |
|---|---|---|
| NFR25 | All of it (alerting contract and runbooks) | First external pilot, or any operation the author does not personally observe |
| NFR24 | "a demonstrated restore drill" only; backups and documented limitations remain in Story 6.5 | First external user, or any non-reproducible data |
| AR24 / AD-24 | N/N-1 compatibility, resumable backfills, `/api/meta` gating, contraction gates; image rollback remains in Story 6.5 | A second concurrent API/worker task, or the first external user |

The canonical register in `requirements-inventory.md` is deliberately left
unchanged — these remain requirements, they simply have no owning story at
Gate B or Gate C, and no gate may claim them as satisfied.

Verified after the edit: **every FR (1–24) and every AR (1–28) retains at least
one owning story.** NFR25 is the only requirement in the plan with no owner,
and it is now documented rather than silent. AR24 retains an owner via Story
2.6's historical-record version-retention clause, which is unaffected by the
rollout deferral.

### Consistency edits

- AR28 split into Gate A / Gate B (local) / Gate C (hosted); "no later gate may weaken an earlier gate's invariants" retained.
- Story 2.2's `Unblocks:` list updated from "4.5–4.9, and 5.11–5.13" to "4.5–4.6, and 6.4".
- Story 1.6-AC2 wording corrected from "visual-regression fixtures" to "a deterministic state fixture" — matching what was actually built and shipped in Epic 1, now that the downstream consumers of a screenshot runner are cut. Wording correction to a completed story, not a re-scope.
- The `> **No Epic 6.**` callout retitled `> **No release-evaluation epic.**` — the round-2/round-3 principle it records is unchanged; the new Epic 6 is a deployment epic, not a release-evaluation epic, and the callout now says so.
- Story Map, epic totals, and the dependency chain updated to `1 -> 2 -> 3 -> 4 -> 5 -> 6`.

## 6. Implementation Handoff

**Scope classification: Moderate.** Backlog reorganization plus a PRD milestone
restatement and one architecture-decision deferral. No application code, no
schema, and no agent invariant changed. Applied directly in this session per
the user's instruction to proceed once approved.

**Success criteria:**

- `epics.md` contains no reference to a cut or renumbered story. *(Verified by sweep — the only remaining mentions of 4.6–4.9 are Story 4.6's deliberate consolidation note.)*
- No AC in Epics 2–6 mandates manual assistive-technology verification or a screenshot baseline. *(Verified by sweep.)*
- Story counts reconcile: 11 + 9 + 12 + 6 + 4 + 5 = **47**, matching the Story Map. *(Verified by count.)*
- Every FR (1–24) and AR (1–28) retains an owning story; NFR25 is the sole orphan and is recorded in the Deferred Requirements table. *(Verified by sweep.)*
- All four NFR35 thresholds retain their owning stories (1.4, 1.5, 2.4, 3.5). *(Verified.)*
- AD-17 remains `[ADOPTED]`; AD-24 is `[DEFERRED]` with a revisit trigger rather than orphaned. *(Verified.)*
- Epic 5 is completable, and the portfolio presentable, with Epic 6 untouched.

**Not done in this session:** changes are applied to the working tree but not
committed, pending review.

**Next step:** Epic 2 is unblocked. Story 2.1 (Establish the Owned Agent Runtime
Boundary) is the entry point; it and Story 2.2 carry sizing notes recommending a
task breakdown before sprint commitment.
