---
baseline_commit: 0350f0648cb07d2760b1d8e2fb8df5991f3e6b58
---

# Story 4.2: Review and Decide the Exact Approval

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want a separate approval review that names the exact consequence and versions,
So that I cannot confuse running optimization with replacing the operational baseline.

**This story owns the epic's one decision endpoint and TX3 in full.** EAD-10 is explicit and is
the reason this story exists as a separate increment: *"there is exactly one decision endpoint.
**Story 4.2 owns it and implements TX3 in full** (reject, expire, stale — binding terminal,
`agent_cancelled(reason)`, audit, event) plus the review rendering. **Story 4.3 owns TX2 only**,
invoked as the approve branch of that same endpoint; it adds no second route and no second reject
path."

**It also closes the deadlock Story 4.1's review deferred to it.** `deferred-work.md:526` records
that an overdue-but-still-`pending` binding permanently blocks its agent run's pending slot *and*
the run's `uq_approval_request_pending_run` slot, while the pure read side renders the blocker as
"expired" and makes the blockage invisible. The ledger names this story as owner and states the
close: *"the decision-attempt transaction has to transition an overdue `pending` row to `expired`
so the slot is released, and a test must drive a second approval request for an agent run whose
first binding expired undecided."* Decision 7 is that close.

**Depends on, and consumes:** Story 4.1's entire substrate — the `d4e5f6a7b8c9` migration
(`approval_request`, `site_baseline`, `audit_event`, `agent_run.status_reason` plus their grants),
`ApprovalBindingV1`, `AuditEnvelopeV1`, `ApprovalRequestActivityV1`, `PostgresApprovalRepository`,
`PostgresAuditWriter`, `PostgresSiteBaselineReader`, `PolicyInputsV1` / `derive_policy_version`,
`api/routers/approvals.py`, `ApprovalRequestCard`, `useRunApprovals`; Story 3.1's
`command_idempotency` table and `lib/idempotency.ts`; Story 2.3's `conversation` / `agent_run` /
`persisted_event` tables and `PostgresConversationRepository`; Story 2.4's SSE replay and
`ActivityItemV1` stream; Story 1.2's `auth.resolve_session` and CSRF-guarded transport;
Story 1.6's shadcn/Radix primitives — including `components/ui/dialog.tsx`, which **exists and is
used by nothing yet**; this story is its first consumer.

**Unblocks:** Story 4.3 (TX2 lands as the approve branch of *this* story's endpoint, reusing
*this* story's revalidation function — it writes no route, no reject path, no second
revalidation), Story 4.4 (terminal bindings and decision audit rows to project provenance from),
Stories 4.5/4.6 (the terminal states, literal reasons, and dialog semantics their proofs assert).

**Scope summary:** **No migration.** One new use case (`decide_approval`, TX3 + the shared
revalidation fork + the approve entry point). One new POST route on the existing `approvals`
router. Two new `ConversationRepository` methods. Two new `ApprovalRepository` methods. Four new
fields on `ApprovalOut`, one on `TimelineOut`. Frontend: one new hook, one new dialog component,
the conversion of `ApprovalRequestCard` into a live decision panel, and the timeline's terminal
approval rendering. **No new dependency. No new setting. No evidence file** — see Task 10.

**This story is the first in the repository to:**

1. **transition an `approval_request` row out of `pending`.** Story 4.1's Completion Notes state
   plainly: *"`pending` is the only reachable stored state; `consumed`, `rejected`, `expired`,
   `stale` exist in the schema and the contract and are unreachable until 4.2/4.3."*
2. **write `agent_run.status_reason`.** The column and its CHECK
   (`ck_agent_run_status_reason`, `schema.py:309`) exist with no writer; the `GRANT UPDATE
   (status, status_reason)` that makes the write legal under RLS was landed by 4.1's migration
   precisely for this story.
3. **write a second `audit_event` outcome.** Only `approval_requested` rows exist today
   (4.1 Decision 10).
