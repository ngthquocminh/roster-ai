# Sprint Change Proposal — The Candidate/Baseline Comparison Has Never Read a Baseline

- **Date:** 2026-09-03
- **Project:** ShiftMind
- **Raised by:** Minh, from Epic 4 retrospective action A3(i)
- **Workflow:** `bmad-correct-course` (incremental mode)
- **Codebase state at analysis:** `2bd89be`, working tree carrying an untracked Story 5.1 file
- **Scope classification:** **Moderate** — backlog reorganization (one inserted story), two artifact amendments, one published-contract change. No PRD change. No rollback.

---

## 1. Issue Summary

`calculate_comparison` takes its baseline side from `ScenarioProjectionReader.get_baseline_assignments`. The PostgreSQL implementation of that method applies its query to a **hardcoded empty tuple**:

```python
# backend/adapters/postgres/scenario_projection.py:637-650
items, next_cursor, total, matching = _apply_query(
    (), query, ASSIGNMENT_SORTS, ASSIGNMENT_FILTERS
)
```

The baseline side is therefore always empty — not null, not an error, *empty*. And empty is computable. This produces **two distinct failures on opposite sides of the first promotion**, and the pre-promotion one has not previously been described.

### Failure 1 — before any promotion: confidently wrong

The `BaselineSupplyUnavailableError` guard fires only when `expected_baseline_schedule_version is not None`. Before the first promotion it is `None`, the guard does not fire, and the comparison is computed against an empty baseline.

`calculate_candidate_metrics((), tasks, demand, facts)` derives `required` from demand (real) and accumulates `served` from assignments (zero). The baseline is therefore modelled as *a schedule in which nobody works at all*.

What the planner reads on the Results page:

| Field | Rendered | Truth |
|---|---|---|
| Baseline version | `No baseline version` | ✅ the only honest line |
| Coverage required delta | `0.00` | correct — both sides read the same demand |
| Coverage served delta | `+` the candidate's entire served minutes | measured against nothing |
| Overtime delta | `+` the candidate's entire overtime | as though the live schedule had zero |
| Cost delta | `+` the candidate's entire cost | **reads as "this repair adds that much money"** |
| Baseline hard constraints | all `Satisfied` | an empty schedule violates nothing |
| Assignment diff | every worker/shift/task `added`, `removed` empty | as though nobody had ever been scheduled |

No field is blank. No warning is shown. Four fabricated numbers sit beside one true label, in the same visual weight, inside a product whose thesis is that every schedule claim is grounded in exact evidence.

### Failure 2 — after the first promotion: loudly missing

`site_baseline` now holds a pointer, `expected_baseline_schedule_version` is non-null, the guard fires. Story 4.3 correctly moved the failure boundary so this degrades to `200` with `comparison: null` plus a stated reason, rather than `409`-ing the whole resource.

Honest — but the headline feature is gone, permanently, for every run snapshotted from that moment on.

### The resulting paradox

> The more correctly the system is used, the more completely the feature disappears — and before it is used correctly, it answers with confident fabrications.

There is no state in which the comparison works.

### Third consequence: the evidence trail

```python
baseline_refs = tuple(EvidenceRefV1(...) for assignment in baseline)
```

`baseline` is empty, so `baseline_refs` is empty, so `ComparisonV1.evidence_refs` carries **candidate locators only**. Every baseline-side claim the page makes — the deltas, the `Satisfied` constraint list — is unbacked. Story 2.8's jump-to-evidence has nothing to jump to on that side. This directly contradicts Epic 2's grounding guarantee.

---

## 2. Impact Analysis

### 2.1 The architecture spine describes this state incorrectly

**EAD-8** (`architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md:95-99`) exists precisely to prevent this hazard, and names it exactly:

> **Prevents:** the first real promotion silently turning Story 3.8's honest empty-baseline comparison into a false "all assignments net-new" claim

Two things are wrong with that sentence, and they matter:

1. **The empty-baseline comparison is not honest.** EAD-8 treats the pre-promotion state as a truthful "there is no baseline" rendering. It is not: it renders deltas, a `Satisfied` constraint list, and a full `added` diff.
2. **The hazard is not created by the first promotion — it already exists before it.** "A false 'all assignments net-new' claim" is a precise description of what `assignment_diff` produces *today*, on a fresh site, with no promotion having occurred.

