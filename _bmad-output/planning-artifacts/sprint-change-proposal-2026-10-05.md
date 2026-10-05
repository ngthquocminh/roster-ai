# Sprint Change Proposal: Assess Gate B (Story 5.13)

Date: 2026-10-05
Author: Developer agent, with Minh
Mode: Batch
Trigger: Epic 5 second-half retrospective, action 1 (`epic-5-retro-2026-10-05.md` §4 and §6; `sprint-status.yaml` `action_items`, epic "5", status `open`).
Status: **Approved by Minh 2026-10-05 as written, including the F4 footer correction. Edits §4.1–§4.5 applied the same day. Story 5.13 handed to `bmad-create-story`.**

## 1. Issue summary

**Type:** a gap in ownership, not a defect or a new requirement. Every Epic 5 story is `done`, but nothing has assessed Gate B. `epics.md` § Release Gate says that after Epic 5's stories pass, "the Evaluation/QA owner evaluates the Gate B rows … and persists `evidence/epic-5/release-gate-report.json`". No story owns that step, and since 09-10 every story that touched it (5.5 through 5.12) has passed it forward on purpose. Until Gate B is assessed, `epic-5` cannot close and Epic 6 cannot start, because Gate C builds on Gate B's report.

**Row state.** The retro measured these rows. Re-checked against the tree on 2026-10-05:

| Gate B row | State |
|---|---|
| Required live conversation journeys | **Passed.** `evidence/story-5.12/live-conversation-journeys.json`, 129/129. |
| Report version binding | **Present** in the 5.6, 5.7 and 5.12 evidence. |
| Deterministic-first CI and live AI readiness | Deterministic half green. **Live half stale:** single-turn live was last measured at 5.5, on 26 cases. 29 cases are flagged `live_eligible` today. The model, instructions and tool descriptions have all changed since then. |
| Golden dataset size | **Not met.** 37 single-turn cases (+6 multi-turn in `golden_multi_turn/`). `demonstration` has 2 of the required 4. Consequential + prohibited is 4 + 5 = 9 of the required 10. Every other capability has ≥4: `scheduling_baseline` 4, `_compute` 4, `_draft` 4, `_draft_discard` 4, `_optimize` 5, `_inspect` 14. |
| Tool routing ≥90% / 100% consequential+prohibited | **Unmeasured.** It only means something live, because the deterministic double replays scripted turns. It depends on the stale live half. |
| NFR35 internal thresholds | Four one-time evidence files (`evidence/story-1.4`, `-1.5`, `-2.4`, `-3.5`), all `passed: true`, recorded 2026-08-09 to 08-21. CI does not re-measure them. Tracing (5.9) and the draft lifecycle (5.11) have changed the request path since. |
| Blocking regressions | Proof suites green in CI, but nothing aggregates them at a bound commit. There is no `gate_b_checks.py`. |

### 1.1 Findings made during this analysis

**F1: the planning artifacts say assessment is not a story.** Two passages in `epics.md` conflict with adding one:
- The Release Gate intro: "Release evaluation is not an epic or story."
- The "No release-evaluation epic" note under the Epic List: "the aggregate release-blocking thresholds are held in the Release Gate section … rather than in a story."

The retro's decision (Option 1, Minh) stands. The intent of those passages also survives: **the thresholds stay in the Release Gate table, and the story owns only the act of assessing them.** That distinction has to be written down, or the next reader will flag 5.13 as a violation. §4.3 amends both passages narrowly.

**F2: the 5.5 live routing result was never version-bound evidence.** `evidence/` has no `story-5.5/` directory. 5.5 recorded its 26/26 result in its Dev Agent Record. The live single-turn test is named `test_golden_cases_against_live_agent_are_non_authoritative`, and it writes diagnostics, not a bound report. So the tool-routing row has **no evidence file at all**, stale or otherwise. Re-measuring is necessary but not enough. The story must also produce a version-bound live-routing evidence file that the Gate B report can read. This is the same "a verdict key Gate B can read" rule that `docs/EVIDENCE-CONVENTION.md` states for Gate A.

**F3: lowering the floor touches the PRD, not only `epics.md`.** The 50-case floor is a PRD `[ASSUMPTION]` in two places: `prd.md:310` (§7) and `prd.md:403` (assumptions list). Both say the size is revised "from observed failure diversity". The `epics.md` caveat (line 1831) and the PRD agree: lower with a recorded rationale, never pad. If decision (c) lowers the threshold, the same change has to update the PRD assumption, the Gate B table row and the caveat. Otherwise the three disagree.