4. **render a modal dialog.** `frontend/src/components/ui/dialog.tsx` is shipped, exported, and
   imported nowhere. `EXPERIENCE.md:190` ("Dialogs trap focus, name their purpose, and return
   focus") has therefore never been exercised.
5. **use `Idempotency-Key` on a route that mutates an existing aggregate** rather than creating
   one.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| **There is exactly one decision endpoint. Story 4.2 owns it and implements TX3 in full (reject, expire, stale); Story 4.3 owns TX2 only, as that endpoint's approve branch, and adds no second route and no second reject path** | EAD-10 (`architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`); ADR-4 D7 |
| **Revalidation is one shared step with a fixed fork:** any *business* mismatch — candidate missing or no longer feasible, baseline version or absence mismatch, parameter or consequence hash mismatch, membership, policy version, or expiry — **terminalizes the binding to `stale`** (or `expired` where expiry is the cause) **and never retries**; only a **transactional or infrastructure write fault** rolls the bundle back, leaving the binding `pending` for an honest retry | EAD-10; ADR-4 D7 |
| **TX3 = terminal binding + `agent_cancelled(reason)` + audit + event, in one transaction.** Any failure rolls the whole bundle back. Repositories and adapters may not widen a bundle; only an application orchestrator crosses owners | EAD-6; AD-22 as amended 2026-08-27 (`ARCHITECTURE-SPINE.md:216-221`); AR22 (`epics.md:168`) |
| Rejected, expired, and stale are **terminal for the binding**, and the same transaction terminalizes the paused agent run as `agent_cancelled` with the matching literal reason from the **closed vocabulary** `approval_rejected \| approval_expired \| approval_stale`. `agent_run.status_reason` exists **so reconnect renders the literal outcome without replaying events**. No run may be left non-terminal once its binding is terminal | EAD-5; ADR-4 D5 |
| **This adds no general user-initiated `AgentRun` cancellation.** Approval outcomes are the only new path into `agent_cancelled` | EAD-5; ADR-4 D6 |
| **Every read path is pure.** A query, render, reconnect, or SSE replay that observes `now() >= expires_at` on a pending binding **presents it as expired, offers no decision control, and writes nothing**. The terminal `expired` state materialises **only inside a decision-attempt transaction** — an approve or reject command against an overdue binding **runs TX3 with reason `approval_expired` instead of its requested outcome**, and returns that literal result. No cron, no sweeper, no write-on-read | EAD-7; ADR-4 D7 |
| `ApprovalRequest` is the closed graph `pending --> {rejected, expired, stale, consumed}`; `AgentRun`'s `approval_required` has edges `--> agent_running: decision recorded` and `--> agent_cancelled: rejected or expired`. **No new states, no merged status types** | AD-7 (`architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:84-128`); AR7 (`epics.md:153`) |
| A setting **snapshotted into the binding at TX1** is immune and never bumps `policy_version`; only settings consulted at **TX2/TX3 revalidation** version the policy, enumerated in the frozen `PolicyInputsV1`. A bump makes pending bindings fail revalidation as `stale` — no baseline moves; the planner refreshes and re-requests | EAD-12; ADR-4 D9 |
| The consequence-summary **text is the literal snapshot persisted on the row at TX1**. **Story 4.2 renders it**; it is **not recomputed at render**, not read live from `ProposalV1.consequence_summary`, never model prose | EAD-11 |
| From Story 4.3 on, any comparison or **approval-review rendering** whose frozen `baseline_schedule_version` is non-null while the baseline assignment supply for that exact version is not authoritatively readable **must fail closed with a distinct outcome** — never render an empty read as "the baseline is empty". **This binds Story 4.2's consequence-summary rendering as much as 4.3's promotion** | EAD-8 |
| Successful mutation audit is unique on `(site_id, effect_key, outcome)`; non-success audit is unique on `(site_id, attempt_id)`. Each accepted attempt has a server-generated `attempt_id`; idempotent replay returns that attempt, a deliberate retry gets a new one. **Telemetry can never authorize, block, or substitute for audit** | AD-12 (`ARCHITECTURE-SPINE.md:154-158`); AR12 (`epics.md:158`) |
| EAD-6's audit-outcome vocabulary is closed: `approval_requested \| approval_consumed \| approval_rejected \| approval_expired \| approval_stale`, and `(site_id, effect_key, outcome)` uniqueness permits **"one request and one decision row per approval"** | EAD-6 |
| Each mutating HTTP command requires an idempotency key scoped to **actor, site, operation, and canonical body hash plus expected resource version**; a replay returns the original semantic result and a conflicting body fails | AD-8 (`ARCHITECTURE-SPINE.md:132-136`); AR8 (`epics.md:154`) |
| **Approval is never encoded as ordinary chat text nor inferred from rendering; TanStack Query cache is never authority for a decision.** The composer submits messages or explicit commands but never encodes approval as ordinary text | AD-14 *Server state has one client owner* (`architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`); AR14 (`epics.md:160`) |
| **No model output, browser value, or client approval flag grants authority**; the application owns identity, site scope, authorization, policy, risk, versions, approvals, idempotency, state transitions, persistence, and audit | AD-2 (`:54-58`); AR2 (`epics.md:147`) |
| Actor and site are **re-resolved from the server-side session inside the command transaction**; unauthorized targets receive the **non-disclosing not-found** shape | AD-3 (`:60-64`); AR3 (`epics.md:148`) |
| `stale`/`expired`/terminal-replay failures return **RFC 7807 problem details carrying literal expected/current context (binding state, versions)**; denied, stale, expired, and conflicting remain **distinct codes** | Epic 4 spine *Consistency Conventions* (Errors row); AD-13 (`:162-166`) |
| Approval lifecycle events ride the **conversation stream** anchored to the paused agent run (`stream_id = conversation_id`, `agent_run_id` set); **no new stream kind** | Epic 4 spine *Consistency Conventions* (Event stream row); Story 4.1 Decision 2 |
| **"Approve as baseline" stays distinct from "Run optimization" in language, control, consequence, and visual treatment**; no single "AI action" treatment spans authority levels | NFR19 (`epics.md:111`); UX-DR12 (`epics.md:200`); UX-DR35 (`epics.md:246`) |
| Approval requests are **bound visibly to exact candidate, baseline, material parameters, consequences, and versions**; approval is a **separate explicit control**, and stale/rejected/expired states **never resubmit** | UX-DR12 (`epics.md:200`) |
| Terminal outcomes expose **only valid next actions**; a non-promotable result **never shows an enabled Approve as baseline control** | UX-DR13 (`epics.md:202`) |
| **Dialogs trap focus, name their purpose, and return focus. Approval's primary action includes the consequence in its accessible name**, e.g. "Approve candidate `c14` as baseline replacing `b12`" | `EXPERIENCE.md:190` (Accessibility Floor) |
| Approval, status, run progress, reconnect and terminal state **use text rather than colour alone**; durable state transitions announce through a polite live region | `EXPERIENCE.md:189`; UX-DR32 (`epics.md:240`) |
| 44×44 CSS-px touch targets, no hover-only actions, **named dialogs, consequence-specific accessible approval names**, visible focus, reduced motion, 200% zoom and text-spacing support | UX-DR29 (`epics.md:234`); UX-DR27 (`epics.md:230`) |
| Manual assistive-technology verification is **out of scope**; automated coverage (axe-core, ARIA/semantic assertions, Playwright) is the **only accepted proof** | `EXPERIENCE.md:196` (Accessibility Floor) |
| The timeline renders approvals in **persisted order** and **deduplicates replay by event identity**; replay never duplicates an activity | UX-DR6 (`epics.md:188`); UX-DR23 (`epics.md:222`) |
| Every new guard must be **observed failing** with its structural assertion removed or a relevant mutation applied, before it is trusted | epic-3 retro §1 *Challenges*, §3 preparation task |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |

**`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments, and it constrains one
thing here: what the review surface may quote.** `outbound`/`inbound` demand is measured in
**volume**, `indirect` in **headcount**, and assignments carry worker identity but **no family**.
Story 4.1 Decision 5 fixed the consequence summary as identity-, version-, and count-only, and it
is **hashed** — this story **renders that stored text verbatim and adds no demand-derived number
of its own**. Do not re-derive the family/unit rule from adapter code; cite the document. A
demand-derived figure added to the review card would put this story inside the exact rule that
produced five of Story 2.7's nine decision-grade findings, *and* would change nothing that was
hashed, so the planner would be reading a number the binding does not cover.

---

## Acceptance Criteria

Verbatim from `epics.md:1169-1200`.

1. **Given** a current pending approval, **When** its Approval request renders in Chat or Results,
   **Then** it shows candidate, current baseline, material parameters, consequence summary,
   policy/expiry context, and versions before the separate Approve as baseline or Reject controls,
   **And** the accessible approval name states which candidate replaces which baseline.
   (FR18, UX-DR12, UX-DR29)

2. **Given** the planner closes the dialog, sends chat text, revisits the page, or reviews the
   draft/result, **When** no explicit authenticated decision is submitted, **Then** the approval
   remains pending and no baseline effect occurs, **And** approval is never encoded as ordinary
   text or inferred from rendering. (FR18, AR10, AR14)

3. **Given** the candidate, baseline, parameters, consequence hash, membership, policy, or expiry
   no longer matches, **When** the planner attempts approval, **Then** the request becomes stale or
   expired with literal expected/current context, the action is disabled/rejected, and no silent
   rebase or resubmission occurs, **And** the planner is offered only refresh, revise, rerun,
   inspect, or return actions that are currently valid. (FR18, UX-DR12, UX-DR13)

4. **Given** rejection, **When** the authenticated decision commits, **Then** the binding becomes
   terminal rejected, the agent run cancels/ends according to its closed graph, and the baseline
   remains unchanged, **And** replay returns the same semantic rejection. (AR7, AR10)

5. **Given** the approve, reject, and stale-approval flows, **When** they render alongside Send and
   Run optimization, **Then** Approve as baseline remains distinct from Run optimization in
   language, control, consequence, and visual treatment; stale actions are disabled; dialogs
   restore focus; and the accessible approval name states which candidate replaces which baseline,
   **And** these are proven by the automated accessibility suite established in Epic 1, without
   manual assistive-technology verification. (NFR18, NFR19, UX-DR12, UX-DR27, UX-DR35)

---

## Twelve decisions were made at story creation — do not re-litigate them

### Decision 1 — One route: `POST /api/v1/approvals/{approval_id}/decision`

EAD-10 fixes "exactly one decision endpoint". Put it on the **existing** `approvals` router
(`api/routers/approvals.py`) — the aggregate being mutated is the `ApprovalRequest`, which AD-22
gives to governance, and 4.1 already mounted that router.

Body: `{ "decision": Literal["approve","reject"], "expected_resource_version": int (ge=1) }`.
Header: `Idempotency-Key`, the exact `IdempotencyKey` annotation 4.1 and `schedule_runs.py:91-93`
already use (`min_length=1, max_length=40`).

`POST`, not `PATCH`/`PUT`: `api/main.py:251-256` sets `allow_methods=["GET", "POST"]`, so any other
unsafe method passes same-origin locally and fails CORS preflight in a deployed topology (Story 3.1
Decision 4, reaffirmed by 4.1 Decision 3).

`decision` is a **required closed literal**, never a boolean. A boolean `approved: bool` would make
the wire shape of "reject" a falsy default, and AD-2's whole point is that no client value grants
or withholds authority by omission.

**Rejected alternative — two routes (`/approve`, `/reject`).** EAD-10 forbids it by name: two
routes is the shape in which "4.2 and 4.3 both build competing reject paths, or each assumes the
other did".

### Decision 2 — One shared revalidation function, exported for Story 4.3

`application/use_cases/decide_approval.py` holds `revalidate_binding(...) -> RevalidationV1`, and
**Story 4.3 imports it** rather than writing a second one. It is the single implementation of
EAD-10's fork:

| Category | Checks | Outcome |
|---|---|---|
| **Expiry** | `clock() >= binding.expires_at` | terminalize `expired` (TX3), reason `approval_expired`. **Checked first** — EAD-7 says an overdue binding runs TX3 with `approval_expired` *instead of its requested outcome*, so expiry outranks every other verdict including a requested reject. |
| **Business mismatch** | candidate row still exists, is still `OPTIMAL`/`FEASIBLE`, still belongs to this site; `schedule_run.resource_version` unchanged since TX1; live `site_baseline` presentation equals `binding.baseline_schedule_version` **in both directions** (`null` matching absence); `baseline_resource_version` unchanged; the **initiating actor** named by `binding.initiated_by_actor_id` still has an active (`revoked_at IS NULL`) membership in `binding.site_id`, supplied by a server-owned membership reader in this command transaction; recomputed `parameter_hash` and `consequence_hash` equal the stored ones; `derive_policy_version(PolicyInputsV1(...))` equals `binding.policy_version` | terminalize `stale` (TX3), reason `approval_stale` |
| **Command-level refusal** | `binding.state != "pending"`; `expected_resource_version != binding.resource_version` | **no write at all** — 409 problem with literal expected/current. A caller who is simply out of date must not be able to kill a live binding. |
| **Valid** | none of the above | proceed to the requested decision |
| **Write fault** | any `DBAPIError` inside the bundle | let it propagate → the transaction rolls back → binding stays `pending` for an honest retry. **Never** convert a write fault into `stale`. |

The consequence hash is recomputed from the **stored** `consequence_summary`
(`contract_digest({"consequence_summary": binding.consequence_summary})` — the exact shape
`request_approval.py:128` hashed), so it detects storage tampering. It is **not** recomputed from
the candidate; EAD-11 forbids regenerating the text.

### Decision 3 — The approve branch's success path is deliberately unreachable in this story

4.2 must accept an *approve attempt* — AC3 requires an approve against a mismatched binding to
become stale/expired, and that is TX3, which is 4.2's. But TX2 is Story 4.3's by EAD-10, and
`site_baseline` has no writer until then.

So: when an **approve** attempt passes revalidation entirely, `decide_approval` raises
`BaselinePromotionNotAvailableError`, **writes nothing**, and leaves the binding `pending`. The
router maps it to `503` with stable code `promotion_not_available` and the literal detail
"Baseline promotion is not available yet." Story 4.3 replaces exactly that raise with TX2.

This is the shape Story 4.1 already established and had reviewed: its `scheduling_baseline`
handler "raises on **every** call, approved or not, with an explicit comment naming Story 4.3 as
the owner of the approved branch. Do not write a speculative promotion body." Do not write one
here either. Put the same named comment at the raise site.

`503`, not `501`/`409`: the condition is a *temporarily* absent server capability, it is not the
client's fault, and it must not be confused with the 409 family that means "your binding is no
longer valid". Story 4.3 deletes the code from `_ERROR_STATUS` in the same change that lands TX2.

### Decision 4 — TX3 writes one `success=True` audit row keyed on the binding's own effect key

`ck_audit_event_outcome` (`schema.py:520`) admits exactly the five EAD-6 outcomes; there is no
`denied` member and **this story adds no migration** (Decision 11), so a refused *attempt* cannot
be audited even if we wanted to. Therefore:

- **A committed TX3 writes one row**: `success=True`, `outcome ∈ {approval_rejected,
  approval_expired, approval_stale}`, `effect_key = binding.request_effect_key`,
  `decided_by_actor_id = <session principal>`, `initiated_by_actor_id =
  binding.initiated_by_actor_id`, `before_version = binding.baseline_schedule_version`,
  `after_version = None` (nothing moved), `attempt_id = uuid4()`, `safe_summary =
  binding.consequence_summary`.
- **Nothing else writes audit.** A command-level refusal (terminal binding, stale
  `expected_resource_version`, `promotion_not_available`) writes no row.

`success=True` for a rejection is deliberate and is what the shipped semantics already mean:
Story 4.1 writes `approval_requested` with `success=True` although no baseline moved. `success`
names *"the recorded consequential act completed"*, not *"the pointer moved"*. Reusing
`binding.request_effect_key` (unique per binding via `uq_approval_request_effect`) with the
outcome discriminator gives exactly EAD-6's "one request and one decision row per approval", and
makes a second decision row for the same binding-and-outcome **structurally impossible** under
`uq_audit_event_success_effect`. A freshly minted UUID here would repeat the defect 4.1's review
caught (*"Audit `effect_key` is a freshly minted `uuid4()`, so `uq_audit_event_success_effect` can
never collide"*).

The `(site_id, attempt_id)` non-success index stays **unused by this story**, exactly as 4.1's
`SCOPE_CONTROLS` declared (`audit:non_success_outcomes_owned_by_story_4_3`). Story 4.1's Open
Question 1 to Winston — *does the closed vocabulary need a denied member?* — is carried forward
unanswered, still owned by 4.3 whose AC4 names "denied" explicitly.

### Decision 5 — TX3's single event is an `approval_request` activity carrying the terminal state

EAD-6 fixes TX3 as four things, one of which is "event" — singular. The `approval_request`
discriminant already exists, already carries `approval_state`, is already rendered by
`ActivityTimeline`, and is already deduped by `activity_id` (UX-DR6). Reuse it: TX3 appends one
more `ApprovalRequestActivityV1` on the same conversation stream with
`approval_state ∈ {rejected, expired, stale}`.

**Do not add a `TerminalReasonV1` member and do not write a `terminal_outcome` activity for the
cancellation.** EAD-5 states the reason `agent_run.status_reason` exists at all: *"so reconnect
renders the literal outcome **without replaying events**"*. The run's cancellation is read from
the row, not from a second event. Adding `approval_rejected` to `TerminalReasonV1` would put the
same fact in two places with no rule for which wins, and would drag
`test_every_emittable_failure_reason_has_a_terminal_mapping` and the frontend's
`TERMINAL_LABELS` into a change they do not need.

Refactor `_append_approval_activity` (`adapters/postgres/conversation.py:60`) rather than copying
it: it is already parameterised by `binding` and `agent_run_id`, and `activity.approval_state`
already reads `binding.state`. It needs one change — `occurred_at` currently falls back to
`binding.created_at`, which on a decision event would stamp the decision with the *request's*
timestamp. Pass the decision time explicitly.

### Decision 6 — `cancel_agent_run_for_approval` is a new `ConversationRepository` method, guarded to `approval_required`

TX3's agent-run half goes through `ConversationRepository`, not a second adapter reaching into
`agent_run` (the rule 4.1 Task 7 set). Add
`cancel_agent_run_for_approval(connection, *, agent_run_id, binding, reason, request_id,
occurred_at)` **beside** `pause_agent_run_for_approval`:

- **Lock order is `conversation`, THEN `agent_run`** — the same order `finish_agent_run` and
  `pause_agent_run_for_approval` take. 4.1's review caught the ABBA deadlock from getting this
  backwards; do not reintroduce it.
- It guards `current.status == "approval_required"` (as `pause_...` guards `agent_running`) and
  raises `AgentRunNotQueuedError` otherwise.
- It writes `status="agent_cancelled", status_reason=<reason>` in one `UPDATE`, appends the
  Decision 5 activity, and bumps `conversation.resource_version` — the same sequence
  `pause_agent_run_for_approval` uses.
- **It is the only method that may write `status_reason`, and it accepts only the three closed
  reasons.** D6 forbids a general user-initiated `AgentRun` cancellation; this method must not
  become one. Add the comment saying so.

On the **planner-initiated** path `binding.agent_run_id` is `NULL` (no run was ever paused), so
TX3 appends the activity through `append_approval_request_activity` and touches no `agent_run` row.
Both initiator paths must be covered by tests — 4.1's review found the agent path had no
wiring-level test at all, and that is why its envelope defect shipped.

### Decision 7 — A presented-expired binding offers exactly one control: "Dismiss expired request"

This is the close for `deferred-work.md:526`. EAD-7 makes the terminal `expired` state
materialise *only* inside a decision-attempt transaction, and the pure read side offers no
approve/reject control — so with no control at all, an abandoned binding is unreachable forever,
blocking both `uq_approval_request_pending_agent_run` and `uq_approval_request_pending_run` and
parking the agent run in `approval_required` for good.

The presented-expired card therefore renders **one** control, **"Dismiss expired request"**, which
issues the ordinary decision command with `decision: "reject"` and receives the literal
`approval_expired` outcome — precisely the mechanism EAD-7 names ("an approve or reject command
against an overdue binding runs TX3 with reason `approval_expired` instead of its requested
outcome"). Its accessible name is *"Dismiss expired approval request {id}; the operational
baseline does not change."*

**This is the story's one interpretation of a spine sentence, and it is deliberate.** EAD-7's
"offers no decision control" is read as *no approve-or-reject-on-the-merits control* — a control
that records an expiry which is already true is not a decision about the candidate. Every other
reading leaves `:526` open, and `:526` names this story as the owner that must close it. Recorded
as Open Question 1 for Winston: overrule before Story 4.3 if this reading is wrong.

**Resolved Architecture Decision 2A (Winston, 2026-08-30) — membership means the initiating
actor's current membership in the bound site.** EAD-10 does not refer to the deciding actor and does
not impose separation of duties. The binding snapshots the server-owned identifiers
`initiated_by_actor_id` and `site_id` at TX1. The shared `revalidate_binding` imported by Story 4.3
must use those values with a server-owned transactional membership reader and require an active row
(`revoked_at IS NULL`) inside the command transaction. Absence is a business mismatch and takes TX3
as `stale` / `approval_stale`, with expected/current membership context and zero baseline effect.

The deciding actor remains a separate admission guard: `auth.resolve_session` INNER JOINs active
membership before the route runs. A revoked or wrong-site deciding actor receives the existing
authentication/non-disclosing refusal and performs no approval mutation; `revalidate_binding` must
not convert that denial into staleness. The current implementation does not yet supply the initiating
membership reader, so its `SCOPE_CONTROLS["membership"]` remains an honest implementation gap owned
by Story 4.3, not an open architecture question.

**Proof this actually closes it** — CORRECTED AT CODE REVIEW 2026-08-30. The ledger's own sentence
("a second approval request **for an agent run** whose first binding expired undecided") was written
before EAD-5's cancellation semantics existed and cannot hold: Decision 6 terminalizes that run to
`agent_cancelled`, and `pause_agent_run_for_approval` claims only `agent_running`. The agent-run
slot `uq_approval_request_pending_agent_run` guards is therefore released onto a run that is, by
design, finished — closed-as-designed, not closed-as-fixed. The slot that matters in production is
`uq_approval_request_pending_run` on `(site_id, schedule_run_id)`. So: drive TX1 for an
agent-run-backed binding, advance the injected clock past `expires_at`, dismiss, assert the run is
terminal `agent_cancelled('approval_expired')`, then **drive a real `request_approval` for the same
schedule run** — planner path, or a fresh agent run. Going through the use case is the point: it is
what exercises Trap 8's blocker. A test that only asserts the row went terminal, or that inserts the
second binding with `create_pending`, does not close `:526`.

### Decision 8 — Idempotency: `command_idempotency` for replay, the binding's own state for exactly-once

Two mechanisms, distinct jobs, both already in the repository:

- **`command_idempotency`** through the existing `get_idempotent_result` /
  `_store_idempotent_result` pair (declared on `ScheduleRunRepository`,
  `ports/schedule_run.py:274,299`), `operation = f"decide_approval:{approval_id}"`, following
  `enqueue_compute.py:126-146` and 4.1's route line for line. A replay returns the original
  response; a **different body under the same key** is `409 idempotency_key_conflict`. This is
  what makes AC4's "replay returns the same semantic rejection" true.
- **`binding.state != "pending"`** is the structural exactly-once guarantee. A *new* key against
  an already-terminal binding is not a replay — it is a second decision, and it is refused with
  `409 approval_not_pending` carrying literal expected/current context (`{"expected_state":
  "pending", "current_state": "rejected", "resource_version": 3}`) and writes nothing.

Follow 4.1's replay fix: **re-derive the presented state on replay** rather than returning the
payload frozen at decision time, so POST and GET never disagree about one binding.

### Decision 9 — Terminalizing outcomes are RETURNED, never raised, so the transaction commits

`get_site_context` (`api/deps.py:256-263`) yields a connection inside a `with` block: the request
handler **returning** commits; an exception propagating out **rolls back**.

So a stale/expired outcome — which *did* write a terminal binding, an audit row, an event, and
possibly a cancelled run — must come back from `decide_approval` as a **value**
(`DecisionResultV1(outcome="stale"|"expired"|"rejected", binding=..., ...)`), and the router must
**`return problem_response(...)`** for the refusing ones. Raising a typed error there would roll
back the very terminalization AC3 requires.

Only the **non-writing** refusals (`approval_not_pending`, `stale_resource_version`,
`promotion_not_available`, `approval_not_found`) may be raised — nothing was written, so a
rollback costs nothing. **This is the single most dangerous line in the story; Trap 1 restates it
and Task 10 requires a test that asserts the row is terminal after a 409 stale response.**

Status mapping (all RFC 7807, all with literal expected/current context in the problem body):

| Code | Status | Wrote anything? |
|---|---|---|
| `approval_not_found` | 404 | no |
| `approval_not_pending` | 409 | no |
| `stale_resource_version` | 409 | no |
| `promotion_not_available` | 503 | no |
| `approval_expired` | 409 | **yes — TX3 committed** |
| `approval_stale` | 409 | **yes — TX3 committed** |
| `approval_not_granted` | 403 | no |
| `idempotency_key_conflict` | 409 | no |
| `invalid_approval_command` | 422 | no |

A **rejection** is a `200` with the terminal `ApprovalOut` — the planner asked for it and got it.

### Decision 10 — Controls render from the **live binding**, never from the persisted activity payload

AD-14 forbids approval being "inferred from rendering", and Story 4.1 AC2 requires "only currently
valid decision controls". A replayed `approval_request` activity carries the state **at event
time**; driving a live Approve button off it would offer to approve a binding that has since been
rejected.

Therefore:

- New `ApprovalDecisionPanel` (`features/approvals/ApprovalDecisionPanel.tsx`) takes an
  `approvalId`, reads the current binding through a new `useApproval(approvalId)` hook over the
  **already-shipped** `GET /api/v1/approvals/{approval_id}`, renders `ApprovalRequestCard` for the
  facts, and renders controls **only** when the live state is `pending` and not overdue.
- `ScenarioResults` and `ActivityTimeline`'s `approval_request` case both render this panel.
- **The timeline's terminal events do not render a second panel.** When the activity payload's
  `approval_state` is not `pending`, render a compact literal line — "Approval rejected · {id}" —
  and nothing else. Otherwise TX3's event would duplicate the request's card in the timeline.
  **CORRECTED AT CODE REVIEW 2026-08-30: this mechanism only blocked one direction.** TX1's event
  keeps its `pending` payload forever, so after a decision it went on mounting a live panel —
  reading "Terminal approval state: rejected" — directly above TX3's compact line, which is the
  duplication this bullet exists to prevent. The condition is therefore **two** things: the panel
  renders only for the **newest** `approval_request` activity of that `approval_id` **and** only
  while that payload is `pending`; every superseded activity renders as the compact line. Dedupe
  stays keyed on `activity_id` (UX-DR6) — these are two genuinely distinct events, and collapsing
  them by `approval_id` would merge what the dedupe comment explicitly warns must stay separate.
- **Fail closed, exactly as `ScenarioResults` already does for `pendingApproval`:** while the live
  query is loading or errored, render **no** controls and say why. `!query.isSuccess` gates the
  controls; do not use `query.data?.state === "pending"` alone, which is `undefined`-falsy in a
  way that happens to work and will not survive an edit.

`ApprovalRequestCard` keeps its current props and gains **no** decision logic; the panel composes
it. Its existing tests must keep passing unchanged.

### Decision 11 — No migration, and the grants to prove it

EAD-1 gives every Epic 4 table to Story 4.1's single additive migration, and 4.1 landed the
column grants **for this story by name**: `GRANT UPDATE (state, decided_by_actor_id, decided_at,
consumed_at, resource_version) ON approval_request` and `GRANT UPDATE (status, status_reason) ON
agent_run TO shiftmind_runtime` (4.1 Task 2, whose own note reads *"Without this the Story 4.2
write fails at runtime with a permission error, not as a test failure"*).

**Verify this under `shiftmind_runtime` with a `@pytest.mark.postgres` test rather than by
reading the migration** — Trap 4 of Story 4.1 is exactly this failure mode, and the unit suite does
not run as that role. If a grant genuinely turns out to be missing, adding a *new* additive
migration is correct; **editing `d4e5f6a7b8c9` is not** (4.1 is merged and applied).

`ApprovalBindingV1` already carries `decided_at`, `consumed_at`, and `decided_by_actor_id` — TX3
sets `decided_at` and `decided_by_actor_id` and leaves `consumed_at` `NULL` (nothing was consumed;
that field is TX2's).

### Decision 12 — "Approve as baseline" is a dialog-confirmed primary; "Reject" is a dialog-confirmed outline; neither shares Send's or Run optimization's treatment

NFR19/UX-DR35 require visual and linguistic discontinuity across authority levels, and
`EXPERIENCE.md:190` requires the consequence in the accessible name. Fix it here so 4.6's state
matrix has something stable to assert:

- Inline on the panel: **"Approve as baseline"** (`variant="destructive"`, `min-h-11`) and
  **"Reject"** (`variant="outline"`, `min-h-11`). Both open the shared
  `ApprovalDecisionDialog`; neither mutates on the first click.
- The dialog is `components/ui/dialog.tsx` (Radix — focus trap, Escape, and focus return to the
  invoking trigger are the primitive's behaviour, not something to hand-roll). `DialogTitle` names
  the purpose: "Approve candidate as baseline" / "Reject approval request".
- The confirming button's accessible name carries the consequence verbatim:
  `Approve candidate {candidate_schedule_version_id} as baseline replacing {baseline_schedule_version}`,
  or `… replacing no current baseline` when it is `null`. The reject confirm reads
  `Reject approval request {approval_id}; the operational baseline does not change.`
- State is text, never colour alone (`EXPERIENCE.md:189`); the decision outcome announces once
  through a polite live region — follow `ActivityTimeline`'s `isLatest`-only `role="status"`
  pattern so a refetch does not re-announce history.
- **"Run optimization" and "Send" are not touched by this story.** The distinctness assertion is a
  *test* that renders them together, not a restyling.

---

## Tasks / Subtasks

- [x] **Task 1 — `decide_approval` use case: shared revalidation + TX3 (AC: 2, 3, 4)**
  - [x] `application/use_cases/decide_approval.py`. Errors mirror
        `request_approval.py`'s hierarchy: `DecideApprovalError(ValueError)` with `code`, and
        subclasses `ApprovalNotFoundError` (`approval_not_found`), `ApprovalNotPendingError`
        (`approval_not_pending`), `StaleResourceVersionError` (`stale_resource_version`),
        `ApprovalNotGrantedError` (`approval_not_granted`),
        `BaselinePromotionNotAvailableError` (`promotion_not_available`).
  - [x] `revalidate_binding(...) -> RevalidationV1` exactly per Decision 2's table, exported for
        Story 4.3. Put the fork's rule in the docstring, citing EAD-10.
  - [x] `DecisionResultV1` frozen dataclass: `outcome: Literal["rejected","expired","stale"]`,
        `binding: ApprovalBindingV1` (post-write state), `activity: ExecutedAgentRunV1 | None`,
        `expected: dict`, `current: dict` (the literal context AC3 requires).
  - [x] TX3 as **one** bundle in the caller's transaction, in this order: terminal binding update →
        `agent_cancelled(reason)` when `binding.agent_run_id` is not `None` → audit append → event
        append. No repository commits.
  - [x] Approve-and-valid raises `BaselinePromotionNotAvailableError` with the Story 4.3 comment
        (Decision 3). **Write no promotion body.**
  - [x] `SCOPE_CONTROLS` naming what this use case does not cover: `promotion:owned_by_story_4_3`,
        `audit:denied_attempts_owned_by_story_4_3`, `resume:deferred_tool_results_owned_by_story_4_3`.

- [x] **Task 2 — Repository surface (AC: 3, 4)**
  - [x] `application/ports/approval.py`: add `terminalize(connection, *, approval_id, site_id,
        state, decided_by_actor_id, decided_at, expected_resource_version) -> ApprovalBindingV1 |
        None` to `ApprovalRepository`. It is a **compare-and-set on `(id, site_id, state='pending',
        resource_version)`** returning the updated row, or `None` when it matched nothing — so two
        concurrent decisions cannot both terminalize. Ports stay SQL- and transport-free.
  - [x] `adapters/postgres/approval.py`: implement it with
        `update(...).where(...).returning(approval_request)`, bumping `resource_version`. Keep the
        explicit `site_id` predicate the class docstring promises.
  - [x] `application/ports/conversation.py` + `adapters/postgres/conversation.py`:
        `cancel_agent_run_for_approval` per Decision 6, with the lock-order comment.
  - [x] Give `_append_approval_activity` an explicit `occurred_at` parameter (Decision 5) and pass
        the decision clock from TX3; the request path keeps passing `binding.created_at`.

- [x] **Task 3 — Route wiring (AC: 1, 2, 3, 4)**
  - [x] `api/routers/approvals.py`: `POST "/{approval_id}/decision"`, `ApprovalDecisionIn`
        (`decision: Literal["approve","reject"]`, `expected_resource_version: int = Field(ge=1)`),
        `Idempotency-Key` header, the `enabled_feature_policy` pre-check 4.1's POST already does.
  - [x] Decision 9's return-vs-raise split, with the comment saying why. Extend `_ERROR_STATUS`
        with the new codes; add `503` to `_RESPONSES`.
  - [x] Problem bodies carry literal expected/current context (binding state, versions) — the Epic 4
        spine's Errors row. Never `str(exc)` (`schedule_runs.py:333-341`).
  - [x] Idempotency per Decision 8, re-deriving presented state on replay.
  - [x] Extend `ApprovalOut` with `agent_run_id: UUID | None` and `created_at` — AC2 of Story 4.1
        requires the agent-run identifier to stay visible, and `created_at` is the review surface's
        "requested at". Extend `_out` accordingly and RENDER both on `ApprovalRequestCard`; the
        presented-expired derivation is unchanged. **CORRECTED AT CODE REVIEW 2026-08-30:** this
        task originally also added `parameter_hash` and `consequence_hash` on the stated grounds
        that *"AC1 requires 'material parameters' … on the review surface"*. That rationale is
        wrong. AC1 asks the surface to show the material parameters **themselves** — the run,
        candidate and baseline versions, which the card already renders — not the digest sealing
        them; a planner does not verify a sha256 by eye. Both hashes were published into
        `openapi.json` and `schema.d.ts` and read by nothing, and provenance (Story 4.4) reads them
        from `audit_event`, which carries both. They are removed from `ApprovalOut`.
  - [x] `TimelineOut` / `ConversationTimelineV1` gain `latest_agent_run_status_reason: str | None`,
        sourced from `agent_run.status_reason`, so Chat renders the literal cancellation cause —
        EAD-5's stated purpose for the column.

- [x] **Task 4 — Gate A and docs (AC: 4)**
  - [x] Add `("POST", "/api/v1/approvals/{approval_id}/decision")` to
        `test_gate_a_mutation_audit.py`'s `versioned` literal — the guard that forces a human to
        record every new write path. **Note the literal is alphabetically ordered** (4.1's Debug
        Log records losing time to exactly this).
  - [x] Add its row to `docs/GATE-A-RUNBOOK.md`'s approved-write-path table, stating that it writes
        governance and evidence rows, may cancel an agent run, and **does not move the baseline
        pointer**.
  - [x] `docs/API.md`: the route, its body, and every problem code in Decision 9's table.
        No `docs/CONFIGURATION.md` change — this story adds no setting.

- [x] **Task 5 — Frontend data layer (AC: 1, 2, 3)**
  - [x] `npm run codegen` (export OpenAPI, regenerate `src/api/schema.d.ts`). **No hand-authored
        types.**
  - [x] `src/api/approvals.ts`: `getApproval(approvalId)` and `decideApproval(approvalId, body,
        idempotencyKey)`, same thrown-error shape as the existing wrappers.
  - [x] `src/hooks/useApproval.ts`: `approvalKey = (id) => ["approval", id]`.
  - [x] `src/hooks/useDecideApproval.ts`: mutation over `decideApproval`, reusing
        `createIdempotencyKeyHolder`. **Copy `useRequestApproval`'s settle rule verbatim** — settle
        on a server-answered failure (`getErrorStatus(error) !== undefined`), retain the key on a
        network failure. Invalidate `["approval", id]`, `["run-approvals"]`, and the conversation
        timeline key on settle.

- [x] **Task 6 — Review and decision UI (AC: 1, 2, 3, 5)**
  - [x] `features/approvals/ApprovalDecisionPanel.tsx` per Decision 10: live-binding-driven,
        fail-closed while loading or errored, composes the untouched `ApprovalRequestCard`.
  - [x] `features/approvals/ApprovalDecisionDialog.tsx` per Decision 12, on
        `components/ui/dialog.tsx`. Named title, consequence-bearing accessible name on the
        confirming action, `min-h-11` targets, no colour-only state.
  - [x] Presented-expired: no Approve/Reject; exactly one **"Dismiss expired request"** control
        (Decision 7) plus the literal "Refresh" already available on Results.
  - [x] Terminal states (`rejected`/`expired`/`stale`/`consumed`): no controls at all; render the
        literal state and, when the binding named an agent run, the cancellation reason. UX-DR13.
  - [x] Stale/expired **response** handling: render the returned expected/current context as
        literal text and offer only currently valid actions (refresh the comparison, rerun,
        inspect) — never an auto-resubmit. UX-DR12's "never resubmit" is a behaviour, not copy.
  - [x] `ScenarioResults.tsx`: render `ApprovalDecisionPanel` where it renders
        `ApprovalRequestCard` today; keep the existing `approvals.isError` fail-closed wiring.
  - [x] `ActivityTimeline.tsx`: the `approval_request` case renders the panel for a `pending`
        payload and the compact literal line otherwise (Decision 10). **Do not remove** the
        `activity_id` dedupe, the `isLatest`-only live region, or the unknown-discriminant runtime
        fallback.
  - [x] `ChatView.tsx`: render `latest_agent_run_status_reason` beside the `agent_cancelled` status
        word, mapped through an explicit `Record<string, string>` the way `RUN_STATUS_WORDS` is —
        never by stripping a prefix.

- [x] **Task 7 — Proof: use case and repository (AC: 2, 3, 4)**
  - [x] `backend/tests/test_decide_approval.py` (fake repositories): every revalidation fork arm —
        expiry outranking a requested reject; each business mismatch (candidate gone, candidate no
        longer feasible, run resource version moved, baseline moved, baseline appeared where
        absence was expected, baseline disappeared where a version was expected, parameter hash
        mismatch, consequence hash mismatch, policy version bumped) terminalizing to `stale`; a
        valid reject committing; a valid approve raising `BaselinePromotionNotAvailableError` with
        **no write**; a `DBAPIError` inside the bundle leaving the binding `pending` (**this is
        EAD-10's second fork arm and 4.5 proves it again — it must be distinctly proven here, not
        implied**).
  - [x] Both initiator paths: `agent_run_id` set → run cancelled with the matching `status_reason`;
        `agent_run_id` `NULL` → no `agent_run` write at all.
  - [x] `terminalize`'s compare-and-set returns `None` when the row is already terminal, and TX3
        writes nothing further in that case.

- [x] **Task 8 — Proof: router (AC: 1, 3, 4)**
  - [x] `backend/tests/test_approvals_api.py` (extend): every code in Decision 9's status table;
        idempotent replay returns the original semantic rejection; a changed body under one key is
        `409 idempotency_key_conflict`; a second decision on a terminal binding is
        `409 approval_not_pending` with literal expected/current; `promotion_not_available` is 503.
  - [x] **Decision 9's commit test**: a stale-outcome request returns 409 **and** a follow-up GET
        shows the binding terminal. Observe it red by converting the router's `return
        problem_response(...)` into a `raise`.
  - [x] Cross-site: a binding in another site is `404 approval_not_found`, never 403 (AD-3's
        non-disclosing shape).

- [x] **Task 9 — Proof: real PostgreSQL (AC: 3, 4)**
  - [x] `backend/tests/test_approval_governance_postgres.py` (extend, `@pytest.mark.postgres`):
        TX3 end-to-end through the real `Postgres*` adapters on both initiator paths — binding
        terminal, `agent_run.status='agent_cancelled'` with the matching `status_reason` accepted by
        `ck_agent_run_status_reason`, one `audit_event` row, one `persisted_event`.
  - [x] **Decision 11's grant proof**: run the TX3 writes as `shiftmind_runtime` and assert they
        succeed; assert `has_table_privilege` for `UPDATE (status_reason)` on `agent_run` and
        `UPDATE (state)` on `approval_request`. Observe red by revoking in a rolled-back
        transaction.
  - [x] `uq_audit_event_success_effect` refuses a second `(site_id, effect_key,
        'approval_rejected')` row while still admitting the story-4.1 `approval_requested` row for
        the same effect key — this is what proves the outcome discriminator is doing work.
  - [x] **Decision 7's ledger close** — CORRECTED AT CODE REVIEW 2026-08-30. As first written this
        task demanded a second approval request **for the same agent run**, which Decision 6 makes
        unreachable: TX3 terminalizes that run to `agent_cancelled`, and
        `pause_agent_run_for_approval` claims only `agent_running`. The two statements contradicted
        each other and the implementation satisfied the letter by inserting the second binding with
        `create_pending`, bypassing `request_approval` entirely. The real close: expire an
        agent-run-backed binding by clock, dismiss it, assert the run is terminal
        `agent_cancelled('approval_expired')`, then **drive a real `request_approval` for the same
        schedule run on the planner path**. That releases and refills
        `uq_approval_request_pending_run` — the slot that matters in production — and it is what
        exercises Trap 8's blocker (`ApprovalAlreadyPendingError` counts overdue rows,
        `request_approval.py`). A test that stops at "the row is terminal", or that inserts the
        second binding directly, does not close `deferred-work.md:526`.

- [x] **Task 10 — Proof: frontend and accessibility (AC: 1, 2, 5)**
  - [x] Vitest: panel states (pending with controls; loading and errored with **no** controls;
        presented-expired with only Dismiss; each terminal state with no controls); the dialog's
        accessible name for both a named baseline and `null`; Escape and Cancel leave the binding
        untouched (AC2) and **return focus to the invoking control** (AC5); a stale 409 renders the
        expected/current context and does not resubmit; timeline dedupe still holds and a terminal
        payload renders the compact line, not a second panel.
  - [x] `src/test/accessibility-contract.test.tsx`: extend with the decision surface — text-not-
        colour state, 44px targets, named dialog.
  - [x] **NFR19/UX-DR35 distinctness test**: render Send, Run optimization, and Approve as baseline
        in one tree and assert their accessible names, roles, and variant classes differ. This is
        the assertion 4.6's matrix inherits.
  - [x] `frontend/e2e/`: extend the existing accessibility/journey specs (`accessibility.spec.ts`,
        `repair-journey-accessibility.spec.ts`) with the dialog open/close/focus-return path at
        100% and 200% zoom with reduced motion. Automated only — `EXPERIENCE.md:196`.
  - [x] **Every new guard gets a demonstrated-red note in the Debug Log** naming the mutation that
        made it fail. A guard with no recorded red is not evidence (retro §1).
  - [x] Full suites before hand-off: `uv run pytest`, `uv run pytest -m postgres`,
        `uv run alembic check`, `npm test`, `npx tsc -b`, `npm run lint`, `npm run test:e2e`.
        **Run `npx tsc -b`, not only `npm run typecheck`** — 4.1 recorded that the root
        `tsconfig.json` declares `"files": []`, so bare `tsc --noEmit` is effectively a no-op.
  - [x] **No evidence file.** No AC here carries a measured threshold;
        `docs/EVIDENCE-CONVENTION.md` exists to stop unmeasured files being written. Stories
        4.5/4.6 own Epic 4's evidence.

- [x] **Task 11 — Ledger reconciliation (retro §3)**
  - [x] Close `deferred-work.md:526` with Decision 7's mechanism **and** the second-request test as
        the evidence. Do not close it on the terminalization alone.
  - [x] Update `deferred-work.md:300`: the decision endpoint lands here; **`DeferredToolResults` on
        the request path does not** — it is only reachable on approve, so it moves to Story 4.3.
        The entry's closure text currently lumps them together.
  - [x] Leave `deferred-work.md:486` (comparison staleness vacuously false) **open** — still no
        pointer writer.
  - [x] Record the EAD-9 supplier entry for this story's one new guard: revalidation's decide-time
        policy input, whose real supplier is `Settings.scheduling_baseline_enabled` via
        `PolicyInputsV1` / `derive_policy_version` — not a seeded stand-in.
  - [x] Record the new deferred item this story creates: **`AgentApprovalDecisionV1(approved=False)`
        has no producer.** EAD-5 cancels the run on rejection instead of resuming it with a denial,
        so the contract's denial branch stays unused. Owner: whoever needs a denied-and-resumed
        turn, if ever.

### Review Findings

Code review 2026-08-30 (`/bmad-code-review 4.2`), three adversarial layers against
`0350f06..92ad4f7`. 4 decision-needed, 24 patch, 3 deferred, 3 dismissed as noise. All resolved 2026-08-30; two further items were found while patching and are recorded in `deferred-work.md` (the missing `approval_request` SSE listener, fixed; and a pre-existing Results-page contrast violation, deferred).

**Decision-needed — RESOLVED 2026-08-30.** D1 → (a) re-drive the proof through `request_approval` and correct the spec/ledger wording. D2 → (b) pin the deciding-actor reading, enforce at the session layer, raise Open Question 2 for Winston. D3 → (a) render `created_at`, remove both hashes from `ApprovalOut`, correct the Task 3 rationale. D4 → (a) panel only for the newest activity of an approval, dedupe still keyed on `activity_id`.

- [x] [Review][Decision] `deferred-work.md:526` is marked CLOSED on a proof production cannot reproduce, and the deadlock persists on the agent path — TX3 sets the run to `agent_cancelled`, but `pause_agent_run_for_approval` claims only `agent_running` (`adapters/postgres/conversation.py:97`), so no second approval can ever be created for that agent run in production. `test_dismissing_expiry_releases_the_agent_pending_slot_for_a_second_request` manufactures the second binding with `PostgresApprovalRepository().create_pending(...)` directly, bypassing `request_approval` — so Trap 8's blocker (`ApprovalAlreadyPendingError` counts overdue rows, `request_approval.py:107-109`) is never exercised. Options: (a) re-drive the proof through `request_approval` for a NEW agent run on the same schedule run, (b) narrow the ledger claim to the `uq_approval_request_pending_run` slot only, (c) reopen `:526`.
- [x] [Review][Decision] `revalidate_binding` omits the membership check Decision 2 and AC3 enumerate [`backend/application/use_cases/decide_approval.py:61-79`] — `get_session` (`api/deps.py:196`) re-resolves membership per request and returns 401/403 first, which is defensible under AD-3, but that is a DIFFERENT outcome from the `stale` terminalization AC3 names. Story 4.3 imports this function verbatim and inherits the gap. Options: (a) add the membership arm to `revalidate_binding`, (b) record session-level resolution as satisfying AC3 and amend Decision 2.
- [x] [Review][Decision] AC1's "material parameters" are transported but rendered nowhere — Task 3 added `parameter_hash`, `consequence_hash`, `created_at` to `ApprovalOut`/`openapi.json`/`schema.d.ts` explicitly because "AC1 requires 'material parameters' and versions on the review surface", but `ApprovalRequestCard.tsx` is unchanged and renders none of them, and `ApprovalDecisionDialog` renders only `consequence_summary`. Options: (a) render them on the card, (b) accept the existing version fields as AC1's "material parameters" and drop the Task 3 justification.
- [x] [Review][Decision] After any decision the timeline renders the same approval twice — TX1's `pending` event still mounts a full `ApprovalDecisionPanel` (now showing "Terminal approval state: rejected") directly above TX3's "Approval rejected · {id}" line, because dedup is keyed on `activity_id` and TX3 mints a fresh one [`frontend/src/features/chat/ActivityTimeline.tsx:303-306`, `:338`]. Decision 10's stated intent ("Otherwise TX3's event would duplicate the request's card") is only half met. Options: (a) dedup by `approval_id` keeping the newest, (b) render the panel only for the newest approval activity, (c) accept — the duplication is a line, not a second card.

**Patch — unambiguous fixes**

- [x] [Review][Patch] A successful dismissal and the by-design 503 both render "The approval changed. Refresh, rerun, or inspect…" — the single undifferentiated `mutation.isError` branch never discriminates on status/code, so `409 approval_expired` (the dismissal succeeding, per EAD-7) and `503 promotion_not_available` (every valid approve) both tell the planner the opposite of what happened [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:22`]
- [x] [Review][Patch] `Expected: {}` / `Current: {}` render as literal noise — `DecideApprovalError` defaults both to `{}` and the router always passes them; `{}` is truthy in JS so the guard never suppresses them [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:22`, `backend/application/use_cases/decide_approval.py:30-33`]
- [x] [Review][Patch] `AgentRunNotQueuedError` / `RuntimeError` from `cancel_agent_run_for_approval` escape the route as HTTP 500 and roll back a compare-and-set that already won, re-blocking the slot — the route catches only `DecideApprovalError` [`backend/api/routers/approvals.py`, `backend/adapters/postgres/conversation.py:110-111`]
- [x] [Review][Patch] Decision 3's mandated literal detail "Baseline promotion is not available yet." is never emitted — every `DecideApprovalError` gets `detail="The approval is no longer valid for this decision."`, which is factually wrong for `promotion_not_available` (the approval IS valid) and for `approval_not_granted` [`backend/api/routers/approvals.py:115-116`]
- [x] [Review][Patch] Decision 9's commit guard proves nothing — `test_decision_stale_response_returns_409_after_the_terminal_write` monkeypatches `approvals_router.decide_approval`, overrides `get_site_context` to `lambda: object()` (no transaction), and asserts on an in-memory fake with no follow-up GET; Task 8 required "a follow-up GET shows the binding terminal" [`backend/tests/test_approvals_api.py:161`, `:197-209`]
- [x] [Review][Patch] The `DBAPIError` fork arm is proven at the weakest point — the fault is injected into `terminalize`, the bundle's FIRST statement, before any write; nothing faults at the audit or event append, which is exactly where a "convert a write fault into stale" bug would live [`backend/tests/test_decide_approval.py`]
- [x] [Review][Patch] `approval_expired` (409) and `invalid_approval_command` (422) have no router test, though Task 8 required every code in Decision 9's table — `approval_expired` is the code Decision 7's entire mechanism returns [`backend/tests/test_approvals_api.py`]
- [x] [Review][Patch] `ActivityTimeline.test.tsx` mocks `ApprovalDecisionPanel` with a stub hardcoding `State: pending` / `No current baseline` — the exact two strings the surviving assertion checks, so it now tests the mock's literals; and Task 10's terminal-line test was never written despite the task being checked [`frontend/src/features/chat/ActivityTimeline.test.tsx:4-6`, `:160-164`]
- [x] [Review][Patch] The NFR19/UX-DR35 distinctness test is self-fulfilling — it renders synthetic Send and Run optimization buttons whose variants the test itself picks, then asserts only that three `data-variant` values differ; real components, accessible names, and roles are never involved, and Story 4.6 inherits this [`frontend/src/features/approvals/ApprovalDecisionPanel.test.tsx`]
- [x] [Review][Patch] Keyboard focus lands on `<body>` after a confirmed decision — the panel flips to its terminal branch, unmounting the trigger, and `onCloseAutoFocus` is `preventDefault`ed onto a detached node; two overlapping bare `setTimeout` focus calls compound it. Escape and Cancel are tested; confirm is not [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:13,16-21`, `ApprovalDecisionDialog.tsx:7`]
- [x] [Review][Patch] No polite live region announces the decision outcome — the only `role="status"` is on the error branch; the success path renders a plain paragraph, so the durable pending→rejected transition is silent to a screen reader (Decision 12, `EXPERIENCE.md:189`, UX-DR32) [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:22`]
- [x] [Review][Patch] "Dismiss expired request" has no `disabled={mutation.isPending}` and no confirmation — two clicks issue two mutations sharing one unsettled idempotency key [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:22`]
- [x] [Review][Patch] One `createIdempotencyKeyHolder` per panel is shared across approve / reject / dismiss — a transport failure deliberately retains the key, so the next DIFFERENT decision reuses it and gets `409 idempotency_key_conflict`; the key identifies a component instance, not an intent [`frontend/src/hooks/useDecideApproval.ts:8-9`]
- [x] [Review][Patch] `useApproval` is never invalidated by the conversation stream — a decision made in another session leaves live Approve/Reject controls on a stale binding, against UX-DR13 [`frontend/src/hooks/useApproval.ts`, `frontend/src/hooks/useDecideApproval.ts`]
- [x] [Review][Patch] `presentedExpired` is computed from `new Date()` once per render with no timer and no refetch policy — crossing `expires_at` while the panel is mounted keeps offering Approve/Reject [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:12`, `frontend/src/hooks/useApproval.ts`]
- [x] [Review][Patch] A closing reject dialog momentarily re-renders as the approve dialog — `decision ?? "approve"` and `open={decision !== null}` flip in the same commit while Radix keeps `DialogContent` mounted through the exit [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:22`, `ApprovalDecisionDialog.tsx:5-7`]
- [x] [Review][Patch] `cancel_agent_run_for_approval` takes `reason: str` unvalidated — Decision 6 says it accepts only the three closed reasons, and Trap 3 warns any other literal is a runtime `ck_agent_run_status_reason` failure, not a test failure; the comment is present, the mechanism is not [`backend/adapters/postgres/conversation.py:103-112`]
- [x] [Review][Patch] `_append_approval_activity` reports `agent_run_status="approval_required"` for a run TX3 just set to `agent_cancelled` — latent today because the router discards `result.activity`, but `DecisionResultV1.activity` is the shared surface Story 4.3 imports [`backend/adapters/postgres/conversation.py:87`, `backend/application/use_cases/decide_approval.py:105`]
- [x] [Review][Patch] `expected` / `current` are injected at runtime but absent from the published contract — `ProblemDetailsV1`, `openapi.json`, `schema.d.ts` and the new `docs/API.md` rows declare none of it, so the panel reads them through an unchecked cast; and `body.update(extra)` runs after the reserved members, so a caller passing `type`/`title`/`status`/`code` silently corrupts the problem document [`backend/api/problems.py:13-19`, `backend/api/schemas.py`]
- [x] [Review][Patch] Decision 10's mandated `!query.isSuccess` gate was not used — the panel gates on `query.isPending` then `query.isError || !query.data`, the exact falsy shape Decision 10 named and forbade; `isSuccess` is never exercised by the panel test [`frontend/src/features/approvals/ApprovalDecisionPanel.tsx:10-11`]
- [x] [Review][Patch] `ChatView`'s `CANCELLATION_REASONS` rendering has no test, and the raw-value fallback would ship a wire literal unnoticed [`frontend/src/features/chat/ChatView.tsx:42-46,273-275`]
- [x] [Review][Patch] `accessibility.spec.ts` was not extended though Task 10 named both specs — only `repair-journey-accessibility.spec.ts` changed. (The 1280/640 viewport pair IS a legitimate 200%-zoom proxy, matching `layout-accessibility.spec.ts:85`.) [`frontend/e2e/accessibility.spec.ts`]
- [x] [Review][Patch] `503` is published on `POST /api/v1/approvals` and both GET routes via the shared `_RESPONSES`, none of which can emit it [`backend/api/routers/approvals.py:24`, `frontend/openapi.json`]
- [x] [Review][Patch] Missing blank line between `cancel_agent_run_for_approval` and `latest_terminal_outcome_for_site` [`backend/adapters/postgres/conversation.py:112-113`]