EAD-8 guarded the wrong side of the promotion boundary. Its rule is sound for what it covers; its stated premise about the other side is false. **This is not a criticism of the decision — it is the kind of thing only implementation reveals, and the guard it did build is what kept Failure 2 honest.**

### 2.2 Story 3.8's second acceptance criterion is violated today

`epics.md:1044-1047`, Story 3.8 AC2 (UX-DR11, UX-DR21):

> **And** missing metrics say "Not computed" rather than zero or an invented value.

The baseline metrics are missing. They are rendered as zero-derived deltas. **This is not new scope — Part B below is Story 3.8's own AC2, unimplemented.**

The frontend was already built for it: `ComparisonSummary.tsx:16-17` reads

```ts
return candidate === null || baseline === null ? "Not computed" : (candidate - baseline).toFixed(2);
```

The helper has always handled the null case. The backend has never sent null.

### 2.3 The deferral's revisit trigger has fired

Spine Deferred table, `:226`:

| Decision | Why it waits | Revisit trigger |
|---|---|---|
| Wiring `get_baseline_assignments` to the promoted baseline (plus authoritative wages and selected shifts) | EAD-8 fails closed instead; prerequisites named by Stories 3.8/3.10 are undischarged | **first story needing authoritative baseline-side metrics after a real promotion** |

Story 5.4 publishes a walkthrough asserting that *"every claim it makes about behavior is reproducible by the Story 5.3 command."* A walkthrough of the approve → promote → compare loop needs authoritative baseline-side metrics after a real promotion. **The trigger has fired on time.** This proposal is that trigger firing, exactly as `sprint-change-proposal-2026-09-01.md` was Story 4.4's trigger firing.

### 2.4 The deferral assumed a more expensive supply than the fix needs

The Deferred entry, and EAD-8's rule, both assume the supply must come from **`schedule_assignment` rows** — which is why the wage and selected-shift prerequisites from Stories 3.8/3.10 were named as blockers.

There is a second, already-complete, authoritative source that neither considered:

| Fact | Location |
|---|---|
| `ScheduleVersionV1.assignments` is `tuple[AssignmentV1, ...]` — the exact type `calculate_candidate_metrics` consumes and `get_baseline_assignments` pages | `application/contracts/schedule_version.py:125`, `application/contracts/scenario_projection.py:98` |
| `schedule_version.payload` persists the entire `ScheduleVersionV1` as JSONB; `get_candidate` already hydrates from it | `adapters/postgres/schedule_run.py:99-106` |
| `site_baseline.schedule_version_id` FK-pins that row, `ondelete=RESTRICT` | `adapters/postgres/schema.py:517` |
| `snapshot.baseline_schedule_version` is `str(schedule_version_id)` — the exact UUID, not a label needing lookup | `adapters/postgres/scenario_projection.py:557-560` |

**The baseline's assignments already exist in the database, immutable, FK-pinned, checksum-bound, in the correct type.** The comparison is reading the wrong source, not missing a source. The wage/selected-shift prerequisites gate the *projection* supply — a different consumer (the Scenario Data workspace) with a different need — and are not on this path.

### 2.5 Risk to the fix is low, because the mathematics is already proven

`deferred-work.md`, Story 3.10 entry: *"Story 3.10 substitutes `RepairProjectionReader` through the existing port, proves the full `_preserved_locks` → proposal → snapshot → finalizer chain and non-vacuous base[line comparison]."*

The comparison calculators have been proven correct against a substituted reader. What has never run is the real wiring. **This change reconnects a proven calculator to a real source; it does not build new calculation.**

### 2.6 Epic and story impact

| Artifact | Impact |
|---|---|
| **Epic 4** | None. Closed and retrospected; deliberately not reopened. Its Story 4.3 degradation stays exactly as shipped and remains correct. |
| **Epic 5** | One inserted story. No existing Epic 5 story changes scope. |
| **Story 5.1** (telemetry) | No dependency either direction — 5.1 declares zero frontend diff and no API response field. One cosmetic sentence needs adjusting (see 4.4). |
| **Story 5.2, 5.3** | Unaffected. |
| **Story 5.4** (walkthrough) | **Blocked by this story.** Its limitations section and its reproducibility claim both depend on the outcome. |
| **Story 3.8** | AC2 becomes true for the first time. No AC text change needed. |
| **Epic 6** | Unaffected. |
| **PRD** | No change. FR15 and AR11/AR20 are satisfied *more* completely, not differently. |
| **UX** | No new screen, no new flow. UX-DR21's existing rule is honoured where it currently is not. |
| **Architecture spine** | EAD-8's premise sentence amended; the Deferred row closed with its trigger recorded. |

