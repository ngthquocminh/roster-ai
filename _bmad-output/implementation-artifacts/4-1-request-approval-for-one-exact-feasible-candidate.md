---
baseline_commit: ef043c0f8b19bfb4eeb1c7ece0c85ba0652a27b5
---

# Story 4.1: Request Approval for One Exact Feasible Candidate

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want approval proposed only for the exact feasible candidate I reviewed,
So that optimization completion never implicitly changes the operational baseline.

**This is Epic 4's foundation story and the largest single increment since Story 3.1.** It lands
the epic's whole storage substrate (one additive migration creating `approval_request`,
`site_baseline`, `audit_event`, and `agent_run.status_reason`), the two canonical contracts
(`ApprovalBindingV1`, `AuditEnvelopeV1`), the first `consequential`-risk product capability, the
TX1 request-approval bundle on both of its legal initiator paths, and the literal presentation
and replay of the `approval_required` pause. Stories 4.2 and 4.3 build the decision endpoint on
top of it; neither creates a table.

**It also reopens and closes the Epic 2/3 approval STOPGAP.** `execute_turn.terminal_status`
maps the adapter's `suspended` outcome to `agent_cancelled` with reason `approval_unsupported`,
naming this story by name as the owner that must restore the `approval_required` mapping
together with a persisted pending-call payload
(`backend/application/use_cases/execute_turn.py`, `deferred-work.md:300`). Its tripwire —
`test_request_path_grants_no_approval_capability_in_this_milestone`
(`backend/tests/test_evaluation_harness.py:728`) — fails the moment a capability with a
non-`none` approval policy becomes reachable. This story makes one reachable, so that test must
be **replaced, not weakened**; see Decision 9.

**Depends on, and consumes:** Story 1.1's `site`/`scenario_version` tables and RLS/grant idiom;
Story 1.2's `auth.resolve_session` and CSRF-guarded transport; Story 2.3's `conversation`,
`message`, `agent_run`, `persisted_event` tables, `ConversationRepository`, and `PersistedEventV1`;
Story 2.4's SSE replay and `ActivityItemV1` discriminated stream; Story 2.5/2.6's
`CapabilityModuleV1`, `compose_granted_capabilities`, `CapabilityGrantContextV1`, and the
capability conformance suite; Story 2.9's `TerminalOutcomeV1` and the `suspended` stopgap it
recorded; Story 3.1's `command_idempotency` table and `lib/idempotency.ts`; Story 3.2's
`schedule_version` and `ck_schedule_run_candidate_completed`; Story 3.3's `workflow.job_queue`
lease facts (`lease_owner`, `attempt_id`, `fencing_epoch`); Story 3.6's `scheduling_optimize`
module, `explicit_run_request` grant gate, `_positive_int` settings validation, and
`POST /api/v1/schedule-runs`; Story 3.7's `RunsTable`; Story 3.8's `ComparisonV1`,
`ComparisonSummary`, and `calculate_candidate_metrics`.