**Deferred — real, not actionable in this story**

- [x] [Review][Defer] The decision endpoint has no actor-level authorization; the requester can decide their own approval [`backend/api/routers/approvals.py:97-98`] — deferred, pre-existing: no story owns separation of duties
- [x] [Review][Defer] Candidate drift is not revalidated: `scenario_version_id` and the candidate assignment count build the consequence summary at TX1 but are never compared at decide time [`backend/application/use_cases/decide_approval.py:66-79`] — deferred, beyond Decision 2's enumerated checks
- [x] [Review][Defer] `ScenarioResults` discards the list payload and issues one GET per approval; a single failure erases an approval the list already returned [`frontend/src/routes/ScenarioResults.tsx:42`] — deferred, a consequence of Decision 10's live-binding mandate

**Dismissed as noise (3):** the terminal timeline line "dropping AC2 identifiers" (Decision 10 mandates exactly that line "and nothing else", and the identifiers stay on the live panel); the `503` path storing no idempotency record (nothing was written, so re-execution is a genuinely new command); `cancel_agent_run_for_approval` splitting Decision 6's bundle (the net writes are correct — `_append_approval_activity` does bump `conversation.resource_version`).

**Environment note, not a story finding:** the two `tests/test_openrouter_provider.py` failures under the full suite are pre-existing test-order pollution — they pass in isolation and fail identically with this story's new test files excluded.

