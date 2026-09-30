# Draft lifecycle: one working draft per conversation

Date: 2026-09-28 · Status: approved in brainstorming, awaiting spec review
Revised 2026-09-30 against `main` at `ba8c706` (live eval graded by per-turn expectations,
draft-id rebinding, baseline-answer instructions). Changes are in §2.1, §4 and §5.2.

## Problem

Every `scheduling_draft` call mints a new proposal (`scheduling_draft.py` builds a
`ProposalV1` with a fresh `proposal_id`; `finalize_agent_run` calls `create_draft`).
Asking for two constraints in one message yields one draft; asking for them in two
messages yields two drafts, both `active`, both runnable, with no indication which is
current. The agent is instructed to carry earlier constraints forward
(`agent/scheduling_instructions.py`, "Revising a draft"), so the second draft is
usually a superset — but the first is never retired, because `ProposalStateV1` has only
`active` and `rejected` (Story 3.1 deliberately shipped no supersede state).

Separately, the draft card's **Revise proposal** button is hard to use: it edits one
constraint at a time through a select, only numeric arguments, shows no inputs for
`exclude_worker_from_task`, and gives no success feedback beyond a changed version UUID.

## Intent

A planner can always tell which draft is "the one" in a conversation. Adding a
constraint through chat and editing values on the card both change that draft instead
of creating stray copies, and the timeline stays readable.

Constraints carried over unchanged: drafts are reversible and never touch the baseline;
runs pin an exact `proposal_version_id`; run optimization stays planner-only; NL-derived
constraints remain soft.

## Decisions

| # | Decision | Chosen |
|---|---|---|
| D1 | Draft model | **One working draft per conversation.** Every change is a new version of it. |
| D2 | When the working draft ends | When the planner (or agent, on explicit request) **discards** it, or when a run from it is **promoted to baseline**. |
| D3 | Card edit scope | **Edit values + remove constraints.** Adding or retargeting goes through chat. |
| D4 | How the agent reaches the working draft | **Server resolves it** (option A). `scheduling_draft` keeps its input — the full constraint list, no draft id. |
| D5 | Agent discard | **Yes**, new capability `scheduling_draft_discard`, used only on explicit request. |
| D6 | Undo / restore | **Deferred.** The planner asks to remove or change a constraint instead. |
| D7 | Version diff on the card | **Not built.** The card lists every constraint; the planner reviews it before running. |

## 1. States and lifecycle

`ProposalStateV1 = Literal["active", "rejected", "applied", "superseded"]`

| State | Meaning | UI label | Editable | Runnable |
|---|---|---|---|---|
| `active` | The conversation's working draft (at most one) | Working draft | yes | yes, unless stale |
| `rejected` | Discarded | Discarded / Discarded by assistant | no | no |
| `applied` | A run from it was promoted to baseline | Applied to baseline — vN promoted | no | no |
| `superseded` | Went stale and a newer draft replaced it | Replaced by a newer draft (the scenario changed) | no | no |

`rejected` keeps its persisted value; only the UI label changes. The contract file treats
renaming a persisted member as a contract migration, which a label does not justify.

Transitions:

- No working draft + agent drafts → new proposal, `active`, v1.
- Working draft (not stale) + agent drafts → new version of it, full constraint list replaced.
- Working draft + planner card edit → new version via the existing revise command.
  Removing the last constraint is refused; the planner discards instead.
- Planner discards (card) or agent discards (tool) → `rejected`. Allowed while stale.
- A run whose snapshot pins this proposal is promoted → `applied`, in the promotion
  transaction.
- Working draft is stale + agent drafts → old one `superseded` and a new `active` draft
  created, in one transaction.

Edge cases decided:

- **Promoting an older version.** Planner runs v2, edits to v3, promotes the v2 run: the
  draft still becomes `applied`, labelled "Applied to baseline — v2 promoted". The v3
  constraints remain visible on the read-only card and can be asked for again.
- **Identical content.** An agent draft whose content equals the current version still
  appends a version. Harmless, and not worth a special case. The card's Save is disabled
  until something differs, so the planner path cannot produce one.
- **Ended drafts refuse every command.** Revise, reject/discard
  (`manage_proposal.py`) and run optimization (`create_run_snapshot.py`, today's
  `rejected_proposal` check) refuse any non-`active` proposal, not only `rejected`. The
  run route gains a matching RFC 7807 code and the card a matching message.