**Unblocks:** Story 4.2 (a pending binding to review and decide, and the endpoint's TX3 half),
Story 4.3 (TX2 promotion against a real `site_baseline` and `audit_event`), Story 4.4 (rows to
project provenance from), Stories 4.5/4.6 (the fixtures and literal states their proofs assert).

**Scope summary:** One additive migration (3 tables + 1 column + grants). Two new
`application/contracts` modules. One new `consequential`-risk capability module — the first
product one in the repository. One new use case (`request_approval`, TX1). One new router with
one POST and two GETs. One new activity type. Two new settings. One replaced guard test.
Frontend: one new card, one new hook pair, and the conversion of two disabled "Approve as
baseline" placeholders. **No new dependency. No evidence file** — see Task 11.

**This story is the first in the repository to:**

1. **write an `audit_event` row.** `AuditEnvelopeV1` does not exist in `backend/` at all;
   `enqueue_compute.py:31-33` carries `"NOT COVERED: audit:owned_by_epic_4"` and
   `demonstration.py:41` carries `"NOT COVERED: audit envelope emission (Epic 4)"` by name.
2. **register a `risk_class="consequential"` PRODUCT capability.** Today the only one is
   `demonstration`, a harness module that defaults OFF precisely because "an approval suspension
   from it terminates a real planner turn" (`settings.py:128-131`).
3. **persist an `agent_run` row in a non-terminal state from the finalisation path.** Every
   status `finish_agent_run` has ever written is terminal.
4. **give `site_baseline` a storage home.** `deferred-work.md:264` records that both producers
   still return `None` and that "moving and supplying the scenario baseline pointer remains
   owned by Epic 4".
5. **derive `policy_version` instead of hand-typing it.** `registry.py:11` is the constant
   `POLICY_VERSION = "one-user-mvp-v1"`.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code —
that re-derivation produced five of Story 2.7's nine decision-grade findings and is the single
most expensive pattern of Epics 1–2.

| Fact | Where it is written |
|---|---|
| Approval is a **one-time persisted state machine** bound to actor, site, action type, normalized parameter hash, existing feasible candidate `ScheduleVersion`, baseline version, consequence-summary hash, policy version, and expiry. **There is no durable approved-but-unconsumed state.** Rejected, expired, stale are terminal. Candidate creation happened at solver completion and is never repeated by promotion | AD-10 (`architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:144-148`); AR10 (`epics.md:156`) |
| `AgentRun`, `ScheduleRun`, `ApprovalRequest` use **separate closed graphs**; `approval_required` is a WAITING state with edges `--> agent_running: decision recorded` and `--> agent_cancelled: rejected or expired`; `ApprovalRequest` is `pending --> {rejected, expired, stale, consumed}` | AD-7 (`ARCHITECTURE-SPINE.md:84-128`); AR7 (`epics.md:153`) |
| The model **proposes typed calls only**; the application owns identity, site scope, authorization, policy, risk, versions, budgets, approvals, idempotency, state transitions, persistence, and audit. **No model output, browser value, or client approval flag grants authority** | AD-2 (`ARCHITECTURE-SPINE.md:54-58`); AR2 (`epics.md:147`) |
| Actor and site are **re-resolved from the server-side session on every operation**; unauthorized targets receive the non-disclosing not-found shape | AD-3 (`ARCHITECTURE-SPINE.md:60-64`); AR3 (`epics.md:148`) |
| Persisted workflow is the recovery boundary: approval requests, decisions, and their events **commit before acknowledgement**; reconnect/replay restores `approval_required` from persistence alone | AD-6; EAD-4 (`architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`) |
| Both AD-8 key shapes are legal here: an HTTP command keys on **actor/site/operation/body-hash plus expected versions**; an agent-initiated tool effect keys on **`(agent_run_id, tool_call_id)`**. Both write the same row through one use case via a single opaque `request_effect_key` column — **never a synthetic body hash faked from tool arguments** | AD-8 (`ARCHITECTURE-SPINE.md:132-136`); EAD-3; AR8 (`epics.md:154`) |
| An **absent `site_baseline` row is the valid "no baseline" state**; `ApprovalBindingV1.baseline_version = null` means *expects absence*. No synthetic baseline row is ever fabricated | EAD-2; ADR-4 D1 |
| `actor_id` always names the **server-derived authenticated human principal** of a user-initiated command. Every consequential audit envelope carries `initiated_by_actor_id` and `decided_by_actor_id` as **separate fields** even while the one-user MVP makes them equal; the automated executor appears only as worker facts (`lease_owner`, `attempt_id`, `fencing_epoch`), with **no `app_user` row** | EAD-3; ADR-4 D2/D3 |
| Storage homes: `approval_request` is **governance-owned**; `site_baseline` is a **scheduling-owned dedicated one-row-per-site record** — never a column on `site`, never derived from "latest schedule version"; `audit_event` is **evidence-owned and append-only** with no UPDATE/DELETE on the normal application path. **Story 4.1 lands the single additive migration creating all three plus `agent_run.status_reason`** | EAD-1 |
| TX1 request-approval is a **fixed atomic bundle**: pending binding + persisted pending-call payload + `approval_required` transition + audit + event. **Repositories and adapters may not widen a bundle**; only an application orchestrator crosses owners | EAD-6; AD-22 as amended 2026-08-27 (`ARCHITECTURE-SPINE.md:216-221`); AR22 (`epics.md:168`) |
| Successful mutation audit is unique on `(site_id, effect_key, outcome)`; non-success audit is unique on `(site_id, attempt_id)`. **Telemetry can never authorize, block, or substitute for audit** | AD-12 (`ARCHITECTURE-SPINE.md:154-158`); AR12 (`epics.md:158`) |
| **Every read path is pure.** A query, render, reconnect, or SSE replay that observes `now() >= expires_at` on a pending binding **presents it as expired and writes nothing**. The terminal `expired` state materialises only inside a decision-attempt transaction. There is no cron, sweeper, or write-on-read path | EAD-7; ADR-4 D7 |
| A setting **consulted once at TX1 and snapshotted into the binding** (expiry duration → absolute `expires_at`, parameter/consequence hashes, candidate/baseline versions) is immune by construction and **never bumps `policy_version`**. Only settings consulted at TX2/TX3 revalidation version the policy, enumerated in one frozen `PolicyInputsV1`; `policy_version` is **derived**, never hand-typed | EAD-12; ADR-4 D9 |
| The consequence-summary **text has exactly one home**: an application-owned literal snapshot persisted on the `approval_request` row beside its canonical hash at TX1. Not recomputed at render, not read live from `ProposalV1.consequence_summary`, **never model prose** | EAD-11 |
| Every Epic 4 contract or guard **names its production supplier or a seeded proof plus an explicit gap**; a story introducing a new one extends EAD-9's table or fails review | EAD-9; retro §3 preparation task (Amelia) |
| Contracts live in `application/contracts` with normative minimums fixed in Structural Seed: `ApprovalBindingV1` = approval ID and state (`pending`,`consumed`,`rejected`,`expired`,`stale`), actor/site/action, parameter hash, candidate/baseline versions, consequence hash, policy version, creation/expiry, decision/consumption times; `AuditEnvelopeV1` = audit/attempt/correlation IDs, actor/site and workflow IDs, action/policy outcome, safe hashes/summaries, before/after versions, model/prompt/tool/policy/app versions, evidence refs, occurred time. Hashes are **SHA-256 over RFC 8785 canonical JSON with algorithm and schema version stored beside the digest** | AD-20 (`ARCHITECTURE-SPINE.md:208`, Structural Seed `:330-331`); AR20 (`epics.md:166`) |
| Persisted events carry stream ID, decimal sequence, event type, occurred time, resource version, correlation IDs, and **one typed activity payload**; SSE IDs are `<stream_uuid>:<sequence>`; replay returns only greater matching-stream sequences | AD-21; AR21 (`epics.md:167`) |
| **Approval is never encoded as ordinary chat text nor inferred from rendering**; TanStack Query cache is never authority for a decision | AD-14; AR14 (`epics.md:160`) |
| Application errors map to RFC 7807 problem details with **stable codes**; denied, stale, missing, invalid, timed-out, cancelled and failed remain **distinct** | AD-13 (`ARCHITECTURE-SPINE.md:162-166`); *Consistency Conventions* Errors row (`:259`) |
| **Send, Run optimization, and Approve as baseline remain distinct in language, control, consequence, and visual treatment**; no single "AI action" treatment spans authority levels | NFR19 (`epics.md:111`); UX-DR12 (`epics.md:200`); UX-DR35 (`epics.md:246`) |
| A non-promotable result **never shows an enabled Approve as baseline control**; terminal outcomes expose only valid next actions | UX-DR13 (`epics.md:202`) |
| The conversation timeline renders approvals in persisted order and **deduplicates replay by event identity**; replay never duplicates an activity | UX-DR6 (`epics.md:188`); UX-DR23 (`epics.md:222`) |
| Approval, status, run progress, reconnect and terminal state **use text rather than color alone**; dialogs trap focus, name their purpose, and return focus; approval's primary action includes the consequence in its accessible name | `EXPERIENCE.md:190-191` (Accessibility Floor) |
| Manual assistive-technology verification is **out of scope**; automated coverage (axe-core, ARIA/semantic assertions, Playwright) is the only accepted proof | `EXPERIENCE.md:196` (Accessibility Floor) |
| Every new guard must be **observed failing** with its structural assertion removed or a relevant mutation applied, before it is trusted. "A passing assertion is insufficient unless it can be made to fail by an intentional relevant mutation" | epic-3 retro §1 *Challenges*, §3 preparation task (Amelia + Murat) |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |

**`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments, and it constrains one
thing here: the consequence summary.** `outbound`/`inbound` demand is measured in **volume**,
`indirect` in **headcount**, and assignments carry worker identity but **no family**. Decision 5
keeps this story out of that territory entirely — the consequence summary quotes only identities,
versions, and a candidate-side assignment count. **Do not add a demand-derived number to the
consequence summary**, and do not re-derive the family/unit rule from adapter code; cite the
document.

---

## Acceptance Criteria

Verbatim from `epics.md:1140-1167`.

1. **Given** a completed feasible candidate and current baseline comparison, **When** the planner
   or agent requests baseline approval, **Then** a pending `ApprovalBindingV1` records actor,
   site, action, normalized parameter hash, candidate/version, baseline/version,
   consequence-summary hash, policy version, creation/expiry, and one-time state, **And** the
   related agent run pauses in approval-required state with a persisted event, **And** this story
   independently owns `ApprovalRequest` persistence, the agent-run approval-required transition,
   and its literal presentation. (FR13, FR17, FR18, AR10, AR20)

2. **Given** a browser disconnect or reload while an agent run is approval-required, **When** Chat
   or Results reconstructs the persisted activity stream, **Then** the approval-required state,
   exact binding, and only currently valid decision controls replay once without losing or
   duplicating the pending decision, **And** the same agent-run and approval identifiers remain
   visible. (FR13, UX-DR6, UX-DR10, UX-DR23)

3. **Given** a missing candidate or a run that is infeasible, timed-out, cancelled, failed, or
   stale, **When** approval is proposed, **Then** policy rejects the request and creates no
   approvable binding, **And** optimization completion or model prose never changes the baseline
   pointer. (FR17, AR2)

4. **Given** a request-approval command replay, **When** actor/site/operation/body hash and
   expected versions match, **Then** the original binding/result is returned, **And** altered
   parameters or versions fail without a second effective request. (FR18, AR8)

---

## Eleven decisions were made at story creation — do not re-litigate them

### Decision 1 — The agent path is a real `consequential` capability whose suspension *is* the request

AC1 says "the planner **or** agent requests baseline approval", and EAD-3 fixes the agent path as
"a typed capability tool call keyed by `(agent_run_id, tool_call_id)`". EAD-4 requires TX1 to
persist "the adapter's `AgentApprovalPendingV1` payload (pending calls plus the resumable owned
turn history)". `AgentApprovalPendingV1` is produced by exactly one path
(`agent/runtime.py:318-331`), when PydanticAI returns `DeferredToolRequests` — which happens when
`capability_tools.py:96-103` converts a handler's `CapabilityApprovalRequired` into the
framework's `ApprovalRequired`, and that conversion requires
`module.manifest.approval_policy != "none"`.

So the agent path is not a separate "request approval" tool. **It is the consequential
promote-baseline tool suspending before it acts.** Ship a new module, **`scheduling_baseline`**,
`risk_class="consequential"`, `approval_policy="exact_action"`,
`required_feature_policy="scheduling_baseline_enabled"` (default `True`).

The handler follows `demonstration.demonstrate`'s **authority-before-effect** shape exactly:
validate arguments, then raise `SchedulingBaselineApprovalRequired` **before computing anything**.
Nothing is promoted by the handler on any path this story ships: TX2 belongs to Story 4.3, and
until it exists an approved re-invocation is unreachable (no decision can be recorded until 4.2
ships the endpoint). The handler therefore raises on **every** call, approved or not, with an
explicit comment naming Story 4.3 as the owner of the approved branch. Do not write a speculative
promotion body.

**The handler cannot resolve the candidate.** `AgentDepsV1` carries a projection reader, a clock,
a budget and a result sink — no repository, no unit of work — and
`test_handler_module_has_no_adapter_or_framework_import` (`test_capability_conformance.py:145-148`)
forbids importing `adapters`, `sqlalchemy`, `fastapi` or `pydantic_ai` from a handler module.
Resolution and the policy gate live in the `request_approval` use case, exactly as Story 3.6
Decision 1 put validation in the handler and the write in `enqueue_compute`.

**Grant gate:** `consequential` is gated by exact-action approval, not by AD-5's
`explicit_run_request` flag — that clause is `compute`-only (`ARCHITECTURE-SPINE.md:72-76`). The
module is therefore granted on ordinary chat turns. That is the point of the story: the binding,
not the toolset, is the gate.

**Rejected alternative — a non-suspending `request_baseline_approval` tool that just writes a
binding.** It would never produce an `AgentApprovalPendingV1`, so EAD-4's persisted pending-call
payload and EAD-5's `AgentTurnRequestV1.approvals` resume seam would both have nothing to carry,
and Story 4.3 would have to invent a second resume mechanism that EAD-5 forbids.

### Decision 2 — Every approval event rides the **conversation** stream; the planner path resolves its conversation server-side

The Epic 4 spine's *Consistency Conventions* fix the event stream: "approval lifecycle events ride
the conversation stream anchored to the paused agent run (`stream_id = conversation_id`,
`agent_run_id` set); no new stream kind". The agent path satisfies this trivially.

The planner-initiated HTTP path has no conversation in scope at the transport, and
`ck_persisted_event_stream_owner` (`schema.py:330-337`) admits only `conversation_id` or
`schedule_run_id` as stream owner — so an event with neither cannot be written at all.
**Resolve the conversation server-side** rather than inventing a stream kind:
`schedule_run → run_snapshot.proposal_id → proposal.conversation_id`, all NOT NULL, all already
joined by `PostgresScheduleRunRepository`. The planner path then writes the same
`ApprovalRequestActivityV1` on the same conversation stream with `agent_run_id = NULL`.

This is what makes AC2's "Chat **or** Results reconstructs the persisted activity stream" true for
both initiators through one replay mechanism, and it needs no schema change.

**Rejected alternative — ride the schedule-run stream for the planner path.** Legal under the
CHECK, but the run stream's declared SSE frame model is `RunProgressActivityOut`, whose `status`
is a closed *solver* vocabulary (`api/schemas.py:167-186`); putting an approval payload on it
would either widen that model or fork the frame contract, and would split replay across two
streams for one binding.

### Decision 3 — `POST /api/v1/approvals` on a new `approvals` router, `Idempotency-Key` header, pinned run resource version

The aggregate created is an `ApprovalRequest`, which AD-22 gives to **governance**; no existing
router owns that aggregate, and the Epic 4 Structural Seed names `api/routers/approvals.py`
explicitly. Mount at `/api/v1` beside the others (`api/main.py:266-272`).

Body: `{ "schedule_run_id": UUID, "expected_run_resource_version": int (ge=1),
"expected_baseline_schedule_version": str | null }`. Header: `Idempotency-Key`, `min_length=1`,
`max_length=40` — the exact `IdempotencyKey` annotation the shipped commands use
(`schedule_runs.py:91-93`).

`expected_baseline_schedule_version` is **required in the body and may be `null`**, because `null`
is a meaningful assertion under EAD-2 ("expects absence"), not an omission. A missing key and an
explicit `null` must not be conflated: declare it `Field(...)` with no default so Pydantic rejects
omission.

`POST` and not `PUT`/`PATCH`: `api/main.py:251-256` sets `allow_methods=["GET", "POST"]`, so any
other unsafe method passes same-origin locally and fails CORS preflight in a deployed topology
(Story 3.1 Decision 4).

Two read routes ship with it, both pure (EAD-7): `GET /api/v1/approvals/{approval_id}` and
`GET /api/v1/approvals?schedule_run_id={id}`.

### Decision 4 — One opaque `request_effect_key` column; the HTTP path *additionally* uses the existing `command_idempotency` table

EAD-3 requires "one opaque `request_effect_key` column" holding whichever key shape applies, and
forbids faking a body hash from tool arguments. It does **not** say the HTTP path abandons AD-8's
body-hash conflict detection, which AC4 requires by name ("altered parameters or versions fail
without a second effective request").

So both, with distinct jobs:

- `approval_request.request_effect_key` (TEXT, `UNIQUE (site_id, request_effect_key)`) is the
  **single-row guarantee**. HTTP writes `command:{actor_id}:{operation}:{idempotency_key}`; the
  agent path writes `tool:{agent_run_id}:{tool_call_id}`.
- The HTTP path *also* reads and writes `command_idempotency` through the existing
  `get_idempotent_result` / `_store_idempotent_result` pair, following `enqueue_compute.py:126-146`
  line for line, so a replay returns the original response and a **different body under the same
  key raises `IdempotencyKeyConflictError` → 409 `idempotency_key_conflict`**.

The agent path has no body hash and needs none: its key shape is already exact.

### Decision 5 — The consequence summary is identity-, version-, and count-only; it quotes no demand metric

EAD-11 gives the text one home (a literal snapshot on the row, hashed beside it). It does not say
what the text contains. This story fixes that: **candidate schedule version, baseline schedule
version or the literal "no current baseline", scenario version, and the candidate's assignment
count** — nothing else.

Two reasons, both load-bearing:

1. **EAD-8's hazard.** Baseline-side metrics are not authoritatively readable:
   `get_baseline_assignments()` is empty by construction, and `comparison.py` uses
   `wage_per_hour=0.0` / `selected_shifts=()` for the baseline side (`deferred-work.md:484`). A
   consequence summary quoting a baseline-side cost or coverage delta would be a wrong number
   wearing a governed hash. EAD-8's fail-closed guard binds from Story 4.3 on; this story stays out
   of its way by never asking the question.
2. **`docs/DOMAIN-MODEL.md`.** A demand-derived number in the summary would put this story inside
   the family/unit rule — the exact territory that produced five of Story 2.7's nine
   decision-grade findings. An assignment count is an assignment-side fact and carries no family,
   which the domain model states explicitly.

Compute it in `application/` from the persisted candidate `schedule_version` and
`schedule_assignment` rows. It is **never** `ProposalV1.consequence_summary` (model-adjacent draft
prose), never read live at render, and never regenerated.

### Decision 6 — `policy_version` is derived from a frozen `PolicyInputsV1`; `POLICY_VERSION` is renamed `POLICY_GENERATION` and `AgentDepsV1` keeps the generation string

EAD-12 fixes the mechanism:
`f"{POLICY_GENERATION}+{sha256(canonicalize_json(asdict(inputs)))[:12]}"`, reusing
`application/contracts/canonical.py`'s existing convention.

Today `registry.py:11` reads `POLICY_VERSION = "one-user-mvp-v1"`. **Rename it to
`POLICY_GENERATION`** (the spine's name) keeping the value, and add
`derive_policy_version(inputs: PolicyInputsV1) -> str` beside it.

`PolicyInputsV1` is a frozen dataclass holding exactly the **decide-time** settings that gate
whether baseline approval is grantable — today one field, `scheduling_baseline_enabled: bool`.
Enumerating it is the load-bearing act; adding a field later is a deliberate, reviewable change.
Hashing the whole of `Settings` would be wrong for the opposite reason: it would invalidate every
pending approval because someone edited a CORS origin.

**`AgentDepsV1.policy_version` keeps the generation string, unchanged.** It is the
capability-grant policy stamp, not the approval rulebook, and it is byte-pinned into Story 2.2's
golden fixtures (`evals/report.py:177` hardcodes `"one-user-mvp-v1"`). Only the binding carries the
derived value. Record this two-meanings-one-name hazard in a comment at both sites; do **not**
unify them in this story.

### Decision 7 — Expiry duration is `approval_expiry_seconds = 3600`, snapshotted to an absolute `expires_at`

The Epic 4 spine's one Open Question is this number, "fixed at Story 4.1 creation", supplier
`Settings`, one site-wide duration.

**3600 seconds.** Rationale: expiry is a belt-and-braces bound, not the correctness guard — drift
is caught by EAD-10's revalidation of versions, hashes, membership and policy at decide time, which
fails closed regardless of the clock. The number therefore only needs to bound a decision to a
single working session. One hour does that, survives a demo or a review without expiring mid-flow,
and is short enough that an abandoned binding does not linger across days.

Add it as `_positive_int` (Story 3.6's hardened parser), validated at process start. TX1 writes
`expires_at = clock() + timedelta(seconds=approval_expiry_seconds)` and **never consults the
setting again** — the `session_ttl_s` precedent (`api/routers/auth.py`), and the reason EAD-12
exempts it from `policy_version`.

### Decision 8 — `site_baseline` gets exactly one reader, and **both** existing `None` producers move to it in this story

EAD-1: "`scenario_catalogue`'s `literal(None)` baseline field is replaced by a real read of
`site_baseline`; no other module may read or write the pointer directly."

There are **two** producers, not one. `adapters/postgres/scenario_catalogue.py:117` selects
`literal(None, type_=String)`, and `adapters/postgres/scenario_projection.py:556` returns
`baseline_schedule_version=None` on `ScenarioOverviewV1`. `calculate_comparison` compares the run
snapshot's frozen value (sourced from the *catalogue*) against the *projection's* current value
(`deferred-work.md:486`). **Moving only one of them creates permanent false staleness the moment
Story 4.3 writes a pointer** — the frozen value would be a real version and the current value
`None` forever.

Ship one `PostgresSiteBaselineReader` in `adapters/postgres/site_baseline.py` and have both call
sites obtain the value from it. The presented value is `str(site_baseline.schedule_version_id)`,
which keeps `create_run_snapshot`'s existing `str | None` comparison and
`run_snapshot.baseline_schedule_version String(100)` working unchanged.

Nothing writes `site_baseline` in this story, so in production every 4.1 binding carries
`baseline_version = null`. That is correct under EAD-2 and must be stated in Completion Notes; the
non-null branch is proven with a seeded row.

### Decision 9 — The Story 2.9 tripwire test is **replaced by its own remediation**, never weakened

`test_request_path_grants_no_approval_capability_in_this_milestone`
(`test_evaluation_harness.py:728-770`) asserts that no granted module declares an approval policy,
and its message spells out the remediation: "persist the pending calls, an approval decision
endpoint, `DeferredToolResults` on the request path" and "restore the `approval_required` mapping
per AD-7".

This story lands two of the three (persistence and the `approval_required` mapping); the decision
endpoint is Story 4.2. **Delete the test and replace it with the guard its message describes**, in
`backend/tests/test_approval_request.py`:

1. `suspended` finalises as `approval_required`, never `agent_cancelled`, when TX1 created a
   binding.
2. `outcome.approval.pending_calls` and `outcome.approval.turn` are persisted on the row and read
   back byte-identically.
3. The only granted module declaring an approval policy is `scheduling_baseline`
   (`demonstration_enabled` still defaults `False`) — so a *third* consequential capability
   arriving without its own persistence still fails a test.

Each must be observed failing before being trusted (retro A2). Do **not** relax the old assertion
to an allowlist and leave it standing; that converts a tripwire into decoration.

### Decision 10 — A policy-refused request creates no binding, no audit row, and no pause

AC3 requires that a missing/infeasible/timed-out/cancelled/failed/stale candidate "creates no
approvable binding". EAD-6's closed audit-outcome vocabulary is
`approval_requested | approval_consumed | approval_rejected | approval_expired | approval_stale`
— every member presupposes an `approval_id`, and a refused request never mints one.

So: **this story writes audit only on the success path** (`outcome = 'approval_requested'`,
`effect_key = approval_id`, unique on `(site_id, effect_key, outcome)`). A refusal is recorded as a
persisted `TerminalOutcomeActivityV1` on the agent path and as an RFC 7807 problem on the HTTP path
— both literal, both already-existing mechanisms.

`audit_event`'s **non-success uniqueness on `(site_id, attempt_id)` is still created by this
story's migration** (EAD-1 gives 4.1 the table), so Story 4.3 — whose AC4 owns "successful, denied,
stale, failed, cancelled, rejected, or expired" — writes into a shape it does not have to alter.
Whether the closed vocabulary needs a denied-request member is recorded as an open question below,
not answered here.

**Agent-path refusal landing:** finalise as `agent_cancelled` — unchanged from today's stopgap
landing, which AD-7's own "rejected or expired" edge sanctions as terminal and truthful — with a
new `TerminalOutcomeV1(status="suspended", reason="approval_not_grantable", ...)` replacing
`approval_unsupported`. Leave `agent_run.status_reason` **NULL** on this path: per EAD-5 that
column names a *binding* outcome from the closed vocabulary
`approval_rejected | approval_expired | approval_stale`, and no binding existed. Keep
`approval_unsupported` in the frontend's `TERMINAL_LABELS` for historical rows.

### Decision 11 — The request control lives on Results only; `RunsTable`'s placeholder becomes a link, not a second command

`deferred-work.md:462` assigns this story the two disabled sub-states of `RunsTable`'s
`ApproveButton` ("stale baseline" vs plain-disabled), because 4.1 "supplies the real approval
command and is the first story that can tell them apart".

The better answer dissolves the question. UX-DR12 requires an approval request to be "bound visibly
to exact candidate, baseline, material parameters, consequences, and versions". A table row shows
none of that, so requesting approval from a row would bind a consequence the planner never saw —
the exact failure the story's own "So that" clause exists to prevent.

Therefore:

- **`ComparisonSummary`** (`frontend/src/components/run-results/ComparisonSummary.tsx:38`) — the one
  surface that renders both versions, the deltas, and the constraint results — gains the real
  **"Request approval"** control. Disabled with a **visible literal reason** when
  `comparison.stale` is true ("Comparison is stale — refresh before requesting approval") or when a
  pending binding already exists for the run ("A decision is already pending"). Never a bare `title`
  attribute.
- **`RunsTable`'s `ApproveButton`** (`RunsTable.tsx:163-169`) becomes a `Link` to that run's
  Results, labelled **"Review for approval"**. This satisfies Story 3.7 AC3 ("no … promotion
  control is invented") better than a permanently disabled button does, and removes the disabled
  command whose two sub-states `:462` asked about. Close `:462` in the same commit with this
  reasoning recorded — closed by dissolution, not by implementation.
- **"Approve as baseline" is not used as a label anywhere in this story.** It is the *decision*
  control and belongs to Story 4.2, where UX-DR12/NFR19's distinctness from "Run optimization"
  applies. Requesting and deciding must not share a label.

---

## Tasks / Subtasks

- [ ] **Task 1 — Contracts (AC: 1)**
  - [ ] `application/contracts/approval_binding.py`: `ApprovalBindingV1` (frozen dataclass,
        `schema_version`) with AD-20's normative minimums — `approval_id`, `state`
        (`Literal["pending","consumed","rejected","expired","stale"]`), `site_id`, `action`
        (`Literal["promote_baseline"]`), `initiated_by_actor_id`, `decided_by_actor_id | None`,
        `conversation_id`, `agent_run_id | None`, `schedule_run_id`,
        `candidate_schedule_version_id`, `baseline_schedule_version | None`,
        `baseline_resource_version | None`, `parameter_hash`, `consequence_summary`,
        `consequence_hash`, `checksum_algorithm`, `checksum_schema_version`, `policy_version`,
        `created_at`, `expires_at`, `decided_at | None`, `consumed_at | None`,
        `request_effect_key`, `resource_version`.
  - [ ] `application/contracts/audit_envelope.py`: `AuditEnvelopeV1` with AD-20's minimums —
        `audit_id`, `attempt_id`, `request_id`, `site_id`, `initiated_by_actor_id`,
        `decided_by_actor_id | None`, `conversation_id | None`, `agent_run_id | None`,
        `approval_id | None`, `schedule_run_id | None`, `action`, `outcome`, `success: bool`,
        `effect_key`, `before_version | None`, `after_version | None`, `safe_summary`,
        `parameter_hash`, `consequence_hash`, `policy_version`, `app_version`, `worker_facts`
        (`lease_owner`/`attempt_id`/`fencing_epoch` — all `None` on this story's paths),
        `evidence_refs`, `occurred_at`, `schema_version`.
  - [ ] `ApprovalStateV1` and the audit `outcome` vocabulary as `Literal`s in the contracts,
        matching EAD-6 exactly. No open `str`.
  - [ ] `application/contracts/activity.py`: add `ApprovalRequestActivityV1` — the reserved
        `"approval_request"` discriminant at `activity.py:18` has had no dataclass since Story 2.3
        — carrying the common activity fields plus `approval_id`, `approval_state`,
        `agent_run_id | None`, `schedule_run_id`, `candidate_schedule_version_id`,
        `baseline_schedule_version | None`, `consequence_summary`, `parameter_hash`,
        `consequence_hash`, `policy_version`, `expires_at`. Add it to the `ActivityItemV1` union and
        `__all__`.
  - [ ] **No decision fields on the activity.** Controls and outcomes are Story 4.2's.

- [ ] **Task 2 — One additive migration (AC: 1, 3)**
  - [ ] New revision with `down_revision = "c4d5e6f7a8b9"` — verify it is still head with
        `uv run alembic heads` before writing.
  - [ ] `approval_request` (governance): columns per Task 1; `state` CHECK listing exactly the five
        states; composite FKs to `conversation`, `agent_run`, `schedule_run`, `schedule_version`
        **paired with `site_id`** (the repo-wide idiom); partial unique index on `(agent_run_id)`
        `WHERE state = 'pending' AND agent_run_id IS NOT NULL`; `UNIQUE (site_id,
        request_effect_key)`; `UNIQUE (id, site_id)`; hash regex CHECKs (`~ '^[0-9a-f]{64}$'`) and
        the `sha256` / `rfc8785-v1` literal CHECKs copied from `proposal_version`;
        `pending_payload JSONB NULL`.
  - [ ] `site_baseline` (scheduling): `UNIQUE (site_id)`, composite FK to `schedule_version`,
        `resource_version BIGINT NOT NULL DEFAULT 1`, `updated_at`, `updated_by_actor_id`.
  - [ ] `audit_event` (evidence): append-only; `success BOOLEAN NOT NULL`; **two partial unique
        indexes** — `(site_id, effect_key, outcome) WHERE success` and
        `(site_id, attempt_id) WHERE NOT success` — implementing AD-12's two different rules on one
        table.
  - [ ] `ALTER TABLE agent_run ADD COLUMN status_reason VARCHAR(40) NULL` plus a CHECK admitting
        exactly `approval_rejected | approval_expired | approval_stale` or NULL. **Written by Story
        4.2, created here.**
  - [ ] RLS/grants for all three new tables copied from `f1a2b3c4d5e6:115-124`:
        `ENABLE`/`FORCE ROW LEVEL SECURITY`, `{table}_site_isolation` policy,
        `GRANT SELECT, INSERT`, `REVOKE UPDATE, DELETE`. Then narrow column grants:
        `GRANT UPDATE (state, decided_by_actor_id, decided_at, consumed_at, resource_version) ON
        approval_request TO shiftmind_runtime` (for 4.2/4.3) and
        `GRANT UPDATE (schedule_version_id, resource_version, updated_at, updated_by_actor_id) ON
        site_baseline TO shiftmind_runtime` (for 4.3). **`audit_event` gets no UPDATE grant at
        all** — that is AD-12's append-only rule expressed as a privilege, and Story 4.4's AC4 ("the
        normal application path cannot update or delete audit events") is proven against it.
  - [ ] `GRANT UPDATE (status, status_reason) ON agent_run TO shiftmind_runtime`, widening
        `c7d6e5f4a3b2`'s single-column grant. **Without this the Story 4.2 write fails at runtime
        with a permission error, not as a test failure.**
  - [ ] Mirror every table into `adapters/postgres/schema.py` metadata plus `ix_{table}_site_id`
        indexes; `uv run alembic check` must be clean.
  - [ ] Working `downgrade()` in reverse order, matching the existing files' convention.

- [ ] **Task 3 — `site_baseline` reader, wired at both producers (AC: 1)**
  - [ ] `application/ports/site_baseline.py`: `SiteBaselineV1` + `SiteBaselineReader` Protocol.
  - [ ] `adapters/postgres/site_baseline.py`:
        `PostgresSiteBaselineReader.get(connection, site_id) -> SiteBaselineV1 | None`. Absence is
        the "no baseline" answer (EAD-2), never an error.
  - [ ] Replace `scenario_catalogue.py:117`'s `literal(None, type_=String)` with a value from this
        reader, presented as `str(schedule_version_id)`.
  - [ ] Replace `scenario_projection.py:556`'s `baseline_schedule_version=None` from the **same**
        reader. **Both, in this story** — Decision 8's false-staleness trap.
  - [ ] Test that with no row both producers return `None`, and with a seeded row both return the
        *same* string. Observe it failing by moving only one producer.

- [ ] **Task 4 — Policy version and settings (AC: 1)**
  - [ ] `settings.py`: `approval_expiry_seconds: int = 3600` via `_positive_int`;
        `scheduling_baseline_enabled: bool = True` via `_flag`. Both validated at process start.
  - [ ] `application/capabilities/registry.py`: rename `POLICY_VERSION` → `POLICY_GENERATION` (same
        value), update `conversations.py:64,213`, add frozen `PolicyInputsV1` and
        `derive_policy_version()` per EAD-12 using `canonical.canonicalize_json`.
  - [ ] Comment the two-meanings hazard at both `AgentDepsV1.policy_version` and the binding field.
  - [ ] Test: changing `scheduling_baseline_enabled` changes the derived value; changing an
        unrelated setting (a CORS origin) does not. Both directions, both observed failing.

- [ ] **Task 5 — `scheduling_baseline` capability module (AC: 1, 3)**
  - [ ] `application/capabilities/scheduling_baseline.py` modelled on `scheduling_optimize.py` plus
        `demonstration.py`: `SchedulingBaselineRequestV1(schedule_run_id: UUID,
        expected_baseline_schedule_version: str | None)`; a `SchedulingBaselineError` hierarchy with
        `SchedulingBaselineApprovalRequired(CapabilityApprovalRequired)`; `ERROR_CODES`;
        `SCOPE_CONTROLS` declaring `NOT COVERED: promotion:owned_by_story_4_3` and
        `NOT COVERED: decision:owned_by_story_4_2`; manifest with `risk_class="consequential"`,
        `permission="site_baseline:promote"`, `approval_policy="exact_action"`,
        `idempotency_semantics` naming `(agent_run_id, tool_call_id)`, and `evaluation_fixtures`.
  - [ ] Register in `installed.py:_INSTALLED_FACTORIES`. `test_capability_conformance.py` must pass,
        including the manifest-`errors` / exception-subclass set equality.
  - [ ] Golden fixtures under `evals/golden/scheduling_baseline/` for the suspension case, driven by
        the Story 2.2 harness.
  - [ ] Handler raises approval-required on **every** call, with the Story 4.3 comment.

- [ ] **Task 6 — `request_approval` use case: TX1 (AC: 1, 3, 4)**
  - [ ] `application/use_cases/request_approval.py`. One transaction, one bundle, both initiators:
        pending binding + pending-call payload (agent path only) + `approval_required` transition
        (agent path only) + audit + persisted event.
  - [ ] **Policy gate, before any write** (AC3): the `schedule_run` exists and is visible in this
        site; `status == 'solver_completed'`; `candidate_schedule_version_id IS NOT NULL`;
        `schedule_version.solver_status IN ('OPTIMAL','FEASIBLE')`; the run's `resource_version`
        matches the pinned expected value; the supplied `expected_baseline_schedule_version` matches
        the live `site_baseline` presentation — including `null` matching absence, in **both**
        directions. Any failure raises a typed error and writes nothing.
  - [ ] Mint `approval_id` first (EAD-6: it is the `effect_key` for all three bundles).
  - [ ] Compute `consequence_summary` per Decision 5, then `parameter_hash` and `consequence_hash`
        via `contract_digest` (SHA-256 over RFC 8785), storing algorithm and schema version beside
        each digest.
  - [ ] `expires_at = clock() + approval_expiry_seconds`;
        `policy_version = derive_policy_version(...)`.
  - [ ] `initiated_by_actor_id` gets the server-derived session principal; `decided_by_actor_id`
        stays `NULL` until a decision exists. Both fields exist structurally now (EAD-3) even though
        the one-user MVP will make them equal later.
  - [ ] Agent path: persist `AgentApprovalPendingV1` (pending calls plus the resumable owned turn)
        as `pending_payload`, and move `agent_run` to `approval_required`. Read it back and assert
        round-trip equality in tests.
  - [ ] HTTP path: `command_idempotency` replay per Decision 4, returning the original binding.
  - [ ] `SCOPE_CONTROLS` naming what this use case does not cover: `decision:owned_by_story_4_2`,
        `promotion:owned_by_story_4_3`, `audit:non_success_outcomes_owned_by_story_4_3`.

- [ ] **Task 7 — Repositories (AC: 1, 2, 4)**
  - [ ] `application/ports/approval.py`: `ApprovalRepository` Protocol (`create_pending`, `get`,
        `list_for_schedule_run`, `get_pending_for_agent_run`) and `AuditWriter` (`append`). Ports
        stay SQL- and transport-free.
  - [ ] `adapters/postgres/approval.py` and `adapters/postgres/audit.py` implementing them on the
        caller's connection. **Repositories never commit** (*Consistency Conventions*, Transactions).
  - [ ] The conversation-side write — the `approval_required` transition and the
        `ApprovalRequestActivityV1` event — goes through `ConversationRepository`, not a second
        adapter reaching into `agent_run`. Add `pause_agent_run_for_approval(...)` beside
        `finish_agent_run`; it guards `current == 'agent_running'` the same way, and it is the only
        method that may write a non-terminal status.

- [ ] **Task 8 — Route wiring (AC: 1, 2, 3, 4)**
  - [ ] `api/routers/approvals.py`: `POST ""` (Decision 3), `GET "/{approval_id}"`, `GET ""`
        filtered by `schedule_run_id`. Mount at `/api/v1` in `api/main.py`.
  - [ ] `api/schemas.py`: `ApprovalRequestIn`, `ApprovalOut`, `ApprovalListOut`,
        `ApprovalRequestActivityOut`; add the activity to **both** `ConversationActivityItemOut` and
        `ActivityItemOut` unions.
  - [ ] Problem mapping with distinct stable codes (AD-13): `candidate_not_found` (404),
        `candidate_not_promotable` (409), `stale_resource_version` (409),
        `stale_baseline_version` (409), `approval_already_pending` (409),
        `idempotency_key_conflict` (409), `approval_not_granted` (403 when the capability is not
        granted), `invalid_approval_command` (422, fixed copy — never `str(exc)`, per
        `schedule_runs.py:333-341`).
  - [ ] Both GETs apply EAD-7: a pending binding with `now() >= expires_at` is **presented** as
        `expired`, offers no decision control, and the request **writes nothing**. Assert the
        no-write property with a read-only connection or a write-counting spy, not by inspection.
  - [ ] `api/routers/conversations.py`: `execute_agent_turn`'s finalisation branches on
        `outcome.status == "suspended"` → `request_approval(...)`, else `finalize_agent_run(...)` as
        today. Keep the existing `AgentRunNotQueuedError` / `RuntimeError` 409 handling.
  - [ ] `execute_turn.py`: `terminal_status` maps `"suspended"` → `"approval_required"`; delete the
        STOPGAP comment block; `terminal_outcome` returns the `approval_not_grantable` shape on the
        refused branch (Decision 10).

- [ ] **Task 9 — Gate A and docs (AC: 1)**
  - [ ] Add `("POST", "/api/v1/approvals")` to `test_gate_a_mutation_audit.py`'s `versioned` literal
        (`:257-269`) — the guard that forces a human to record a new write path.
  - [ ] Add its row to `docs/GATE-A-RUNBOOK.md`'s approved-write-path table (`:42-49`), stating that
        it writes governance and evidence rows and **does not move the baseline pointer**.
  - [ ] `docs/API.md`: the three routes and their problem codes.
  - [ ] `docs/CONFIGURATION.md`: the two new settings.

- [ ] **Task 10 — Frontend (AC: 1, 2)**
  - [ ] `npm run codegen` (export OpenAPI, regenerate `src/api/schema.d.ts`). **No hand-authored
        types.**
  - [ ] `src/api/approvals.ts` (typed `openapi-fetch` wrapper), `src/hooks/useRequestApproval.ts`
        (mutation, reusing `lib/idempotency.ts`'s key holder), `src/hooks/useRunApprovals.ts`.
  - [ ] `src/features/approvals/ApprovalRequestCard.tsx`: literal binding facts only — approval ID,
        state, candidate version, baseline version or "No current baseline", scenario version,
        consequence summary, policy version, expiry. Text-not-color for state
        (`EXPERIENCE.md:190`). Identifier copy buttons via the existing `IdentifierCopyButton`.
        **No approve/reject control** — Story 4.2 owns decisions, and AC2's "only currently valid
        decision controls" is satisfied by rendering none.
  - [ ] `ActivityTimeline.tsx`: new `case "approval_request"` before the `const exhaustive: never`
        guard. The existing `activity_id` dedupe already satisfies AC2's "replay once".
  - [ ] `ComparisonSummary.tsx` and `RunsTable.tsx` per Decision 11.
  - [ ] `ScenarioResults.tsx`: render `ApprovalRequestCard` for the run's current binding.
  - [ ] Vitest coverage for each: card states (pending / presented-expired), the two disabled
        request-control reasons, replay dedupe, and the timeline's unknown-discriminant runtime
        fallback still working.

- [ ] **Task 11 — Proof (AC: 1, 2, 3, 4)**
  - [ ] `backend/tests/test_approval_request.py`: TX1 on both initiator paths; every AC3 refusal
        (missing, infeasible, timed-out, cancelled, failed, stale run version, stale baseline
        version in both directions) writes nothing; AC4 replay returns the original binding and a
        changed body conflicts; the agent-path `(agent_run_id, tool_call_id)` key admits no second
        row.
  - [ ] Decision 9's three replacement guards, with the old test deleted.
  - [ ] `@pytest.mark.postgres` coverage for the migration: RLS forced on all three tables;
        `audit_event` UPDATE/DELETE denied to `shiftmind_runtime`; the partial unique index refuses a
        second `pending` row for one agent run; the two audit uniqueness rules hold independently.
  - [ ] EAD-7's purity: a GET on an overdue pending binding presents `expired`, writes nothing, and
        leaves the stored state `pending`.
  - [ ] **Every new guard gets a demonstrated-red note in the Debug Log** naming the mutation that
        made it fail. A guard with no recorded red is not evidence (retro §1).
  - [ ] Full suites before hand-off: `uv run pytest`, `uv run pytest -m postgres`,
        `uv run alembic check`, `npm test`, `npm run typecheck`, `npm run lint`, `npm run test:e2e`.
  - [ ] **No evidence file.** No AC in this story carries a measured threshold, and
        `docs/EVIDENCE-CONVENTION.md` exists to stop unmeasured files being written. Stories 4.5/4.6
        own Epic 4's evidence.

- [ ] **Task 12 — Ledger reconciliation (retro §3, Amelia)**
  - [ ] Close `deferred-work.md:300` (the `suspended` stopgap) — landed here.
  - [ ] Close `deferred-work.md:462` (`RunsTable` `ApproveButton` sub-states) by dissolution, with
        Decision 11's reasoning recorded.
  - [ ] Update `deferred-work.md:264` (baseline pointer supply): the reader and storage land here;
        **values remain Story 4.3's**.
  - [ ] Update `deferred-work.md:486` (comparison staleness "vacuously false in production"): still
        vacuous after this story, because nothing writes the pointer yet. **Do not close it.**
  - [ ] Leave `deferred-work.md:427-437` (worker/actor attribution) open and re-point it at Stories
        4.3/4.4, which read the audit rows. This story adds the two structural fields
        `initiated_by_actor_id` / `decided_by_actor_id` but writes no worker-driven audit.
  - [ ] Leave `deferred-work.md:280` (`revoked_conversation_ids` has no supplier) open. This story
        adds no revocation source.
  - [ ] Record in Completion Notes the EAD-9 supplier entries for the two new guards this story
        introduces: the `scheduling_baseline` grant (real supplier: `Settings` +
        `enabled_feature_policy`) and the consequence-summary calculator (real supplier: persisted
        `schedule_version` / `schedule_assignment` rows).

---

## Dev Notes

### Files being modified — read these before editing

| File | Current state | What this story changes | What must not break |
|---|---|---|---|
| `backend/application/use_cases/execute_turn.py` | `terminal_status` maps `suspended → agent_cancelled` behind a long STOPGAP comment naming this story; `terminal_outcome` returns `approval_unsupported` | `suspended → approval_required`; STOPGAP deleted; refused branch returns `approval_not_grantable` | `test_every_emittable_failure_reason_has_a_terminal_mapping`; the `failure_source` discrimination (never string-match a reason); `rehydrate_history`'s bounded owned history |
| `backend/api/routers/conversations.py` | `execute_agent_turn` always calls `finalize_agent_run` in `_finish()` | branches to `request_approval` for `suspended` | the claim/finish threadpool split (nothing holds a transaction over the model call); both 409 branches; `deps` construction order and the "guard starts HERE" comment |
| `backend/adapters/postgres/conversation.py` | `finish_agent_run` guards `current == 'agent_running'`, writes a terminal status, appends one event | gains `pause_agent_run_for_approval` beside it | the `with_for_update()` conversation lock, `resource_version + 1`, the `max(sequence) + 1` derivation, and the `TypeError` on an unsupported payload type |
| `backend/application/contracts/activity.py` | reserves `"approval_request"` in `ActivityTypeV1` with no dataclass | adds `ApprovalRequestActivityV1` to the union | the mid-file import ordering and every existing discriminant |
| `backend/adapters/postgres/scenario_catalogue.py` | selects `literal(None, type_=String)` as the baseline field | reads `site_baseline` | the version-ordinal ordering that decides which scenario version a context describes |
| `backend/adapters/postgres/scenario_projection.py` | returns `baseline_schedule_version=None` on the overview | same reader as the catalogue | `baseline_assignment_count=0` and `get_baseline_assignments`'s empty supply stay untouched (EAD-8) |
| `backend/application/capabilities/registry.py` | `POLICY_VERSION = "one-user-mvp-v1"` | renamed `POLICY_GENERATION`; adds `PolicyInputsV1` + `derive_policy_version` | `compose_granted_capabilities`'s cross-site and revoked-conversation branches; the `compute`/`explicit_run_request` gate |
| `backend/tests/test_evaluation_harness.py` | holds the Story 2.9 tripwire | tripwire deleted, replaced per Decision 9 | every other harness test |
| `frontend/src/features/chat/ActivityTimeline.tsx` | exhaustive switch with a `never` guard and a runtime fallback | one new case | the `activity_id` dedupe (UX-DR6), the `isLatest`-only live region, and the runtime fallback for unknown discriminants |
| `frontend/src/components/run-results/ComparisonSummary.tsx` | disabled "Approve as baseline" with a `title` attribute | real "Request approval" with visible disabled reasons | the stale banner, "Not computed" absence rendering, and the version copy buttons |
| `frontend/src/components/runs/RunsTable.tsx` | disabled `ApproveButton` for `solver_completed` | link to Results, "Review for approval" | Cancel/Retry/View gating sets and the `min-h-11` touch target |

### Traps

1. **`claim_queued_run` only claims `agent_queued`.** A run parked in `approval_required` cannot be
   re-executed by any existing path. That is correct for this story (resume is Story 4.3's), but it
   means a TX1 that commits the pause and then fails to commit the binding would strand the run
   forever. The bundle is one transaction precisely to make that impossible — do **not** split it
   across two `open_site_context` blocks the way `_claim`/`_finish` are split.
2. **`persisted_event.actor_id` is `NOT NULL` with an FK to `app_user`.** There is no system-user row
   and EAD-3 forbids creating one. The planner path's session principal fills it; the agent path uses
   `claimed.actor_id` (the initiating human), as `finish_agent_run` already does.
3. **`ck_persisted_event_stream_owner` admits only conversation- or schedule-run-owned streams.**
   Decision 2 is what keeps the planner path legal. Verify the CHECK before assuming a third shape.
4. **`agent_run.status_reason` needs a column grant.** `c7d6e5f4a3b2` granted `UPDATE (status)` only.
   A missing widening surfaces as a PostgreSQL permission error at runtime under RLS, not as a unit
   test failure — the unit suite does not run as `shiftmind_runtime`.
5. **Two producers of the baseline pointer.** Decision 8. Moving one is worse than moving neither.
6. **`policy_version` now means two things.** Decision 6. Do not "fix" `AgentDepsV1` in this story;
   it is byte-pinned into Story 2.2's golden fixtures.
7. **The consequence summary is hashed.** Any later change to its text changes `consequence_hash`,
   which EAD-10 revalidates at decide time — so a cosmetic edit in Story 4.2 would mark every pending
   binding `stale`. Fix the text here and treat it as a contract.
8. **`_to_deferred_results` has no duplicate-`tool_call_id` detection** (`deferred-work.md:201`). Not
   this story's to fix — no path produces duplicates — but the pending-payload round-trip test must
   not be written in a way that depends on that absence.
9. **`ActivityTimeline`'s `never` guard is compile-time; the runtime fallback is what protects an
   older bundle meeting a newer backend.** Adding the case must not remove the fallback.
10. **Regenerate the OpenAPI types, do not hand-author them.** `npm run codegen` runs the backend
    exporter first; a stale `openapi.json` produces types that typecheck and lie.

### Honest gaps this story ships with — state them in Completion Notes

- **No binding created in production will carry a non-null `baseline_version`,** because nothing
  writes `site_baseline` until Story 4.3. The non-null branch is proven with a seeded row only.
- **No decision can be recorded.** `pending` is the only reachable stored state; `consumed`,
  `rejected`, `expired`, `stale` exist in the schema and the contract and are unreachable until
  4.2/4.3. The *presented*-expired read path (EAD-7) is reachable and is proven.
- **Non-success audit is not written.** Decision 10. The uniqueness rule and columns exist; only
  `approval_requested` rows are produced.
- **The approved re-invocation of `scheduling_baseline` is unreachable** and the handler raises
  unconditionally. Story 4.3 supplies the approved branch.
- **`initiated_by_actor_id` and `decided_by_actor_id` will hold the same principal** whenever Story
  4.2 fills the second. The distinction is structural; the production gap is a second real user
  (parent Deferred, EAD-9).
- **Comparison staleness stays vacuously false in production** (`deferred-work.md:486`) — the
  mechanism now has a place to read from, but no writer.

### Testing requirements

- Backend tests in `backend/tests/`, `test_*.py`, never co-located. PostgreSQL-dependent tests carry
  `@pytest.mark.postgres` (`pyproject.toml:52`).
- Frontend tests co-located, Vitest + Testing Library; assert accessible names and roles, not class
  names.
- Accessibility is proven by automated coverage alone (`EXPERIENCE.md:196`). No screenshot baseline,
  no manual assistive-technology pass.
- Every new guard needs a recorded demonstrated-red. This is the epic's single most-repeated process
  lesson.

### Project structure notes

Additive, matching the Epic 4 Structural Seed and AR26's convergence targets. New files:
`backend/application/contracts/{approval_binding,audit_envelope}.py`,
`backend/application/capabilities/scheduling_baseline.py`,
`backend/application/use_cases/request_approval.py`,
`backend/application/ports/{approval,site_baseline}.py`,
`backend/adapters/postgres/{approval,audit,site_baseline}.py`,
`backend/api/routers/approvals.py`, one `backend/migrations/versions/*.py`,
`frontend/src/api/approvals.ts`, `frontend/src/hooks/{useRequestApproval,useRunApprovals}.ts`,
`frontend/src/features/approvals/ApprovalRequestCard.tsx`. No renames.

`use_cases/decide_approval.py` (Story 4.2) and `use_cases/promote_baseline.py` (Story 4.3) are
**not** created here, not even as stubs — an empty module invites the next session to assume it is
owned.

### Open questions for Winston — raise before Story 4.3, not during implementation

1. **Does EAD-6's closed audit-outcome vocabulary need a denied-request member?** Decision 10 writes
   no audit for a policy-refused request because every member of
   `approval_requested | approval_consumed | approval_rejected | approval_expired | approval_stale`
   presupposes an `approval_id`. FR21 requires authoritative evidence for "denied" consequential
   actions, and Story 4.3's AC4 names denied explicitly. Either the vocabulary gains a member, or 4.3
   records refusals under a non-approval effect key.
2. **Should the planner path pin a scenario version as well as a run resource version?** AC1 names
   "current baseline comparison"; this story pins the run's resource version and the baseline
   version. Scenario drift is currently surfaced only through `comparison.stale`.

### References

- Epic 4 spine:
  `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
  (EAD-1 storage homes and the 4.1-owned migration; EAD-2 no-baseline; EAD-3 identity and the two key
  shapes; EAD-4 the persisted pause; EAD-5 `status_reason` and the resume seam; EAD-6 TX1 and the
  closed outcome vocabulary; EAD-7 lazy expiry and pure reads; EAD-8 the baseline-supply guard;
  EAD-9 supplier table; EAD-11 the consequence-summary home; EAD-12 policy derivation)
- ADR-4: `.../architecture-epic-4-2026-08-27/ADR-4-consequential-workflow.md` (D1–D9 rationale; the
  brownfield facts verified 2026-08-27)
- Parent spine: `.../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-2 `:54`,
  AD-3 `:60`, AD-5 `:72-76`, AD-7 `:84-128`, AD-8 `:132`, AD-9 `:138`, AD-10 `:144`, AD-11 `:150`,
  AD-12 `:154`, AD-13 `:162`, AD-20 `:208` and Structural Seed `:330-331`, AD-22 + Amendment
  `:216-221`, AD-23 `:227`, Consistency Conventions `:255-262`
- Epic and requirements: `_bmad-output/planning-artifacts/epics.md` — Story 4.1 `:1140-1167`,
  FR13 `:49`, FR17–FR21 `:57-65`, AR2/AR5/AR7/AR8/AR10/AR12/AR14/AR20/AR21/AR22 `:147-168`,
  UX-DR6 `:188`, UX-DR10 `:196`, UX-DR12 `:200`, UX-DR13 `:202`, UX-DR23 `:222`, UX-DR35 `:246`
- UX: `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`
  Accessibility Floor `:185-196`
- Domain: `docs/DOMAIN-MODEL.md` §1 (family determines unit; assignments carry no family)
- Conventions: `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md:42-49`, `docs/TESTING.md`
- Process: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1, §3
- Ledger: `_bmad-output/implementation-artifacts/deferred-work.md` lines 201, 264, 280, 300,
  427–437, 462, 484, 486

---

## Dev Agent Record

### Agent Model Used

### Debug Log References

- 2026-08-27: Red/green recorded for Task 1: `backend/tests/test_approval_contracts.py` initially failed collection because the approval contract modules did not exist; after implementation it passed. Focused verification currently green: `uv run pytest tests/test_conversation_contracts.py tests/test_capability_conformance.py tests/test_approval_contracts.py` — 71 passed. The migration head is `d4e5f6a7b8c9`.

### Completion Notes List

### File List

---

## Change Log

| Date | Change |
|---|---|
| 2026-08-27 | Story created from `epics.md:1140-1167`, the Epic 4 architecture spine and ADR-4, and a live audit of the codebase at `ef043c0`. |
