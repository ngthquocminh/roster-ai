# ADR-4 — Consequential Workflow: Approval, Promotion, Audit, and Recovery Semantics

- **Status:** accepted (2026-08-27)
- **Scope:** Epic 4 "Exact Baseline Decision and Decision Record", Stories 4.1–4.3; inherited implications for 4.4–4.6
- **Audience:** product, architecture, implementation, and test owners creating and reviewing Epic 4 work
- **Companion:** `ARCHITECTURE-SPINE.md` in this folder (the enforceable EAD-1…EAD-12 rules). This note is the citable rationale; the spine is the contract.
- **Parent authority:** `../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-2, AD-3, AD-6…AD-12, AD-14, AD-15, AD-16, AD-20, AD-22 are binding here. AD-22 was amended on 2026-08-27 by this run's findings (see Consequences); every other inherited AD is used unweakened.

## Context

Epic 3 delivered the complete non-consequential repair loop: drafts, immutable run snapshots, deterministic candidates, leased/fenced execution, comparison, and recovery — all proven at correctness, recovery, and browser layers. Epic 4 adds the one consequential act: replacing the operational baseline. The Epic 3 retro (§3) required four design decisions to be citable **before Story 4.1 is created**, so that approval, promotion, audit, and recovery semantics are not re-decided mid-implementation or re-litigated at code review — the pattern that cost the most across Epics 1–3.

Brownfield facts this note rests on (verified live 2026-08-27, independently re-verified at review): the `agent_run` status CHECK already contains `approval_required` and `agent_cancelled` but the table has no reason column; `persisted_event.actor_id` is a `NOT NULL` FK to `app_user`, and its stream-owner CHECK constrains only `conversation_id`/`schedule_run_id`, leaving the conversation-stream convention compatible today; the baseline pointer is served as `literal(None)` with no storage; no approval or audit table and no `ApprovalBindingV1`/`AuditEnvelopeV1` contract module exists yet.

Two further facts are load-bearing and shaped the decisions below. First, `execute_turn.py` carries an explicit STOPGAP mapping the adapter's `suspended` outcome to `agent_cancelled` with reason `approval_unsupported`, naming Epic 4 (AD-10, Stories 4.1–4.3) as the owner that must restore the `approval_required` mapping **together with a persisted pending-call payload**; its guard test fails the moment an approval capability becomes reachable, which is what reopens the decision. Second, the resume seam already exists in owned contracts — `AgentApprovalPendingV1` returns the suspension to the application rather than resolving it in-process, and `AgentTurnRequestV1.approvals` carries a server-owned `AgentApprovalDecisionV1` supplied "from a persisted approval record, never by model output". Epic 4 therefore persists a payload and feeds a decision back through machinery that is already designed for it; it invents no resume mechanism.

## Decisions

### D1 — "No baseline" is an explicit valid state (adopted; spine EAD-2)

An absent `site_baseline` row *is* the no-baseline state. The first approval establishes the initial operational baseline (binding carries `baseline_version = null`, meaning *expects absence*; promotion revalidates absence and inserts). Every later approval replaces one exact named baseline (non-null `baseline_version`; promotion compare-and-sets `site_baseline.resource_version`). Any mismatch in either direction marks the binding `stale`. No synthetic baseline row is ever fabricated — the refusal Stories 3.1/3.2/3.8 already recorded stands.

### D2 — `actor_id` is the server-derived authenticated human principal (adopted; spine EAD-3)

`actor_id` names the human whose session issued a user-initiated command, resolved server-side inside the command transaction. It is never a worker identity and never supplied by browser or model input. No synthetic system-user row is created for automation.

### D3 — Audit distinguishes three roles (adopted; spine EAD-3)

Every consequential audit envelope carries, as separate fields: **initiating planner** (`initiated_by_actor_id` — who requested the approval/run), **deciding planner** (`decided_by_actor_id` — who approved or rejected), and the **automated executor** represented only by worker facts (`lease_owner`, `attempt_id`, `fencing_epoch`). In the one-user MVP the two human fields hold the same principal; the distinction is structural and is proven with seeded distinct actors (production gap: a second real user — parent Deferred). Worker-driven persisted events set `actor_id` to the initiating human of the enqueuing command (the run *requester*, per Story 3.6's fix, verified in `enqueue_compute`), with executor facts in the payload; after a resumed run, continued worker events keep the initiating principal and the approver appears only through `decided_by_actor_id`. This resolves the attribution item Story 3.5's review deferred to Epic 4.

Story 4.1's "planner **or agent** requests approval" is two key shapes on one row, both already legal under parent AD-8: the planner path is an HTTP command keyed by body-hash plus expected versions; the agent path is a typed capability tool call keyed by `(agent_run_id, tool_call_id)`. Both write the same `approval_request` row through one use case via a single opaque `request_effect_key` column — never a synthetic body hash faked from tool arguments, which is what a narrower reading of AD-8 would have forced.

### D4 — Approval is a persisted workflow (adopted; spine EAD-4, EAD-5)

request approval → persist the exact immutable binding and the `approval_required` pause **before acknowledgement** → reconnect/replay restores pause, binding, and identifiers from persistence alone → explicit approve/reject/expiry/stale outcome → literal persisted terminal/result state. Policy refuses to create a binding for a missing, infeasible, timed-out, cancelled, failed, or stale candidate. Solver completion and model prose can never move the pointer.

### D5 — Rejection/expiry/staleness cancels the paused run with literal reasons (adopted; spine EAD-5)

A terminal non-consumed binding (rejected, expired, stale) terminalizes the paused agent run as `agent_cancelled` with the matching reason from the closed vocabulary `approval_rejected | approval_expired | approval_stale`, in the same transaction. `agent_run` gains a nullable `status_reason` column (additive migration) so the literal outcome renders on reconnect without event replay. On approve, the run returns to `agent_running` and is driven to a terminal state through the **existing** owned seam — the persisted decision is supplied as `AgentApprovalDecisionV1` on a resumed turn and finalises through the normal `execute_turn` path — so no approved run is left parked. **This adds no general user-initiated AgentRun cancellation** (D6, adopted verbatim).

### D6 — No general user-initiated AgentRun cancellation (adopted)

Approval outcomes are the only new path into `agent_cancelled`. Anything broader is a separate product decision Epic 4 does not take.

### D7 — One atomic, idempotent transaction per consequential act (adopted; spine EAD-6)

Three fixed bundles, each a single transaction: **TX1 request-approval** (pending binding + persisted pending-call payload + pause + audit + event), **TX2 decide-approve** (revalidation + `pending → consumed` + baseline CAS + audit + event + run resume), **TX3 decide-reject/expire/stale** (terminal binding + `agent_cancelled(reason)` + audit + event). The `effect_key` for all three is the server-generated `approval_id` minted at TX1, disambiguated by the closed outcome vocabulary `approval_requested | approval_consumed | approval_rejected | approval_expired | approval_stale`, so AD-12's uniqueness makes a second pointer movement structurally impossible. Replays return the original semantic result; a decision against a terminal binding fails with literal expected/current context.

**Ownership is named** (spine EAD-10) because "three bundles across three stories" is exactly where two dev sessions build competing code or each assume the other did: there is one decision endpoint; Story 4.2 owns it and implements TX3 in full, and Story 4.3 owns TX2 only, as that endpoint's approve branch. Story 4.1 lands the single additive migration for all three tables, since it must read the baseline pointer before 4.3 ever writes it. Revalidation has one fixed fork: any **business** mismatch (candidate, baseline, hashes, membership, policy, expiry) terminalizes to `stale`/`expired` and never retries; only a **transactional write fault** rolls back and leaves the binding `pending` for an honest retry.

Expiry has no sweeper: it is **lazily materialized** (spine EAD-7), and **reads never write**. A query, render, reconnect, or replay that sees an overdue pending binding presents it as expired and offers no decision control — it persists nothing. The terminal `expired` state materializes only inside a decision-attempt transaction, which runs TX3 with reason `approval_expired` instead of the requested outcome. The earlier draft's "render-time state read that mutates" was withdrawn at review: it would have made every page load of an overdue approval write an audit row and an event, and this codebase has no write-on-read pattern to build it on.

### D8 — Every contract or guard names its production supplier (adopted; spine EAD-9)

The spine's supplier table is the checklist: real suppliers exist today for actor identity (`auth.resolve_session`), executor attribution (job-queue lease), and candidate feasibility (DB constraint); seeded-proof-plus-gap entries cover the two-planner distinction, `policy_version` (derived per D9 from `PolicyInputsV1`), and expiry duration (Settings; value fixed at Story 4.1 creation). The **baseline assignment supply has no production supplier** and is deliberately guarded rather than wired (next section). A story introducing a new guard extends the table or fails review.

### D9 — Only decide-time settings version the policy (spine EAD-12)

`policy_version` exists so a binding minted under one rulebook is not consumed under another. That makes the test **snapshot-time versus decide-time**, not "did any setting change".

A setting consulted once at TX1 and snapshotted into the binding is immune by construction and never bumps the version. The expiry duration is the leading case: TX1 writes `expires_at = now() + duration`, and from then on the binding carries its own absolute deadline. This is the same shape as the existing `session_ttl_s`, which becomes an absolute deadline at sign-in (`api/routers/auth.py`) and does not retroactively move live sessions. Changing the duration therefore affects only approvals minted afterwards, which is correct and needs no mechanism.

Only settings consulted at TX2/TX3 revalidation change the rulebook. They are enumerated explicitly in one frozen `PolicyInputsV1` — today the capability feature flags gating whether baseline approval is grantable — and `policy_version` is *derived* from that subset rather than hand-typed: `POLICY_GENERATION` (the semantic string `one-user-mvp-v1`) plus a truncated SHA-256 over RFC 8785 canonical JSON, reusing AD-20's existing convention in `application/contracts/canonical.py`.

Deriving it rather than hand-editing the constant is deliberate: a constant somebody must remember to bump is the "guard that passes without proving a failure" pattern the Epic 3 retro names as this project's recurring failure mode. The enumeration is the load-bearing act — it forces an explicit answer to which settings carry authority, which is currently written down nowhere. Hashing the whole of `Settings` would be wrong for the opposite reason: it would invalidate every pending approval because someone edited a CORS origin.

A bump makes pending bindings fail EAD-10's revalidation as `stale`. No baseline moves; the planner refreshes and re-requests.

## Consequences

- **Comparison honesty after first promotion.** Story 3.8's comparison is truthful today only because the baseline assignment supply is empty. Once 4.3 moves a real pointer, an empty read would falsely render "all assignments net-new". Spine EAD-8 therefore requires comparison to **fail closed with a distinct outcome** when the frozen baseline version is non-null but its assignments are not authoritatively readable. Wiring the real supply — including the wage and selected-shift prerequisites Stories 3.8/3.10 recorded — is deferred with a named trigger. Pointer movement *does* activate 3.8's staleness detection, discharging its "vacuously false in production" deferral.
- **The consequence-summary text gets one home** (spine EAD-11): a literal application-computed snapshot persisted on the `approval_request` row beside its canonical hash at TX1. Without this, 4.1 (hash), 4.2 (render), and 4.4 (provenance replay) each had a plausible different source, and the text a planner approved could drift from the text that was hashed and audited.
- **Parent AD-22 was amended rather than diverged from** (2026-08-27, approved by Minh). Three conflicts were surfaced by this run: AD-22's `request-approval` bundle carried no audit write while AD-12 requires one for a consequential attempt; its `promote-baseline` bundle omitted the agent-run resume AD-7's own state diagram draws; and it enumerated no rejection bundle at all. The parent's AD-22 Rule now carries all three, with its AD ID unchanged and the prior 2026-07-22 wording preserved in an Amendment note beside it. EAD-6 therefore implements the parent as it now stands.
- **Stories 4.4–4.6 inherit, not re-decide:** 4.4's provenance projection reads the three-role identity model and AD-3's non-disclosing not-found; 4.5's proof matrix must cover the spine's seven verification obligations (initial promotion, replacement, stale/expired/rejected, reconnect, idempotent replay, transaction rollback, audit integrity), each with a demonstrated-red case; 4.6's state matrix gains the new literal states and reasons, proven by automated coverage alone per the Accessibility Floor.
- **New schema is additive only, in one migration owned by Story 4.1:** `approval_request`, `site_baseline`, `audit_event`, and `agent_run.status_reason`. No existing table is renamed or repurposed; the `agent_run` status vocabulary is already in place.
- **Story 4.1 also reopens the `execute_turn.py` STOPGAP** by restoring the `approval_required` finalisation mapping and persisting the pending-call payload; the existing guard test is the tripwire that forces this to land with the first reachable approval capability rather than after it.

## Open questions (not silently answered)

1. **The approval expiry duration value** — fixed at Story 4.1 creation (supplier: `Settings`). Assumption: one site-wide duration, not per-request. D9 settles the mechanism around it; only the number is open.

Closed:

- *Whether changing the expiry duration bumps `policy_version`* — no. It is snapshotted to an absolute `expires_at` at TX1 (D9).
- *Parent AD-22 amendment* — accepted and applied 2026-08-27; the parent Rule now carries all three bundles.
- *The `persisted_event` stream-owner CHECK* constrains only `conversation_id`/`schedule_run_id` and not `agent_run_id`, so riding the conversation stream is compatible with the schema as it stands — this needed no deferral to Story 4.3.
