# Sprint Change Proposal — One working draft per conversation

Date: 2026-09-30
Author: Developer agent, with Minh
Mode: Batch
Trigger: design spec `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` (brainstormed 2026-09-28, revised twice on 2026-09-30, the second time after a 14-point adversarial spec review checked against the code).
Status: **Approved by Minh 2026-09-30. Artifact edits §4.1–§4.7 applied the same day, as written. Story 5.11 handed to `bmad-create-story`.**

## 1. Issue summary

**Type:** a defect in how the product behaves, found by using it, plus the design that fixes it. It is not a new stakeholder requirement: FR-10 ("reviewable, editable, and rejectable") is already in the PRD. The problem is that the implementation makes FR-10 hard to honour once a conversation holds more than one draft.

**Today:**
- Every `scheduling_draft` call mints a new proposal. Two constraints asked in two messages give two `active`, runnable drafts, and nothing says which one is current. The first draft is never retired, because `ProposalStateV1` has only `active` and `rejected`. Story 3.1 deliberately shipped no supersede state.
- The card's **Revise proposal** control edits one constraint at a time through a select. It accepts numeric arguments only, shows no inputs for `exclude_worker_from_task`, and gives no feedback on success.

**The design** (spec §1–§6, decisions D1–D8):
- A conversation has **one working draft**, and every change is a new version of it.
- A draft ends only by **discard** (planner card, or the agent on explicit request) or by **promotion** of a run from it. That adds the state `applied`.
- The server resolves the working draft for the agent, and a finalize guard makes any concurrent change win over the agent's turn.
- The card allows in-place value edits and row removal.
- Undo, restore and diff are deferred.

### 1.1 Findings made during this analysis (not in the spec)

Each was checked against the code or the planning artifacts on 2026-09-30.

**F1 — EAD-6 lists TX2's writes as exact, and the spec adds one.** The Epic 4 spine says "Epic 4's atomic bundles are *exactly* … TX2 decide-approve = revalidation + `pending → consumed` + `site_baseline` CAS + audit + event + run resume". Spec §2.4 adds `proposals.mark_applied` inside TX2. It is the right place for it, because the draft must not show `applied` for a promotion that rolled back. But it is an architecture amendment, not an implementation detail. The spec's "Out of scope" line says approval rules and contracts are unchanged, which is true, but the *bundle composition* does change. The EAD-6 rollback proof (spine test 6: "fault injection on each write inside TX2") must add the new write.

**F2 — The new capability would fail the Gate B dataset floor.** Gate B requires "at least four per allowed capability". Every enabled capability has ≥4 golden cases today (`scheduling_draft` 4, `scheduling_baseline` 4, `scheduling_compute` 4, `scheduling_optimize` 5, `scheduling_inspect` 14). Spec §2.3 lists **three** fixtures for `scheduling_draft_discard`. It needs a fourth. The obvious one is the negative routing case the instructions care most about: "start over with just X" must route to `scheduling_draft` and **not** to discard.

**F3 — The artifacts' live-scenario count is already stale.** The code has `REQUIRED_SCENARIOS = {A:6, B:12, C:12, D:6}`. Scenario D was added in `40c29fb`, but the PRD (§ live conversation acceptance), Story 5.7's acceptance and the Gate B row in `epics.md` still say "three scenarios (6, 12, 12 user turns)". Scenario E would make five. This proposal fixes the wording once, so it doesn't drift a second time.

**F4 — Who owns the re-measured live evidence.** `backend/evals/baselines/live-conversations.json` is a projection of `evidence/story-5.7/live-conversation-journeys.json` (its `source_evidence_path`). Re-measuring after scenario E and the instruction changes produces a new measurement.
- **Recommendation:** the new live story writes `evidence/story-5.12/live-conversation-journeys.json` and re-projects the baseline from it.
- Story 5.7's evidence stays historical and is not rewritten.
- Gate B's `live_conversation_journeys` verdict then binds to the newest measurement. This follows `docs/EVIDENCE-CONVENTION.md` and the 5.8 derive script.

**F5 — New feature flag, outside the approval policy.** `scheduling_draft_discard_enabled` is added beside the other `scheduling_*_enabled` flags (`settings.py:165-170`), and must appear in `.env.example` and `docs/CONFIGURATION.md`. It does not gate baseline approval, so it is **not** a `PolicyInputsV1` input (EAD-12) and does not version the approval policy.

