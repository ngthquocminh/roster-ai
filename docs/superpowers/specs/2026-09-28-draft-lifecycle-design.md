# Draft lifecycle: one working draft per conversation

Date: 2026-09-28 · Status: approved in brainstorming, awaiting spec review

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

- Existing scenarios whose turns say "Revise the draft…" / "Add to that draft…"
  (`evals/live_conversations/scenarios.json`, the two `requires_persisted_draft` follow-up
  turns) now expect the **same** proposal at a new version; their persisted-draft check
  accepts an update and asserts it did not create a second proposal.
- New live scenario **E — draft lifecycle**: create → add → remove one → "undo that"
  (clarify or concrete removal, never a claimed undo) → "start over with just X"
  (replace, not discard) → explicit discard → new request (fresh draft).
- Re-derive the live baseline and drop-check floor for the new turn count, following
  `docs/EVIDENCE-CONVENTION.md`: commit code, measure, generate through
  `backend/scripts/evidence_binding.py`, commit evidence separately.

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

## Out of scope

Per-actor draft ownership (Story 3.1's `authz:site_scoped_shared_drafting` stands);
changes to runs, approvals, or the solver.