### 2.7 Technical impact

- **Published contract change.** `ComparisonV1.baseline_metrics` becomes nullable → `openapi.json` and `schema.d.ts` regenerate via `npm run codegen`. Breaking for any consumer assuming non-null; the only consumer is the in-repo frontend.
- **New port method.** `ScheduleRunRepository.get_version(connection, *, schedule_version_id, site_id)`, mirroring the existing `get_candidate` which reads by `schedule_run_id`.
- **No migration.** No new table, no new column, no new index.
- **No new dependency, no new route.**
- **RLS to verify:** reading `schedule_version` keyed by `schedule_version_id` rather than `schedule_run_id` must be confirmed to pass site-scoped row security. A first-ten-minutes check in the story.
- **Payload compatibility to verify:** `schedule_version.payload` rows written before this change must still deserialize. Same check.

---

## 3. Recommended Approach

**Option 1 — Direct Adjustment (add one story within the existing epic structure): SELECTED.**

- Effort: **Low–Medium.** One port method, one call-site rewiring, one nullable contract field, codegen, and proof.
- Risk: **Low** on logic (§2.5), **Medium** on contract (nullable is breaking for the in-repo frontend, caught by `tsc -b`).
- Timeline impact: precedes Story 5.4 only. Does not block 5.1, 5.2, or 5.3.

**Option 2 — Rollback: not viable and not desirable.** Nothing to roll back. Story 4.3's degradation is the correct behaviour for a genuinely unreadable supply and is retained unchanged; only its *reason for firing* goes away.

**Option 3 — MVP scope reduction (disclose the gap in Story 5.4 instead of fixing it): rejected by the Project Lead, and the analysis supports that rejection.** Disclosure cannot address Failure 1. A limitations section at the end of a walkthrough does not reach a planner reading a fabricated cost delta on the Results page. Disclosure is the right instrument for a *missing* capability; this is a *wrong* one.

---

## 4. Detailed Change Proposals

### 4.1 New story: **Story 5.0 — Compare a Candidate Against the Real Promoted Baseline**

Inserted at the head of Epic 5. Numbered `5.0` rather than renumbering `5.1`–`5.4`, because it is a corrective prerequisite rather than a member of the portfolio sequence, and renumbering four stories would churn `sprint-status.yaml` keys, `epics.md`, and the already-created Story 5.1 file for no benefit.

**As a planner, I want the comparison to measure my candidate against the schedule that is actually running, so that I can judge a repair before approving it — and, when there is no baseline yet, be told so rather than shown deltas against nothing.**

**AC1 — the baseline side reads the promoted version**
**Given** a completed candidate whose run snapshot froze a non-null `baseline_schedule_version`
**When** `ComparisonV1` is calculated
**Then** the baseline assignments are read from the `schedule_version` row that identifier names, through a site-scoped repository read
**And** every baseline-side metric, constraint result, and assignment-diff entry is derived from those assignments
**And** `ComparisonV1.evidence_refs` carries a baseline locator for each of them. (FR15, AR11, AR20, EAD-8)

**AC2 — "no baseline" is an explicit state, not zero**
**Given** a site with no promoted baseline
**When** Results renders the comparison
**Then** `baseline_metrics` is null, every delta reads "Not computed", and the baseline constraint list states that there is no baseline rather than listing satisfied constraints
**And** no assignment-diff entry claims a worker, shift, or task was added relative to a baseline that does not exist. (UX-DR11, UX-DR21, ADR-4 D1, spine EAD-2)

**AC3 — the guard distinguishes unreadable from empty**
**Given** a non-null frozen `baseline_schedule_version`
**When** the named `schedule_version` row cannot be read
**Then** `BaselineSupplyUnavailableError` fails closed exactly as today
**And** a readable version whose assignment set is legitimately empty produces a real comparison instead, with that emptiness visible rather than inferred. (EAD-8; closes the Story 4.3 review deferral "A legitimately empty baseline is indistinguishable from an unreadable supply")

