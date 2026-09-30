# Draft lifecycle: one working draft per conversation

Date: 2026-09-28 · Status: approved in brainstorming; revised after spec review 2026-09-30
Revised 2026-09-30 against `main` at `ba8c706` (live eval graded by per-turn expectations,
draft-id rebinding, baseline-answer instructions), then again after a 14-point spec review
checked against the code. The review's main correction: a conversation is pinned to one
scenario version, which removes the `superseded` state entirely (§1, "Staleness").

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
| D8 | Concurrent change during a turn | **The turn loses.** Finalize re-checks the working draft it observed; if anything changed, the turn's draft change is not applied and the turn ends with a visible "draft changed" outcome (§2.2). |

## 1. States and lifecycle

`ProposalStateV1 = Literal["active", "rejected", "applied"]`

| State | Meaning | UI label | Editable | Runnable |
|---|---|---|---|---|
| `active` | The conversation's working draft (at most one) | Working draft (or "Working draft · out of date" when stale) | yes, unless stale | yes, unless stale |
| `rejected` | Ended without promotion | by `ended_by`: "Discarded" (`planner`), "Discarded by assistant" (`assistant`), "Replaced by a newer draft" (`system`, migration only) | no | no |
| `applied` | A run from it was promoted to baseline | Applied to baseline — vN promoted | no | no |

`rejected` keeps its persisted value; only the UI label changes. The contract file treats
renaming a persisted member as a contract migration, which a label does not justify.

Transitions:

- No working draft + agent drafts → new proposal, `active`, v1.
- Working draft + agent drafts → new version of it, full constraint list replaced.
- Working draft + planner card edit → new version via the existing revise command.
  Removing the last constraint is refused; the planner discards instead.
- Planner discards (card) or agent discards (tool) → `rejected`. Allowed while stale.
- A run whose snapshot pins this proposal is promoted → `applied`, in the promotion
  transaction (§2.4).

### Staleness

A conversation is pinned to one scenario version at creation (`conversation.scenario_version_id`,
set once in `adapters/postgres/conversation.py`), and every agent turn runs with that pin
(`api/routers/conversations.py` builds `AgentDepsV1(scenario_version_id=claimed.scenario_version_id)`).
`scheduling_draft` already refuses when the scenario's current version differs from the
pin (`VersionMismatchError`, `scheduling_draft.py:264`). Consequences:

- Every draft in a conversation carries the conversation's pinned version, so the drafts
  of one conversation are always stale together, never individually.
- After a reimport the agent cannot draft in that conversation at all. There is no
  "stale working draft + new agent draft" case to handle, so no `superseded` state.
- `active` + stale is a real, lasting state: the working draft of a conversation whose
  scenario moved on. The card labels it "Working draft · out of date", keeps today's stale
  explanation, disables editing and Run, and still offers Discard. Work continues in a new
  conversation on the new version, which gets its own working draft (the invariant is per
  conversation).

Edge cases decided:

- **Promoting an older version.** Planner runs v2, edits to v3, promotes the v2 run: the
  draft still becomes `applied`, labelled "Applied to baseline — v2 promoted". The v3
  constraints remain visible on the read-only card and can be asked for again.
- **Identical content.** An agent draft whose content equals the current version still
  appends a version. Harmless, and not worth a special case. The card's Save is disabled
  until something differs, so the planner path cannot produce one.
- **Ended drafts refuse every command.** Revise, reject/discard (`manage_proposal.py`)
  and run optimization (`create_run_snapshot.py:76`) refuse any non-`active` proposal.
  Codes (RFC 7807, 409): `rejected_proposal` stays for `rejected` (existing clients and
  `schedule_runs.py:253` keep working); `applied_proposal` is new for `applied`. The use
  case gains `AppliedProposalError` beside `RejectedProposalError`; the card maps both.
- **Idempotent replay after the draft ended.** `_replay_or_conflict` runs before the
  state check, so a replayed key returns the stored result of the original command (with
  staleness recomputed, as today), even if the draft has since become `applied`. That is
  correct: a replay answers "what did my command do", not "what is the draft now". The
  card re-reads the proposal after any command, so it shows the current state.
