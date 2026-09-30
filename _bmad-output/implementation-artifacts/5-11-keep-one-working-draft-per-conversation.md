---
baseline_commit: 8a85f4f
---

# Story 5.11: Keep One Working Draft per Conversation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want each conversation to have exactly one working draft that chat requests and card edits both change,
So that I always know which draft I would run, and the timeline stays readable.

**Inserted 2026-09-30 by `sprint-change-proposal-2026-09-30.md` [Corrective Insert].** The design
source is `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` ("the spec"), §1–§4, §5.1
and decisions D1–D8. This story implements the spec **by reference**. Where creation found the spec
wrong about the code, or silent on something the code forces, the correction is recorded below as a
finding (C1–C19) and resolved by a numbered Decision. **When this file and the spec disagree, this
file wins; when this file is silent, the spec governs.**

**What exists today.** Every `scheduling_draft` call mints a fresh `proposal_id`
(`application/capabilities/scheduling_draft.py:287-298`) and `finalize_agent_run` always calls
`create_draft` (`application/use_cases/finalize_agent_run.py:41-62`). `ProposalStateV1` is
`active | rejected` (`application/contracts/proposal.py:25`). The Draft card edits one constraint at
a time through a select, only numeric arguments (`frontend/src/features/chat/DraftCard.tsx:19-32,
241-275`), and every `draft` activity mounts its own live card
(`frontend/src/features/chat/ActivityTimeline.tsx:405-414`).