**F4: the story-map footer count is already wrong.** `epics.md` says "47 stories across 6 epics". The Story Map table lists 56 before this change: 11 + 9 + 12 + 6 + 13 + 5. It also omits 4.4a and 5.8, which have entries in the epic body or in `sprint-status.yaml`. Adding 5.13 would make the footer wronger. §4.4 proposes correcting the count at the same time. That is optional and can be dropped if you'd rather keep this change to Gate B only.

**F5: the reader-facing docs overstate the gap.** `README.md:161` and `docs/WALKTHROUGH.md:88` say the dataset "contains 30 cases". It has 37. Both sentences also frame the floor as the only blocker. Fixing them is scope item (f). The final wording depends on how the gate comes out, so the story owns it rather than this proposal.

## 2. Impact analysis

### 2.1 Checklist results

| Item | Status | Finding |
|---|---|---|
| 1.1 Trigger | [x] | Retro action 1. Every Epic 5 story is done and Gate B has never been assessed. |
| 1.2 Problem | [x] | Nobody owns the Gate B assessment, and two rows have no current measurement (§1). |
| 1.3 Evidence | [x] | Row table above, re-verified against the tree. F2: no live-routing evidence file exists. |
| 2.1 Current epic (5) | [x] | `epic-5` stays `in-progress`. 5.13 is its closing story. |
| 2.2 Epic-level change | [x] | Add one story, **5.13 Assess Gate B**. No completed story's acceptance is rewritten. |
| 2.3 Future epics | [x] | Epic 6 is unchanged in content. 5.13 blocks it (Gate C builds on Gate B's report), as the existing 1 → … → 6 ordering already implies. |
| 2.4 Obsolete / new epics | [N/A] | None. |
| 2.5 Order | [x] | 5.13 → `epic-5` done (if Gate B passes) → Epic 6. |
| 3.1 PRD | [!] | No change now. It changes only if decision (c) lowers the floor (F3); the story then amends `prd.md:310`/`:403`. |
| 3.2 Architecture | [N/A] | AD-26 (NFR35 on the CI reference environment) and the evidence convention are unchanged. 5.13 consumes them. |
| 3.3 UX | [N/A] | No UI change. |
| 3.4 Other artifacts | [!] | `epics.md` (story, Epic List notes, Release Gate wording, story map); `sprint-status.yaml`; `README.md` and `docs/WALKTHROUGH.md` (inside 5.13). |

### 2.2 Technical impact (inside 5.13)

- **New code:** `backend/scripts/gate_b_checks.py`, a declarative row registry like `gate_a_checks.py`, plus a readiness test like `test_gate_a_readiness.py`. Every row needs a verdict key the aggregator reads; an unbound row fails loudly.
- **New evidence:**
  - a version-bound live single-turn routing report (F2);
  - `evidence/epic-5/release-gate-report.json`.
  
  Both are generated through `backend/scripts/evidence_binding.py`. Code is committed first, then measured, then the evidence is committed separately.
- **Paid run:** 29 live-eligible single-turn cases against the configured provider. Team agreement 2 applies: smoke one case and estimate the cost before the ACs freeze. Minh's go-ahead is required before the full run.
- **Possibly new cases:** only if decision (c) finds behaviour no existing case covers.
- **No migration, no contract change, no agent behaviour change.** If the live re-measurement shows a regression, the story records it as a failing row. It does not fix routing in the same pass unless Minh scopes that in (see §3, risk).

## 3. Recommended approach

**Direct Adjustment:** add one closing story to Epic 5 and make narrow wording amendments in `epics.md`.

| | 5.13 Assess Gate B |
|---|---|
| Effort | **Medium.** Aggregator and readiness test, one paid live measurement, two evidence files, a dataset decision, two doc fixes. |
| Risk | **Medium.** The live re-measurement may show a routing regression: the model and instructions changed after 5.5. The story then reports Gate B as **not passed, with named failing rows**, which is a valid outcome for the done-when. Any fix becomes a follow-up story through correct-course, not scope creep in 5.13. |
| Timeline | One story. Blocks Epic 6. |

**Rejected alternatives** (from the retro): disclose and stop, which leaves the portfolio-milestone claim qualified; pad to 50, which the caveat forbids.

**Owner decisions settled at story creation, not at review.** These follow the retro and team agreement 1:
- **(c) Dataset floor.** For each shortfall (`demonstration` 2/4, consequential+prohibited 9/10, total 37/50), either name an untested behaviour and add a case for it, or lower that threshold with a recorded rationale. Whether the 6 multi-turn cases count toward the total is part of this decision.
- **(d) NFR35.** Either the August evidence stands, with the rationale for why tracing and the draft lifecycle do not move the four measured paths, or the four thresholds are re-measured under the canonical protocol.

`bmad-create-story` must bring both questions to Minh and record the answers as the story's "decisions made at creation" before the story moves to `ready-for-dev`.

## 4. Detailed change proposals

### 4.1 `epics.md`: new Story 5.13

Insert after Story 5.12, before `## Epic 6`:

```markdown
### Story 5.13: Assess Gate B [Technical Enabler]

**Inserted 2026-10-05** by `sprint-change-proposal-2026-10-05.md`, from the Epic 5 second-half retrospective's action 1 (`epic-5-retro-2026-10-05.md` §4, §6). It is Epic 5's closing story and blocks Epic 6: Gate C builds on Gate B's report. It owns the act of assessing Gate B. The thresholds stay in the Release Gate table below.

As the Evaluation/QA owner,
I want every Gate B row evaluated at one bound commit and persisted as one report,
So that the portfolio milestone is either claimed on evidence or not claimed, with the failing rows named.

**Decisions settled with Minh at story creation, not at review:** (c) the dataset floor and (d) NFR35, below. The story is not `ready-for-dev` until both are recorded.

**Acceptance Criteria:**

**Given** the Gate B rows in the Release Gate table
**When** `backend/scripts/gate_b_checks.py` is built, mirroring `gate_a_checks.py`
**Then** every row is registered with the evidence file or test suite that proves it and the verdict key read from it, and a readiness test fails loudly on an unregistered row, a missing file, or an unreadable verdict. (Release Gate; EVIDENCE-CONVENTION "a verdict key the gate can read")

**Given** Minh's go-ahead for the paid run, after a one-case smoke and a cost estimate
**When** single-turn live routing runs on every `live_eligible` golden case (29 at creation) against the configured provider
**Then** a version-bound live-routing report is generated through `backend/scripts/evidence_binding.py`, and the Tool routing row is evaluated from it: at least 90% overall and 100% on consequential/prohibited cases. (Gate B: Deterministic-first CI and live AI readiness; Tool routing)

**Given** the golden dataset's measured shortfalls at creation (37 single-turn cases against 50; `demonstration` 2 of 4; consequential + prohibited 9 of 10)
**When** decision (c) is applied
**Then** each shortfall is closed either by a case that tests behaviour no existing case covers, or by a lowered threshold with a recorded rationale, never by padding
**And** a lowered threshold is updated consistently in this document's Gate B row and caveat and in the PRD's golden-dataset assumption (`prd.md` §7 and the assumptions list). (Dataset-threshold caveat; PRD §7)

**Given** the NFR35 evidence from Stories 1.4, 1.5, 2.4, and 3.5
**When** decision (d) is applied
**Then** either the August evidence stands, with a recorded rationale for why later request-path changes (5.9 tracing, 5.11 draft lifecycle) do not affect the four measured paths, or the four thresholds are re-measured under the canonical protocol on the CI reference environment. (NFR35, AD-26)

**Given** every row evaluated
**When** the report is emitted
**Then** `evidence/epic-5/release-gate-report.json` is generated through `evidence_binding.py` after the code commit and committed separately, and it records Gate B as passed, or as not passed with each failing row and its artifact versions named
**And** a live failure is not hidden behind a release exception unless that exception records owner, rationale, scope, expiry, and user-facing limitation. (Release Gate; EVIDENCE-CONVENTION)

**Given** the reader-facing docs
**When** the report is committed
**Then** `README.md` (Current limitations) and `docs/WALKTHROUGH.md` (Gate B paragraph) state the actual case count and the assessed Gate B outcome, linking the report.
```

Rationale: these are the retro's scope items (a)–(f), framed as acceptance criteria. F2 adds the live-routing evidence file, and F3 adds the PRD consistency requirement. `[Technical Enabler]` because its outcome is evidence, not a planner-visible feature. The done-when matches the retro's: the report exists, and Gate B is assessed as passed or not passed with named rows.

### 4.2 `epics.md`: Epic 5 implementation note (Epic List)

**OLD** (end of the Epic 5 implementation-notes paragraph):
> … 5.12's measurement replaces Story 5.7's as the source of the live-conversation baseline.

**NEW:**
> … 5.12's measurement replaces Story 5.7's as the source of the live-conversation baseline. Story 5.13 (added 2026-10-05, sprint-change-proposal-2026-10-05) assesses Gate B and emits `evidence/epic-5/release-gate-report.json`. It is the epic's closing story and blocks Epic 6.

### 4.3 `epics.md`: reconcile the two "not a story" passages (F1)

**Release Gate intro. OLD:**
> Release evaluation is not an epic or story. Each epic proves its own slice through its own proof stories on the Story 2.2 harness, and this checklist holds only the aggregate thresholds that no single story can measure.

**NEW:**
> Release evaluation is not an epic. Each epic proves its own slice through its own proof stories on the Story 2.2 harness, and this checklist holds only the aggregate thresholds that no single story can measure. The thresholds live here and nowhere else. A gate's *assessment* may be owned by a story (Gate B: Story 5.13, added 2026-10-05) so that someone is accountable for doing it, but that story evaluates these rows. It does not restate or redefine them.

**Gate B paragraph. OLD:**
> **Gate B — the portfolio milestone.** After Epic 5's stories pass, the Evaluation/QA owner evaluates …

**NEW:**
> **Gate B — the portfolio milestone.** After Epic 5's stories pass, the Evaluation/QA owner (Story 5.13) evaluates …

**Tool routing row, Evidence owner column. OLD:** `Gate B` → **NEW:** `Story 5.13 (Gate B)`

**"No release-evaluation epic" note.** Append one sentence:
> Story 5.13 (added 2026-10-05) owns the act of assessing Gate B; the thresholds themselves remain in the Release Gate section.

### 4.4 `epics.md`: Story Map

**Epic 5 row.** Append ` - 5.13 Assess Gate B [TE]` after `5.12 Live draft-lifecycle proof`.

**Footer (F4, optional). OLD:** `47 stories across 6 epics.` → **NEW:** `57 stories across 6 epics.` This counts the table's 56 rows plus 5.13. 4.4a and 5.8 stay out of the table as they are today; adding them is a separate cleanup.

### 4.5 `sprint-status.yaml`

After `5-12-prove-the-draft-lifecycle-in-live-conversations: done`, insert:

```yaml
  # 5.13 added 2026-10-05 by sprint-change-proposal-2026-10-05.md, from the 2026-10-05 retro's
  # action 1. Closing story of Epic 5: gate_b_checks.py aggregator, live single-turn routing
  # re-measured as bound evidence (paid; Minh's go-ahead), dataset floor (c) and NFR35 (d)
  # decided with Minh AT CREATION, evidence/epic-5/release-gate-report.json via
  # evidence_binding.py, README/WALKTHROUGH "30 cases" corrected. Blocks Epic 6.
  # epic-5 stays in-progress until this lands.
  5-13-assess-gate-b: backlog
```

Under the 2026-10-05 action 1 entry, replace the comment line "The story is not yet in epics.md -- add it there before create-story (correct-course or a direct epics edit)." with:
```yaml
    # 2026-10-05: added to epics.md as Story 5.13 (sprint-change-proposal-2026-10-05.md);
    # 5-13-assess-gate-b is backlog. Status stays open until the report lands.
```

`epic-5: in-progress` is unchanged.

### 4.6 Not changed by this proposal

- **PRD:** changes only if decision (c) lowers the floor, and 5.13 does it (F3).
- **`README.md`, `docs/WALKTHROUGH.md`:** inside 5.13, because the wording depends on the outcome (F5).
- **Architecture, UX:** no change.

## 5. Implementation handoff

**Scope: Minor.** One additive story and wording amendments. No replan, and no reorganization beyond one backlog line.

| Who | Does |
|---|---|
| Developer agent (now, on approval) | Apply §4.1–§4.5 to `epics.md` and `sprint-status.yaml`. Mark this proposal approved. |
| Minh + `bmad-create-story` | Create 5.13. Settle decisions (c) and (d) **before** `ready-for-dev`. Approve the paid live run after the smoke and cost estimate. |
| Developer agent (5.13) | Build, measure, emit, and fix the docs per the ACs. |

**Success criteria:**
- `evidence/epic-5/release-gate-report.json` exists, generated through `evidence_binding.py` and bound to a clean commit.
- Gate B is recorded as passed, or not passed with named failing rows.
- Retro action 1 is marked `done`.
- `epic-5` moves to `done` only if Gate B passes. Otherwise the failing rows route through correct-course.