**Spec references verified:**
- `promote_baseline` (`application/use_cases/promote_baseline.py:106`) has no `proposals` parameter today, which confirms spec §2.4's signature change.
- `VersionMismatchError` at `scheduling_draft.py:264` confirms the per-conversation staleness argument that removed `superseded`.
- `ScheduleRunSummaryV1` already carries `proposal_id`/`proposal_version` (`ports/schedule_run.py:75-76`).

## 2. Impact analysis

### 2.1 Checklist results

| Item | Status | Finding |
|---|---|---|
| 1.1 Trigger | [x] | The design spec, produced from product use after Epic 5's live conversations. No story is blocked. |
| 1.2 Problem | [x] | Drafts multiply and none is clearly current; the card's revise control is unusable for most constraints. |
| 1.3 Evidence | [x] | Spec "Problem"; §1.1 above. |
| 2.1 Current epic (5) | [x] | Epic 5 is `in-progress`, and Gate B is open. The change moves the live-conversation baseline that Gate B's `live_conversation_journeys` row reads, so it belongs **before** the Gate B re-assessment. |
| 2.2 Epic-level change | [x] | Add two corrective inserts: **5.11** (lifecycle, end to end) and **5.12** (live proof and re-baseline). No completed story's acceptance is rewritten. Story 3.1 gets a pointer note only. |
| 2.3 Future epics | [x] | Epic 6: no change. 6.4's hosted parity and mutation-denial proof covers proposal routes generically. |
| 2.4 Obsolete / new epics | [N/A] | None. |
| 2.5 Order | [x] | 5.11 → 5.12 → Gate B re-assessment → Epic 6. |
| 3.1 PRD | [!] | FR-10 unchanged. It already covers "editable, rejectable", and the change makes it true in practice. One stale count fixed (F3). |
| 3.2 Architecture | [!] | AD-9 gains the one-working-draft invariant and the ended states. EAD-6 (TX2) gains the proposal write (F1). |
| 3.3 UX | [!] | UX-DR9, the EXPERIENCE Draft-card row and the DESIGN component row describe the old revise/reject controls. |
| 3.4 Other artifacts | [!] | `sprint-status.yaml`; the spec's status line; `.env.example` and `docs/CONFIGURATION.md` (F5, inside 5.11); `docs/TESTING.md` scenario list (inside 5.12). `deferred-work.md` already carries the spec's §6 items (commit `94965a9`). |

### 2.2 Technical impact

- **Migration (5.11):** widen `ck_proposal_state` to three values; add nullable `ended_by` and `applied_version_id`; collapse duplicate-active drafts; add the partial unique index `uq_proposal_one_active_per_conversation`; write a downgrade path. The migration runs on existing development databases that already hold duplicate active drafts.
- **Concurrency (5.11):** finalize takes a conversation-row lock and re-checks the working draft it observed. The partial unique index is a backstop that should never fire. This is the highest-risk piece, and spec §5.1 asserts it on the **user-visible** result (the terminal outcome), not only on database state.
- **Cross-aggregate write (5.11):** `mark_applied` inside TX2 (F1).
- **Contracts (5.11):** all additive under V1 names (spec §2.7), then OpenAPI and `schema.d.ts` regeneration. The new RFC 7807 code is `applied_proposal`.
- **Agent (5.11):** a new capability module with ≥4 golden cases (F2), the model-view widening, and the §4 instruction rewrite. These instruction changes move the `behavioral_digest`, which is why 5.12 re-measures A–D.
- **Live eval (5.12):** two new code-check kinds, scenario E (7 turns), updates to B:6, B:10 and C:9, then a re-measurement of 43 turns × 3 = 129. It needs the real provider (OpenRouter through the proxy) and follows the evidence convention.

## 3. Recommended approach

**Direct Adjustment:** two additive stories in Epic 5, plus small text amendments to the PRD, the architecture, the Epic 4 spine and the UX specification.

| | 5.11 One working draft | 5.12 Live proof and re-baseline |
|---|---|---|
| Effort | **High.** Migration, repository and ports, finalize guard, new capability, promotion hook, contracts, instructions, Draft card and timeline | **Medium.** Two check kinds, scenario E, three turn edits, one live measurement, evidence commit |
| Risk | **Medium-high.** Concurrency (the finalize guard) and a cross-aggregate write in TX2 | **Medium.** Live flakiness and cost; the B:10 baseline-answer turn depends on the rewritten instruction step |
| Mitigation | Spec §5.1's race tests are acceptance criteria, not optional. The EAD-6 rollback proof is extended to the new write. | Run A–E once clean before the three-repetition measurement, and re-check B:10 first. |

Rollback: N/A. MVP review: N/A, since this delivers FR-10 as written.