---

## Dev Notes

### Files being modified — read these before editing

| File | Current state | What this story changes | What must not break |
|---|---|---|---|
| `backend/api/routers/approvals.py` | POST create + two pure GETs; `_out` derives presented-expired; `_ERROR_STATUS` maps 4.1's codes | one new POST; new codes incl. 503; Decision 9's return-vs-raise | `_out`'s EAD-7 purity on both GETs; the replay re-derivation; `approval_not_granted` staying **403 at both sites** (4.1's review found two statuses for one state) |
| `backend/adapters/postgres/conversation.py` | `_append_approval_activity`, `pause_agent_run_for_approval`, `finish_agent_run`; lock order conversation → agent_run | `cancel_agent_run_for_approval`; `occurred_at` parameter on the activity helper | the lock order (ABBA deadlock, fixed at 4.1 review), `with_for_update()`, `resource_version + 1`, `max(sequence) + 1`, the `TypeError` on an unsupported payload type, and `ExecutedAgentRunV1.agent_run_status=None` on the planner path (never a fabricated status) |
| `backend/adapters/postgres/approval.py` | reads only; every read carries an explicit `site_id` predicate | `terminalize` compare-and-set | the explicit site predicate on **every** statement; the repository never commits |
| `backend/api/schemas.py` | `ApprovalOut` (10 fields), `TimelineOut`, both activity unions | four `ApprovalOut` fields, one `TimelineOut` field, `ApprovalDecisionIn` | `expected_baseline_schedule_version` staying `Field(...)` with **no default** on `ApprovalRequestIn` (4.1 fixed omission-vs-`null` here); both activity unions staying in sync |
| `backend/application/use_cases/request_approval.py` | TX1; `ApprovalAlreadyPendingError` on any pending row | nothing structural — but its pending pre-check now coexists with terminalizable overdue rows (Decision 7) | the policy gate order, the `command_idempotency` replay, `effect_key = request_effect_key` in the envelope |
| `frontend/src/features/approvals/ApprovalRequestCard.tsx` | pure presentation, derives presented-expired from `expires_at` | **nothing** — the panel composes it | its existing tests must pass unchanged |
| `frontend/src/features/chat/ActivityTimeline.tsx` | `approval_request` case renders the card; `activity_id` dedupe; `isLatest`-only live region; runtime fallback for unknown discriminants | pending → panel, terminal → compact line | the dedupe (UX-DR6), the live-region rule, the runtime fallback, `TERMINAL_LABELS` incl. the historical `approval_unsupported` entry |
| `frontend/src/routes/ScenarioResults.tsx` | renders a card per approval; `pendingApproval` fails closed on `!approvals.isSuccess` | renders the panel | the fail-closed derivation and the `approvalsUnavailable` wiring — 4.1's review found this failing **open** |
| `frontend/src/features/chat/ChatView.tsx` | `RUN_STATUS_WORDS` explicit map incl. `approval_required` | adds the cancellation reason beside `agent_cancelled` | the explicit mapping (a prefix-strip was already tried and shipped a raw wire value to the planner) |
| `backend/tests/test_gate_a_mutation_audit.py` | `versioned` literal, alphabetically ordered | one entry | every other Gate A assertion |