## 2. Backend mechanism

### 2.1 Working-draft resolution

New repository read on `ProposalRepository`:
`get_working(connection, *, conversation_id, for_update: bool) -> ProposalRecord | None`
— the conversation's `active` proposal, if any.

`scheduling_draft`, at tool time, resolves the working draft and produces one of:

| Working draft | Result | Outcome reported |
|---|---|---|
| none | new `proposal_id`, v1 | `created`, version 1 |
| exists, not stale | same `proposal_id`, new `proposal_version_id`, `expected_resource_version = current` | `updated`, version N+1 |
| exists, stale | new `proposal_id`, v1, `supersedes = <old id>` | `created`, version 1 |

The model view grows from `{draft_id}` to `{draft_id, outcome, version}` so the reply can
say "Updated your draft (now v3)" instead of "Created a draft".

Two things on `main` constrain this, and both still hold:

- `agent/runtime.py` reads only `content["draft_id"]` from the tool return
  (`_draft_ids_this_run`), so the wider view is compatible. On `updated` the `draft_id` is
  the *existing* proposal id, so a model that cites an earlier turn's id is citing the right
  draft; a garbled citation is still rebound to the run's latest `draft_id`.
- A turn may call `scheduling_draft` more than once, and nothing is persisted until
  finalize, so every call resolves against the same pre-turn state. Only the draft the final
  output cites is persisted (the rebinding above picks the latest when the citation matches
  none), so two `created` results in one turn cannot both hit the unique index, and two
  `updated` results carry the same `expected_resource_version`, of which only the cited one
  is applied.

### 2.2 Persistence at finalize (one transaction, unchanged boundary)

`finalize_agent_run` branches on the trusted result:

- `updated` → `append_revision`, conditional on `resource_version = expected`. Zero rows
  updated means the planner edited the card during the turn: the draft is **not**
  persisted and the turn ends with a visible "Your draft changed while I was working — ask
  again". Nothing is silently overwritten.
- `created` with `supersedes` → mark the old proposal `superseded` (`ended_by='system'`),
  then `create_draft`.
- `created` → `create_draft`, as today.

A `DraftActivityV1` is still written on every agent draft, now pointing at the same
`proposal_id` with the new `proposal_version_id` when updating.

### 2.3 Agent discard — `scheduling_draft_discard`

New capability module (manifest, feature policy `scheduling_draft_discard_enabled`, golden
fixtures), no arguments, risk class `draft`. The tool validates that a working draft
exists and records a trusted "discard working draft" result; `finalize_agent_run` applies
it as `state='rejected'`, `ended_by='assistant'` in the turn's transaction. It reports
`discarded`. No new activity type: the newest draft card re-reads and shows the ended
state, and the agent's reply states it. The planner's card discard keeps its HTTP route
(`POST /api/v1/proposals/{proposal_id}/rejection`), now also setting `ended_by='planner'`.

### 2.4 Promotion hook

`schedule_version` already carries `proposal_id` and `proposal_version_id`. Inside
`promote_baseline`'s transaction:

```sql
UPDATE proposal
   SET state = 'applied', ended_by = 'system', applied_version_id = :proposal_version_id
 WHERE id = :proposal_id AND state = 'active'
```

A draft already discarded or superseded is left alone.

### 2.5 Schema and migration

- `ck_proposal_state`: `state IN ('active','rejected','applied','superseded')`.
- New nullable columns on `proposal`: `ended_by` (`planner` | `assistant` | `system`,
  checked) and `applied_version_id` (FK to `proposal_version` with `site_id`, as the
  existing version FKs do).
- New partial unique index `uq_proposal_one_active_per_conversation` on
  `proposal(conversation_id) WHERE state = 'active'` — the one-working-draft invariant is
  enforced by the database, so two racing turns cannot both create one.
- **Data step before the index:** in every conversation with more than one `active`
  proposal, keep the newest (by `created_at`) and set the rest to `superseded`,
  `ended_by='system'`. Existing development databases already hold such conversations.

### 2.6 Read model

- `ProposalViewV1` exposes `version_ordinal` (already on the repository record),
  `ended_by`, and the applied version's ordinal when `applied`.