**AC4 — the loop works end to end, proven against PostgreSQL**
**Given** a real promoted baseline
**When** a later run completes and its result is read
**Then** the comparison is present and its deltas are measured against the promoted schedule
**And** a demonstrated-red mutation table records each new guard per the standing evidence rule.

**Explicitly out of scope**, with reason: the hardcoded `baseline_assignment_count=0` in the overview projection (`scenario_projection.py:567`) and `get_baseline_assignments` itself. Those serve the Scenario Data workspace — a different consumer whose need genuinely does depend on the Stories 3.8/3.10 wage and selected-shift prerequisites. This story changes what *comparison* reads, and leaves the projection group as it is.

### 4.2 Architecture spine amendment — EAD-8

**OLD** (`ARCHITECTURE-SPINE.md:98`):
> **Prevents:** the first real promotion silently turning Story 3.8's honest empty-baseline comparison into a false "all assignments net-new" claim

**NEW:**
> **Prevents:** a comparison presenting an unreadable baseline supply as an empty one. **Amended 2026-09-03:** the premise that the pre-promotion empty-baseline comparison was *honest* was false. With no baseline pointer the guard does not fire, and the rendering produces exactly the "all assignments net-new" claim named here — plus zero-derived cost, overtime, and coverage deltas and an all-`Satisfied` baseline constraint list — before any promotion has occurred. EAD-8 guarded the post-promotion side of the boundary correctly and mis-described the pre-promotion side. Story 5.0 makes "no baseline" an explicit rendered state per EAD-2, which is what the original premise assumed already existed.

**Rationale:** the spine is cited by every story that touches comparison. Leaving a false premise in an ADOPTED decision propagates it — which is the exact cross-document undefined-term shape carried by retrospective action A2.

### 4.3 Architecture spine amendment — Deferred table

**OLD** (`:226`): row as written.

**NEW:** mark the row **CLOSED 2026-09-03 by Story 5.0**, recording that the trigger fired at Story 5.4's walkthrough requirement, and that the wage and selected-shift prerequisites proved not to be on the path: they gate the `schedule_assignment`-row supply for the **projection** consumer, while comparison reads the promoted `schedule_version.payload`, which is already authoritative. Add a successor row for the projection consumer, which remains genuinely deferred behind those prerequisites.

### 4.4 Story 5.1 — one sentence

**OLD:** "**This is the first story of Epic 5, the portfolio milestone.**"
**NEW:** "**This is the first story of Epic 5's portfolio sequence.** Story 5.0, inserted by `sprint-change-proposal-2026-09-03.md`, precedes it as a corrective prerequisite and is independent of it in both directions."

Story 5.1 is `ready-for-dev` and not yet started; this is a context correction, not a scope change. No AC, task, or decision in 5.1 is touched.

### 4.5 `epics.md` — insert Story 5.0

Insert the story above `### Story 5.1` with a note that it is a corrective insert from this proposal, matching how Story 4.4a is recorded.

### 4.6 `sprint-status.yaml`

Add `5-0-compare-a-candidate-against-the-real-promoted-baseline: backlog` above the existing `5-1-` key. Mark retrospective action **A3(i)** as addressed-by-story, leaving A3(ii) and A3(iii) open.

---

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization plus artifact amendments.

| Recipient | Responsibility |
|---|---|
| **Product Owner / Developer** | Apply §4.4, §4.5, §4.6 — the backlog and epic edits |
| **Architect (Winston)** | Apply §4.2 and §4.3 — the two spine amendments. These are corrections to an ADOPTED decision and should not be made by a story. |
| **Developer (Amelia)** | Create and implement Story 5.0 via `bmad-create-story` → `bmad-dev-story` |
| **Test Architect (Murat)** | AC4's PostgreSQL end-to-end proof and the mutation table |

**Success criteria**

1. A planner on a fresh site sees "Not computed" deltas and an explicit no-baseline statement — never a number derived from an empty baseline.
2. A planner who has promoted a baseline sees a real comparison against it, with baseline evidence locators present.
3. `BaselineSupplyUnavailableError` fires only on a genuinely unreadable version row.
4. The mutation table shows each new guard demonstrated red by mutating finished code.
5. Story 5.4 can state the approve → promote → compare loop works, and reproduce it with the Story 5.3 command.

**Sequencing:** Story 5.0 must complete before Story 5.4 is created. It does not block Stories 5.1, 5.2, or 5.3, which may proceed in parallel.