**Scope summary.** One Alembic migration (three-state check, `ended_by`, `applied_version_id`,
lifecycle CHECK, duplicate collapse, partial unique index, grants, reversible downgrade); proposal
contracts widened additively; five new repository methods and one conversation lock; a per-turn
draft state on `AgentDepsV1`; `scheduling_draft` resolving the working draft; a new
`scheduling_draft_discard` capability (manifest, flag, four golden cases, smoke case); the finalize
guard; ended-draft refusals on revise/discard/run; the TX2 `mark_applied` write; API/OpenAPI/
`schema.d.ts`; the workflow snapshot and instructions; the timeline and a rebuilt Draft card.
**No new dependency, no live run, no provider spend, no evidence file, no change to runs, the
solver, approval contracts, `PolicyInputsV1`, the live-eval harness or its baseline** (those are
Story 5.12's).

**Depends on:** Story 3.1's proposal aggregate and commands; Story 4.3's TX2
(`promote_baseline`); Story 4.5's TX2 fault matrix; Story 3.6's run command; Story 2.2/2.6's
capability registry and golden harness; Story 5.7's instruction sections ("Saying what the
baseline is now").

**Unblocks:** Story 5.12 (live proof and re-baseline), then the Gate B re-assessment.

---

## What creation found — corrections and gaps the spec does not state

Each was checked against the code at `8a85f4f`. Each is resolved by the Decision named.

| # | Finding | Evidence | Resolved by |
|---|---|---|---|
| C1 | **`draft_id` is NOT the proposal id.** Spec §2.1 says "On `updated` the `draft_id` is the *existing* proposal id". It is the content-addressed `result_id` (`derive_draft_id(...)`), and the runtime rebinds a garbled citation to this run's latest `draft_id` from tool returns only. The spec's *conclusion* (the wider model view is compatible) holds; its *reason* does not. | `scheduling_draft.py:283,157-158`; `SCOPE_CONTROLS["identity:content_addressed_citation_only"]` (`:70-75`); `agent/runtime.py:200-221,540-548` | Decision 5 |
| C2 | **A tool cannot read proposals today.** The route builds `AgentDepsV1(connection=None, projection_reader=ShortTransactionScenarioProjectionReader(...))`; `AgentDepsV1` has no proposal reader. "`scheduling_draft`, at tool time, resolves the working draft" (spec §2.1) needs a new, per-turn, short-transaction read. | `api/routers/conversations.py:306-324`; `application/capabilities/deps.py:17-57`; `adapters/postgres/short_transaction_projection.py` | Decision 4 |
| C3 | **Lock-order inversion if `mark_applied` sits where "after the CAS" first suggests.** `finish_agent_run` locks the conversation row, then the agent run; the finalize guard adds conversation → proposal. TX2's conversation writes (`_append_approval_activity`, `resume_agent_run_for_approval`) lock the conversation row *after* the CAS. Writing the proposal right after the CAS gives TX2 proposal → conversation: a deadlock cycle with a concurrent finalize in the same conversation. EAD-6's amendment says only "after the `site_baseline` CAS", which the **last** position also satisfies. | `adapters/postgres/conversation.py:67-68,135-145,508-519`; `promote_baseline.py:141-207` | Decision 10 |
| C4 | **The proposals router emits `proposal_rejected`, not `rejected_proposal`.** The AC requires `rejected_proposal`; `schedule_runs.py:253`, `RunsTable.tsx:61` and `DraftCard.tsx:58` already use `rejected_proposal`, so the card's mapping has never matched a revise/reject refusal. Nothing consumes `proposal_rejected` (repo-wide grep). | `api/routers/proposals.py:82-86` | Decision 9 |
| C5 | **Command check order would hide `applied_proposal`.** `mark_applied` bumps `resource_version`; `enqueue_compute` compares the expected resource version *before* `create_run_snapshot` checks state, and `revise_proposal` checks scenario staleness *before* state. Run on an applied draft would answer `stale_resource_version`; revise on a stale applied draft would answer `stale_proposal`. | `enqueue_compute.py:146-150,168`; `manage_proposal.py:196-202`; `create_run_snapshot.py:76-79` | Decision 9 |
| C6 | **A draft turn has no model prose.** The draft output is `DraftProposalV1{draft_id}` only; its visible text is the application-composed `consequence_summary` and its activity is a `DraftActivityV1`. Spec §4's "Word the reply from the reported outcome — 'Created a draft (v1)' vs 'Updated your draft (now v3)'" has no carrier on a draft turn. | `execute_turn.py:394-404,433-434`; `agent/runtime.py:385-392`; `contracts/activity.py:87-100` | Decision 12 |
| C7 | **"The composer's busy state" is not an in-flight signal.** `useSendMessage` resolves when the message is *accepted*; the agent turn executes afterwards in a detached promise. `mutation.isPending` is therefore false for the whole turn. The in-flight fact already on the page is the timeline's `latest_agent_run_status`. | `frontend/src/hooks/useSendMessage.ts:5-41`; `ChatView.tsx:318-325,336-341` | Decision 13 |
| C8 | **Moving the live card remounts it.** When the agent appends a version, a new `draft` activity becomes the newest; the live card moves to a different `<li>`, React unmounts the old instance and its `useState` edits vanish silently — the exact case the "This draft changed to vN … [Load vN]" notice exists for. | `ActivityTimeline.tsx:474-489`; `DraftCard.tsx:96-110` | Decision 13 |
| C9 | **An agent discard or a promotion never refreshes the card.** Neither creates a `draft` activity, `useProposal` has no invalidation from turn completion, and the revise/reject hooks write the response body straight into the cache — a replay (spec §1 "Idempotent replay") would stand as current state. | `useProposal.ts`; `useReviseProposal.ts:15-18`; `useRejectProposal.ts:14-17`; `useSendMessage.ts:30-36`; `useDecideApproval.ts:32-37` | Decision 14 |
| C10 | **"Integers only" is wrong for two kinds.** `factor` and `max_hours` are floats in the resolver; only `n`, `start_minute`, `end_minute` are integers. | `application/drafting/resolve.py:152-221`; `contracts/proposal.py:37-41` | Decision 14 |
| C11 | **The golden harness grants exactly one module per case and shares one deps.** `_runtime_for_case` selects the single module named by the case tag; `_report_deps` has no per-case state; `CASE_FIELDS` rejects unknown keys. The discard fixtures "after-draft-same-turn" and "start-over-is-not-discard" need `scheduling_draft` granted beside discard; "valid" needs a seeded working draft. | `evals/report.py:46,418-436,504-523`; `evals/cases.py:516-555` | Decision 15 |
| C12 | **Installing a capability requires a two-turn smoke case.** | `tests/test_live_conversation_smoke_cases.py:14-19`; `evals/live_conversations/smoke_cases.py:16-35` | Decision 6 |
| C13 | **`proposal` has a column-scoped UPDATE grant and FORCE RLS.** New columns need their own grant. A data step under FORCE RLS sees rows only as a superuser/BYPASSRLS role (the local provisioning role `rosterai` is the container superuser). | `migrations/versions/e9f0a1b2c3d4_add_reversible_proposals.py:88-94`; `c4d5e6f7a8b9_…py:88-91` (docstring); `docker-compose.yml:6,29` | Decision 1 |
| C14 | **Staleness has a second, baseline dimension.** `create_run_snapshot` refuses when `expected_baseline_schedule_version` ≠ the current baseline, while `ProposalViewV1.stale` compares scenario versions only. An agent `updated` version must pick a baseline pin; the planner revise path copies the old one (`**current.__dict__`). | `create_run_snapshot.py:89-96`; `manage_proposal.py:57-62,215-227` | Decision 5 |
| C15 | **Instructions do not move `behavioral_digest`.** It hashes model, judge, reasoning effort and the env override file only. Proposal §2.2's "These instruction changes move the `behavioral_digest`" is inaccurate. Default CI is therefore unaffected by the §4 rewrite; 5.12's reason to re-measure A–D (behaviour changed) stands on its own. | `evals/live_conversations/configuration.py:133-155` | Decision 17 (ledger) |
| C16 | **The golden multi-turn harness persists nothing**, so spec §5.1's "golden multi-turn case … ends with exactly one `active` proposal" cannot be asserted there. | `evals/golden_multi_turn/`; `evals/report.py` (double runtime, `_report_deps`) | Decision 16 |
| C17 | **`decide_approval` has eight test call sites in six files** besides the router; a new required parameter touches each. | `tests/test_approval_audit_invariants_postgres.py:339`, `test_approval_governance_postgres.py:523,567,992,1161`, `test_decide_approval.py:80`, `architecture/test_telemetry_boundaries.py:592`, `test_telemetry_correlation.py:172` | Decision 10 |
| C18 | **Pre-existing `rejected` rows carry no `ended_by`.** Before this story the only path to `rejected` is the planner route. | `manage_proposal.py:243-294`; `api/routers/proposals.py:140-161` | Decision 1 |
| C19 | **Most `SCHEDULING_*_ENABLED` flags are undocumented.** Only `SCHEDULING_BASELINE_ENABLED` appears in `docs/CONFIGURATION.md`; none is in `backend/.env.example`. F5 requires the new flag in both. | `docs/CONFIGURATION.md:52`; `settings.py:536-561` | Decision 6, 17 |

---

## Facts this story depends on — each one written down and citable

Retro action A3 requires this pass before decisions. None of these may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **The ACs** (frozen, below). | `_bmad-output/planning-artifacts/epics.md:1633-1677` |
| **The design**: states, transitions, staleness, resolution, finalize guard, discard, promotion hook, schema, read model, contracts, card, instructions, deterministic tests, deferrals. | spec §1–§4, §5.1, §6 |
| **F1** (TX2 composition is an architecture amendment), **F2** (≥4 golden cases incl. the negative start-over case), **F5** (new flag, not a `PolicyInputsV1` input, documented). | `sprint-change-proposal-2026-09-30.md` §1.1 |
| **AD-9 as amended**: at most one `active` proposal per conversation, partial unique index; ended as `rejected` or `applied` (inside the promotion transaction); ended proposals refuse revise, discard and run; versions append-only; `applied` records the promoted version. | `architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:142` |
| **EAD-6 as amended**: TX2 gains one write after the `site_baseline` CAS; zero rows is normal; commits and rolls back with the bundle; approval contracts, effect key, outcome vocabulary, `PolicyInputsV1` unchanged. **Verification obligation 6**: fault injection on each TX2 write "(binding, pointer, proposal, audit, event)". | `architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md:87-88,221` |
| **TX2 rollback mechanics**: post-write failures must *raise and escape*; catching and returning commits a partial bundle. | `backend/application/use_cases/promote_baseline.py:1-45` |
| **FR9** (validated proposal), **FR10** (reviewable, editable, rejectable, abandonable), **FR23** (versioned capability modules with manifest, errors, fixtures; registration grants nothing), **NFR9** (promotion, audit and event share one consistency boundary), **NFR26** (CI deterministic-first, keyless), **NFR28** (≥4 golden cases per allowed capability). | `epics.md:41,43,69,91,125,129` |
| **UX-DR9 as amended** (version and lifecycle state beside the title; in-place edit and row removal saved as a new version; separate Discard and Run; ended drafts read-only), **UX-DR25** (distinct stale/loading/error states), **UX-DR35** (Send, Run optimization and Approve visually discontinuous). | `epics.md:194,226,246` |
| **EXPERIENCE Draft card row** and **DESIGN Draft card row** (Card, Input, Button, Badge, Separator — Select is no longer listed). | `ux-ShiftMind-2026-07-22/EXPERIENCE.md:87`; `DESIGN.md:128` |
| **Accessibility Floor**: automated coverage only; errors associated with affected controls; durable transitions announce through a polite live region; drafts retained after recoverable failures. | `EXPERIENCE.md:185-197` |
| **AD-8 idempotency**: operation is what the command does; body hash includes the expected version; a replay returns the original result with staleness recomputed. | `manage_proposal.py:89-142` |
| **Shared drafting authorization**: any planner in a site may revise or reject any draft; `created_by_actor_id` is audit only (Story 3.1). Unchanged. | `scheduling_draft.py:76-81` |
| **A conversation is pinned to one scenario version**, and every turn runs with that pin. | `adapters/postgres/conversation.py:184-218`; `api/routers/conversations.py:306-314` |
| **Runtime grants and RLS on `proposal`**: `GRANT SELECT, INSERT`, `REVOKE UPDATE, DELETE`, `GRANT UPDATE (state, current_version_id, resource_version)`, FORCE RLS keyed on `app.site_id`. | `e9f0a1b2c3d4_add_reversible_proposals.py:88-94` |
| **Downgrade precedents**: a data-destroying reversal is refused; a one-step downgrade test proves a migration's own reversal and that an ancestor grant survives. | `c4d5e6f7a8b9_…py:74-102`; `tests/test_approval_governance_postgres.py:762-812` |
| **Deferred** (not this story): undo/restore, restore control, re-activation, diff, full editor, merge of unsaved edits. | `_bmad-output/implementation-artifacts/deferred-work.md:1223-1246` |
| **Demonstrated red and the mutation table** are required before review. | `_bmad/custom/bmad-dev-story.toml` |
| **Evidence convention**: this story produces no `evidence/**` file. | `docs/EVIDENCE-CONVENTION.md` |
| **Domain model.** This story computes no metric, reads no demand row and adds no assignment field. The workflow snapshot's candidate/baseline assignment previews are unchanged. Cited because the standing rule requires it. | `docs/DOMAIN-MODEL.md` §1–§3, §5 |

---

## Acceptance Criteria

Verbatim from `epics.md:1645-1677`. Frozen. Numbered for reference only.

**AC1.**
**Given** a conversation with no working draft, or with one
**When** the agent drafts
**Then** it creates v1 of a new proposal, or appends the next version of the working draft with the full constraint list replaced, and reports `created` or `updated` with `version_ordinal`
**And** at most one `active` proposal exists per conversation, enforced by the partial unique index `uq_proposal_one_active_per_conversation`. (FR9, FR10, AD-9)

**AC2.**
**Given** the planner edited or discarded the draft, a run from it was promoted, or another turn finalized, while an agent turn was in flight
**When** that turn finalizes
**Then** nothing is written to `proposal` or `proposal_version`, and the turn ends with the `capability_error` terminal outcome "Your draft changed while I was working, so I didn't apply this change."
**And** each of the four races is tested on that visible outcome and on unchanged proposal rows. (spec §2.2, D8)

**AC3.**
**Given** the planner explicitly asks to discard the draft
**When** the agent calls `scheduling_draft_discard`
**Then** the draft becomes `rejected` with `ended_by='assistant'`, "start over with just X" replaces the draft rather than discarding it, and discard-then-draft in one turn is ordered by the tools
**And** the capability ships with a manifest, the feature flag `scheduling_draft_discard_enabled`, and at least four golden cases, including the negative "start over" routing case. (FR23, Gate B dataset floor)

**AC4.**
**Given** a run whose snapshot pins this proposal
**When** it is promoted to baseline
**Then** TX2 marks the draft `applied` with `applied_version_id` = the pinned version, an already-ended draft is left alone, and a TX2 rollback leaves the draft `active`
**And** revise, discard and run optimization on an ended draft fail with `rejected_proposal` or `applied_proposal` (RFC 7807, 409), while an idempotent replay still returns the original result. (FR10, AD-9, EAD-6 as amended)

**AC5.**
**Given** the migration runs on a database with duplicate active drafts
**When** it upgrades
**Then** the newest by `(created_at DESC, id DESC)` stays `active`, the rest become `rejected`/`system`, and the downgrade round-trips. (spec §2.5)

**AC6.**
**Given** the working draft in Chat
**When** the planner reviews it
**Then** only the newest draft activity for a proposal mounts the live card, and older ones render one history line
**And** the card edits values in place and removes rows (never the last row). Save changes and Cancel enable only when there is a valid difference; Run optimization is disabled while edits are unsaved; Discard asks for inline two-step confirmation; controls are disabled while an agent turn is in flight; and "This draft changed to vN … [Load vN]" appears when the draft changes under unsaved edits. (UX-DR9 as amended, UX-DR25, UX-DR35)

**AC7.**
**Given** an ended or stale draft
**When** its card renders
**Then** it is read-only and states "Discarded", "Discarded by assistant", "Replaced by a newer draft", "Applied to baseline — vN promoted" or "Working draft · out of date"
**And** the automated accessibility contract covers every new control, the save acknowledgement, the changed-under-you notice and each ended state. (Accessibility Floor, automated only)

**Out of scope, deliberately** (epics.md:1677). Undo, restore, diff, re-activation, adding or
retargeting constraints on the card, and merging card edits with a concurrent assistant update (all
recorded in `deferred-work.md`). No change to runs, the solver, or approval rules and contracts.

**Reading notes.**
* "Save changes and Cancel enable only when there is a valid difference": Cancel needs only *a*
  difference (valid or not) — you must be able to cancel an invalid edit. Save needs a difference
  **and** every input valid. Decision 14 pins this; it is the only sane reading.
* AC7's "Working draft · out of date" is an `active` draft whose conversation's scenario moved on
  (spec §1 "Staleness"). It is **not** read-only for Discard: spec §1 and §3.2 keep Discard available
  on a stale draft. "Read-only" in AC7 means no value edit, no Save, no Run.
* AC4's codes are RFC 7807 problem codes, so "revise, discard and run optimization" there means the
  three **HTTP commands** (`/revisions`, `/rejection`, `POST /schedule-runs`). The agent tool has no
  problem response: it cannot see an ended draft at all (`get_working` returns only `active`), so it
  answers `no_working_draft` at tool time, and a draft that ends mid-turn is AC2's finalize guard.

---

## Seventeen decisions were made at story creation — do not re-litigate them

Each states its mechanism **and what it does not cover**.

### Decision 1 — The migration: one revision, reversible, fail-loud under a non-bypass role

New file `backend/migrations/versions/a8b9c0d1e2f3_one_working_draft_per_conversation.py`,
`down_revision = "f7a8b9c0d1e2"` (the current head). `adapters/postgres/schema.py` must mirror every
object so `command.check` stays clean (`tests/test_postgres_integration.py:1208-1227`).

**Upgrade, in this order:**
1. Drop and recreate `ck_proposal_state` as `state IN ('active','rejected','applied')` (the
   `_replace` shape of `e5f6a7b8c9d0`).
2. Add `ended_by VARCHAR(20) NULL` with `ck_proposal_ended_by`:
   `ended_by IS NULL OR ended_by IN ('planner','assistant','system')`.
3. Add `applied_version_id UUID NULL` with composite FK `fk_proposal_applied_version_site`
   `(applied_version_id, site_id) → proposal_version(id, site_id)` `ON DELETE RESTRICT`
   (`use_alter=True` in `schema.py`, like `fk_proposal_current_version_site`).
4. **Data:** `UPDATE proposal SET ended_by = 'planner' WHERE state = 'rejected'` (C18).
5. **Data:** in every conversation with more than one `active` proposal, keep the newest by
   `(created_at DESC, id DESC)`; set the rest to `state='rejected', ended_by='system',
   resource_version = resource_version + 1` (one `UPDATE … FROM (SELECT … ROW_NUMBER() OVER
   (PARTITION BY conversation_id ORDER BY created_at DESC, id DESC))`).
6. Add `ck_proposal_lifecycle`:
   `(state = 'active' AND ended_by IS NULL AND applied_version_id IS NULL) OR
    (state = 'rejected' AND ended_by IS NOT NULL AND applied_version_id IS NULL) OR
    (state = 'applied' AND ended_by = 'system' AND applied_version_id IS NOT NULL)`.
   This CHECK is a creation decision beyond the spec: it makes "an ended proposal always says who
   ended it" a database fact rather than an adapter habit.
7. `CREATE UNIQUE INDEX uq_proposal_one_active_per_conversation ON proposal (conversation_id)
   WHERE state = 'active'` (`op.create_index(..., unique=True, postgresql_where=sa.text("state =
   'active'"))`; `Index(..., unique=True, postgresql_where=text(...))` in `schema.py`).
8. `GRANT UPDATE (ended_by, applied_version_id) ON proposal TO shiftmind_runtime` (C13).

**Downgrade, in this order:** revoke the step-8 grant; drop the index; drop `ck_proposal_lifecycle`;
`UPDATE proposal SET state = 'active' WHERE state = 'applied'` (spec §2.5: their pre-feature state);
drop the FK, `applied_version_id`, `ck_proposal_ended_by`, `ended_by`; restore the two-value
`ck_proposal_state`. Collapsed rows stay `rejected` (the old schema accepts them). The downgrade
never deletes a row, so it is not refused the way `c4d5e6f7a8b9` is.

**The docstring must state the RLS behaviour (C13).** Both data steps run under FORCE RLS. As the
container superuser they see every row. Under a role without BYPASSRLS they match zero rows, and the
migration then **fails loudly**: the upgrade's unique-index build sees every duplicate (index
builds are not subject to RLS) and raises; the downgrade's two-value CHECK validates against every
`applied` row and raises. Neither can silently half-apply.