**Why two stories, not three.** 5.11 is large but coherent: backend, agent and card change the same state machine, and splitting the card from the backend would leave an unreleasable half-state where the server has one working draft but the UI still offers stray drafts. If `bmad-create-story` finds 5.11 too large for one dev session, it may split tasks into ordered sub-phases inside the story. It must not split them into separately releasable stories.

## 4. Detailed change proposals

### 4.1 Epics — `epics.md`

**New stories, inserted after Story 5.10:**

> ### Story 5.11: Keep One Working Draft per Conversation [Corrective Insert]
>
> **Inserted 2026-09-30** by `sprint-change-proposal-2026-09-30.md`. The design source is `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` (§1–§4, §5.1, decisions D1–D8), which the story implements; this entry does not restate it.
>
> As a planner,
> I want each conversation to have exactly one working draft that chat requests and card edits both change,
> So that I always know which draft I would run, and the timeline stays readable.
>
> **Acceptance Criteria:**
>
> **Given** a conversation with no working draft, or with one
> **When** the agent drafts
> **Then** it creates v1 of a new proposal, or appends the next version of the working draft with the full constraint list replaced, and reports `created` or `updated` with `version_ordinal`
> **And** at most one `active` proposal exists per conversation, enforced by the partial unique index `uq_proposal_one_active_per_conversation`. (FR9, FR10, AD-9)
>
> **Given** the planner edited or discarded the draft, a run from it was promoted, or another turn finalized, while an agent turn was in flight
> **When** that turn finalizes
> **Then** nothing is written to `proposal` or `proposal_version`, and the turn ends with the `capability_error` terminal outcome "Your draft changed while I was working, so I didn't apply this change."
> **And** each of the four races is tested on that visible outcome and on unchanged proposal rows. (spec §2.2, D8)
>
> **Given** the planner explicitly asks to discard the draft
> **When** the agent calls `scheduling_draft_discard`
> **Then** the draft becomes `rejected` with `ended_by='assistant'`, "start over with just X" replaces the draft rather than discarding it, and discard-then-draft in one turn is ordered by the tools
> **And** the capability ships with a manifest, the feature flag `scheduling_draft_discard_enabled`, and at least four golden cases, including the negative "start over" routing case. (FR23, Gate B dataset floor)
>
> **Given** a run whose snapshot pins this proposal
> **When** it is promoted to baseline
> **Then** TX2 marks the draft `applied` with `applied_version_id` = the pinned version, an already-ended draft is left alone, and a TX2 rollback leaves the draft `active`
> **And** revise, discard and run optimization on an ended draft fail with `rejected_proposal` or `applied_proposal` (RFC 7807, 409), while an idempotent replay still returns the original result. (FR10, AD-9, EAD-6 as amended)
>
> **Given** the migration runs on a database with duplicate active drafts
> **When** it upgrades
> **Then** the newest by `(created_at DESC, id DESC)` stays `active`, the rest become `rejected`/`system`, and the downgrade round-trips. (spec §2.5)
>
> **Given** the working draft in Chat
> **When** the planner reviews it
> **Then** only the newest draft activity for a proposal mounts the live card, and older ones render one history line
> **And** the card edits values in place and removes rows (never the last row). Save changes and Cancel enable only when there is a valid difference; Run optimization is disabled while edits are unsaved; Discard asks for inline two-step confirmation; controls are disabled while an agent turn is in flight; and "This draft changed to vN … [Load vN]" appears when the draft changes under unsaved edits. (UX-DR9 as amended, UX-DR25, UX-DR35)
>
> **Given** an ended or stale draft
> **When** its card renders
> **Then** it is read-only and states "Discarded", "Discarded by assistant", "Replaced by a newer draft", "Applied to baseline — vN promoted" or "Working draft · out of date"
> **And** the automated accessibility contract covers every new control, the save acknowledgement, the changed-under-you notice and each ended state. (Accessibility Floor, automated only)
>
> **Out of scope, deliberately.** Undo, restore, diff, re-activation, adding or retargeting constraints on the card, and merging card edits with a concurrent assistant update (all recorded in `deferred-work.md`). No change to runs, the solver, or approval rules and contracts.