### Traps

1. **Raising after TX3 rolls it back.** `get_site_context` commits on return and rolls back on
   exception. A stale/expired outcome has already written a terminal binding, an audit row, an
   event, and possibly a cancelled run — the router must **return** the 409 problem, never raise.
   Decision 9. Task 8 has the demonstrated-red for it.
2. **Expiry outranks the requested decision.** EAD-7: an approve *or reject* against an overdue
   binding runs TX3 with `approval_expired` **instead of** the requested outcome. A reject that
   silently succeeds past `expires_at` is wrong, and it is the difference between `:526` closing
   and not.
3. **`ck_agent_run_status_reason` admits only three literals or `NULL`.** Any other reason string
   is a database error at runtime, not a test failure — the unit suite does not run as
   `shiftmind_runtime` and does not hit the CHECK on a fake repository.
4. **`status_reason` needs its column grant.** 4.1 landed `GRANT UPDATE (status, status_reason)`
   for this story; a missing grant surfaces as a PostgreSQL permission error under RLS, not as a
   unit-test failure. Prove it as `shiftmind_runtime` (Decision 11).
5. **`_append_approval_activity`'s `occurred_at` falls back to `binding.created_at`.** Left alone,
   every decision event is stamped with the *request's* time, and the timeline orders two events at
   one instant.