**Not covered:** no backfill of `applied` for promotions that happened before this migration
(spec §2.5); the migration does not re-point `current_version_id`; a downgrade leaves a
conversation that held an `applied` and an `active` draft with two `active` rows, which the old
schema permits.

### Decision 2 — Contracts: additive V1, and the persisted version payload is untouched

In `application/contracts/proposal.py`:
* `ProposalStateV1 = Literal["active", "rejected", "applied"]`.
* `ProposalEndedByV1 = Literal["planner", "assistant", "system"]`.
* `DraftOutcomeV1 = Literal["created", "updated"]`.
* `ProposalViewV1` gains `version_ordinal: int | None = None`, `ended_by: ProposalEndedByV1 | None =
  None`, `applied_version_ordinal: int | None = None` (spec §2.6). The defaults exist only so
  `command_idempotency.response_payload` rows written before this story still decode on replay;
  every fresh read populates `version_ordinal`.
* New trusted, frozen contracts (framework-free, same file):
  * `WorkingDraftObservationV1(proposal_id: UUID, resource_version: int, version_ordinal: int)`.
  * `AgentDraftWriteV1(proposal: ProposalV1, outcome: DraftOutcomeV1, version_ordinal: int,
    observed_working_id: UUID | None, observed_resource_version: int | None)` — what finalize
    applies for a draft (spec §2.1, §2.7 "Trusted draft result").
  * `AgentDraftDiscardV1(proposal_id: UUID, observed_resource_version: int, version_ordinal: int)`.
* `application/contracts/agent_runtime.py`: `AgentRunOutcomeV1.resolved_draft` becomes
  `AgentDraftWriteV1 | None`; add `resolved_discard: AgentDraftDiscardV1 | None = None`. Update the
  field comment.

`ProposalV1` — the payload stored in every `proposal_version` row — **gains no field**.
`ProposalRecordV1` (port, not contract) gains `ended_by`, `applied_version_id`,
`applied_version_ordinal`.

**Not covered:** `ProposalV1.state` inside a stored version payload keeps whatever it held at write
time (always `active`); the `proposal` row is the authority and `get_current` already overlays
`state`/`resource_version` from it (`adapters/postgres/proposal.py:88-95`). Nothing may read state
from a version payload.

### Decision 3 — Repository and conversation ports

`application/ports/proposal.py` `ProposalRepository` gains, and `PostgresProposalRepository`
implements:
* `get_working(connection, *, conversation_id: UUID, for_update: bool) -> ProposalRecordV1 | None`
  — the conversation's `active` proposal (at most one row by the index).
* `append_agent_version(connection, *, proposal: ProposalV1, site_id: UUID, version_ordinal: int)
  -> None` — version row + `current_version_id` + `resource_version`, **no idempotency row**
  (spec §2.2: the claimable guard already makes finalize exactly-once).
* `end_by_assistant(connection, *, proposal_id: UUID, resource_version: int) -> None` —
  `state='rejected', ended_by='assistant', resource_version = :resource_version`.
* `mark_applied(connection, *, site_id: UUID, schedule_version_id: UUID) -> bool` — reads
  `proposal_id`/`proposal_version_id` from `schedule_version`, then the spec §2.4 `UPDATE … WHERE
  id = :proposal_id AND state = 'active'`; returns whether a row changed. Zero rows is **not** an
  error.