> ### Story 5.12: Prove the Draft Lifecycle in Live Conversations [Corrective Insert]
>
> **Inserted 2026-09-30** by `sprint-change-proposal-2026-09-30.md`. It implements spec §5.2 after Story 5.11.
>
> As a planner,
> I want real-provider conversations to show that chat edits update one draft and that discard and promotion end it,
> So that the lifecycle holds with the configured model, not only in deterministic tests.
>
> **Acceptance Criteria:**
>
> **Given** the per-turn expectation grader
> **When** the new code checks `draft_updates_turn: n` and `draft_state_is: <state>[/<ended_by>]` are registered
> **Then** each has unit tests in `tests/test_live_conversation_expectations.py`, and `Bindings.draft` records the version ordinal. (spec §5.2)
>
> **Given** scenarios A–D and the new scenario E (7 turns: create, add, remove, "undo that", "start over with just Z", "throw this draft away", then a new request)
> **When** the suite is authored
> **Then** B:6 and C:9 assert `draft_updates_turn`, B:10 asserts `draft_state_is: applied`, every E turn carries authored `expect` checks, and `REQUIRED_SCENARIOS` is `{A: 6, B: 12, C: 12, D: 6, E: 7}`.
>
> **Given** the committed code of Stories 5.11 and 5.12
> **When** the suite runs one clean pass per scenario plus three repetitions on the configured provider and the real stack
> **Then** `evidence/story-5.12/live-conversation-journeys.json` is generated through `backend/scripts/evidence_binding.py` and committed separately from the code, and `backend/evals/baselines/live-conversations.json` and the drop-check floor are re-derived from it with `derive_live_conversation_baseline.py` (129 executed turns)
> **And** no counted run makes a false claim, including a claimed undo. Missing, partial or stale evidence blocks Gate B's `live_conversation_journeys` row. (Gate B, EVIDENCE-CONVENTION)

**Story 3.1: append one line after its last criterion** (the acceptance itself is unchanged):
```
> *Superseded in part (2026-09-30):* the one-working-draft lifecycle, the `applied` state and the in-place card editor are owned by Story 5.11. This story's acceptance stands as delivered.
```

**UX-DR9 (line 194)**
```
OLD: UX-DR9: Implement Draft cards showing resolved entities, proposed constraints/objectives, preserved locks, expected versions, consequence summary, and the label “Draft — no baseline change,” with separate revise, reject, and Run optimization controls.
NEW: UX-DR9: Implement Draft cards showing resolved entities, proposed constraints/objectives, preserved locks, expected versions, consequence summary, and the label “Draft — no baseline change,” with the draft's version and lifecycle state beside it; in-place value editing and row removal saved as a new version, a separate Discard draft control, and a separate Run optimization control. Ended drafts are read-only. (Amended 2026-09-30, Story 5.11.)
```

**Epic 5 implementation notes, append:** `Stories 5.11–5.12 (added 2026-09-30, sprint-change-proposal-2026-09-30) give each conversation one working draft and re-prove live conversations against it; 5.12's measurement replaces Story 5.7's as the source of the live-conversation baseline.`

**Gate B row "Required live conversation journeys" (F3)**
```
OLD: | Required live conversation journeys | B | Story 5.7 (right-sized 2026-09-17): three scenarios (6, 12, 12 user turns); every installed tool ...
NEW: | Required live conversation journeys | B | Story 5.7 (right-sized 2026-09-17), extended by Story 5.12: the scenarios fixed by `REQUIRED_SCENARIOS` (A–E: 6, 12, 12, 6, 7 user turns); every installed tool ...
```
Evidence-owner cell: `Story 5.7` → `Stories 5.7, 5.12`. The rest of the row is unchanged.

**Story Map, Epic 5 row, append:** ` - 5.11 One working draft per conversation - 5.12 Live draft-lifecycle proof`. The story-count sentence is left alone. It was already stale; see the 2026-09-24 application note.

### 4.2 PRD — `prds/prd-ShiftMind-2026-07-21/prd.md` (live conversation acceptance, line 291)

```
OLD: Story 5.7 requires three authored conversations (introduction/clarification, a 12-turn draft-to-baseline journey, and a tool tour), coverage of every installed tool ...
NEW: Story 5.7 requires authored conversations — at minimum introduction/clarification, a 12-turn draft-to-baseline journey, and a tool tour, extended since by turn routing and the draft lifecycle (the set is fixed by `REQUIRED_SCENARIOS`) — coverage of every installed tool ...
```
FR-10 and every NFR are unchanged.

### 4.3 Architecture spine — `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`, AD-9

**Rule, append:**
```
2026-09-30 (sprint-change-proposal-2026-09-30, Story 5.11): a conversation has at most one working (`active`) proposal, enforced by a partial unique index. A proposal ends as `rejected` (discarded) or `applied` (a run from it was promoted, set inside the promotion transaction); ended proposals refuse revise, discard and run. Versions stay append-only and runs keep pinning an exact version, so an `applied` proposal records the version that was promoted, not its latest.
```