6. **The consequence summary is hashed and is a contract.** Any edit to its text changes
   `consequence_hash` and marks every live pending binding `stale` at revalidation. Story 4.1 Trap 7
   said this in advance; do not "improve" the wording here.
7. **Do not wire `get_baseline_assignments` or quote a baseline-side metric on the review card.**
   EAD-8 binds this story's rendering: the baseline assignment supply is empty by construction and
   has no production supplier. Render the stored consequence summary; add no number.
8. **`ApprovalAlreadyPendingError` counts overdue rows too.** Until a dismissal terminalizes it, an
   overdue binding still occupies `uq_approval_request_pending_run`. That is intended (EAD-7's pure
   reads), and it is precisely why Decision 7's control has to exist and its test has to go all the
   way to a **second successful request**.
9. **Two concurrent decisions.** The read-then-write revalidation cannot close the race; the
   `terminalize` compare-and-set on `state='pending' AND resource_version=?` is what does. Treat a
   `None` return as "someone else decided" → `409 approval_not_pending`, not a 500.
10. **Regenerate the OpenAPI types, do not hand-author them.** `npm run codegen` runs the backend
    exporter first; a stale `openapi.json` produces types that typecheck and lie.
11. **`npm run typecheck` is inert.** The root `tsconfig.json` declares `"files": []`; `npx tsc -b`
    is what actually type-checks the tree. 4.1 recorded this after it hid a real prop mismatch.