- The per-turn workflow snapshot (`conversation_workflow_context.py`) exposes
  `working_draft` (the active proposal with its version ordinal) separately from ended
  drafts, which keep their state. The existing 10-draft cap and `drafts_truncated` flag
  apply to ended drafts.

### 2.7 Planner card edits

No backend change: the revise command already accepts any list of 1..max constraints, so
removal is a shorter list.

## 3. Card and timeline

### 3.1 Timeline

Only the **newest** `DraftActivityV1` for a given `proposal_id` mounts the live
`DraftCard`. Older activities for the same proposal render one history line from their
persisted summary: *"Earlier version of this draft · {consequence_summary} · updated
below"*. This mirrors the existing approval rule (`ActivityTimeline.tsx`, the
`isCurrentApproval` branch). Planner card edits create no activity; the live card updates
in place.

### 3.2 Live card (working draft)

```
┌ Draft — no baseline change            [Working draft · v3] ┐
│ <consequence summary>                                      │
│ Constraints                                                │
│  • Minimum workers on Pick ........ [ 3 ]           [×]    │
│  • Max hours · Ann ................ [ 38 ]          [×]    │
│  • Exclude Ben from Loading                         [×]    │
│                         [Cancel]  [Save changes]           │
│ ────────────────────────────────────────────────────────── │
│ [Run optimization]                        [Discard draft]  │
└────────────────────────────────────────────────────────────┘
```

- The title keeps the UX-DR9 literal; version and state are a badge beside it.
- Every constraint row is editable in place (the "Constraint to revise" select is
  removed). Rows with a numeric argument get inputs (`lock_worker_shift` gets start and
  end minute). Every row has a remove control; it is disabled on the last remaining row
  with the hint "Discard the draft instead".
- **Revise proposal → Save changes**, disabled until the local list differs from the
  server version; **Cancel** resets. Success announces "Saved as vN" in a polite live
  region.
- **Run optimization is disabled while there are unsaved edits**, explained as "Save or
  cancel your changes first".