### 4.4 Epic 4 spine — `architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`, EAD-6 (F1)

**Add below the Rule, following the EAD-8 amendment's format:**
```
- **AMENDED 2026-09-30** (`sprint-change-proposal-2026-09-30.md`, Story 5.11). TX2 gains one write after the `site_baseline` CAS: the promoted run's proposal moves `active → applied` with `applied_version_id`; zero rows (proposal already ended, or none) is a normal result. It commits and rolls back with the bundle, so a draft never reads `applied` for a promotion that did not happen. Approval contracts, the effect key, the outcome vocabulary and `PolicyInputsV1` are unchanged.
```
**Proof list item 6:** `(binding, pointer, audit, event)` → `(binding, pointer, proposal, audit, event)`.

### 4.5 UX — `ux-designs/ux-ShiftMind-2026-07-22/`

**EXPERIENCE.md, Draft card row (line 87)**
```
OLD: | Draft card | Chat | Shows resolved entities, proposed constraints/objectives, preserved locks, expected versions, and consequence summary. Parameters may be revised or rejected; no baseline changes. Run optimization is a separate explicit control. |
NEW: | Draft card | Chat | The conversation's one working draft: resolved entities, proposed constraints/objectives, preserved locks, expected versions, consequence summary, version and state. Values are edited in place and rows removed, saved as a new version; the draft may be discarded; no baseline changes. Run optimization is a separate explicit control, disabled while edits are unsaved. Ended drafts are read-only with a literal state line. |
```

**DESIGN.md, Draft card row (line 128)**
```
OLD: | Draft card | Inherits shadcn Card, Input, Select, Button, and Separator. “Draft — no baseline change” is a text label above parameters. |
NEW: | Draft card | Inherits shadcn Card, Input, Button, Badge, and Separator. “Draft — no baseline change” is a text label above parameters; the version and state badge sits beside it. |
```

### 4.6 Sprint status — `implementation-artifacts/sprint-status.yaml`

Under `epic-5`, after `5-10-…: done`:
```yaml
  # 5.11/5.12 added 2026-09-30 by sprint-change-proposal-2026-09-30.md (draft lifecycle).
  # Design source: docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md. 5.11 = one
  # working draft end to end (migration, finalize guard, discard capability with >=4 golden
  # cases, TX2 proposal write per amended EAD-6, card). 5.12 = live checks + scenario E +
  # re-measurement; writes evidence/story-5.12/ and re-derives the live baseline. Both BEFORE
  # the next Gate B assessment.
  5-11-keep-one-working-draft-per-conversation: backlog
  5-12-prove-the-draft-lifecycle-in-live-conversations: backlog
```

### 4.7 Spec status line — `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md`

```
OLD: Date: 2026-09-28 · Status: approved in brainstorming; revised after spec review 2026-09-30
NEW: Date: 2026-09-28 · Status: approved; planned as Stories 5.11–5.12 by sprint-change-proposal-2026-09-30
```
Plus one line in spec §2.3: the golden fixtures gain `start-over-is-not-discard.json` (F2).

## 5. Implementation handoff

**Scope classification: Moderate.** Two new backlog stories and text amendments to the PRD, architecture and UX. No replan, and no rewritten acceptance on a completed story.

| Recipient | Responsibility |
|---|---|
| Developer agent (this session, on approval) | Apply §4.1–§4.7 artifact edits exactly as written. |
| `bmad-create-story` → 5.11 | Carry the spec by reference plus F1, F2 and F5. Order the dev tasks: migration and repository, then finalize guard, then capability and instructions, then promotion hook, then contracts and codegen, then card. |
| `bmad-dev-story` → 5.11, then 5.12 | For 5.12: code commit → measure → `evidence_binding.py` → separate evidence commit (EVIDENCE-CONVENTION). Re-check B:10 before the full measurement. |
| Minh | Approve this proposal. No credentials needed beyond the live-eval provider access already configured. |

**Success criteria:**
1. After any sequence of chat requests and card edits, a conversation holds at most one `active` proposal, and the card always shows which version would run.
2. A race during an agent turn never overwrites a planner's change; the turn visibly says so.
3. Promoting a run marks its draft `applied` atomically with the baseline; a TX2 rollback leaves it `active`.
4. Default CI stays keyless and green, and the golden floor holds for every enabled capability.
5. `live_conversation_journeys` passes on the new evidence (129 turns), with the baseline re-derived from it.