* `get_version(connection, *, proposal_version_id: UUID) -> tuple[int, ProposalV1] | None` — the
  ordinal and payload of one version (for the snapshot's `applied_version`, Decision 12).
* `reject(...)` gains nothing in its signature; the adapter now also writes `ended_by='planner'`.
* `get_current` also selects `ended_by`, `applied_version_id`, and the applied ordinal through an
  outer join on `applied_version_id` (spec §2.6: "nothing is stored twice").

`application/ports/conversation.py` `ConversationRepository` gains
`lock_conversation(connection, *, conversation_id: UUID) -> None` (`SELECT … FOR UPDATE`; raises
`RuntimeError` when not visible, the same contract `finish_agent_run` has at `conversation.py:513-514`).

**Not covered:** no method moves a proposal back to `active`, and none writes `applied` outside
`mark_applied` (deferred re-activation, spec §6).

### Decision 4 — A per-turn draft state on `AgentDepsV1` (C2)

New `application/drafting/turn_state.py` with a mutable, per-turn class `DraftTurnState` (same
standing as `EvidenceRegistry`: built fresh with every deps, `compare=False, repr=False`):
* constructed with `read_working: Callable[[], WorkingDraftObservationV1 | None]`;
* `observe()` — calls `read_working` **once per turn** and memoizes it (spec §2.1: "every call
  resolves against the same pre-turn state and records the same observation");
* `note_drafted()`, `drafted: bool`;
* `record_discard(observation)`, `discarded: WorkingDraftObservationV1 | None`.

`AgentDepsV1` gains `draft_turn: DraftTurnState = field(default_factory=lambda:
DraftTurnState(lambda: None), compare=False, repr=False)`. The default ("no working draft") keeps
every existing deps construction in tests and evals valid. **The execute route must wire the real
reader**: a closure that opens `open_site_context(claimed.site_id)` and calls
`proposal_repository.get_working(connection, conversation_id=claimed.conversation_id,
for_update=False)`, mapping the record to a `WorkingDraftObservationV1` — the
`ShortTransactionScenarioProjectionReader` shape. A route test proves it is wired (Task 13).

**Not covered:** a change between `observe()` and finalize — that is exactly what the finalize
guard (Decision 8) catches; the approval-resume path never drafts, so it needs no wiring beyond the
default.

### Decision 5 — `scheduling_draft` resolves the working draft (spec §2.1, C1, C14)

At tool time, after the existing validation and before building the proposal:
* If `deps.draft_turn.discarded` is set → treat as **no working draft** (spec §2.1).
* Else `observed = deps.draft_turn.observe()`.
* **No working draft** (including after a same-turn discard): exactly today's `ProposalV1` (fresh
  `proposal_id`, `resource_version=1`), `outcome="created"`, `version_ordinal=1`,
  `observed_working_id=None`, `observed_resource_version=None`. The same-turn discard reaches
  finalize separately, as `outcome.resolved_discard` (Decision 7); Decision 8's "discard + draft
  `created`" row checks it.
* **Working draft:** `proposal_id = observed.proposal_id`, fresh `proposal_version_id`,
  `resource_version = observed.resource_version + 1`, `outcome="updated"`,
  `version_ordinal = observed.version_ordinal + 1`, observed id and resource version recorded.
* Every other field is built **exactly as today** from this call's resolution: constraints
  (full replacement), fresh `preserved_locks`, `consequence_summary`, `canonical_hash`, and
  `expected_baseline_schedule_version = overview.baseline_schedule_version` **at tool time**
  (C14). An agent update is a fresh resolution against current state, as every agent draft is today.
* Call `deps.draft_turn.note_drafted()` on success.

`SchedulingDraftResultV1` gains `outcome`, `version_ordinal`, `observed_working_id`,
`observed_resource_version`. `SchedulingDraftModelViewV1` gains `outcome` and `version_ordinal`;
**`draft_id` stays the content-addressed `result_id`** (C1). Rewrite
`SCOPE_CONTROLS["identity:content_addressed_citation_only"]`'s NOT COVERED sentence (the
`proposal_id` is now the working draft's when one exists; `proposal_version_id` is always fresh) and
add `"lifecycle:one_working_draft"` naming the mechanism and what it does not cover (a change after
observation — the finalize guard's). Update `model_description` ("writes the conversation's one
working draft: creates v1 when none exists, otherwise appends the next version with the full list
you send; omit a constraint to remove it").

**Not covered:** the planner revise path keeps copying the old baseline pin (unchanged behaviour,
C14), and `ProposalViewV1.stale` still reports scenario drift only. A working draft left
baseline-stale by a promotion in *another* conversation is refused by `create_run_snapshot` with
`stale_proposal`, as today. Recorded in the ledger (Decision 17), not fixed here.

### Decision 6 — The `scheduling_draft_discard` capability (spec §2.3, F2, F5, C12, C19)

New `application/capabilities/scheduling_draft_discard.py`, following `scheduling_draft.py`'s shape:
* `CAPABILITY_NAME = "scheduling_draft_discard"`, `SCHEDULING_DRAFT_DISCARD_POLICY =
  "scheduling_draft_discard_enabled"`.
* `SchedulingDraftDiscardRequestV1(schema_version: str = "1")` — no arguments (spec §2.3).
* `SchedulingDraftDiscardResultV1` (TRUSTED): `result_id`, `proposal_id`,
  `observed_resource_version`, `version_ordinal`. Model view:
  `{outcome: "discarded", version_ordinal}` — never the proposal id.
* Errors (`CapabilityError` subclasses, set-equal to `manifest.errors`): `no_working_draft`,
  `draft_changed_this_turn` ("this turn already changed the draft"), `budget_exhausted`.
  `retryable_error_codes = {"no_working_draft", "draft_changed_this_turn"}` so the model sees the
  refusal and can tell the planner (spec §2.1 "a capability error the model sees").
* Handler: budget check; if `deps.draft_turn.drafted` → `draft_changed_this_turn`; if
  `deps.draft_turn.discarded` → `no_working_draft`; `observed = deps.draft_turn.observe()`; `None` →
  `no_working_draft`; else `record_discard(observed)` and return the result.
* Manifest: `risk_class="draft"`, `permission="scenario:draft"`,
  `scope="current_site/current_conversation"`, `approval_policy="none"`, `budget_limit=1`,
  `timeout_seconds=settings.scheduling_draft_timeout_seconds`, `citable_result_id=False`,
  `evaluation_fixtures` = the four files of Decision 15. `SCOPE_CONTROLS` with NOT COVERED sentences.
* `model_description`: call only when the planner explicitly asks to discard, delete, or throw away
  the draft; "start over with just X" is `scheduling_draft` with only X, never discard.
* Install in `application/capabilities/installed.py`. `settings.py`: field
  `scheduling_draft_discard_enabled: bool = True` and `_flag("SCHEDULING_DRAFT_DISCARD_ENABLED",
  …, True)`. It is **not** a `PolicyInputsV1` input (F5).
* `evals/live_conversations/smoke_cases.py`: add
  `ConversationToolSmokeCase(id='discard-working-draft', capability='scheduling_draft_discard',
  precondition='baseline', second_turn='Throw away my current draft.',
  expected_activity='agent_response')`. With no draft the tool answers `no_working_draft` and the
  model replies — still one tool call. **Authored only; it is not run in this story** (5.12 owns
  live runs).
* Docs: a `SCHEDULING_DRAFT_DISCARD_ENABLED` row in `docs/CONFIGURATION.md` beside
  `SCHEDULING_BASELINE_ENABLED`, and a commented line in `backend/.env.example`.

**Not covered:** the smoke case's live result; the other undocumented `SCHEDULING_*_ENABLED` flags
(C19 — ledger).

### Decision 7 — Binding the trusted results in `execute_turn`

* `resolve_draft_citation` binds the cited `SchedulingDraftResultV1` into an `AgentDraftWriteV1`
  (`resolved_draft`). Its failure branch is unchanged.
* For **every** `completed` outcome (answer, draft, clarification, refusal), `execute_turn` binds
  `resolved_discard` from the one `SchedulingDraftDiscardResultV1` in `calculation_results`, if any
  (the handler makes a second one impossible; assert at most one).
* `activity_payload` returns the `AgentDraftWriteV1` for a draft; `outcome_visible_text` and
  `terminal_outcome` read `resolved_draft.proposal.consequence_summary` / `is not None` as before.
* `evals/report.py` keeps calling `resolve_draft_citation`; nothing else there reads the type.

**Not covered:** a turn that is not `completed` (failed, timed out, suspended) binds and applies
neither a draft nor a discard — nothing persists from a failed turn, as today.

### Decision 8 — The finalize guard (spec §2.2, AC2)

`finalize_agent_run(conversation_repository, proposal_repository, connection, *, claimed, status,
payload: GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1 | AgentDraftWriteV1,
discard: AgentDraftDiscardV1 | None = None, request_id)`. The three `_finish` call sites in
`api/routers/conversations.py` pass `discard=outcome.resolved_discard`.

**The guard runs only when the payload is an `AgentDraftWriteV1` or `discard` is not `None`.** Every
other turn finalizes exactly as today, with no new lock. When it runs:
1. `conversation_repository.lock_conversation(...)` — **conversation first** (lock order,
   Decision 10).
2. `working = proposal_repository.get_working(..., for_update=True)`.
3. Apply the table; `updated` together with a discard is a programming error (`ValueError`), since
   the tools make it unreachable (Decision 6):

| Turn carries | Applied only if | Writes, after `finish_agent_run` |
|---|---|---|
| discard, no draft | `working` is the discard's proposal at its `observed_resource_version` | `end_by_assistant(resource_version = observed + 1)` |
| draft `created`, no discard | `working is None` | `create_draft` |
| discard + draft `created` | `working` is the discard's proposal at its observed resource version | `end_by_assistant`, **then** `create_draft` (index order) |
| draft `updated` | `working.proposal_id == observed_working_id` **and** `working.resource_version == observed_resource_version` | `append_agent_version` |

4. **If the check fails:** call `finish_agent_run` with `status="agent_failed"` and
   `TerminalOutcomeV1(status="failed", reason="capability_error", detail="Your draft changed while
   I was working, so I didn't apply this change.", next_step="Ask again to apply it to the current
   draft.")`, write nothing to `proposal`/`proposal_version`, and return. The model's reply is not
   persisted (spec §2.2). The caller's telemetry already reports `completed.agent_run_status`.
5. `finish_agent_run` still runs **before** any proposal write (its docstring's claimable-guard
   ordering, `finalize_agent_run.py:35-39`). A `DraftActivityV1` still carries
   `proposal_id`/`proposal_version_id`/`consequence_summary` — for `updated`, the existing proposal
   id and the new version id.

**Not covered:** the index is a backstop that should never fire; if it does, the `IntegrityError`
propagates (spec §2.2: a bug, not a user path). The guard does not reconcile or merge — the turn
loses whole (D8).

### Decision 9 — Ended drafts refuse every command, with the right code (AC4, C4, C5)

* `manage_proposal.py`: add `AppliedProposalError(ProposalCommandError)`. In **both**
  `revise_proposal` and `reject_proposal` the order becomes: resolve record → replay → **ended-state
  check** (`rejected` → `RejectedProposalError`, `applied` → `AppliedProposalError`) → scenario
  staleness (revise only) → expected resource version. The last-row rule stays with the existing
  `1 <= len(constraints)` check.
* `reject_proposal` (the planner's discard) writes `ended_by='planner'` through the adapter
  (Decision 3); allowed while stale, as today.
* `api/routers/proposals.py`: `RejectedProposalError` → `code="rejected_proposal"` (was
  `proposal_rejected`, C4); `AppliedProposalError` → 409 `code="applied_proposal"`, title "Draft was
  applied", detail "This draft was applied to the baseline and cannot be changed. Describe the
  change again to start a new draft."
* `create_run_snapshot.py`: `applied` → `SnapshotCreationError("applied_proposal", …)` beside the
  existing `rejected` branch. `enqueue_compute.py`: after the replay block and **before** the
  resource-version comparison, refuse `rejected`/`applied` with the same `SnapshotCreationError`
  codes (C5). `api/routers/schedule_runs.py` `_SNAPSHOT_PROBLEMS` gains `"applied_proposal": (409,
  "Draft was applied", "This draft was already applied to the baseline, so it cannot start a run.")`.
* Frontend copy maps both codes (Decision 14).

**Not covered:** an idempotent replay still returns the stored original result (spec §1); the card
then re-reads (Decision 14). Replays of `enqueue_compute` likewise return the stored run.

### Decision 10 — The promotion hook: last write in TX2 (AC4, F1, C3, C17)

* `promote_baseline(..., proposals: ProposalRepository, ...)` and `decide_approval(...,
  proposals, ...)` gain a **required** keyword (no default: a missing wiring must fail, not silently
  skip `applied`). `api/routers/approvals.py:412` passes the already-injected `proposals`.
  Update every test call site listed in C17 and the `test_promote_baseline.py` doubles.
* `proposals.mark_applied(connection, site_id=binding.site_id,
  schedule_version_id=binding.candidate_schedule_version_id)` is the **last write of TX2** — after
  the audit append and after the conversation activity / resume, on both initiator paths. That is
  "after the `site_baseline` CAS" (EAD-6 as amended) and keeps one lock order everywhere:
  conversation before proposal (C3). A comment states why it is last.
* Its return value is ignored for control flow (zero rows is normal); a raised error escapes like
  every other TX2 post-write fault (`promote_baseline.py:1-45`).
* Add the `"proposal"` node to `_TX2_FAULTS` in
  `tests/test_approval_audit_invariants_postgres.py` (`get_proposal_repository`,
  `PostgresProposalRepository`, `"mark_applied"`), and assert the seeded run's proposal is still
  `active` after the fault and `applied` with `applied_version_id` = the run's pinned version after
  the retry. That is verification obligation 6's "proposal" write.

**Not covered:** no backfill for earlier promotions; the approval's actor and time are still not
visible to the agent (spec §6's related open items).

### Decision 11 — Read model and API contract (spec §2.6–§2.7)

* `manage_proposal._view` takes the record and fills `version_ordinal`, `ended_by`,
  `applied_version_ordinal`; `get_proposal`, revise and reject results carry them. The replay path
  (`_replay_or_conflict`) keeps the **stored** view's three fields and recomputes only `stale`, as
  today (a replay answers "what did my command do").
* `api/schemas.py` `ProposalOut`: `state: Literal["active", "rejected", "applied"]`, plus
  `version_ordinal: int | None`, `ended_by: Literal["planner","assistant","system"] | None`,
  `applied_version_ordinal: int | None`. `_out` builds it from the view (not only
  `proposal.__dict__`).
* Regenerate: `cd frontend && npm run codegen` (runs `codegen:export` then `codegen:types`), and
  commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts`.

**Not covered:** `DraftActivityV1` and `DraftReferenceV1` are unchanged — the timeline gets version
and state from the proposal read, not the activity.

### Decision 12 — Workflow snapshot and instructions (spec §2.6, §4, C6)

**Snapshot** (`application/use_cases/conversation_workflow_context.py`):
* `working_draft`: `get_working(connection, conversation_id=claimed.conversation_id,
  for_update=False)` → `asdict(proposal) | {"version_ordinal": …}` or `None`. Read directly, so it
  is present even when its activities fell outside the 100-activity window.
* `drafts`: the ended drafts referenced in history (the working one excluded), each with `state`,
  `ended_by`, `version_ordinal`, and for `applied` an `applied_version: {version_ordinal,
  constraints, consequence_summary}` from `get_version(applied_version_id)`. The existing 10-draft
  cap and `drafts_truncated` apply to these.
* Runs keep `proposal_id` and `proposal_version` (already there, `ports/schedule_run.py:75-76`).

**Instructions** (`agent/scheduling_instructions.py`), per spec §4 with one correction:
* Replace **"Revising a draft"**, update **stage 2 "Draft (you)"**, add a discard rule and the
  routing line "Discarding the working draft on explicit request: scheduling_draft_discard, only.",
  add "Ended drafts are read-only facts … 'bring the old one back' means drafting its constraints
  again" and the "Undo" rule, and update step 2 of **"Saying what the baseline is now"** to describe
  the draft's `applied_version`, cross-checked against the run's `proposal_version`.
* **C6 correction:** do not tell the model to "word the reply" on a draft turn — the draft output
  *is* the reply, and the card shows the version. Say instead: when you mention the draft in a
  prose answer (after a discard, or when asked about it), use the reported outcome and version
  ("Discarded your draft (v3)", "Your working draft is v3"). Keep "After a successful
  scheduling_draft call, return the draft output citing the exact draft_id" verbatim.
* "Tool routing" is also in `DIRECT_INSTRUCTIONS` (`_DIRECT_SECTIONS`); both compose from the same
  section.

**Not covered:** no new prose channel on the draft output (`DraftProposalV1` is unchanged); whether
a real model follows the rules is Story 5.12's live proof.

### Decision 13 — Timeline: newest activity mounts the live card; edits survive the move (AC6, C7, C8)

In `ActivityTimeline.tsx`:
* Compute `currentDraftActivity: Map<proposal_id, activity_id>` exactly like
  `currentApprovalActivity`. The newest mounts `<DraftCard …>`; every older one renders one line:
  `Earlier version of this draft · {consequence_summary}` (spec §3.1).
* **Edit buffers live in `ActivityTimeline`**, keyed by `proposal_id`:
  `{ baseVersionId: string; rows: EditRow[] }`, passed to the live card with a setter. When the live
  card moves to a newer activity, the buffer — and the version it was made from — survives, so the
  card can show the changed-under-you notice instead of silently dropping edits.
* `agentTurnInFlight` prop: `ChatView` passes
  `["agent_queued", "agent_running"].includes(timeline.data.latest_agent_run_status ?? "")` (C7) to
  `ActivityTimeline`, which forwards it to the live card only.

**Not covered:** leaving the conversation (ChatView unmount) drops unsaved edits; a turn running in
*another* tab is not visible as in-flight here — the server guard still decides.

### Decision 14 — The Draft card (spec §3.2–§3.4, AC6, AC7, C9, C10)

**Header:** `CardTitle` keeps the literal "Draft — no baseline change"; a `Badge` beside it carries
the one state line:

| Proposal | Badge text (verbatim) | Controls |
|---|---|---|
| `active`, fresh | `Working draft · v{N}` (`Working draft` if `version_ordinal` is null) | full editor |
| `active`, `stale` | `Working draft · out of date` | inputs, Save, Run disabled with the existing stale explanation; **Discard** and **Refresh proposal** available |
| `rejected`, `ended_by='planner'` | `Discarded` | none |
| `rejected`, `ended_by='assistant'` | `Discarded by assistant` | none |
| `rejected`, `ended_by='system'` | `Replaced by a newer draft` | none |
| `applied` | `Applied to baseline — v{applied_version_ordinal} promoted` | none |

The badge node is the state's accessible text; ended states render the constraint list read-only
and **no** buttons. **An ended state wins over staleness**: the stale `role="status"` region (keep
its copy) renders for `active` drafts only, and the old "Draft is rejected" region is removed (the
badge replaces it). This deliberately changes `DraftCard.test.tsx:206` ("shows both notices when a
rejected proposal is also stale"): an ended draft offers no action for staleness to block. Keep the
identifiers `dl`, adding "Draft version" `v{N}`.

**Editor (fresh `active` only):** the "Constraint to revise" `Select` is removed. Each constraint
row shows its server description and, by kind: `set_min_workers_per_task` → one integer input
"Minimum workers"; `scale_demand` → one number input "Demand factor"; `set_max_hours` → one number
input "Maximum hours"; `lock_worker_shift` → integer inputs "Start minute" and "End minute";
`exclude_worker_from_task` → no input. Every row has a remove button whose accessible name includes
the row's description ("Remove {description}"); on the last remaining row it is disabled with the
visible hint "Discard the draft instead".

**Validation (C10)** mirrors `resolve.py`: `n` a whole number > 0; `factor` a finite number > 0;
`max_hours` a finite number > 0 and ≤ 56; `start_minute`, `end_minute` whole numbers with
`0 ≤ start < end ≤ horizon`, where `horizon` is `useScenarioOverview(proposal.scenario_id).data
?.horizon_minutes` (skip only the horizon bound while it is unavailable — the resolver stays the
authority). Each invalid input gets `aria-invalid` and an `aria-describedby` message (Accessibility
Floor: errors associated with affected controls).

**Buttons and literals (verbatim):**
* **Cancel** — enabled when the local rows differ from the server rows; resets them.
* **Save changes** — enabled when they differ **and** every input is valid; sends the full row list
  through the existing revise command. On success a polite live region announces `Saved as v{N}`.
* **Run optimization** — disabled while there are unsaved edits, explained as `Save or cancel your
  changes first` (plus today's reasons: stale, ended, command pending).
* **Discard draft** — first click reveals, inline, `Discard this draft? It can't be restored.` with
  **Discard** and **Keep** buttons; no browser dialog.
* **While `agentTurnInFlight`**: Save, Discard and Run disabled with `Wait for the assistant to
  finish`.
* **Changed under unsaved edits** (buffer `baseVersionId` ≠ server `proposal_version_id`): keep the
  local values visible, disable Save, and show `This draft changed to v{N}. Your edits were not
  saved.` with a **Load v{N}** button that replaces the buffer with the server rows.

**Error copy:** `CODE_MESSAGES` gains `applied_proposal` ("This draft was applied to the baseline,
so it cannot be changed or run. Describe the change again to start a new draft.") and keeps
`rejected_proposal`, now reachable from revise/discard (C4). UX-DR35: Save, Cancel, Discard,
Keep, Load and Run use distinct verbs and variants (`stateMatrix.test.tsx`'s signature rule).

**Query freshness (C9):** `useReviseProposal`/`useRejectProposal` `onSuccess` keep `setQueryData`
and then `invalidateQueries({ queryKey: proposalKey(id) })`; `useSendMessage`'s `finally` and
`useDecideApproval`'s `onSuccess` also invalidate the `["proposal"]` prefix.

**Not covered:** adding or retargeting rows, restore, diff, merging edits (deferred); the frontend
validation is a convenience — the resolver's error still surfaces through "Command not applied".

### Decision 15 — Golden cases and harness (AC3, F2, C11)

* `evals/golden/scheduling_draft_discard/`: `valid.json` (seeded working draft → discard → prose
  answer), `no-working-draft.json` (no seed → `no_working_draft` retry → prose answer),
  `after-draft-same-turn.json` (seeded → `scheduling_draft` → discard refused
  `draft_changed_this_turn` → draft output), `start-over-is-not-discard.json` (seeded; prompt "Start
  over with just …"; `expected_tool_calls` is `scheduling_draft` only; discard is **granted** and
  not called). All four carry `"capability": "scheduling_draft_discard"`, `"risk_class": "draft"`.
* `evals/report.py`: replace the one-name `EVAL_TAG_TO_CAPABILITY` with one declared mapping
  `EVAL_TAG_GRANTS: dict[str, tuple[str, ...]]` = `{"demonstration": ("shiftmind_demonstration",),
  "scheduling_draft_discard": ("scheduling_draft_discard", "scheduling_draft")}` (default: the tag
  itself), with a comment that the negative routing case is meaningless unless both tools are
  offered. Update its three users (`report.py:512`, `tests/test_evaluation_harness.py:735`,
  `tests/test_trace_export_failure_independence.py:217`).
* `evals/cases.py`: add optional `seeded_working_draft: bool = False` to `GoldenCase` and
  `CASE_FIELDS` (the `live_*` optional-field precedent). `_report_deps(sink, *,
  seeded_working_draft=False)` builds `DraftTurnState(lambda: WorkingDraftObservationV1(<fixed ids>,
  1, 1))` when set; `runtime_for_modules` passes the case's flag.
* `tests/test_evaluation_harness.py`: add `"scheduling_draft_discard"` to
  `MVP_PRODUCT_CAPABILITIES`.
* `evals/golden/scheduling_draft/*.json` change **only if** a case asserts the model view; the
  `draft_id` derivation is unchanged, so the pinned ids stay valid.
* Add a README paragraph for Story 5.11's four cases (the README records every contribution).

**Not covered:** golden cases are scripted conformance, not routing quality (README); a real model's
routing of "start over" is Story 5.12's live proof.

### Decision 16 — Where the deterministic proofs live (spec §5.1, C16)

The lifecycle and race proofs run against **real PostgreSQL** in a new
`backend/tests/test_draft_lifecycle_postgres.py` (marker `postgres`), driving the real tool
handlers with a real `DraftTurnState` reader and the real `finalize_agent_run` on real repositories.
A race is staged **sequentially and deterministically**: (1) the tool observes; (2) the competing
action commits (planner `revise_proposal`, planner `reject_proposal`, `mark_applied` via a real
promotion, or a second turn's finalize); (3) the first turn finalizes. Plus one **two-connection**
test for the lock itself (Task 13). Spec §5.1's "golden multi-turn case" is this file's five-turn
test, because the golden multi-turn harness persists nothing (C16).

**Not covered:** true thread-interleaving beyond the one two-connection lock test.

### Decision 17 — Docs, ledger, status

* `docs/CONFIGURATION.md`, `backend/.env.example` (Decision 6). No change to `docs/TESTING.md`'s
  live-scenario list (5.12's).
* `deferred-work.md`, a new "Deferred from: Story 5.11 creation (2026-09-30)" section: (a) C14 —
  `ProposalViewV1.stale` ignores baseline drift, so a working draft left baseline-stale by another
  conversation's promotion shows no stale state but is refused on Run; (b) C19 — undocumented
  `SCHEDULING_*_ENABLED` flags; (c) C15 — for Story 5.12: `behavioral_digest` does not hash
  instructions, so the proposal's stated reason for re-measuring A–D should be corrected there.
* Spec and proposal are **not** edited (they are planning records; this file carries the
  corrections). `sprint-status.yaml` moves past `ready-for-dev` only through `bmad-dev-story` /
  `bmad-code-review`.

**Not covered:** no evidence file, no live measurement (5.12).

---

## Tasks / Subtasks

Order follows the proposal's handoff (§5): migration and repository → finalize guard → capability
and instructions → promotion hook → contracts and codegen → card. Sub-phases, not separate stories
(proposal §3).

- [x] **Task 1 — Clean, re-verified baseline (all ACs)**
  - [x] Work on the session's designated development branch. Bring up PostgreSQL
        (`.claude/sandbox/docker-dev.sh` in a cloud session; see `.claude/sandbox/README.md`).
  - [x] Record: backend `cd backend && uv run --frozen pytest -q` (5.10 closed at 2367 passed, 1
        skipped, 10 deselected — re-measure, do not assume); frontend `npm run typecheck && npm run
        lint && npm test`. Record drift in the Dev Agent Record.
  - [x] Re-confirm C3 (lock order), C4 (`proposal_rejected` has no consumer) and C5 (check order)
        against the tree before relying on them.

- [x] **Task 2 — Migration and schema (AC1, AC5) — per Decision 1**
  - [x] `a8b9c0d1e2f3_one_working_draft_per_conversation.py`; mirror in `schema.py` (columns, both
        CHECKs, FK with `use_alter`, partial unique `Index`).
  - [x] Update `tests/test_proposal_persistence.py` column-set and CHECK assertions (lines 25-51).
  - [x] Migration tests (fresh DB, `fresh_postgres_database_url`): upgrade to `f7a8b9c0d1e2`, seed
        one conversation with three `active` drafts (two sharing `created_at`, broken by `id`) and a
        `rejected` one, upgrade to head → AC5's survivor, `rejected/system` for the rest,
        `ended_by='planner'` backfilled; the index refuses a second `active`; `command.check` clean;
        grants (`has_column_privilege` on both new columns); one-step downgrade to `f7a8b9c0d1e2`
        then upgrade again (the `test_approval_governance_postgres.py:762-812` shape), including an
        `applied` row that returns to `active`, and the ancestor `UPDATE (state, …)` grant surviving.

- [x] **Task 3 — Contracts and repositories (AC1, AC4) — per Decisions 2, 3**
  - [x] Contracts; `tests/test_proposal_contracts.py:54` state tuple; frozen/framework-free checks for
        the new contracts.
  - [x] Port methods and `PostgresProposalRepository` implementations; `reject` writes
        `ended_by='planner'`; `get_current` fields. `ConversationRepository.lock_conversation` and
        its adapter.
  - [x] Postgres tests: `get_working`; `append_agent_version` (ordinal, pointer, resource version,
        no idempotency row); `end_by_assistant`; `mark_applied` (applied + `applied_version_id` =
        the schedule version's pinned version; `False` on an ended draft).

- [x] **Task 4 — Per-turn draft state and `scheduling_draft` (AC1) — per Decisions 4, 5**
  - [x] `DraftTurnState`; `AgentDepsV1.draft_turn`; route wiring in `execute_agent_turn`.
  - [x] `scheduling_draft` created/updated; result and model-view fields; `SCOPE_CONTROLS`;
        `model_description`.
  - [x] Unit tests (`tests/test_scheduling_draft.py`): created and updated each record their
        observation; a second call in one turn observes the same state even when the reader would
        now answer differently; a call after a same-turn discard reports `created`; baseline pin is
        the tool-time overview value.

- [x] **Task 5 — Binding and the finalize guard (AC1, AC2) — per Decisions 7, 8**
  - [x] `execute_turn` bindings; `AgentRunOutcomeV1` fields; `activity_payload`.
  - [x] `finalize_agent_run` guard and its three call sites. Update
        `tests/test_proposal_persistence.py:74-127` (payload type) and, where a test's run
        finalizes a draft or a discard, the repository doubles in `tests/test_conversations_api.py`,
        `test_agent_approval_path.py`, `test_gate_a_mutation_audit.py`,
        `tests/architecture/test_model_outage_boundaries.py` (they now need
        `get_working`/`lock_conversation`).
  - [x] Unit tests with recording doubles: guard-not-run for non-draft turns (no lock call); call
        order lock → get_working → finish → proposal write; each table row; the failure payload's
        exact literals and `agent_failed`.

- [x] **Task 6 — The discard capability (AC3) — per Decision 6**
  - [x] Module, errors, manifest, install, settings flag + parse, `.env.example`,
        `docs/CONFIGURATION.md`, smoke case.
  - [x] Update `tests/architecture/test_execute_turn_boundaries.py:92-139` (the `all_on`/`all_off`
        settings and one flag-off case), `tests/test_settings.py`, and
        `tests/test_capability_conformance.py`'s per-capability table (`:58-70`, `:470`).
  - [x] Unit tests: refuses with no working draft; refuses after a same-turn draft; refuses a
        second discard; records the observation; the model view carries no proposal id.

- [x] **Task 7 — Snapshot and instructions (AC1, AC3, AC4) — per Decision 12**
  - [x] `conversation_workflow_context.py`; tests: `working_draft` present when its activities are
        outside the window; ended drafts carry `state`/`ended_by`; `applied_version` from the pinned
        version, not the latest.
  - [x] `scheduling_instructions.py` edits; keep every section header the composer reads
        (`_sections`, `_DIRECT_SECTIONS`).

- [x] **Task 8 — Ended-draft refusals (AC4) — per Decision 9**
  - [x] Use cases, router codes, `_SNAPSHOT_PROBLEMS`.
  - [x] Tests: revise/reject/run on `rejected` → `rejected_proposal`, on `applied` →
        `applied_proposal`, each 409 through the real route; on an applied **and** stale draft still
        `applied_proposal`; run with the pre-`applied` resource version still `applied_proposal`
        (C5); a revise replay after the draft became `applied` returns the stored original.
        Update `tests/test_create_run_snapshot.py:146` and `test_schedule_runs_api.py:667-669` if
        their tables need the new code.

- [x] **Task 9 — Promotion hook (AC4) — per Decision 10**
  - [x] `promote_baseline`/`decide_approval` signature; router; six call sites; doubles.
  - [x] `tests/test_promote_baseline.py`: `mark_applied` called last on both paths (recording
        double); not called when the consume or pointer CAS loses; a fault in it propagates.
  - [x] `_TX2_FAULTS["proposal"]` node with the two proposal-state assertions.
  - [x] Postgres: an already-ended (`rejected`) draft stays `rejected` through a promotion; a
        v2-promoted-then-edited-to-v3 draft reads `applied` with `applied_version_ordinal == 2`.

- [x] **Task 10 — API contract and codegen (AC4, AC7) — per Decision 11**
  - [x] `ProposalOut`, `_out`, `_view`; `npm run codegen`; commit `openapi.json` and `schema.d.ts`.

- [x] **Task 11 — Golden cases and harness (AC3) — per Decision 15**
  - [x] Four fixtures; `EVAL_TAG_GRANTS`; `seeded_working_draft`; floor set; README paragraph.
  - [x] `uv run --frozen pytest tests/test_evaluation_harness.py` green, including the NFR28 floor.

- [x] **Task 12 — Timeline and Draft card (AC6, AC7) — per Decisions 13, 14**
  - [x] `ActivityTimeline.tsx`, `ChatView.tsx`, `DraftCard.tsx`, the four hooks.
  - [x] `src/test/stateMatrix.tsx`: draft family states `fresh`, `stale` ("Working draft · out of
        date"), `discarded`, `discarded by assistant`, `replaced`, `applied`, `unsaved edits`,
        `changed under edits`, `in flight`, `discard confirming`; `EXPECTED_FAMILIES` unchanged.
  - [x] `DraftCard.test.tsx` / `ActivityTimeline.test.tsx`: rewrite the tests that name the removed
        controls ("Revise proposal", "Reject proposal", "Constraint to revise") and add the proof
        suite rows below.

- [x] **Task 13 — AC-level proofs (all ACs) — per Decision 16**
  - [x] `tests/test_draft_lifecycle_postgres.py`: the rows of *Proof suite minimum* marked Postgres.
  - [x] Route test: `execute_agent_turn` builds deps whose `draft_turn` reads through
        `get_working` (a recording proposal repository proves the reader is the route's, not the
        default).

- [x] **Task 14 — Close-out**
  - [x] Mutation table (below) in the Dev Agent Record, every row demonstrated red on finished code
        and restored.
  - [x] `deferred-work.md` per Decision 17. Full backend and frontend suites; record counts.
  - [x] Commit (no evidence commit — this story produces none).

---

## Dev Notes

### Traps — the quietest first

1. **Putting `mark_applied` right after the CAS** reads naturally from EAD-6 and creates a deadlock
   cycle with the finalize guard (C3). It is the last TX2 write.
2. **`draft_id` must stay the content hash** (C1). Switching it to `proposal_id` breaks the pinned
   golden `draft_id`s and `_draft_ids_this_run`'s rebinding.
3. **A `DraftTurnState` that re-reads on every call** makes two drafts in one turn observe
   different states. Memoize `observe()`.
4. **The composer's `isPending` is not "turn in flight"** (C7).
5. **The live card remounts** when a newer activity arrives (C8). Edits kept in the card's own
   `useState` vanish without the notice ever showing.
6. **Replayed bodies in the cache** (C9): `setQueryData` alone shows a replay's old state as
   current.
7. **The resource-version check before the state check** hides `applied_proposal` (C5).
8. **Migration data steps under FORCE RLS** (C13): they work because the local provisioning role is
   a superuser. Do not "fix" a zero-row data step by setting `app.site_id` in the migration — the
   fail-loud behaviour in Decision 1 is the design.
9. **`ProposalV1.state` in a version payload is always stale** (Decision 2). Read state from the
   row.
10. **The golden harness grants one module per tag** (C11). The start-over case is vacuous unless
    discard is *offered*.
11. **`factor` and `max_hours` are not integers** (C10).
12. **`decide_approval` defaulting `proposals=None`** would silently skip `applied` in any caller
    that forgot it. Required keyword.
13. **Never write Windows-CRLF** over tracked LF files; edit with the Edit tool.

### Files being modified — read these before editing

| File | What it does today | What changes | What must be preserved |
|---|---|---|---|
| `backend/adapters/postgres/schema.py` | `proposal` with 2-state CHECK (`:352-367`) | Decision 1 objects | every other table, name and index |
| `backend/application/contracts/proposal.py` | `ProposalStateV1`, `ProposalViewV1` | Decision 2 | `ProposalV1` fields and order (pinned, `test_proposal_contracts.py:40-46`) |
| `backend/application/contracts/agent_runtime.py` | `resolved_draft: ProposalV1` | Decision 2 | every other field |
| `backend/application/ports/proposal.py`, `adapters/postgres/proposal.py` | create/get/revise/reject | Decision 3 | existing method signatures; the outer-join invariant in `get_current` (`:67-87`) |
| `backend/application/ports/conversation.py`, `adapters/postgres/conversation.py` | turn and approval writes | `lock_conversation` | `finish_agent_run`'s lock and claimable checks |
| `backend/application/capabilities/deps.py` | trusted deps | `draft_turn` | every field and its comment |
| `backend/application/capabilities/scheduling_draft.py` | mints a proposal per call | Decision 5 | validation order, lock drain, error vocabulary, `derive_draft_id` |
| `backend/application/capabilities/installed.py` | six modules | + discard | the literal-tuple rule |
| `backend/settings.py` | flags | + discard flag | every other flag and default |
| `backend/application/use_cases/execute_turn.py` | binds draft citation | Decision 7 | grounding, shadow check, terminal copy, `rehydrate_history` |
| `backend/application/use_cases/finalize_agent_run.py` | create-draft bundle | Decision 8 | "finish first" ordering and the AD-22 translation |
| `backend/api/routers/conversations.py` | claim/execute/finalize | deps wiring, `discard=` | every error arm and telemetry emission |
| `backend/application/use_cases/manage_proposal.py` | revise/reject | Decision 9 order, `_view` fields | AD-8 operation/body-hash rules, replay staleness recompute |
| `backend/application/use_cases/create_run_snapshot.py`, `enqueue_compute.py` | run start | Decision 9 | idempotent replay path first; capacity check after validation |
| `backend/api/routers/proposals.py`, `schedule_runs.py` | problem maps | Decision 9 codes | every other code |
| `backend/application/use_cases/promote_baseline.py`, `decide_approval.py`, `api/routers/approvals.py` | TX2 | Decision 10 | the failure-mode table, raise-and-escape rule, audit fields |
| `backend/application/use_cases/conversation_workflow_context.py` | snapshot | Decision 12 | pin checks, 60 000-char bound, candidate/baseline previews |
| `backend/agent/scheduling_instructions.py` | master prompt | Decision 12 | every other section's text |
| `backend/api/schemas.py` | `ProposalOut` | Decision 11 | `ProposalRevisionIn`'s untrusted shape |
| `backend/evals/report.py`, `evals/cases.py` | harness | Decision 15 | fail-closed loader, grounding and policy evaluators |
| `frontend/src/features/chat/{ActivityTimeline,ChatView,DraftCard}.tsx`, hooks | timeline and card | Decisions 13, 14 | dedupe by `activity_id`, approval-panel rule, run acknowledgement tied to `run.variables`, most-recent-error rule, pending-state summary |

New files: `backend/migrations/versions/a8b9c0d1e2f3_one_working_draft_per_conversation.py`,
`backend/application/drafting/turn_state.py`,
`backend/application/capabilities/scheduling_draft_discard.py`,
`backend/evals/golden/scheduling_draft_discard/{valid,no-working-draft,after-draft-same-turn,start-over-is-not-discard}.json`,
`backend/tests/test_draft_lifecycle_postgres.py`, `backend/tests/test_scheduling_draft_discard.py`,
the migration test (in `test_draft_lifecycle_postgres.py` or its own file).

### Proof suite minimum

| AC | Proof | Where |
|---|---|---|
| AC1 | no working draft → v1 `active`; working draft → same `proposal_id`, ordinal N+1, full list replaced, `resource_version` +1, a new `DraftActivityV1` with the new version id | Postgres |
| AC1 | inserting a second `active` proposal for a conversation raises on `uq_proposal_one_active_per_conversation` | Postgres |
| AC1 | the five-turn lifecycle: draft → add → remove → discard → new request ⇒ exactly one `active`, the first `rejected/assistant`, ordinals 1,2,3 then 1 (spec §5.1, Decision 16) | Postgres |
| AC2 | card edit (`revise_proposal`) mid-turn → `updated` loses | Postgres |
| AC2 | card discard (`reject_proposal`) mid-turn → `updated` and `discard` each lose | Postgres |
| AC2 | promotion (`mark_applied`) mid-turn → `updated` and `discard` each lose | Postgres |
| AC2 | a second turn finalizes first → the first turn's `created` and `updated` each lose | Postgres |
| AC2 | for every loss: the persisted activity is `terminal_outcome` with reason `capability_error` and the exact detail and next step; `agent_run.status = agent_failed`; `proposal` rows and the `proposal_version` count unchanged | Postgres |
| AC2 | two connections: turn A holds its finalize transaction open; turn B's finalize blocks on the conversation lock; after A commits, B loses with the terminal outcome (never an `IntegrityError`) | Postgres |
| AC3 | agent discard → `rejected/assistant`; discard then draft in one turn → old `rejected/assistant`, new v1 `active`; draft then discard → discard refused (`draft_changed_this_turn`) and the draft applies | unit + Postgres |
| AC3 | four golden cases pass; NFR28 floor includes `scheduling_draft_discard`; flag off → not granted | harness, architecture |
| AC4 | promotion → `applied`, `applied_version_id` = pinned version; already `rejected` → unchanged; TX2 fault on `mark_applied` → `active` and baseline unmoved, retry → `applied` once | unit + Postgres |
| AC4 | revise / reject / run on ended drafts → the two codes, 409, through the routes; replay after `applied` → original result | API + Postgres |
| AC5 | migration upgrade/downgrade/upgrade on seeded duplicates (Task 2) | Postgres |
| AC6 | newest activity only mounts the card; history line literal; Save/Cancel enablement incl. invalid input; each validation bound; row removal; last-row guard + hint; Run disabled with unsaved edits + literal; in-flight disables Save/Discard/Run + literal; inline confirm; changed-under-you + Load vN keeps then drops edits; edits survive the card moving to a newer activity | Vitest |
| AC7 | each badge literal; ended states render no buttons; stale keeps Discard and Refresh; `stateMatrix` axe + role/name tree for every new state; `Saved as vN` and the changed notice in polite live regions | Vitest |

### Mutation table minimum (Task 14)

Each row: mutate finished code, run the named guard, record before/after, restore exact bytes.

| Mutation | Guard that must redden |
|---|---|
| migration omits the partial unique index | AC1 second-`active` test; migration test |
| collapse keeps the **oldest** (`ASC`) | AC5 survivor test |
| collapse ignores `id` as tie-breaker | AC5 equal-`created_at` test |
| `ended_by` backfill for `rejected` removed | migration test (and `ck_proposal_lifecycle` build) |
| guard skips the `resource_version` comparison | card-edit race |
| guard omits `lock_conversation` | two-connection test (turns into `IntegrityError`) |
| guard applies the draft when the check fails | every race row (rows changed) |
| `DraftTurnState.observe()` not memoized | second-call-same-observation unit |
| discard allowed after a same-turn draft | `after-draft-same-turn` case + unit |
| draft after discard reports `updated` | discard-then-draft unit + Postgres |
| `mark_applied` without `AND state = 'active'` | already-ended promotion test |
| `mark_applied` moved before the conversation write | call-order unit in `test_promote_baseline.py` |
| `mark_applied` call removed from TX2 | AC4 promotion test |
| `_TX2_FAULTS["proposal"]` node removed | (document as the matrix's own coverage row) |
| ended-state check moved after the resource-version check in `enqueue_compute` | run-with-old-version → `applied_proposal` test |
| proposals router code back to `proposal_rejected` | API code test |
| snapshot reads `working_draft` from history only | window test |
| `EVAL_TAG_GRANTS` drops `scheduling_draft` for the discard tag | start-over / after-draft cases |
| `seeded_working_draft` ignored | discard `valid` case |
| card: Save enabled with no diff; remove enabled on last row; Run enabled with unsaved edits; controls enabled in flight; live card on an older activity; edit buffer kept in `DraftCard` state; replay body not invalidated | the matching Vitest row |

### Testing requirements

* Backend from `backend/`: `uv run --frozen pytest -q`. Postgres tests carry `@pytest.mark.postgres`
  and need the local service. No live provider, no network; the default suite stays keyless (NFR26).
* Frontend from `frontend/`: `npm run typecheck`, `npm run lint`, `npm test`. `schema.d.ts` is
  generated, never hand-edited.
* New guards follow the demonstrated-red rule (`_bmad/custom/bmad-dev-story.toml`).

### Project structure notes

* `application/drafting/turn_state.py` sits beside `resolve.py`: both are drafting logic shared by
  two capabilities; it imports only contracts (the domain/application boundary is unchanged).
* The discard capability lives beside `scheduling_draft.py`; its golden cases under
  `evals/golden/scheduling_draft_discard/`, matching the per-capability directory rule.
* No new route: the planner discard keeps `POST /api/v1/proposals/{proposal_id}/rejection`.

### Previous-story intelligence

* **Story 5.10** (last in the epic) touched only live-eval publication; nothing here depends on it.
  Its lesson that carries over: measure against the real artifact (here, the real TX2 and real
  locks), never a double of it, for the claims the ACs make.
* **Story 4.5** built the TX2 fault matrix this story extends; its comment on `_TX2_FAULTS` explains
  why each initiator path is a node — `mark_applied` runs on both, so one node covers both only if
  the test seeds an agent-backed binding (the existing tuple's fourth element).
* **Story 4.2 review** (the source of three `persistent_facts`): tasks cite decisions; decisions
  state what they do not cover; a self-consistency pass was run over this file before freezing.
* **Story 3.1** shipped no supersede state deliberately; this story adds `applied`, not
  `superseded` (spec: a conversation is pinned, so drafts are stale together).

### Git intelligence

The last five commits are the draft-lifecycle planning (`7856bb2` spec, `2b7597b`/`94965a9`
revisions, `6384eda` proposal, `8a85f4f` artifact edits) on top of `ba8c706` (live eval per-turn
expectations, PR #44). No code has changed since `ba8c706`; the files this story edits were last
shaped by Stories 3.1 (proposals), 4.3/4.5 (TX2), 5.7 (instructions, runtime draft recovery) and
the chat-UI polish commits (`9421656`, `4ee535c`).

### Latest technical notes

No new dependency. SQLAlchemy partial indexes: `Index(name, col, unique=True,
postgresql_where=text("state = 'active'"))`; Alembic: `op.create_index(name, "proposal",
["conversation_id"], unique=True, postgresql_where=sa.text("state = 'active'"))`. TanStack Query v5:
an observer mounting on a stale cached query refetches (`refetchOnMount` default), which is why the
moved live card re-reads after an agent update; discard and promotion need the explicit
invalidations in Decision 14.

### References

* ACs — `_bmad-output/planning-artifacts/epics.md:1633-1677`
* Spec — `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` §1–§4, §5.1, §6
* Proposal §1.1 (F1, F2, F5), §2.2, §3, §5 — `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-30.md`
* AD-9 — `…/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:142`
* EAD-6 and obligation 6 — `…/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md:87-88,221`
* UX — `…/ux-ShiftMind-2026-07-22/EXPERIENCE.md:87,185-197`; `DESIGN.md:128`; `epics.md:194,226,246`
* Code anchors — see *What creation found* and *Files being modified*
* Domain model (cited per the standing rule; no metric touched) — `docs/DOMAIN-MODEL.md` §1–§3, §5

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5.5 (`claude-sonnet-5-5`).

### Debug Log References

- **Baseline (Task 1), measured on a clean checkout of `ee8c07f`:** backend 22 failed, 2684 passed, 2 skipped, 10 deselected. All 22 failures are `tests/test_evidence_convention.py` (11 x `test_every_recorded_commit_is_a_real_ancestor_that_touched_code`, 11 x `test_evidence_file_is_fully_bound`): the sandbox's git history lacks the recorded evidence commits (`git_commit e2ecdb62… is not a real commit object`). They are unrelated to this story and fail identically before and after. Drift from the story's "2367 passed" is large (the suite has grown since 5.10); nothing was assumed. Frontend: 90 files / 694 tests, typecheck clean, oxlint 3 warnings (pre-existing).
- **C3, C4, C5 re-confirmed** against the tree before relying on them: `finish_agent_run` locks conversation then agent run; nothing consumed `proposal_rejected`; `enqueue_compute` compared the resource version before the state check.
- **Route test order-dependence.** `test_every_ended_draft_command_answers_409...` passed alone and failed in the full run: another suite leaves `api.main`/`api.deps` such that a freshly imported `app` is not the one the fixture's `TestClient` serves, so a `dependency_overrides` entry was ignored and the real projection reader ran against an empty scenario. Reproduced with `tests/architecture tests/test_a*.py tests/test_c*.py tests/test_d*.py`; fixed by overriding on `client.app` with the router's own captured dependency. Two intermediate commits (`e57bdef`, `22b80c4`) carry the partial and final fix.
- `test_proposal_persistence.py`, `test_agent_runtime_adapter.py`, `test_conversations_postgres.py`, `test_execute_turn_use_case.py`, `test_scheduling_draft.py`, `test_capability_conformance.py`, `test_evidence_binding.py`, `test_turn_routing.py` (pinned prompt hash), the live inventory/smoke tests and `tests/compose_proof.py` were updated for the widened contracts; each is listed in the File List.

### Implementation Plan

Followed the story's task order and its seventeen decisions: migration and schema (D1); additive contracts (D2); repository and conversation-lock ports (D3); `DraftTurnState` wired through the execute route (D4); `scheduling_draft` resolving the working draft (D5); `scheduling_draft_discard` (D6); `execute_turn` bindings (D7); the finalize guard, lock order conversation then proposal (D8); ended-draft refusals with the ended check before the resource-version check (D9); `mark_applied` as TX2's last write (D10); read model and codegen (D11); snapshot and instructions (D12); timeline-owned edit buffers (D13); the rebuilt card (D14); golden cases and harness (D15); real-PostgreSQL proofs (D16); docs and ledger (D17).

### Completion Notes List

- Backend: full suite at close-out: 22 failed, 2773 passed, 2 skipped, 10 deselected (the 22 failures are the pre-existing evidence-convention tests; the clean-checkout baseline was 22 failed, 2684 passed). The only failures are the 22 pre-existing evidence-convention tests above. Frontend: 93 files, 764 tests, `npm run typecheck` clean, `npm run lint` at its 3 baseline warnings. `npm run codegen` regenerated `frontend/openapi.json` and `frontend/src/api/schema.d.ts`.
- **No live run, no provider spend, no evidence file, no change to runs, the solver, approval contracts, `PolicyInputsV1`, or the live-eval harness/baseline.** The four discard golden cases are `live_eligible: false` and the `discard-working-draft` smoke case is authored only (Story 5.12 owns live runs).
- **Deviations from the story text (all small, all in `deferred-work.md`):** (1) `scheduling_draft_discard`'s manifest also declares `draft_discard_failed`, its base error code, because the conformance suite requires the declared vocabulary to equal every code the module can raise. (2) `finalize_agent_run` receives `discard` only for an `agent_completed` turn (a completed-but-unusable turn ends `agent_failed` and applies nothing). (3) `tests/compose_proof.py` now ends an earlier working draft before creating a second one in the same conversation, mirroring discard-then-draft, because that proof drafts twice per conversation. (4) The `DraftCard` takes optional `buffer`/`onBufferChange`/`agentTurnInFlight` props; without them it keeps a local buffer so it still renders standalone. (5) UX-DR35: Cancel, Keep, Load and Refresh are all outline buttons, so each got a distinct border colour to satisfy `stateMatrix`'s merged-treatment rule.
- Resolved `Not covered` items are recorded rather than fixed: baseline-staleness of a working draft (C14), undocumented `SCHEDULING_*_ENABLED` flags (C19), `behavioral_digest` not hashing instructions (C15, for 5.12), no prose channel on a draft turn (C6).
- **The mutation table below found one weak guard.** `seeded_working_draft ignored` stayed green: the discard `valid` case only asserts routing, and a refused discard also calls the tool once. Fixed by `test_the_discard_cases_prove_the_seeded_working_draft_reaches_the_handler`, which asserts the trusted discard result; the mutation then reddens. Several rows were caught first by a unit test under `-x`; the Postgres-only re-runs at the end of the table show the named Postgres guards reddening on their own.

### Mutation table (Task 14)

Every mutation was applied to finished, committed code, the named guard run before (green) and after (red), and the file restored byte-for-byte; `git status` was clean after each. Harness: a scratch script driven from a JSON list of `(file, old, new, command)` rows, asserting green-before, red-after and a clean tree.

| Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|
| migration: partial unique index not created | migration test; AC1 second-`active` test | 3 passed | red (`test_the_partial_unique_index_and_lifecycle_check_are_enforced`) |
| migration: collapse keeps the oldest (`created_at ASC`) | `test_upgrade_collapses_duplicate_active_drafts...` | green | red |
| migration: collapse ignores `id` as tie-breaker | same test (two rows share `created_at`) | green | red |
| migration: `ended_by` backfill for `rejected` removed | same test (and the lifecycle CHECK build) | green | red |
| finalize guard skips the `resource_version` comparison | `test_updated_applies_only_if...` (unit) | 37 passed | red |
| same, Postgres card-edit race only | `test_a_card_edit_mid_turn_makes_the_turn_lose[update]` | 2 passed | red |
| finalize guard omits `lock_conversation` | `test_the_guard_orders_lock_then_working_read...` (unit) | 37 passed | red |
| same, Postgres two-connection test only | `test_the_conversation_lock_serializes_two_finalizes...` | 1 passed | red |
| guard applies the write when the check fails | `test_created_applies_only_when_there_is_no_working_draft` (unit) | 37 passed | red |
| same, Postgres race rows only | `test_a_card_edit_mid_turn_makes_the_turn_lose[update]` and the other race rows | 8 passed | red |
| `DraftTurnState.observe()` not memoized | `test_two_calls_in_one_turn_see_the_same_pre_turn_state...` | 23 passed | red |
| discard allowed after a same-turn draft | `test_it_refuses_after_a_same_turn_draft` | 189 passed | red |
| draft after a same-turn discard reports `updated` | discard-then-draft unit + Postgres | green | red |
| `mark_applied` without `AND state = 'active'` | already-`rejected` promotion test | green | red |
| `mark_applied` moved before the conversation write | `test_mark_applied_is_the_last_write_on_both_initiator_paths` | green | red |
| `mark_applied` call removed from TX2 | same test; AC4 promotion tests; TX2 `proposal` fault node | 18 passed | red |
| `mark_applied` fault swallowed (partial-bundle commit) | `test_a_fault_in_mark_applied_escapes...`; `_TX2_FAULTS["proposal"]` | 8 passed | red |
| ended-state check moved after the resource-version check in `enqueue_compute` | `test_an_ended_draft_is_refused_before_the_resource_version_comparison[applied-applied_proposal]` | 10 passed | red |
| proposals router code back to `proposal_rejected` | `test_every_ended_draft_command_answers_409...[rejected-rejected_proposal]` | 2 passed | red |
| snapshot `working_draft` not read from the repository | workflow-context tests | 26 passed | red |
| `EVAL_TAG_GRANTS` drops `scheduling_draft` for the discard tag | `test_all_version_controlled_golden_cases_pass_deterministically` | 152 passed | red |
| `seeded_working_draft` ignored | `test_the_discard_cases_prove_the_seeded_working_draft_reaches_the_handler` | **152 passed with the old guards (green: a finding), 1 passed with the new one** | red with the new guard |
| card: Save enabled with no diff | `DraftCard.test` (Save/Cancel enablement) | 41 passed | red |
| card: remove enabled on the last row | `DraftCard.test` (never removes the last row) | 41 passed | red |
| card: Run enabled with unsaved edits | `DraftCard.test` (Run optimization) | 41 passed | red |
| card: Run enabled while an agent turn is in flight | `DraftCard.test` (in flight) | 41 passed | red |
| card: Discard enabled while an agent turn is in flight | `DraftCard.test` (in flight) | 41 passed | red |
| timeline: live card on the OLDEST activity (first wins) | `ActivityTimelineDrafts.test` | 5 passed | red |
| card: edit buffer kept in `DraftCard` state | `ActivityTimelineDrafts.test` (edits survive the move) | 5 passed | red |
| `useReviseProposal`: replay body not re-read | `proposalCommandHooks.test` | 2 passed | red |
| `ChatView`: in-flight signal not passed | `ChatView.test` in-flight rows | green | red |
| validation: max-hours bound loosened to 100 | `draftEdits.test` / `DraftCard.test` | green | red |
| validation: `start < end` not enforced | `draftEdits.test` | 15 passed | red |
| card: stale notice shown on ended drafts | `DraftCard.test` (ended state wins over staleness) | 41 passed | red |
| `useSendMessage`: proposals not re-read after a turn | `useSendMessage.test` | 2 passed | red |
| `useDecideApproval`: proposals not re-read after promotion | `useDecideApproval.test` | 1 passed | red |
| `_TX2_FAULTS["proposal"]` node removed | **honest gap:** removing a matrix node just runs one fewer parametrized case, and nothing asserts the node count. The node's own coverage is proven through the two `mark_applied` rows above (call removed, fault swallowed), which redden its assertions. | n/a | n/a |

### File List

- `backend/.env.example`
- `backend/adapters/postgres/conversation.py`
- `backend/adapters/postgres/proposal.py`
- `backend/adapters/postgres/schema.py`
- `backend/agent/scheduling_instructions.py`
- `backend/api/routers/approvals.py`
- `backend/api/routers/conversations.py`
- `backend/api/routers/proposals.py`
- `backend/api/routers/schedule_runs.py`
- `backend/api/schemas.py`
- `backend/application/capabilities/deps.py`
- `backend/application/capabilities/installed.py`
- `backend/application/capabilities/scheduling_draft.py`
- `backend/application/capabilities/scheduling_draft_discard.py`
- `backend/application/contracts/agent_runtime.py`
- `backend/application/contracts/proposal.py`
- `backend/application/drafting/turn_state.py`
- `backend/application/ports/conversation.py`
- `backend/application/ports/proposal.py`
- `backend/application/use_cases/conversation_workflow_context.py`
- `backend/application/use_cases/create_run_snapshot.py`
- `backend/application/use_cases/decide_approval.py`
- `backend/application/use_cases/enqueue_compute.py`
- `backend/application/use_cases/execute_turn.py`
- `backend/application/use_cases/finalize_agent_run.py`
- `backend/application/use_cases/manage_proposal.py`
- `backend/application/use_cases/promote_baseline.py`
- `backend/evals/README.md`
- `backend/evals/cases.py`
- `backend/evals/golden/scheduling_draft_discard/after-draft-same-turn.json`
- `backend/evals/golden/scheduling_draft_discard/no-working-draft.json`
- `backend/evals/golden/scheduling_draft_discard/start-over-is-not-discard.json`
- `backend/evals/golden/scheduling_draft_discard/valid.json`
- `backend/evals/live_conversations/smoke_cases.py`
- `backend/evals/report.py`
- `backend/migrations/versions/a8b9c0d1e2f3_one_working_draft_per_conversation.py`
- `backend/settings.py`
- `backend/tests/architecture/test_execute_turn_boundaries.py`
- `backend/tests/architecture/test_telemetry_boundaries.py`
- `backend/tests/compose_proof.py`
- `backend/tests/test_agent_runtime_adapter.py`
- `backend/tests/test_approval_audit_invariants_postgres.py`
- `backend/tests/test_approval_governance_postgres.py`
- `backend/tests/test_capability_conformance.py`
- `backend/tests/test_conversation_workflow_context.py`
- `backend/tests/test_conversations_api.py`
- `backend/tests/test_conversations_postgres.py`
- `backend/tests/test_create_run_snapshot.py`
- `backend/tests/test_decide_approval.py`
- `backend/tests/test_draft_lifecycle_migration_postgres.py`
- `backend/tests/test_draft_lifecycle_postgres.py`
- `backend/tests/test_enqueue_compute.py`
- `backend/tests/test_evaluation_harness.py`
- `backend/tests/test_evidence_binding.py`
- `backend/tests/test_execute_turn_use_case.py`
- `backend/tests/test_finalize_agent_run_guard.py`
- `backend/tests/test_live_conversation_inventory.py`
- `backend/tests/test_live_conversation_smoke_cases.py`
- `backend/tests/test_promote_baseline.py`
- `backend/tests/test_proposal_contracts.py`
- `backend/tests/test_proposal_persistence.py`
- `backend/tests/test_schedule_runs_api.py`
- `backend/tests/test_scheduling_draft.py`
- `backend/tests/test_scheduling_draft_discard.py`
- `backend/tests/test_settings.py`
- `backend/tests/test_trace_export_failure_independence.py`
- `backend/tests/test_turn_routing.py`
- `docs/CONFIGURATION.md`
- `frontend/openapi.json`
- `frontend/src/api/schema.d.ts`
- `frontend/src/features/chat/ActivityTimeline.tsx`
- `frontend/src/features/chat/ActivityTimelineDrafts.test.tsx`
- `frontend/src/features/chat/ChatView.test.tsx`
- `frontend/src/features/chat/ChatView.tsx`
- `frontend/src/features/chat/DraftCard.test.tsx`
- `frontend/src/features/chat/DraftCard.tsx`
- `frontend/src/features/chat/draftEdits.test.ts`
- `frontend/src/features/chat/draftEdits.ts`
- `frontend/src/hooks/proposalCommandHooks.test.tsx`
- `frontend/src/hooks/useDecideApproval.test.tsx`
- `frontend/src/hooks/useDecideApproval.ts`
- `frontend/src/hooks/useRejectProposal.ts`
- `frontend/src/hooks/useReviseProposal.ts`
- `frontend/src/hooks/useSendMessage.test.tsx`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/test/PressOnMount.tsx`
- `frontend/src/test/accessibility-contract.test.tsx`
- `frontend/src/test/stateMatrix.tsx`

- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/5-11-keep-one-working-draft-per-conversation.md`

## Change Log

| Date | Change |
|---|---|
| 2026-09-30 | Story created by `bmad-create-story` from `sprint-change-proposal-2026-09-30.md` and the draft-lifecycle spec; 19 creation findings, 17 decisions. Status `ready-for-dev`. |
| 2026-09-30 | Implemented by `bmad-dev-story`: migration `a8b9c0d1e2f3`, contracts and repositories, `DraftTurnState`, `scheduling_draft` working-draft resolution, `scheduling_draft_discard` (flag, four golden cases, smoke case), finalize guard, ended-draft refusals, TX2 `mark_applied`, API/OpenAPI, snapshot and instructions, timeline-owned edit buffers and the rebuilt Draft card; real-PostgreSQL lifecycle and race proofs; 33-row mutation table (one weak guard found and fixed); deferred-work ledger. Status `review`. |