12. **This story adds no second path into `agent_cancelled`.** D6 excludes general user-initiated
    `AgentRun` cancellation. `cancel_agent_run_for_approval` takes a binding and one of three
    reasons, and nothing else may call it.

### Honest gaps this story ships with — state them in Completion Notes

- **A valid approve cannot succeed.** It returns `503 promotion_not_available` and writes nothing
  (Decision 3). `consumed` remains an unreachable stored state until Story 4.3. The Approve
  control is fully rendered, named, and accessibility-proven — only its success path is 4.3's.
- **No non-success audit row is written.** The closed outcome vocabulary has no `denied` member and
  this story adds no migration (Decision 4). Story 4.1's Open Question 1 stays open and is 4.3's.
- **No agent run is ever resumed.** EAD-5's approve edge (`approval_required --> agent_running`) and
  `DeferredToolResults` on the request path are only reachable on approve, so both are Story 4.3's.
  `AgentApprovalDecisionV1(approved=False)` therefore still has no producer.
- **`baseline_version` is `null` on every binding created in production**, because nothing writes
  `site_baseline` until 4.3. The non-null revalidation branch — including the compare-and-set on
  `baseline_resource_version` — is proven with a seeded row only.
- **`initiated_by_actor_id` and `decided_by_actor_id` hold the same principal.** This story fills
  the second field for the first time; the distinction stays structural until a second real user
  exists (parent Deferred, EAD-9).
- **Comparison staleness stays vacuously false in production** (`deferred-work.md:486`) — still no
  pointer writer.
- **`policy_version` mismatch is proven by seeding a bumped value**, not by toggling
  `scheduling_baseline_enabled` mid-process: the setting is read at process start, and the feature
  being off also refuses the command at the `enabled_feature_policy` pre-check, so the two paths
  must be tested separately or the stale arm proves nothing.

### Testing requirements

- Backend tests in `backend/tests/`, `test_*.py`, never co-located. PostgreSQL-dependent tests carry
  `@pytest.mark.postgres` (`pyproject.toml:52`).
- Frontend tests co-located, Vitest + Testing Library; assert accessible names and roles, not class
  names — **except** the NFR19 distinctness assertion, which is explicitly about visual treatment
  and may assert the variant.
- Accessibility is proven by automated coverage alone (`EXPERIENCE.md:196`). No screenshot baseline,
  no manual assistive-technology pass.
- Every new guard needs a recorded demonstrated-red. This is the epic's single most-repeated process
  lesson, and 4.1's review found two guards that could not fail.