- **Removing a row.** The five constraint tools are independent soft penalties; no stored
  constraint refers to another, so removing any row is allowed (except the last).

## 2. Backend mechanism

### 2.1 Working-draft resolution

New repository read on `ProposalRepository`:
`get_working(connection, *, conversation_id, for_update: bool) -> ProposalRecord | None`
— the conversation's `active` proposal, if any.

`scheduling_draft`, at tool time, resolves the working draft and produces:

| Working draft at tool time | Result | Outcome reported |
|---|---|---|
| none | new `proposal_id`, v1 | `created`, `version_ordinal` 1 |
| exists | same `proposal_id`, new `proposal_version_id`, `resource_version` = observed + 1 | `updated`, `version_ordinal` N+1 |

Either way the trusted result records what it **observed**: `observed_working_id`
(`None` when there was no working draft) and `observed_resource_version`. Finalize
checks both (§2.2).

The model view grows from `{draft_id}` to `{draft_id, outcome, version_ordinal}` so the
reply can say "Updated your draft (now v3)" instead of "Created a draft". The same name,
`version_ordinal`, is used in every contract this spec touches.

Two things on `main` constrain this, and both still hold:

- `agent/runtime.py` reads only `content["draft_id"]` from the tool return
  (`_draft_ids_this_run`), so the wider view is compatible. On `updated` the `draft_id` is
  the *existing* proposal id, so a model that cites an earlier turn's id is citing the right
  draft; a garbled citation is still rebound to the run's latest `draft_id`.
- A turn may call `scheduling_draft` more than once, and nothing is persisted until
  finalize, so every call resolves against the same pre-turn state and records the same
  observation. Only the draft the final output cites is persisted.

Discard and draft in one turn (for example "throw it away and draft just X"), made
deterministic by the tools rather than the prompt:

- `scheduling_draft` called **after** `scheduling_draft_discard` in the same run resolves
  as "no working draft" and reports `created`. Finalize applies the discard, then creates.
- `scheduling_draft_discard` called **after** `scheduling_draft` in the same run is
  refused with "this turn already changed the draft" (a capability error the model sees),
  so a turn never updates and discards the same draft.

### 2.2 Persistence at finalize (one transaction, unchanged boundary)

`finalize_agent_run` gains one guard before it writes anything. It locks the conversation
row (`SELECT … FOR UPDATE`), then reads `get_working(for_update=True)`, and compares with
what the turn's trusted result observed:

| Turn result | Applied only if | Then |
|---|---|---|
| `created` | still no working draft (after a same-turn discard, that discard's target is still `active` at its observed `resource_version`) | apply discard if any, then `create_draft` |
| `updated` | working draft id = `observed_working_id` **and** `resource_version` = `observed_resource_version` | new port method `append_agent_version` (version row + `current_version_id` + `resource_version`, no idempotency row: the agent run's claimable guard already makes finalize exactly-once) |
| `discarded` | same id and `resource_version` as observed | `state='rejected'`, `ended_by='assistant'` |

If the check fails, nothing is written to `proposal`/`proposal_version`, and the turn is
finished with `TerminalOutcomeV1(status="failed", reason="capability_error",
detail="Your draft changed while I was working, so I didn't apply this change.",
next_step="Ask again to apply it to the current draft.")`. No new contract member: the
terminal outcome already renders in the timeline and is visible to the eval harness as a
terminal activity. The model's prose reply for that turn is not shown, because it
described a change that did not happen.

This single rule covers every race the review raised:

- Planner edits the card mid-turn → `resource_version` moved → `updated`/`discarded` lose.
- Planner discards mid-turn → no working draft → `updated`/`discarded` lose. (A `created`
  result from a turn that observed none still wins, which is right: nothing is overwritten.)
- A run is promoted mid-turn → draft is `applied`, no longer working → agent discard or
  update loses. **Promotion always wins over the agent**, because the planner approved it
  and it committed first.
- Two turns in one conversation → the conversation-row lock serializes their finalizes;
  the second sees the first's result and loses.

The partial unique index (§2.5) is therefore a backstop that should never fire. If it
does, the `IntegrityError` propagates as a 500; that is a bug, not a user path.

Finalize's docstring ordering still holds: `finish_agent_run` runs before any proposal
write. The guard only *reads* before it, to choose between the draft payload and the
terminal outcome.

A `DraftActivityV1` is still written on every applied agent draft, now pointing at the
same `proposal_id` with the new `proposal_version_id` when updating.

### 2.3 Agent discard — `scheduling_draft_discard`

New capability module (manifest, feature policy `scheduling_draft_discard_enabled`, golden
fixtures under `evals/golden/scheduling_draft_discard/`: `valid.json`,
`no-working-draft.json`, `after-draft-same-turn.json`), no arguments, risk class `draft`.
At tool time it resolves the working draft and records a trusted "discard" result with its
observed id and `resource_version`; it refuses when there is none. Finalize applies it
under the §2.2 guard. It reports `discarded`. No new activity type: the newest draft card
re-reads and shows the ended state, and the agent's reply states it. The planner's card
discard keeps its HTTP route (`POST /api/v1/proposals/{proposal_id}/rejection`), now also
setting `ended_by='planner'`.

### 2.4 Promotion hook

`application/use_cases/promote_baseline.py:promote_baseline` runs TX2. It already writes
across aggregates in that transaction (approvals `consume`, `baseline_writer.promote`,
audit, conversation activity), called from `decide_approval`
(`api/routers/approvals.py:412` wires the dependencies). Changes:

- `promote_baseline` and `decide_approval` gain a `proposals: ProposalRepository`
  parameter; the router passes the existing proposal repository.
- After `baseline_writer.promote` succeeds, `promote_baseline` calls a new port method
  `proposals.mark_applied(connection, site_id=…, schedule_version_id=binding.candidate_schedule_version_id)`.
- The adapter reads `proposal_id`/`proposal_version_id` from `schedule_version`
  (`contracts/schedule_version.py:122`) and runs:

```sql
UPDATE proposal
   SET state = 'applied', ended_by = 'system', applied_version_id = :proposal_version_id,
       resource_version = resource_version + 1
 WHERE id = :proposal_id AND state = 'active'
```

Zero rows (draft already discarded, or a schedule version with no proposal) is a normal
result, not an error. Approval rules, contracts and the decision flow are unchanged.

### 2.5 Schema and migration

- `ck_proposal_state`: `state IN ('active','rejected','applied')`.
- New nullable columns on `proposal`: `ended_by` (`planner` | `assistant` | `system`,
  checked) and `applied_version_id` (FK to `proposal_version` with `site_id`, as the
  existing version FKs do).
- New partial unique index `uq_proposal_one_active_per_conversation` on
  `proposal(conversation_id) WHERE state = 'active'`.
- **Data step, before the index.** In every conversation with more than one `active`
  proposal, keep the newest by `(created_at DESC, id DESC)` and set the rest to
  `state='rejected'`, `ended_by='system'`. Staleness cannot make an older draft the better
  one to keep: all drafts in a conversation share its pinned version (§1). Collapsed drafts
  then show "Replaced by a newer draft" and lose their Run button, because the card reads
  state from the server. No backfill of `applied` for past promotions.
- **Downgrade.** Drop the index; set `applied` rows back to `active` (their pre-feature
  state); drop `applied_version_id` and `ended_by`; restore the two-value check. The
  collapsed `rejected` rows stay `rejected`, which the old schema accepts.

### 2.6 Read model

- `ProposalViewV1` exposes `version_ordinal` (already on the repository record),
  `ended_by`, and `applied_version_ordinal` when `applied`. The adapter joins
  `proposal_version` on `applied_version_id` for it; nothing is stored twice.
- The per-turn workflow snapshot (`conversation_workflow_context.py`) exposes
  `working_draft` (the active proposal with its `version_ordinal`) separately from ended
  drafts, which keep their state. The existing 10-draft cap and `drafts_truncated` flag
  apply to ended drafts.
- Runs in the snapshot already carry `proposal_id` and `proposal_version` (the ordinal
  the run pinned), because the snapshot serializes `ScheduleRunSummaryV1`
  (`ports/schedule_run.py:75-76`). No new field is needed for that. For an `applied` draft
  the snapshot adds `applied_version: {version_ordinal, constraints, consequence_summary}`
  so the agent can describe what the baseline actually contains (§4).

### 2.7 Contract changes

All changes are additive and stay under their V1 names, following the precedent in
`dialogue.py`, where `TerminalReasonV1` gained members in place:

| Contract | Change | Required work |
|---|---|---|
| `ProposalStateV1` | + `applied` | `tests/test_proposal_contracts.py`; frontend label maps in `DraftCard.tsx`, `ActivityTimeline.tsx` and `test/stateMatrix.tsx` |
| `ProposalViewV1` | + `version_ordinal`, `ended_by`, `applied_version_ordinal` (optional) | regenerate `openapi.json` and `schema.d.ts` (`npm run codegen:export && npm run codegen:types`) |
| `scheduling_draft` model view | + `outcome`, `version_ordinal` | update `evals/golden/scheduling_draft/*.json` |
| Trusted draft result | + `observed_working_id`, `observed_resource_version` | internal; unit tests only |
| Workflow snapshot | + `working_draft`, `applied_version` | eval judge context (`CANDIDATE_ASSIGNMENT_PREVIEW` neighbour) unchanged |
| RFC 7807 codes | + `applied_proposal` | router error maps for proposals and schedule runs |

No persisted row holds a new member before the migration runs, so older rows decode
unchanged. The one consumer that could break on a new state is the frontend, and it is
regenerated in the same change.

### 2.8 Planner card edits

No backend change: the revise command already accepts any list of 1..max constraints, so
removal is a shorter list, and it already enforces `expected_resource_version`
(`manage_proposal.py:201`).

## 3. Card and timeline

### 3.1 Timeline

Only the **newest** `DraftActivityV1` for a given `proposal_id` mounts the live
`DraftCard`. Older activities for the same proposal render one history line from their
persisted summary: *"Earlier version of this draft · {consequence_summary}"*. No "updated
below": the newest card may itself be ended, and it already says so. This mirrors the
existing approval rule (`ActivityTimeline.tsx`, the `isCurrentApproval` branch). Planner
card edits create no activity; the live card updates in place.

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
- **Input validation** mirrors the resolver's argument bounds so obvious mistakes never
  leave the browser: integers only; each argument within its tool's declared min/max;
  `lock_worker_shift` start < end and both within the scenario horizon. The server
  resolver (`application/drafting/resolve.py`) stays the authority; its errors surface
  through the existing card message.
- **Revise proposal → Save changes**, disabled until the local list differs from the
  server version and every input is valid; **Cancel** resets. Success announces "Saved as
  vN" in a polite live region.
- **Run optimization is disabled while there are unsaved edits**, explained as "Save or
  cancel your changes first".
- **Reject proposal → Discard draft**, with an inline two-step confirmation ("Discard this
  draft? It can't be restored. [Discard] [Keep]") — no browser dialog.
- **While an agent turn is in flight** in this conversation (the composer's busy state),
  Save, Discard and Run are disabled with "Wait for the assistant to finish". This makes
  the §2.2 race rare in one tab; the server guard still decides.
- **The draft changes under unsaved edits** (the assistant updated it, or another tab
  did): the card keeps the local edits visible but disables Save and shows "This draft
  changed to vN. Your edits were not saved. [Load vN]". Load vN drops the local edits. No
  automatic merge.
- Stale behaviour: inputs, Save and Run disabled with the existing explanation; Discard
  still available; Refresh offered.

### 3.3 Ended drafts

Read-only: constraint list plus one state line, no controls — "Discarded", "Discarded by
assistant", "Replaced by a newer draft", "Applied to baseline — vN promoted".

### 3.4 Accessibility

Automated coverage only, per `EXPERIENCE.md`'s Accessibility Floor: the accessibility
contract tests move to the new controls — distinct accessible names for Save, Cancel,
each row's remove control, Discard and its confirmation, and Load vN; the save
acknowledgement, the changed-under-you notice and the ended state are announced.

## 4. Agent instructions

In `agent/scheduling_instructions.py`:

- Replace "Revising a draft": a conversation has at most one working draft and
  `scheduling_draft` always writes to it. Send every constraint that should remain (from
  the snapshot's `working_draft`) plus the new or changed ones; omit one to remove it.
  Word the reply from the reported outcome — "Created a draft (v1)" vs "Updated your draft
  (now v3)".
- Discard: call `scheduling_draft_discard` only when the planner explicitly asks to
  discard, delete, or throw away the draft. "Start over with just X" replaces the content
  and never discards. "Throw it away and draft just X" is discard, then draft (the tools
  enforce this order, §2.1).
- Ended drafts are read-only facts in the snapshot; "bring the old one back" means
  drafting its constraints again.
- "Undo": no undo tool exists. If the request names a constraint, remove or change that
  constraint; otherwise ask which one. Never claim an undo happened.
- Update workflow stage 2 ("Draft (you)") to match. Stage 3 stays planner-only.
- Tool routing gains "Discarding the working draft on explicit request:
  scheduling_draft_discard, only."
- Update **"Saying what the baseline is now"**, step 2 (added on `main` for live B:10):
  "find the draft whose proposal_id is the run's proposal_id" and describe what it
  changed. Once drafts have versions, that draft's current version can differ from the
  version the run pinned (the v2-promoted-then-edited-to-v3 case in §1). Describe the
  draft's `applied_version` constraints (the snapshot carries them, §2.6), cross-checked
  against the run's `proposal_version`, and say "applied to baseline" from the draft's
  state.

## 5. Testing and evaluation

### 5.1 Deterministic (keyless CI)

- Migration: upgrade on a database with duplicate active drafts (newest kept, including
  an equal-`created_at` tie broken by `id`; the rest `rejected`/`system`); the partial
  unique index; downgrade round-trip.
- Repository: `get_working`; `append_agent_version`; `mark_applied` (sets `applied` and
  `applied_version_id`, zero rows on an ended draft or a proposal-less schedule version).
- `scheduling_draft`: `created` and `updated`, each recording its observation; a second
  call in one turn observes the same state; a call after a same-turn discard reports
  `created`.
- `scheduling_draft_discard`: its three golden fixtures.
- **Finalize guard, asserted on the user-visible result**, not only the database: for each
  race in §2.2 (card edit, card discard, promotion, a second turn), finalize persists the
  `capability_error` terminal outcome with the "draft changed" detail as the turn's
  activity, and the proposal row and version count are unchanged. Discard-then-create in
  one turn ends with the old draft `rejected`/`assistant` and a new v1 `active`.
- `promote_baseline`: the draft becomes `applied` in TX2; an already-ended draft is left
  alone; a TX2 rollback (baseline moved) leaves the draft `active`.
- Commands on ended drafts: revise, discard and run refused with `applied_proposal` for
  `applied` and `rejected_proposal` for `rejected`; an idempotent replay after the draft
  became `applied` returns the original stored result.
- Golden multi-turn case: draft → add → remove → discard → new request ends with exactly
  one `active` proposal in the conversation.
- Frontend: newest-activity-only live card; history lines; Save/Cancel enablement and
  input validation; row removal and the last-row guard; Run disabled with unsaved edits;
  controls disabled during an in-flight turn; the changed-under-you notice and Load vN;
  inline discard confirmation; each ended-state label, including "out of date".

### 5.2 Live

Since `main` (`ba8c706`) scenarios A-D are graded by authored per-turn `expect` lists in
`scenarios.json`: code checks over the reply, its activity and the saved draft, plus narrow
TypeSafe Jev yes/no questions (`evals/live_conversations/expectations.py`). A turn without
`expect` falls back to a holistic judge, so every new turn below is authored with `expect`.

Two new code check kinds, registered in `CODE_CHECKS` and `_FIELDS`, with unit tests in
`tests/test_live_conversation_expectations.py`:

- `draft_updates_turn: n` — the turn's draft has the same `proposal_id` as turn *n*'s and a
  higher `version_ordinal`. Bound from `Bindings.draft`, which already records
  `proposal_id`; it gains the version ordinal.
- `draft_state_is: <state>[/<ended_by>]` — the persisted state of the conversation's most
  recent draft, read after the turn's actions. Required, not optional: the agent-discard
  turn has no other way to be graded.

Changes:

- **Existing turns.** B:6 ("Revise the draft to cap that worker…") and C:9 ("Add to that
  draft…") add `draft_updates_turn` pointing at their earlier draft turn. **B:10** ("What
  is our baseline now…", after B:9's `approve` action) adds `draft_state_is: applied`, which
  covers the promotion hook live, and keeps its baseline-answer checks, now exercising the
  rewritten step 2 of "Saying what the baseline is now".
- **New scenario E — draft lifecycle, 7 turns**:
  1. create ("keep worker X off task Y in a draft") — `activity_is` draft, `draft_state_is: active`
  2. add a constraint — `draft_updates_turn: 1`
  3. remove one — `draft_updates_turn: 1`, `draft_has` the survivor only
  4. "undo that" — no draft change; `mentions_none` of a claimed undo plus a Jev yes/no question (clarifies, or restores by re-adding the named constraint)
  5. "start over with just Z" — `draft_updates_turn: 1` (replace, not discard)
  6. "throw this draft away" — `draft_state_is: rejected/assistant`
  7. new request — `activity_is` draft with a new `proposal_id`, `draft_state_is: active`

  `REQUIRED_SCENARIOS` in `cases.py` becomes `{'A': 6, 'B': 12, 'C': 12, 'D': 6, 'E': 7}`.
- **Baseline.** Today `total_executed` is 108 (36 turns × 3 repetitions). With E it becomes
  129 (43 × 3). The §4 instruction changes move `behavioral_digest`, so A-D are
  re-measured too. Re-derive `backend/evals/baselines/live-conversations.json` and the
  drop-check floor following `docs/EVIDENCE-CONVENTION.md`: commit code, measure, generate
  through `backend/scripts/evidence_binding.py` and
  `derive_live_conversation_baseline.py`, commit evidence separately. Do not hand-edit the
  baseline.

## 6. Deferred

Recorded in `_bmad-output/implementation-artifacts/deferred-work.md` under "Deferred from:
brainstorming of the draft lifecycle design (2026-09-28)":

- **Undo / restore.** Design already worked out: each version stores `undo_target_ordinal`
  and `origin`. A normal edit (including an explicit restore) targets the version it was
  made from; an undo copies the current version's target and inherits that target's own
  target, so repeated undo walks back instead of toggling. Always append-only — never move
  `current_version_id` backwards, because runs pin versions.
- A restore control on the card.
- Re-activating a discarded draft.
- A diff between versions on the card.
- A full card editor (add or retarget constraints).
- Merging a planner's unsaved card edits with a concurrent assistant update (today: Load vN
  drops them).

Related open items on `main` (`deferred-work.md`), not solved here: the agent cannot say
when or by whom a baseline was approved, and does not reuse the approval id it created.
The `applied` state and `applied_version_id` tell the agent *that* a draft was promoted,
not the approval's time or actor; that still needs the approval-repository read path.

## Out of scope

Per-actor draft ownership (Story 3.1's `authz:site_scoped_shared_drafting` stands);
changes to runs, the solver, or approval rules and contracts. The only approval-side
change is the one-line proposal write inside `promote_baseline`'s existing TX2 (§2.4).