- **Reject proposal → Discard draft**, with an inline two-step confirmation ("Discard this
  draft? It can't be restored. [Discard] [Keep]") — no browser dialog.
- Stale behaviour is unchanged: inputs and Save disabled with the existing explanation;
  Discard still available; Refresh offered.

### 3.3 Ended drafts

Read-only: constraint list plus one state line, no controls — "Discarded", "Discarded by
assistant", "Applied to baseline — vN promoted", "Replaced by a newer draft (the scenario
changed)".

### 3.4 Accessibility

Automated coverage only, per `EXPERIENCE.md`'s Accessibility Floor: the accessibility
contract tests move to the new controls — distinct accessible names for Save, Cancel,
each row's remove control, Discard and its confirmation; the save acknowledgement and
ended state are announced.

## 4. Agent instructions

In `agent/scheduling_instructions.py`:

- Replace "Revising a draft": a conversation has at most one working draft and
  `scheduling_draft` always writes to it. Send every constraint that should remain (from
  the snapshot's `working_draft`) plus the new or changed ones; omit one to remove it.
  Word the reply from the reported outcome — "Created a draft (v1)" vs "Updated your draft
  (now v3)".
- Discard: call `scheduling_draft_discard` only when the planner explicitly asks to
  discard, delete, or throw away the draft. "Start over with just X" replaces the content
  and never discards.
- Ended drafts are read-only facts in the snapshot; "bring the old one back" means
  drafting its constraints again.
- "Undo": no undo tool exists. If the request names a constraint, remove or change that
  constraint; otherwise ask which one. Never claim an undo happened.
- Update workflow stage 2 ("Draft (you)") to match. Stage 3 stays planner-only.
- Tool routing gains "Discarding the working draft on explicit request:
  scheduling_draft_discard, only."
- Update **"Saying what the baseline is now"**, step 2 (added on `main` for live B:10):
  "find the draft whose proposal_id is the run's proposal_id" and describe what it
  changed. Once drafts have versions and an `applied` state, that draft's current version
  can differ from the version the run pinned (the v2-promoted-then-edited-to-v3 case in
  section 1). Describe the constraints of the version the run pinned, not the draft's
  latest, and say "applied to baseline" from the draft's state. This needs the run's
  `proposal_version_id` in the workflow snapshot; add it there if the runs list does not
  already carry it.

## 5. Testing and evaluation

### 5.1 Deterministic (keyless CI)

- Migration: widened state check; the partial unique index; duplicate-active collapse.
- Repository: `get_working`; conditional `append_revision` returns zero rows on version
  mismatch; two concurrent creates in one conversation — one fails on the index.
- `scheduling_draft`: `created`, `updated`, `created`+`supersedes`; mid-turn card edit
  produces the "draft changed" outcome and persists nothing.
- `scheduling_draft_discard`: golden fixtures (valid; no working draft); finalize sets
  `rejected` and `ended_by='assistant'`.
- `promote_baseline`: sets `applied` and `applied_version_id`; leaves ended drafts alone.
- Commands on ended drafts (revise, discard, run) are refused for `applied` and
  `superseded`, not just `rejected`.
- Golden multi-turn case: draft → add → remove → discard → new request ends with exactly
  one `active` proposal in the conversation.
- Frontend: newest-activity-only live card; history lines; Save/Cancel enablement; row
  removal and the last-row guard; Run disabled with unsaved edits; inline discard
  confirmation; each ended-state label.

### 5.2 Live

Since `main` (`ba8c706`) scenarios A-D are graded by authored per-turn `expect` lists in
`scenarios.json`: code checks over the reply, its activity and the saved draft, plus narrow
TypeSafe Jev yes/no questions (`evals/live_conversations/expectations.py`). A turn without
`expect` falls back to a holistic judge, so every new turn below is authored with `expect`.

- **Existing turns.** B:6 ("Revise the draft to cap that worker...") and C:9 ("Add to that
  draft...") already assert `activity_is` draft plus `draft_has`. They must now also assert
  the draft was *updated*: same `proposal_id` as the earlier draft turn, higher version. That
  needs one new code check kind (for example `draft_updates_turn: n`), registered in
  `CODE_CHECKS` and `_FIELDS`, bound from `Bindings.draft` (which already records
  `proposal_id`; add the version ordinal). Add its unit tests to
  `tests/test_live_conversation_expectations.py`.
- **New scenario E — draft lifecycle**: create → add → remove one → "undo that" (clarify or
  concrete removal, never a claimed undo) → "start over with just X" (replace, not discard)
  → explicit discard → new request (fresh draft). Register it in `REQUIRED_SCENARIOS` in
  `cases.py` with its turn count. The discard turn uses the agent tool, so it is graded by
  a check on the persisted state (`activity_field_equals` or a new state check), not by the
  authored `reject_draft` action, which is the planner's card path. "Never a claimed undo"
  is a `mentions_none` plus a Jev yes/no question.
- **Baseline.** Adding E changes `total_executed` (now 108 = 36 turns x 3 repetitions), and
  the section 4 instruction changes move `behavioral_digest`, so A-D must be re-measured
  too. Re-derive `backend/evals/baselines/live-conversations.json` and the drop-check floor
  following `docs/EVIDENCE-CONVENTION.md`: commit code, measure, generate through
  `backend/scripts/evidence_binding.py` and `derive_live_conversation_baseline.py`, commit
  evidence separately. Do not hand-edit the baseline.
- **Regression risk to watch.** The B:10 turn ("where is the approval record") now depends
  on the baseline-answer instructions; re-check it after the section 4 edit to step 2.

## 6. Deferred

Recorded in `_bmad-output/implementation-artifacts/deferred-work.md`:

- **Undo / restore.** Design already worked out: each version stores `undo_target_ordinal`
  and `origin`. A normal edit (including an explicit restore) targets the version it was
  made from; an undo copies the current version's target and inherits that target's own
  target, so repeated undo walks back instead of toggling. Always append-only — never move
  `current_version_id` backwards, because runs pin versions.
- A restore control on the card.
- Re-activating a discarded draft.
- A diff between versions on the card.
- A full card editor (add or retarget constraints).

Related open items on `main` (`deferred-work.md`), not solved here: the agent cannot say
when or by whom a baseline was approved, and does not reuse the approval id it created.
The `applied` state and `applied_version_id` tell the agent *that* a draft was promoted,
not the approval's time or actor; that still needs the approval-repository read path.

## Out of scope

Per-actor draft ownership (Story 3.1's `authz:site_scoped_shared_drafting` stands);
changes to runs, approvals, or the solver.