- Follow 4.1's three-file split and keep it: fake-repository **use-case** tests in
  `test_decide_approval.py`; fake-repository **router/HTTP-contract** tests in
  `test_approvals_api.py`; **real-PostgreSQL** tests in `test_approval_governance_postgres.py`.

### Project structure notes

Additive, matching the Epic 4 Structural Seed and AR26. New files:
`backend/application/use_cases/decide_approval.py`, `backend/tests/test_decide_approval.py`,
`frontend/src/features/approvals/{ApprovalDecisionPanel,ApprovalDecisionDialog}.tsx` (+ tests),
`frontend/src/hooks/{useApproval,useDecideApproval}.ts`. No renames. **No migration file.**

`use_cases/promote_baseline.py` (Story 4.3) is **not** created here, not even as a stub — an empty
module invites the next session to assume it is owned. The seam 4.3 needs is
`revalidate_binding`, which this story exports.

### Open questions for Winston — raise before Story 4.3, not during implementation

1. **Is Decision 7's "Dismiss expired request" control compatible with EAD-7's "offers no decision
   control"?** This story reads that clause as *no approve-or-reject-on-the-merits control*, so a
   control that records an already-true expiry is admissible — and it is the only reading under
   which `deferred-work.md:526` can close without a sweeper EAD-7 forbids. Overrule before 4.3 if
   wrong; the alternative is a sweeper, which is a spine change, not a story change.
2. **Carried forward from Story 4.1, still unanswered and now 4.3's:** does EAD-6's closed
   audit-outcome vocabulary need a `denied` member? FR21 requires authoritative evidence for
   "denied" consequential actions, 4.3's AC4 names denied explicitly, and
   `ck_audit_event_outcome` currently makes such a row impossible without a migration.
3. **Should a decision pin the scenario version as well as the binding's resource version?** This
   story revalidates candidate, baseline, hashes, membership, policy, and expiry; scenario drift is
   surfaced only through `comparison.stale`. Also carried from 4.1.

### References

- Epic 4 spine:
  `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
  — EAD-1 (storage homes, 4.1 owns the migration), EAD-2 (no-baseline), EAD-3 (identity, two key
  shapes), EAD-4 (the persisted pause), EAD-5 (`status_reason`, cancel-on-terminal, the resume
  seam), EAD-6 (TX3, effect key, closed outcome vocabulary), EAD-7 (lazy expiry, pure reads),
  EAD-8 (baseline-supply guard binds 4.2's rendering), EAD-9 (supplier table), EAD-10 (**one
  endpoint, 4.2 owns TX3, the revalidation fork**), EAD-11 (consequence-summary home), EAD-12
  (policy derivation), *Consistency Conventions* (errors, event stream, approve control)
- ADR-4: `.../architecture-epic-4-2026-08-27/ADR-4-consequential-workflow.md` — D5 (cancel with
  literal reasons), D6 (no general cancellation), D7 (three bundles, ownership, lazy expiry),
  D9 (decide-time settings)
- Parent spine: `.../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-2 `:54`,
  AD-3 `:60`, AD-7 `:84-128`, AD-8 `:132`, AD-9 `:138`, AD-10 `:144`, AD-12 `:154`, AD-13 `:162`,
  AD-14 *Server state has one client owner*, AD-20 `:208`, AD-22 + Amendment `:216-221`
- Epic and requirements: `_bmad-output/planning-artifacts/epics.md` — Story 4.2 `:1169-1200`,
  FR13 `:49`, FR18 `:59`, FR21 `:65`, NFR18 `:109`, NFR19 `:111`, AR7/AR8/AR10/AR12/AR14/AR22
  `:153-168`, UX-DR6 `:188`, UX-DR12 `:200`, UX-DR13 `:202`, UX-DR23 `:222`, UX-DR27 `:230`,
  UX-DR29 `:234`, UX-DR32 `:240`, UX-DR35 `:246`
- UX: `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`
  Accessibility Floor `:185-196` (dialogs, consequence-bearing approval name, automated-only proof)
- Previous story: `_bmad-output/implementation-artifacts/4-1-request-approval-for-one-exact-feasible-candidate.md`
  — Decisions 1–11, its Traps, its Review Findings (the ABBA deadlock, the audit `effect_key`
  defect, the fail-open `pendingApproval`, the two-status `approval_not_granted`), and its
  Completion Notes' honest gaps
- Domain: `docs/DOMAIN-MODEL.md` §1–§2 (family determines unit; assignments carry no family) — the
  reason the review card quotes the stored summary and adds no number
- Conventions: `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md:42-49`, `docs/API.md:524-540`,
  `docs/TESTING.md`
- Process: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1, §3
- Ledger: `_bmad-output/implementation-artifacts/deferred-work.md` lines 300, 486, **526**

---

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- TX3 ordering guard was red while activity/audit preceded agent cancellation; the bundle now follows terminal binding → cancellation → audit → event.
- Stale-result commit guard was exercised against the rollback mutation (`return problem_response(...)` changed to an exception); the follow-up GET lost the terminal state.
- Dialog focus proof was red in Chromium and Edge when the controlled dialog unmounted before close autofocus; keeping the dialog mounted and restoring the captured trigger fixed Escape and Cancel.
- Expiry-slot proof guards the mutation that leaves the first row `pending`; under that mutation the second insert collides with the pending-agent-run index.
- Audit discriminator proof guards removal of `outcome` from the success uniqueness key; under that mutation `approval_requested` and `approval_rejected` collide.

### Completion Notes List

- Implemented the single approval decision endpoint, exported EAD-10 revalidation, and atomic TX3 terminalization for reject, expiry, and stale outcomes.
- Added site-scoped compare-and-set persistence, literal agent cancellation reasons, decision audit rows, conversation activity, idempotent semantic replay, and expected/current RFC 7807 context.
- Added live approval review/decision UI in Results and Chat, pure presented-expiry behavior, terminal timeline rendering, literal cancellation reasons, named dialogs, consequence-bearing accessible controls, and focus restoration.
- Added fake, HTTP, governed PostgreSQL, frontend accessibility, and two-browser journey coverage; reconciled the deferred-work ledger.
- Full validation: backend 1383 passed / 2 skipped / 7 deselected; PostgreSQL 117 passed; frontend 553 passed; Playwright 54 passed; TypeScript, lint, build, `git diff --check`, and Alembic drift check passed. Lint retains three pre-existing Fast Refresh warnings; build retains the existing bundle-size warning.
- **Re-validated after code review 2026-08-30:** backend **1395 passed / 2 skipped / 7 deselected** (full suite including PostgreSQL; 118 `postgres`-marked); frontend **571 passed** across 82 files; Playwright **60 passed**; TypeScript, lint, build and `git diff --check` clean, with the same three pre-existing Fast Refresh warnings and the same bundle-size warning. Two new guards were observed failing under mutation before being trusted: the Decision 9 commit guard (mutated to return the right status and code without terminalizing — only the persistence assertion catches it) and the Decision 7 ledger close (mutated so TX3 leaves the row `pending` — the second `request_approval` then raises `ApprovalAlreadyPendingError`, which is Trap 8's blocker and which the previous direct-insert test never reached).
- The local PostgreSQL volume was stamped at the prior migration head while missing three Story 4.1 objects. It was repaired non-destructively from the already-committed migration DDL; no migration file was added and no data/table was dropped.
- Honest gaps: valid approve remains `503 promotion_not_available`; `consumed`, baseline promotion, agent resumption/`DeferredToolResults`, non-success audit, and `AgentApprovalDecisionV1(approved=False)` remain Story 4.3 or explicitly deferred. Production baseline remains null until Story 4.3; comparison staleness therefore remains vacuously false.

### File List

- `_bmad-output/implementation-artifacts/4-2-review-and-decide-the-exact-approval.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/adapters/postgres/approval.py`
- `backend/adapters/postgres/conversation.py`
- `backend/api/problems.py`
- `backend/api/routers/approvals.py`
- `backend/api/routers/conversations.py`
- `backend/api/schemas.py`
- `backend/application/ports/approval.py`
- `backend/application/ports/conversation.py`
- `backend/application/use_cases/decide_approval.py`
- `backend/tests/test_approval_governance_postgres.py`
- `backend/tests/test_approvals_api.py`
- `backend/tests/test_decide_approval.py`
- `backend/tests/test_gate_a_mutation_audit.py`
- `docs/API.md`
- `docs/GATE-A-RUNBOOK.md`
- `frontend/e2e/repair-journey-accessibility.spec.ts`
- `frontend/openapi.json`
- `frontend/src/api/approvals.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/features/approvals/ApprovalDecisionDialog.tsx`
- `frontend/src/features/approvals/ApprovalDecisionPanel.test.tsx`
- `frontend/src/features/approvals/ApprovalDecisionPanel.tsx`
- `frontend/src/features/chat/ActivityTimeline.test.tsx`
- `frontend/src/features/chat/ActivityTimeline.tsx`
- `frontend/src/features/chat/ChatView.tsx`
- `frontend/src/hooks/useApproval.ts`
- `frontend/src/hooks/useDecideApproval.ts`
- `frontend/src/hooks/useSendMessage.test.tsx`
- `frontend/src/routes/ScenarioResults.tsx`
- `frontend/src/test/accessibility-contract.test.tsx`

---

## Change Log

| Date | Change |
|---|---|
| 2026-08-29 | Story created from `epics.md:1169-1200`, the Epic 4 architecture spine and ADR-4, Story 4.1's shipped substrate, and a live audit of the codebase at `0350f06`. |
| 2026-08-29 | Implemented and validated the exact approval review/decision flow, TX3 terminal outcomes, live accessible UI, complete automated proof, and ledger reconciliation; status moved to review. |
| 2026-08-30 | Code review: 4 decision-needed resolved, 24 patches applied, 3 deferred, 3 dismissed. Corrected Task 9 / Decision 7 (the ledger's proof demanded an unreachable state), Decision 2 (membership referent, Open Question 2 raised), Task 3 (AC1 rationale; both hashes removed from `ApprovalOut`), and Decision 10 (panel now belongs to the newest activity). Status moved to done. |
