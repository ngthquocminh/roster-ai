---
baseline_commit: 946b5ec1c4c5e1f84623d77910c2a584ec2dcd1d
---

# Story 4.3: Promote the Baseline Atomically with Audit

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want a valid approval to promote exactly one existing candidate once,
So that the operational baseline and its authoritative decision record cannot diverge.

**This story owns TX2 and nothing else on the decision endpoint.** EAD-10 is explicit:
*"there is exactly one decision endpoint. **Story 4.2 owns it and implements TX3 in full** …
**Story 4.3 owns TX2 only**, invoked as the approve branch of that same endpoint; it adds no
second route and no second reject path."*

**It is the epic's keystone: the first and only story that moves the site baseline pointer.**
Everything before it was preparation — 4.1 created the tables and the binding, 4.2 built the
endpoint, the shared revalidation fork, and every terminal outcome except `consumed`.

**Depends on, and consumes:** Story 4.2's entire decision substrate — `decide_approval`,
`revalidate_binding` (**imported, never rewritten**), `DecisionResultV1`,
`ApprovalRepository.terminalize`, `cancel_agent_run_for_approval`,
`POST /api/v1/approvals/{approval_id}/decision`, `_ERROR_STATUS` / `_DECISION_DETAIL` /
`_DECISION_RESPONSES`, `ApprovalDecisionPanel`, `useApproval`, `useDecideApproval`; Story 4.1's
`d4e5f6a7b8c9` migration (including the `site_baseline` INSERT + four-column UPDATE grants
already landed **for this story**), `ApprovalBindingV1`, `AuditEnvelopeV1`,
`PostgresSiteBaselineReader`, `PolicyInputsV1` / `derive_policy_version`,
`scheduling_baseline` capability and its persisted `pending_payload`; Story 3.8's
`calculate_comparison`; Story 2.1's `AgentTurnRequestV1.approvals` →
`_to_deferred_results` seam.

**Unblocks:** Story 4.4 (a `consumed` binding, an `approval_consumed` audit row, and a real
before/after version pair to project provenance from), Story 4.5 (the rollback, replay, and
audit-uniqueness fixtures its proof suite drives), Story 4.6 (the `consumed` state and the
resumed-run transitions its state matrix asserts).

**Scope summary:** **One additive migration** (widen `ck_audit_event_outcome` by one member —
Decision 7). One new use case (`promote_baseline`, TX2). Three new repository methods
(`ApprovalRepository.consume`, `SiteBaselineWriter.promote`,
`ConversationRepository.resume_agent_run_for_approval`), one new port
(`MembershipReader`), one new arm on the **shared** `revalidate_binding`. One new optional
parameter on `execute_turn`. One fail-closed guard in `calculate_comparison` (EAD-8). No new
route, no new reject path, no new revalidation. **No new dependency. No new setting. No new
golden case. No evidence file** — see Task 12.

**This story is the first in the repository to:**

1. **write a `site_baseline` row.** The table has existed since 4.1 and has only ever been
   read; `PostgresSiteBaselineReader` is read-only and there is no writer anywhere.
2. **reach `ApprovalRequestState = consumed`.** Story 4.2's Completion Notes: *"`consumed`
   remains an unreachable stored state until Story 4.3."*
3. **write a non-success (`success=False`) audit row.** `uq_audit_event_failure_attempt` has
   existed unused since 4.1, whose `SCOPE_CONTROLS` read
   `audit:non_success_outcomes_owned_by_story_4_3`.
4. **supply `AgentTurnRequestV1.approvals`.** `_to_deferred_results` (`agent/runtime.py:407`)
   is fully implemented and has **zero producers** — verified by exhaustive grep across
   `application/`, `api/`, and `agent/`.
5. **move an `agent_run` out of `approval_required` on the approve edge**
   (`--> agent_running: decision recorded`, AD-7). 4.2 only ever took the cancel edge.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| **Story 4.3 owns TX2 only, as the approve branch of Story 4.2's endpoint. It adds no second route, no second reject path, and no second revalidation** | EAD-10; ADR-4 D7; Story 4.2 *"What Story 4.3 inherits"* item 1 |
| **TX2 = revalidation + `pending → consumed` + `site_baseline` CAS + audit + event + run resume**, in one transaction. Any failure rolls the whole bundle back and returns the binding to `pending` with no baseline change | EAD-6; AR22 (`epics.md:168`); AD-22 as amended 2026-08-27 |
| **The `effect_key` for all three bundles is the binding's own key**, disambiguated by the closed outcome vocabulary; `(site_id, effect_key, outcome)` uniqueness therefore makes a **second pointer movement structurally impossible** | EAD-6; AD-12 (`ARCHITECTURE-SPINE.md:154-158`); AR12 (`epics.md:158`) |
| **An absent `site_baseline` row is the valid "no baseline" state.** `baseline_version = null` means *expects absence*: promotion revalidates that no row exists and **inserts the first one**. A non-null value names the exact baseline being replaced: promotion revalidates it by **compare-and-set on `site_baseline.resource_version`**. Any mismatch in either direction is a business mismatch and marks the binding `stale` — never a silent rebase, never a second candidate | EAD-2 |
| **Revalidation is one shared step with a fixed fork:** any *business* mismatch terminalizes to `stale` (or `expired`) and never retries; only a **transactional or infrastructure write fault** rolls the bundle back, leaving the binding `pending` for an honest retry | EAD-10; ADR-4 D7 |
| **EAD-10's membership check is the INITIATING actor's current active site membership** — not the deciding actor's, not separation of duties. TX1 snapshots `initiated_by_actor_id` and `site_id`; inside the TX2/TX3 command transaction the shared `revalidate_binding` asks a **server-owned transactional membership reader** whether a row exists for that pair with `revoked_at IS NULL`. Absence is a business mismatch → `stale` / `approval_stale`, zero baseline effect | EAD-10 *Membership referent and supplier* (added at commit `32d9320`); `deferred-work.md` 4.2-review entry, **Owner: Story 4.3** |
| **The DECIDING actor is a different guard**, enforced at the session layer: `auth.resolve_session` INNER JOINs active membership, so a revoked member is 401 before any route body runs. It must **not** be reimplemented inside `revalidate_binding` — terminalizing on behalf of an actor who has lost access lets a revoked actor mutate governance state, where the correct answer is refusal | EAD-10 *Deciding actor is a different guard*; Story 4.2 inheritance item 5 |
| **On approve, the promotion transaction records the decision and returns the run to `agent_running`** (AD-7's "decision recorded" edge); the run is then driven to a terminal state through the **existing owned seam** — the persisted decision supplied as a server-owned `AgentApprovalDecisionV1` in `AgentTurnRequestV1.approvals` on a resumed turn, finalising through the normal `execute_turn` path. **No new resume mechanism, and no run may be left non-terminal once its binding is terminal** | EAD-5; ADR-4 D5 |
| **Terminalizing outcomes are RETURNED, never raised**, because `get_site_context` commits when the handler returns and rolls back when an exception escapes | Story 4.2 Decision 9 + inheritance item 2; `api/deps.py:get_site_context` |
| **`DecisionResultV1.activity` carries a STATED `agent_run_status`, not an inferred one.** TX3 passes `agent_cancelled`; **TX2 must pass `agent_running`** and must not fall back to the `approval_required` default, which describes the state before the transaction | Story 4.2 inheritance item 4; `adapters/postgres/conversation.py:_append_approval_activity` |
| **Delete `promotion_not_available` from `_ERROR_STATUS`, `_DECISION_DETAIL`, and the `503` entry in `_DECISION_RESPONSES`**, remove `BaselinePromotionNotAvailableError` and `SCOPE_CONTROLS["promotion"]`, and drop the 503 rows from `docs/API.md`. Missing any one leaves a published contract advertising a status the route can no longer emit | Story 4.2 inheritance item 3 |
| **From Story 4.3 on, any comparison or approval-review rendering whose frozen `baseline_schedule_version` is non-null while the baseline assignment supply for that exact version is not authoritatively readable must fail closed with a distinct outcome — never render an empty read as "the baseline is empty".** Epic 4 moves the pointer as **metadata only**; it does not wire `get_baseline_assignments`. **Pointer movement does activate Story 3.8's staleness detection, discharging its "vacuously false in production" deferral** | EAD-8 |
| Successful mutation audit is unique on `(site_id, effect_key, outcome)`; **non-success audit is unique on `(site_id, attempt_id)`**. Each accepted attempt has a server-generated `attempt_id`. **Telemetry can never authorize, block, or substitute for audit** | AD-12; AR12 (`epics.md:158`) |
| Successful mutations must write audit evidence **in the business transaction where possible**; **denied and failed** consequential attempts must be recorded **reliably and separately** | NFR31 (`epics.md:135`) |
| Produce unsampled, append-only, site-scoped authoritative evidence for **successful, denied, stale, failed, and cancelled** consequential actions **independently of observability** | FR21 (`epics.md:65`) |
| Atomically consume valid approval, change the baseline pointer **once**, persist authoritative audit and event evidence, and **preserve prior schedule versions** for inspection or separately approval-gated re-promotion | FR19 (`epics.md:61`) |
| Baseline promotion, schedule versioning, successful authoritative audit, and the resulting persisted event **must share one consistency boundary** | NFR9 (`epics.md`, NFR list) |
| One hundred percent of operational-baseline promotions must require **valid parameter- and version-bound approval** | NFR8 (`epics.md`, NFR list) |
| Approval is a **one-time persisted state machine with no approved-but-unconsumed state**; approve, revalidate, consume, promote, audit, and emit the event **atomically or leave the request pending** | AR10 (`epics.md:157`) |
| Each mutating HTTP command requires an idempotency key scoped to actor, site, operation, and canonical body hash plus expected resource version; a replay returns the original semantic result and a conflicting body fails | AD-8; AR8 (`epics.md:154`) |
| Schedule versions are **immutable**; the site baseline is a **versioned pointer** and stale inputs fail closed without silent rebasing | AR9 (`epics.md:156`) |
| A setting **snapshotted into the binding at TX1** is immune and never bumps `policy_version`; only settings consulted at **TX2/TX3 revalidation** version the policy, enumerated in the frozen `PolicyInputsV1` | EAD-12; ADR-4 D9 |
| `stale`/`expired`/terminal-replay failures return **RFC 7807 problem details carrying literal expected/current context**; denied, stale, expired, and conflicting remain **distinct codes** | Epic 4 spine *Consistency Conventions* (Errors row); AD-13 |
| Approval lifecycle events ride the **conversation stream** anchored to the paused agent run; **no new stream kind**. Every persistable `ActivityTypeV1` discriminant needs a `STREAMED_ACTIVITY_EVENTS` listener | Epic 4 spine *Consistency Conventions*; `deferred-work.md` 4.2-review SSE-listener entry |
| Terminal outcomes expose **only valid next actions**; state is **text, not colour alone**, and durable transitions announce once through a polite live region | UX-DR13 (`epics.md:202`); `EXPERIENCE.md:189`; UX-DR32 (`epics.md:240`) |
| Manual assistive-technology verification is **out of scope**; automated coverage is the **only accepted proof** | `EXPERIENCE.md:196` (Accessibility Floor) |
| Every new guard must be **observed failing** with its structural assertion removed or a relevant mutation applied, before it is trusted | epic-3 retro §1 *Challenges*, §3 preparation task |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |

**`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments, and it constrains
one thing here: what the promotion and the post-promotion comparison may claim.**
`outbound`/`inbound` demand is measured in **volume**, `indirect` in **headcount**, and
assignments carry worker identity but **no family**. This story renders no new demand-derived
figure: the consequence summary is the literal text 4.1 hashed and 4.2 renders, and the audit
`safe_summary` is that same string. The one place the rule bites is **Decision 9** — the
post-promotion comparison reads `get_baseline_assignments`, which is assignment-side and
therefore family-agnostic; the guard is about the *supply being empty*, never about a family.
Do not re-derive the family/unit rule from adapter code; cite the document.

---

## Acceptance Criteria

Verbatim from `epics.md:1208-1228`.

1. **Given** a valid pending approval, **When** Approve as baseline is processed, **Then** the
   deciding actor/site/active membership is re-resolved from the authenticated server session
   as the command-admission guard, and the shared command-transaction revalidation checks that
   the initiating actor identified by the binding still has an active membership in the
   binding's site, plus policy, binding hashes, candidate feasibility/version, baseline
   version, expiry, and idempotency, **And** a client boolean or prior UI state is never
   sufficient authorization. (FR18, NFR8)

2. **Given** all revalidation passes, **When** the transaction commits, **Then** the approval
   moves directly from pending to consumed, the site baseline pointer moves to the existing
   candidate, one successful audit envelope and persisted event are written, and prior schedule
   versions remain unchanged, **And** any failure rolls back the entire bundle to pending with
   no baseline change. (FR19, NFR9, AR10, AR22)

3. **Given** a retry or recovered command after successful promotion, **When** the same effect
   key is processed, **Then** uniqueness returns the original semantic result and cannot create
   another candidate, audit outcome, event, or pointer movement, **And** a different
   body/version is rejected. (FR19, NFR6, AR8)

4. **Given** successful, denied, stale, failed, cancelled, rejected, or expired consequential
   attempts, **When** authoritative evidence is recorded, **Then** successful mutation audit is
   transactionally unique by site/effect/outcome and non-success audit is reliably unique by
   site/attempt, **And** observability being disabled cannot remove or prevent the record.
   (FR21, NFR31, AR12)

---

## Twelve decisions were made at story creation — do not re-litigate them

> **Authoring rule in force from this story (commit `2cf598f`):** every Decision below states,
> in one sentence, what its mechanism does **not** cover. Tasks cite these Decisions; they do
> not re-argue them.

### Decision 1 — `promote_baseline.py` holds TX2; `decide_approval` calls it on the approve-and-valid branch

The Structural Seed names `application/use_cases/promote_baseline.py` and Story 4.2
deliberately did **not** create it, *"not even as a stub — an empty module invites the next
session to assume it is owned."* Create it here.

`decide_approval`'s existing approve-and-valid branch currently reads:

```python
if command.decision == "approve":
    # Story 4.3 owns TX2; do not write a speculative promotion body.
    raise BaselinePromotionNotAvailableError("Baseline promotion is not available yet.")
```

Replace **exactly that raise** with a call to `promote_baseline(...)`, which returns a
`PromotionResultV1`. `decide_approval` keeps ownership of admission checks, revalidation, and
TX3; `promote_baseline` owns the consume → CAS → audit → event → resume bundle and nothing else.

**Does not cover:** `promote_baseline` performs **no** revalidation of its own and has **no**
reject, expire, or stale branch — it is only ever reached after `revalidate_binding` returned
`outcome is None` and the decision is `approve`. A caller reaching it otherwise is a bug, and
it asserts that rather than re-deriving the verdict.

### Decision 2 — `revalidate_binding` gains the initiating-actor membership arm, and this changes TX3 as well

EAD-10's *Membership referent and supplier* paragraph and the ledger entry that names this
story as owner both require it. Add a `MembershipReader` port
(`application/ports/membership.py`) with a single method:

```python
def has_active_membership(self, connection, *, app_user_id: UUID, site_id: UUID) -> bool: ...
```

and `PostgresMembershipReader` (`adapters/postgres/membership.py`) implementing it as a
`SELECT 1 FROM membership WHERE app_user_id = :a AND site_id = :s AND revoked_at IS NULL`.
Keyed **only** on `binding.initiated_by_actor_id` and `binding.site_id`; no client value and no
membership identifier is accepted. Wire it through `api/deps.py` as
`get_membership_reader`, and pass it into `decide_approval` → `revalidate_binding`.

An inactive or missing row is a **business mismatch**: `RevalidationV1("stale", …)` with
`{"initiating_actor_membership": "active"}` expected and `{"initiating_actor_membership":
"revoked_or_absent"}` current. It joins the existing `valid = …` conjunction; it does **not**
get its own early return, because the fork has exactly two arms and a third would be a second
revalidation in disguise.

**This is a shared function, so it changes Story 4.2's behaviour too**: a *reject* against a
binding whose initiator lost membership now terminalizes as `stale` / `approval_stale` instead
of `rejected`. That is what EAD-10 asks for and it must be asserted, not discovered.

Remove `SCOPE_CONTROLS["membership"]` from `decide_approval.py` in the same change — its text
still records the superseded deciding-actor reading and the now-answered Open Question 2.

**Does not cover:** the **deciding** actor — enforced at `auth.resolve_session` and explicitly
forbidden from being re-checked here (a revoked decider must be refused, not permitted to
stale a binding); and separation of duties, which stays deferred with no owner.

### Decision 3 — `ApprovalRepository.consume` is a second compare-and-set, not a widened `terminalize`

`terminalize` sets `state`, `decided_by_actor_id`, `decided_at`, and bumps `resource_version`.
It deliberately leaves `consumed_at` `NULL` (4.2 Decision 11: *"that field is TX2's"*). Add:

```python
def consume(self, connection, *, approval_id, site_id, decided_by_actor_id, decided_at,
            expected_resource_version) -> ApprovalBindingV1 | None: ...
```

implemented as `UPDATE approval_request SET state='consumed', decided_by_actor_id=…,
decided_at=…, consumed_at=…, resource_version=resource_version+1 WHERE id=… AND site_id=… AND
state='pending' AND resource_version=… RETURNING *`. A `None` return means another decision won
the race → `409 approval_not_pending`, never a 500 (the same rule 4.2 Trap 9 set).

`state='consumed'` is hardcoded in the method, not a parameter: the CHECK constraint admits
five states and a parameterised `consume` would be `terminalize` with a different name.

**Rejected alternative — add a `consumed_at` parameter to `terminalize`.** It would make one
method serve two vocabularies (`consumed` vs. the three cancellation outcomes) and every 4.2
test that pins `consumed_at is None` after a rejection would then be asserting a default rather
than a decision.

**Does not cover:** the pointer. `consume` writes the `approval_request` row only; a consumed
binding with no pointer movement is possible **only** inside an uncommitted transaction, and
Decision 5's rollback rule is what keeps it that way.

### Decision 4 — `SiteBaselineWriter.promote` does insert-when-absent and CAS-when-present, in one method

New port `SiteBaselineWriter` beside the existing reader in
`application/ports/site_baseline.py`:

```python
def promote(self, connection, *, site_id, schedule_version_id, actor_id, occurred_at,
            expected_resource_version: int | None) -> SiteBaselineV1 | None: ...
```

`expected_resource_version is None` means EAD-2's *expects absence*: `INSERT … ` with
`resource_version = 1` and `updated_by_actor_id = actor_id`. `updated_by_actor_id` is
`NOT NULL` with an FK to `app_user` — supply the **deciding** actor, which is what
`decided_by_actor_id` on the binding also records.

Non-`None` means EAD-2's *names the exact baseline*: `UPDATE site_baseline SET
schedule_version_id=…, resource_version=resource_version+1, updated_at=…,
updated_by_actor_id=… WHERE site_id=… AND resource_version=:expected RETURNING *`, returning
`None` when it matched nothing.

Both branches carry an explicit `site_id` predicate, matching the convention
`PostgresApprovalRepository`'s docstring states. Both are already covered by 4.1's grants —
`_secure()` granted `SELECT, INSERT` and line 118 granted `UPDATE (schedule_version_id,
resource_version, updated_at, updated_by_actor_id)`, landed for this story by name. **Verify
that under `shiftmind_runtime` with a `@pytest.mark.postgres` test rather than by reading the
migration** (Task 10) — 4.1 Trap 4 and 4.2 Decision 11 are both about exactly this.

An `IntegrityError` on the insert branch (`uq_site_baseline_site` lost the race) is treated
identically to a `None` CAS return.

**Does not cover:** reverting a pointer, and any read of the promoted version's assignments —
the spine's Deferred table and EAD-8 keep both out (Decision 9).

### Decision 5 — a TX2 failure must ESCAPE THE ROUTE HANDLER, and "raise it and catch it in the router" does not achieve that

TX2 is the mirror image of TX3: 4.2 Decision 9 **returns** its terminal outcomes so they commit,
because a stale/expired outcome already wrote a terminal binding it must keep. **Nothing in the
promotion bundle may survive a partial failure** (FR19, NFR9, AR10, AR22).

**The mechanism is not symmetric, and this is the trap.** `get_site_context` is a
generator dependency: `with site_context(...) as connection: yield connection`. It rolls back
only when an exception propagates **out of the endpoint function**. A route body that catches an
exception and `return`s a problem response resumes the generator normally, and
`with engine.begin()` **commits everything written before the failure**. Catching in the router
and returning is therefore indistinguishable, at the database, from success.

**This is already latently wrong in inherited code, and Task 4 fixes it.**
`api/routers/approvals.py`'s `except AgentRunNotQueuedError` arm carries the comment *"Nothing
is committed — the exception propagates out of `decide_approval` and `get_site_context` rolls
the whole bundle back"*. It does not: `decide_approval` runs `terminalize` **before**
`cancel_agent_run_for_approval`, so on that arm today a binding is terminalized and committed
while the agent run stays `approval_required` and **no audit row and no event are written** —
precisely the partial commit EAD-6 forbids. Its test
(`test_an_uncancellable_agent_run_is_a_typed_conflict_not_a_500`) monkeypatches `decide_approval`
away and asserts only status and code, so nothing caught it.

So, for every TX2 failure mode:

| Situation | Mechanism | Result |
|---|---|---|
| `consume` returns `None` (concurrent decision) | raise `ApprovalNotPendingError`, **let it escape the endpoint** | rollback, 409, binding untouched by us |
| `promote` returns `None` or raises `IntegrityError` (pointer moved under us) | raise `BaselineConcurrentlyMovedError` (`code = "stale_baseline_version"`, already in `_ERROR_STATUS` at 409), **let it escape** | rollback → binding stays `pending`; the planner's retry re-revalidates and gets the honest `stale` |
| any `DBAPIError` inside the bundle | let it propagate | same rollback, binding `pending` — EAD-10's second fork arm |
| the resume write finds the run outside `approval_required` | let `AgentRunNotQueuedError` escape | rollback, `409 agent_run_not_cancellable` |
| every write succeeded | **return** `PromotionResultV1` up to the router, which returns `200` | the bundle commits |

**"Let it escape" is implemented as a registered FastAPI exception handler**, not as a
`try/except` in the route. `api/main.py` already registers handlers for
`RequestValidationError`, `HTTPException`, and bare `Exception`; add one for the decision
endpoint's rollback-required errors that emits the same RFC 7807 `problem_response(...)` shape
with the same stable codes. The handler runs **after** the dependency's context manager unwinds,
so the rollback has already happened by the time the body is written. Nothing about the wire
contract changes — only where the response is produced.

**Task 4 therefore also moves the existing `AgentRunNotQueuedError` arm** out of the route's
`except` and into that handler, and corrects its comment. Leaving it where it is would keep a
partial TX3 commit shipping while TX2 claims atomicity beside it.

**Rejected alternative — `connection.rollback()` inside the except arm.** `engine.begin()`
opens its own transaction and its `__exit__` would commit a fresh empty one afterwards; it
"works" only by accident and hides the rule in a place no future reader looks.

**Rejected alternative — convert a lost pointer CAS into `stale` inside TX2.** It would commit
a `consumed` binding alongside a problem body saying the approval is stale: two durable
statements about one binding that contradict each other.

**Does not cover:** the non-writing refusals. `approval_not_pending` raised by the *admission*
checks, `stale_resource_version`, `approval_not_found`, and `idempotency_key_conflict` are all
detected **before any write**, so the transaction is healthy and the router keeps catching and
returning them — which is also what lets Decision 7's denial audit row commit. Only the
**post-write** failures need to escape. Two `ApprovalNotPendingError` sites therefore behave
differently by design; Task 3 must make which is which explicit at both raise sites.

### Decision 6 — the success audit row is `approval_consumed`, keyed on the binding's own effect key, with a real before/after pair

One row, in the bundle:

- `outcome = "approval_consumed"`, `success = True`
- `effect_key = binding.request_effect_key` — **never a fresh `uuid4()`**, the defect 4.1's
  review caught and 4.2 Decision 4 restated. With `uq_audit_event_success_effect` on
  `(site_id, effect_key, outcome)`, a second promotion of the same binding is **structurally
  impossible**, which is precisely EAD-6's claim and AC3's mechanism.
- `before_version = binding.baseline_schedule_version` (may be `None` — first promotion)
- `after_version = str(binding.candidate_schedule_version_id)` — **the first non-`None`
  `after_version` in the repository.** Every audit row written so far sets it `None`.
- `decided_by_actor_id = <session principal>`, `initiated_by_actor_id =
  binding.initiated_by_actor_id`, `attempt_id = uuid4()`, `safe_summary =
  binding.consequence_summary`, hashes and `policy_version` copied from the binding.

TX1's `approval_requested` row for the same `effect_key` coexists — the outcome discriminator is
what separates them, and a test must prove that (Task 10).

**Does not cover:** any non-success outcome. Those are Decision 7's, and they use a different
uniqueness index.

### Decision 7 — AC4's "denied" gets ONE new closed-vocabulary member and one additive migration; "failed" is explicitly Story 4.5's

This settles **Story 4.1 Open Question 1**, carried unanswered through 4.2 and named as 4.3's:
*does EAD-6's closed audit-outcome vocabulary need a `denied` member?* **Yes, exactly one.**

`ck_audit_event_outcome` admits five outcomes, none of which can express a refused attempt, and
`uq_audit_event_failure_attempt` — the `(site_id, attempt_id)` index AC4 names by shape — has
existed unused since 4.1. FR21 requires evidence for denied actions and NFR31 requires it
"reliably and separately". Ship a **new additive migration** adding `approval_denied` to the
CHECK. **Do not edit `d4e5f6a7b8c9`** (merged and applied) — 4.2 Decision 11's rule.

**Add exactly one member, not two.** An `approval_failed` member has no writer in this story
(see the boundary below) and would ship as dead vocabulary — the pattern this repo's retro
names as its most expensive.

**Which refusals write a denial row:** exactly the **pre-write** refusals where a binding **in
this site was resolved** — `approval_not_pending` raised by the admission checks, and
`stale_resource_version`. Written with `success=False`, a fresh `attempt_id`,
`outcome="approval_denied"`, and the binding's own identifiers; `after_version` is `None`.

**Which do not, and why:**

- `approval_not_found` — no binding was resolved, and AD-3's non-disclosing shape means a
  cross-site probe must leave no trace in the probed site.
- the router's `enabled_feature_policy` pre-check — it runs before any binding is read.
- **`stale_baseline_version`, and every other Decision 5 post-write failure.** They roll the
  transaction back, so a denial row written inside it rolls back with them. This is the same
  boundary as the write-fault gap below, and it is why Decision 5's split between pre-write and
  post-write refusals is load-bearing here and not merely tidy.

**How it commits:** these refusals are detected **before any write**, so the request's own
transaction is healthy. The router's existing `except DecideApprovalError` arm writes the
denial row and then **`return problem_response(...)`** — Decision 9 of Story 4.2, reused for a
second purpose. No second connection is needed, and "separately" in NFR31 is satisfied by the
separate uniqueness index and the `success=False` discriminator, not by a separate transaction.

**Does not cover — and this is an honest gap, not an oversight:** a **write fault** mid-bundle
("failed" in AC4's list) writes no audit row at all, because any row written inside the failing
transaction rolls back with it and recording it would require a second connection opened after
the rollback. Story 4.5's AC2 owns database-failure-during-the-promotion-bundle by name; the gap
is recorded in the ledger with that owner (Task 13).

### Decision 8 — the run resume is TX2's status write plus **one** post-commit turn through the existing seam

EAD-5 and EAD-6 both put "run resume" inside TX2, and EAD-5 forbids inventing a second
mechanism. Split it exactly where the transaction boundary is:

**Inside TX2** — new `ConversationRepository.resume_agent_run_for_approval(connection, *,
agent_run_id, binding, request_id, occurred_at)`, beside `cancel_agent_run_for_approval`:

- **Lock order is `conversation`, THEN `agent_run`** — the order `finish_agent_run`,
  `pause_agent_run_for_approval`, and `cancel_agent_run_for_approval` all take. 4.1's review
  caught the ABBA deadlock from getting this backwards.
- guards `current.status == "approval_required"`, raising `AgentRunNotQueuedError` otherwise
- writes `status="agent_running", status_reason=None` in one `UPDATE` — clearing the reason is
  required: `status_reason` names a **binding** outcome (EAD-5) and this binding was consumed,
  not cancelled
- appends the Decision 5 activity via `_append_approval_activity` with
  **`agent_run_status="agent_running"`** explicitly (Story 4.2 inheritance item 4), and bumps
  `conversation.resource_version`

**After the transaction commits** — the route drives exactly one resumed turn on a background
thread, the same shape `api/routers/conversations.py` already uses for the initial turn:
`execute_turn(..., approvals=(AgentApprovalDecisionV1(tool_call_id=<from the persisted
pending_payload>, approved=True),), history=<the payload's owned `AgentTurnV1`>)`, then
`finalize_agent_run` on the existing path. `execute_turn` gains **one** optional parameter
(`approvals: tuple[AgentApprovalDecisionV1, ...] = ()`), passed straight into the
`AgentTurnRequestV1` it already builds; `_to_deferred_results` (`agent/runtime.py:407`) does the
rest and is already complete.

Reading the payload needs one more repository method:
`ApprovalRepository.get_pending_payload(connection, *, approval_id, site_id) -> dict | None`.
`create_pending` already writes the column and nothing reads it.

**The planner-initiated path has `binding.agent_run_id is None` and resumes nothing.** That is
the majority path today and it must be the guard — never "the payload is absent", which is a
different condition.

**A failure of the resumed turn does not touch the promotion.** The pointer, the consumed
binding, and the audit row committed before the turn started; a failing turn finalises through
the existing `failed_outcome_for_exception` path, exactly as the initial turn does.

**Does not cover:** `AgentApprovalDecisionV1(approved=False)`. EAD-5 cancels the run on every
non-consumed outcome, so the denial branch of that contract still has no producer and the
ledger entry saying so stays open.

### Decision 9 — EAD-8's fail-closed guard lands in `calculate_comparison`, in this story, because this story is what makes it necessary

Today `PostgresScenarioProjectionReader.get_baseline_assignments` calls `_apply_query((), …)` —
a **hardcoded empty tuple**, not an empty fixture — and
`ScenarioOverviewV1.baseline_schedule_version` reads `site_baseline`, which is empty. So
`calculate_comparison`'s `baseline` is `()`, every candidate assignment lands in
`added_worker_ids`, and that is *truthful* while there is no baseline.

**The moment this story's first promotion commits, that same code claims every assignment is
net-new against a real baseline.** That is the exact hazard EAD-8 exists for, and EAD-8 binds
it to Story 4.3 by name.

Add `BaselineSupplyUnavailableError` to `application/scheduling/comparison.py`, raised when
`expected_baseline_schedule_version is not None` **and** the drained baseline assignment page is
empty. `api/routers/schedule_runs.py` maps it to a **distinct** problem code
`baseline_supply_unavailable` (409) with literal detail naming the version whose supply could
not be read. The frontend renders that literal text where the comparison would be, and offers
only currently valid actions (UX-DR13).

Update `comparison.py`'s `SCOPE_CONTROLS` to record the guard, and narrow its existing
"NOT COVERED: non-empty production baselines need authoritative wages and selected shift
windows" line to say the guard now refuses rather than under-reporting.

**Does not cover:** wiring a real supply. The spine's Deferred table keeps that out of Epic 4
("first story needing authoritative baseline-side metrics after a real promotion"), and it also
requires Story 3.8's wage and selected-shift prerequisites. This guard is deliberately coarse
today — *any* non-null baseline is unreadable — and narrows on its own the moment a real supply
lands.

**This is also what discharges `deferred-work.md`'s "comparison staleness is vacuously false in
production" entry, whose owner is this story**: pointer movement makes
`expected != current` reachable. Close it on the pointer, not on the guard (Task 13).

### Decision 10 — the frontend changes are additive; the approve control, dialog, and accessible names are untouched

Story 4.2 shipped the Approve control, the named dialog, the consequence-bearing accessible
name, focus restoration, the polite live region, and the 44px targets — all accessibility-proven.
This story changes what happens **after** the request, and nothing else:

- `decisionFeedback` in `ApprovalDecisionPanel.tsx` gains a `consumed` success message naming
  the promoted version and the version it replaced, and **loses** its
  `promotion_not_available` case, which becomes unreachable.
- `useDecideApproval`'s `onSettled` gains invalidation of the run comparison / scenario overview
  keys, so the moved pointer is visible without a reload.
- `STREAMED_ACTIVITY_EVENTS` already lists `approval_request` (fixed at 4.2's review) — TX2's
  event rides the same discriminant, so **no new listener is owed**; assert it rather than
  assume it.
- The terminal branch already renders `Terminal approval state: {state}`; `consumed` flows
  through it. Extend the copy so a promoted binding says what moved, not just that it is
  terminal.

**Does not cover:** any restyling of "Approve as baseline", "Run optimization", or "Send". The
NFR19/UX-DR35 distinctness assertion is a *test* Story 4.2 already owns; this story must keep it
green, not rewrite it.

### Decision 11 — one migration, and it is the only one

The migration widens `ck_audit_event_outcome` by one member (Decision 7) and does nothing else.
`site_baseline` needs **no** migration: its table, its RLS policy, its `INSERT` grant, and its
four-column `UPDATE` grant were all landed by `d4e5f6a7b8c9` for this story.
`approval_request`'s `UPDATE (…, consumed_at, …)` grant likewise. `agent_run`'s
`UPDATE (status, status_reason)` grant covers the resume write.

`alembic check` **from the repository root** (`deferred-work.md:138-147`), expecting zero
operations and exactly **one** new migration file.

**Does not cover:** any grant that turns out to be missing. If Task 10's privilege assertions
find one, add it to **this** story's new migration — never edit `d4e5f6a7b8c9`.

### Decision 12 — Gate A: no new write path, one corrected claim

`test_gate_a_mutation_audit.py`'s `versioned` literal already carries
`("POST", "/api/v1/approvals/{approval_id}/decision")` — this story adds no route, so **no new
entry is owed**. But `docs/GATE-A-RUNBOOK.md:44` currently reads *"…it never moves the baseline
pointer"*, which this story makes false. Correct that row to state that the route moves the site
baseline pointer on the approve branch and records an authoritative `approval_consumed` audit
row in the same transaction.

**Does not cover:** any change to the Gate A invariant set or its readiness report. No AC here
carries a measured threshold (Task 12), so no new invariant and no evidence file is owed; Gate A
must still be re-run per AR28.

---

## Tasks / Subtasks

- [x] **Task 1 — Membership reader and the shared revalidation arm (AC: 1)**
  - [x] `application/ports/membership.py`: `MembershipReader` Protocol per Decision 2. SQL- and
        transport-free.
  - [x] `adapters/postgres/membership.py`: `PostgresMembershipReader`, explicit `site_id`
        predicate, `revoked_at IS NULL`.
  - [x] `api/deps.py`: `get_membership_reader`; wire it into the decision route and through
        `decide_approval` into `revalidate_binding`.
  - [x] Add the arm to `revalidate_binding`'s `valid = …` conjunction and to the `stale`
        expected/current context, per Decision 2. Update the function docstring's fork
        description.
  - [x] Delete `SCOPE_CONTROLS["membership"]` from `decide_approval.py` (Decision 2).

- [x] **Task 2 — Repository surface for TX2 (AC: 2, 3)**
  - [x] `application/ports/approval.py` + `adapters/postgres/approval.py`: `consume` per
        Decision 3, and `get_pending_payload` per Decision 8.
  - [x] `application/ports/site_baseline.py` + `adapters/postgres/site_baseline.py`:
        `SiteBaselineWriter.promote` per Decision 4. Keep the existing reader untouched.
  - [x] `application/ports/conversation.py` + `adapters/postgres/conversation.py`:
        `resume_agent_run_for_approval` per Decision 8, with the lock-order comment and the
        `status_reason=None` clear.
  - [x] `api/deps.py`: `get_site_baseline_writer`.

- [x] **Task 3 — `promote_baseline`: TX2 (AC: 1, 2, 3)**
  - [x] `application/use_cases/promote_baseline.py`. `PromotionResultV1` frozen dataclass:
        `binding: ApprovalBindingV1` (post-consume), `baseline: SiteBaselineV1`,
        `activity: ExecutedAgentRunV1 | None`, `resume: ResumeRequestV1 | None` (the
        `agent_run_id` + `tool_call_id` + owned history the route needs after commit).
  - [x] `BaselineConcurrentlyMovedError(DecideApprovalError)` with `code =
        "stale_baseline_version"` (Decision 5).
  - [x] The bundle, in this order, all in the caller's transaction, no repository commits:
        `consume` → `promote` → audit append → activity append → `resume_agent_run_for_approval`
        when `binding.agent_run_id is not None`.
  - [x] Every failure mode follows Decision 5's table. Put that table's rule in the module
        docstring and say **why** the mechanism is not symmetric with TX3's.
  - [x] Make the two `ApprovalNotPendingError` sites explicit at their raise points: the
        admission-check one is pre-write and is caught in the router (Decision 7 audits it); the
        `consume`-returned-`None` one is post-write and must escape (Decision 5).
  - [x] Audit envelope exactly per Decision 6.
  - [x] `SCOPE_CONTROLS` naming what TX2 does not cover:
        `audit:write_fault_outcomes_owned_by_story_4_5`,
        `baseline_supply:guarded_by_ead_8_not_wired`,
        `resume:denied_decisions_have_no_producer`.

- [x] **Task 4 — Wire TX2 into the one endpoint and retire the 503 (AC: 1, 2, 3, 4)**
  - [x] `decide_approval.py`: replace the `BaselinePromotionNotAvailableError` raise with the
        `promote_baseline(...)` call (Decision 1). Widen `DecisionResultV1.outcome` to include
        `"consumed"`, or return the promotion result alongside it — whichever keeps
        `DecisionResultV1`'s existing three-value contract honest for TX3 callers.
  - [x] Delete `BaselinePromotionNotAvailableError` and `SCOPE_CONTROLS["promotion"]`.
  - [x] `api/routers/approvals.py`: remove `promotion_not_available` from `_ERROR_STATUS`, from
        `_DECISION_DETAIL`, and remove the `503` entry from `_DECISION_RESPONSES` — **all three**
        (Story 4.2 inheritance item 3).
  - [x] `api/main.py`: register the rollback-required exception handler per Decision 5, emitting
        the same `problem_response(...)` shape and stable codes. **Move the existing
        `except AgentRunNotQueuedError` arm out of the route into it and correct its comment** —
        as shipped it claims a rollback the mechanism does not produce, and it lets a partial TX3
        commit (terminal binding, no audit, no event, run still `approval_required`).
  - [x] Denial audit on the `except DecideApprovalError` arm, for the two **pre-write** codes
        Decision 7 names and no others, then `return problem_response(...)`.
  - [x] Post-commit resume drive per Decision 8, on the existing background-thread shape.
  - [x] Idempotency is unchanged: the existing `_store_idempotent_result` path stores the `200`
        `ApprovalOut`, and a replay re-derives presented state. Assert AC3 against it rather than
        adding a second mechanism.

- [x] **Task 5 — The resumed turn (AC: 2)**
  - [x] `execute_turn` gains `approvals: tuple[AgentApprovalDecisionV1, ...] = ()`, passed into
        the `AgentTurnRequestV1` it already constructs (Decision 8). No other signature change.
  - [x] The route builds `AgentApprovalDecisionV1(tool_call_id=…, approved=True)` from the
        persisted `pending_payload`'s single pending call, and supplies that payload's owned
        `AgentTurnV1` as history.
  - [x] Finalise through the existing `finalize_agent_run` path; a failing resumed turn must not
        touch the committed promotion.

- [x] **Task 6 — EAD-8 fail-closed comparison guard (AC: 2)**
  - [x] `application/scheduling/comparison.py`: `BaselineSupplyUnavailableError` per Decision 9,
        plus the `SCOPE_CONTROLS` update.
  - [x] `api/routers/schedule_runs.py`: map it to `409 baseline_supply_unavailable` with literal
        context naming the unreadable version. Never `str(exc)`.
  - [x] Frontend: render the literal reason where the comparison would be; offer only currently
        valid actions.

- [x] **Task 7 — Migration (AC: 4)**
  - [x] One additive migration widening `ck_audit_event_outcome` with `approval_denied`
        (Decision 7/11). Drop and recreate the named constraint; `downgrade` restores the
        five-member form.
  - [x] `uv run alembic check` from the repository root: zero operations, exactly one new file.

- [x] **Task 8 — Docs and Gate A (AC: 2, 4)**
  - [x] `docs/GATE-A-RUNBOOK.md`: correct the decision-route row per Decision 12.
  - [x] `docs/API.md`: drop the three `promotion_not_available` / 503 references
        (`:527`, `:532`, `:558`); document the `200 consumed` response, the new
        `baseline_supply_unavailable` code, and the denial-audit behaviour.
  - [x] No `docs/CONFIGURATION.md` change — this story adds no setting.

- [x] **Task 9 — Proof: use case and revalidation (AC: 1, 2, 3)**
  - [x] `backend/tests/test_promote_baseline.py` (fake repositories): first promotion into an
        absent baseline (insert, `resource_version = 1`); replacement against an exact existing
        baseline (CAS); `consume` returning `None` → `ApprovalNotPendingError`, **no pointer
        write**; `promote` returning `None` → `BaselineConcurrentlyMovedError` and **nothing
        committed**; a `DBAPIError` at the **audit** append and again at the **event** append —
        not only at the first statement, which is the weak point 4.2's review caught.
  - [x] Both initiator paths: `agent_run_id` set → run resumed to `agent_running` with
        `status_reason` cleared and the activity carrying `agent_run_status="agent_running"`;
        `agent_run_id` `None` → **no `agent_run` write at all**.
  - [x] `test_decide_approval.py` (extend): the membership arm — active initiator passes;
        revoked and absent initiators terminalize to `stale` on **both** an approve and a
        **reject** attempt (Decision 2's cross-story consequence).
  - [x] Every 4.2 revalidation test still passes with the new argument threaded through.

- [x] **Task 10 — Proof: real PostgreSQL (AC: 1, 2, 3, 4)**
  - [x] `backend/tests/test_approval_governance_postgres.py` (extend, `@pytest.mark.postgres`):
        TX2 end-to-end through the real `Postgres*` adapters on both initiator paths — binding
        `consumed` with `consumed_at` set, `site_baseline` row present and pointing at the
        candidate, exactly one `approval_consumed` audit row, exactly one `persisted_event`.
  - [x] **Decision 6's uniqueness proof:** a second `(site_id, effect_key, 'approval_consumed')`
        row is refused by `uq_audit_event_success_effect` while the story-4.1
        `approval_requested` row **for the same effect key** is still admitted.
  - [x] **AC2's "prior schedule versions remain unchanged":** assert
        `has_table_privilege` shows **no** `UPDATE`/`DELETE` on `schedule_version` for
        `shiftmind_runtime`, and assert the pre-promotion version rows are byte-identical after.
        Prove it by grant, not by re-reading a row nothing tried to change.
  - [x] **Decision 4's grant proof:** run the `site_baseline` insert and CAS as
        `shiftmind_runtime` and assert both succeed; assert `has_table_privilege` for `INSERT`
        and for `UPDATE (schedule_version_id)`. Observe red by revoking in a rolled-back
        transaction.
  - [x] **AC3:** replay the same `Idempotency-Key` and body after a successful promotion →
        original semantic `200`, and **still exactly one** audit row, one event, one pointer
        `resource_version`. A different body under the same key → `409
        idempotency_key_conflict`. A new key against the now-`consumed` binding → `409
        approval_not_pending` with literal expected/current.
  - [x] **AC4's denial rows:** `approval_not_pending` and `stale_resource_version` each write one
        `success=False`, `outcome='approval_denied'` row; two denials write two rows with
        distinct `attempt_id`s; a duplicated `attempt_id` is refused by
        `uq_audit_event_failure_attempt`. `approval_not_found` and the feature-policy pre-check
        write **none** (Decision 7).
  - [x] **AC4's observability clause:** with telemetry export disabled, every row above is still
        written. Audit is PostgreSQL and telemetry is OTel — assert the independence rather than
        assuming it.

- [x] **Task 11 — Proof: router, comparison guard, and frontend (AC: 1, 2, 4)**
  - [x] `backend/tests/test_approvals_api.py` (extend): a valid approve is `200` with
        `state: "consumed"`; `promotion_not_available` and `503` no longer appear in
        `openapi.json` for any approvals route; `stale_baseline_version` is `409` with literal
        context.
  - [x] **Decision 5's rollback guard, through the real route and a real transaction** (this
        belongs in `test_approval_governance_postgres.py`, beside
        `test_a_409_expiry_response_commits_the_terminal_row_through_the_real_route`, which is
        its mirror and the only existing test that runs the decision route inside a real
        transaction — do not weaken that one): drive an approve whose `promote` loses the CAS,
        then assert a follow-up `GET` shows the binding still **`pending`**, no `site_baseline`
        row exists, and no audit row was written. **Observe it red by catching the error in the
        route and returning `problem_response(...)`** — the mutation that reproduces the
        inherited defect Decision 5 names.
  - [x] **The same guard for the corrected `AgentRunNotQueuedError` path:** a decision whose run
        left `approval_required` leaves the binding `pending` with no audit row. This is the
        assertion 4.2's monkeypatched test could not make.
  - [x] `calculate_comparison`: with a non-null frozen baseline and the empty supply →
        `BaselineSupplyUnavailableError`; with a `None` frozen baseline → unchanged behaviour;
        `stale` becomes reachable once the pointer moves (Decision 9).
  - [x] Vitest: the `consumed` feedback message; the removed `promotion_not_available` branch;
        the comparison's fail-closed literal; existing panel, dialog, focus-restoration, live
        region, timeline dedupe, and **the NFR19/UX-DR35 distinctness test** all still green.
  - [x] `frontend/e2e/`: extend the existing approval accessibility coverage with the
        post-promotion terminal state. Automated only — `EXPERIENCE.md:196`.
  - [x] **Every new guard gets a demonstrated-red note in the Debug Log** naming the mutation
        that made it fail. A guard with no recorded red is not evidence (retro §1).
  - [x] `npm run codegen` before any frontend type work. **No hand-authored types.**
  - [x] Full suites before hand-off: `uv run pytest`, `uv run pytest -m postgres`,
        `uv run alembic check`, `npm test`, `npx tsc -b`, `npm run lint`, `npm run test:e2e`.
        **`npx tsc -b`, not `npm run typecheck`** — the root `tsconfig.json` declares
        `"files": []`.

- [x] **Task 12 — No evidence file, and say so**
  - [x] No AC here carries a measured threshold, and NFR35's four rows belong to Stories 1.4,
        1.5, 2.4 and 3.5 (AD-26). Stories 4.5/4.6 own Epic 4's evidence.
        `docs/EVIDENCE-CONVENTION.md` exists to stop unmeasured files being written — do not
        write one. Record the reasoning in Completion Notes.
  - [x] **No new golden case.** `evals/golden/scheduling_baseline/` already holds four
        (`approval-required`, `expected-baseline-pinned`, `injection-chat-text`,
        `invalid-run-identifier`), meeting NFR28's per-capability floor; the Release Gate table
        names Stories 4.5–4.6 as Epic 4's contributors. Do not pad
        (`epics.md:1527`). Confirm the count rather than assuming it.

- [x] **Task 13 — Ledger reconciliation (retro §3)**
  - [x] **Close** the initiating-actor membership entry (4.2 review, owner Story 4.3) on
        Decision 2's supplier plus the active/revoked/absent fixtures.
  - [x] **Close** "comparison staleness is vacuously false in production" (owner Story 4.3) on
        the **pointer movement**, per Decision 9 — not on the guard.
  - [x] **Re-point, do not close,** the candidate-drift entry (`scenario_version_id` and
        assignment count never re-read at decide time), whose revisit trigger names this story:
        either confirm `schedule_version` immutability and close it as not-a-defect **recording
        that immutability where it can be cited** (Task 10's grant assertion is that record), or
        state plainly why it stays open.
  - [x] **Record the new deferred item this story creates:** a write fault inside TX2 leaves no
        audit row, because a second connection would be required. **Owner: Story 4.5**
        (its AC2 names database failure during the promotion bundle).
  - [x] **Record, as found-and-fixed, the partial-commit defect on the inherited
        `AgentRunNotQueuedError` arm** (Decision 5) — the SSE-listener precedent from 4.2's
        review: recorded in the ledger rather than only in this story, because the failure mode
        is structural (a returned problem response silently commits) and nothing mechanically
        fails when a route forgets.
  - [x] **Record the EAD-9 supplier entry:** the baseline pointer's production supplier is
        `site_baseline`, written by this story — the spine's table already predicts
        *"real once 4.1 lands"*; confirm it is now real in both directions (read and write).
  - [x] **Leave open:** `AgentApprovalDecisionV1(approved=False)` still has no producer
        (Decision 8); the baseline assignment supply stays unwired (Decision 9); separation of
        duties stays unowned; `agent_cancelled`'s undefined semantics stay for the Epic 4 retro.

### Review Findings

Adversarial code review 2026-08-31, three layers (Blind Hunter, Edge Case Hunter, Acceptance
Auditor) over `946b5ec..a1aff00`. Severity set at triage from the consequence to the planner,
not inherited from the review layers. 23 findings kept, 3 dismissed as noise.

- [x] [Review][Patch] **RESOLVED 2026-08-31 — Option A: split the failure boundary.** The result route returns `200` with `comparison: null` plus a stated reason instead of `409`; the frontend renders that reason where the comparison block would be and keeps the schedule, evidence, and approval panel rendering; `expected_baseline_schedule_version` is surfaced from the run snapshot so the request-approval control survives a null comparison. **`BaselineSupplyUnavailableError` and its firing condition are unchanged — EAD-8's fail-closed guarantee is preserved exactly.** Rejected: narrowing the guard (invents a partial-comparison contract shape nothing else uses); accepting the one-way door (ships an epic whose headline capability works once); wiring a real supply (out of scope per the spine's Deferred table, and blocked on Story 3.8's wage and selected-shift prerequisites). Original finding follows. **The first successful promotion permanently 409s the result endpoint for every completed run snapshotted afterwards, and hides the approval panel that would allow a second one** — `scenario_catalogue.py:136` freezes the live `site_baseline` pointer into every new run snapshot; `create_run_snapshot.py:41,110` carries it; `schedule_runs.py:592` passes it to `calculate_comparison`; the new guard at `comparison.py:181` raises whenever it is non-null and the supply is empty; and `scenario_projection.py:643` returns a hardcoded `()` on every call. So from the first promotion onward, every subsequently created run returns `409 baseline_supply_unavailable` — permanently, site-wide. `ScenarioResults.tsx:43` then gates the approval panels on `!query.isError`, so a run whose result 409s can never have its pending approval decided from the UI, and `ComparisonSummary` (which carries `onRequestApproval`) is gated on `query.data.comparison`. Epic 4's own loop — approve, promote, approve again — is a one-way door after one use, which blocks Stories 4.4–4.6. **The refusal itself is Decision 9 working as specified; its blast radius is not stated anywhere.** Sources: blind+edge, both CONFIRMED, independently re-verified at triage. **Options:** (a) narrow the guard so it fails only the baseline half of the comparison and still returns the candidate half; (b) have the result route degrade to a comparison-unavailable payload instead of a whole-response 409, keeping the approval panel reachable; (c) wire a real supply (explicitly out of scope — needs Story 3.8's wage and selected-shift prerequisites); (d) accept the one-way door for this story and give 4.4 the unblock by name.
- [x] [Review][Patch] **RESOLVED 2026-08-31 — Option A: refuse chained approvals explicitly.** After `execute_turn` returns in `_drive_resumed_turn`, and inside the existing `try`, a `suspended` outcome raises a typed error; the `except Exception` already at `approvals.py:139` converts it through `failed_outcome_for_exception`, so the run finalizes `agent_failed` with a stable reason instead of being written to `approval_required` with no binding. Rejected: replicating `conversations.py:300-347`'s ~50-line suspended branch (a second approval-creation path in a second router is exactly what EAD-5's "no new resume mechanism" forbids, and it enables approval chaining no epic decision sanctions — revisit as a shared helper if a later story needs it); dropping the capability from the resumed turn's grant (changes capability composition, a spine-level concern). Original finding follows. **A resumed turn that requests approval again parks the agent run in `approval_required` with no binding, unrecoverable** — `_drive_resumed_turn` calls `finalize_agent_run(..., status=terminal_status(outcome), ...)` unconditionally (`approvals.py:141-146`), and `terminal_status` maps `"suspended" → "approval_required"` (`execute_turn.py:113-117`). The resumed turn is granted the same capability set (`approvals.py:124-129`), so it can call `scheduling_baseline` a second time. The sibling route has a dedicated `if outcome.status == "suspended":` branch that creates the TX1 binding (`conversations.py:300-318`); the resume path has none. Result: `agent_run.status = 'approval_required'` with no `approval_request` row, so `get_pending_for_agent_run` returns `None`, `claim_queued_run` only claims `agent_queued`, and the run is stuck forever with no reclaim path. Sources: blind+edge, both CONFIRMED. **Options:** (a) replicate the suspended branch so a resumed turn can request a second approval; (b) refuse chained approvals explicitly — finalize as `agent_failed` with a stable reason; (c) reject the suspension at the runtime boundary so it cannot arise. EAD-5 and Decision 8 do not settle whether a resumed turn may suspend again.

- [x] [Review][Patch] Post-commit resume runs after the response is already sent, and three regions are unguarded — a failure strands the run in `agent_running` forever and raises `RuntimeError: Caught handled exception, but response already started` [backend/api/routers/approvals.py:97-146]
- [x] [Review][Patch] The entire post-commit resume mechanism has zero automated coverage — no test references `_drive_resumed_turn`, `post_commit`, or `PostCommitActions`; all route-level approve tests produce `resume is None`, and the end-to-end promotion test calls `decide_approval` directly, bypassing the router [backend/api/routers/approvals.py:94-146, backend/api/deps.py:266-294]
- [x] [Review][Patch] A consumed, agent-backed binding tells the planner its agent run "was cancelled" when TX2 resumed it — the clause is guarded on `agent_run_id` alone, unconditional on state [frontend/src/features/approvals/ApprovalDecisionPanel.tsx:203]
- [x] [Review][Patch] `stale_baseline_version` — the new 409 this story introduces — is not a case in `decisionFeedback`, so it falls to the default "try again" copy, which cannot succeed, and the `expected`/`current` context the backend attaches is dropped [frontend/src/features/approvals/ApprovalDecisionPanel.tsx:48-64]
- [x] [Review][Patch] `schema.py` still declares the five-member `ck_audit_event_outcome` the migration just widened to six; no drift check exists, so a future `--autogenerate` would emit a migration dropping `approval_denied` [backend/adapters/postgres/schema.py:520]
- [x] [Review][Patch] `agent_run_id IS NOT NULL` does not imply `pending_payload IS NOT NULL`, and a zero/multi pending-call payload raises a bare `RuntimeError` — both produce an untyped 500 undeclared in `_DECISION_RESPONSES`. Also add a comment at `get_pending_payload` noting the absent `state` filter is deliberate (it is called after `consume`) [backend/application/use_cases/promote_baseline.py:116-121, backend/adapters/postgres/approval.py:61-68]
- [x] [Review][Patch] A third `ApprovalNotPendingError` site writes a denial audit row past Decision 7's stated boundary — the router discriminates on `exc.code`, not the raise site, so TX3's post-revalidation `terminalize`-returned-`None` closer also audits. **The story undercounts: there are three sites, not two**; Task 3's "make the two sites explicit at their raise points" is unmet and the admission-check site carries no comment [backend/api/routers/approvals.py:212, backend/application/use_cases/decide_approval.py:91,119]
- [x] [Review][Patch] `baseline_supply_unavailable` is documented in the approvals decision-route problem table, a route that cannot emit it — it is raised only by `GET /schedule-runs/{id}/result`. This is the same defect class Task 8 was cleaning up [docs/API.md:558]
- [x] [Review][Patch] The `baseline_supply_unavailable` alert's only action is a Retry that provably cannot succeed, and no copy says the condition is not transient — UX-DR13 requires exposing only currently valid actions [frontend/src/routes/ScenarioResults.tsx:39]
- [x] [Review][Patch] The insert fork swallows every `IntegrityError`, so an FK or NOT NULL violation is reported to the planner as `409 stale_baseline_version` ("the baseline moved") when nothing moved; the constraint name is never inspected [backend/adapters/postgres/site_baseline.py:27-40]
- [x] [Review][Patch] The rollback handler duplicates the router's status/detail maps, leaving `_ERROR_STATUS["agent_run_not_cancellable"]`, `_DECISION_DETAIL["agent_run_not_cancellable"]` and the `AgentRunNotQueuedError` import unreachable — two sources of truth for one wire contract [backend/api/routers/approvals.py:17,59,69, backend/api/main.py:59-78]
- [x] [Review][Patch] The `AgentRunNotQueuedError` handler is registered app-wide with no `/api/v1/` guard (unlike its three siblings) and hardcodes cancellation wording that is wrong on the approve path, where the operation was a *resume* [backend/api/main.py:61,70-73]
- [x] [Review][Patch] `execute_turn` took a second signature change the story forbade ("No other signature change") — `history` was widened to `| AgentTurnV1`, and that branch bypasses `rehydrate_history`'s 100-activity bound, named in the story's own "What must not break" column [backend/application/use_cases/execute_turn.py:66-77]
- [x] [Review][Patch] AC4's observability clause is asserted by a comment, not a test — the test disables the *feature policy*, never telemetry, and asserts the opposite direction (zero rows on unaudited arms, not "every row is still written"). A live-exporter precedent exists at `tests/architecture/test_model_outage_boundaries.py:556-570` [backend/tests/test_approval_governance_postgres.py:1035-1063]
- [x] [Review][Patch] Task 9's stated resume assertions (`agent_run_status="agent_running"`, cleared `status_reason`) live only in the `@pytest.mark.postgres` file, which is deselected from the default suite; `test_promote_baseline.py` stubs the method to return `None` and asserts only that it was called [backend/tests/test_promote_baseline.py:40,86-89]
- [x] [Review][Patch] Three documentation corrections: the ledger closes the candidate-drift entry citing `test_runtime_role_preserves_schedule_versions_but_can_move_the_baseline`, which does not exist (the real name is `test_runtime_privileges_keep_versions_immutable_and_allow_baseline_cas`); `promote_baseline`'s module docstring states Decision 5's rule but never the mechanism (a generator dependency rolls back only when the exception escapes the endpoint) that Trap 1 calls the story's most dangerous line; and the migration's `downgrade` is one-way once any `approval_denied` row exists, undocumented [deferred-work.md:544, backend/application/use_cases/promote_baseline.py:1-6, backend/migrations/versions/e5f6a7b8c9d0_add_approval_denied_audit_outcome.py]

- [x] [Review][Defer] A legitimately empty `OPTIMAL`/`FEASIBLE` baseline is indistinguishable from an unreadable supply [backend/application/scheduling/comparison.py:181] — deferred, coupled to the one-way-door decision above
- [x] [Review][Defer] `approval_denied` audit rows are unbounded and not idempotency-suppressed [backend/api/routers/approvals.py:212-230] — deferred, the story deliberately specifies this behaviour
- [x] [Review][Defer] The 200 is sent to the client before TX2 commits [backend/api/deps.py:285-294] — deferred, pre-existing dependency shape

#### Review patch results — 2026-08-31

All 18 patch items applied. Suites after the patches:

| Suite | Result |
|---|---|
| `uv run pytest` | **1431 passed**, 2 skipped, 7 deselected, 0 failed |
| `uv run pytest -m postgres` | **129 passed**, 0 failed |
| `uv run --project backend alembic check` | *No new upgrade operations detected* |
| `npx vitest run` | **579 passed** across 83 files, 0 failed |
| `npx tsc -b` | clean (exit 0) |
| `npm run lint` | 3 pre-existing `only-export-components` warnings, none from this change |
| `npm run test:e2e` | **62 passed**, 0 failed |

The three backend failures 4.2/4.3 recorded as pre-existing did not reproduce in
this environment; the suite is fully green rather than green-with-known-failures.

**Demonstrated red** (retro §1 — a guard with no recorded red is not evidence):

- **D2's chained-approval refusal.** Deleting the `ResumedTurnSuspendedError`
  raise turns `test_a_resumed_turn_that_defers_again_is_refused_instead_of_parked`
  red with `assert 'approval_required' == 'agent_failed'` — the exact stranding
  this guard exists to prevent. `terminal_status` is deliberately NOT mocked in
  that test; stubbing it would have made the assertion vacuous, which is how the
  original defect survived.
- **D1's failure boundary.** Restoring the `409 problem_response` turns both
  `test_result_route_reports_unreadable_baseline_with_literal_version` (backend)
  and `keeps the run usable when only the baseline comparison is unavailable`
  (Vitest) red; the Vitest case additionally pins that no impossible **Retry**
  action is offered.
- **`_ERROR_STATUS` narrowing.** Removing `stale_baseline_version` — which looked
  dead from the decision route — turned
  `test_maps_every_policy_refusal_to_a_distinct_stable_problem_code[error3-…]`
  red, catching that the CREATE route still raises it as a pre-write refusal. The
  entry was restored with the two-routes/two-mechanisms reason recorded inline.
  Found by the existing suite during this patch pass, not by inspection.

**Notes on two patches that changed the finding rather than confirming it:**

- The third `ApprovalNotPendingError` site is now `ConcurrentDecisionError` and is
  **deliberately kept** in the denial audit: it is a denied consequential attempt
  against a resolved binding whose `terminalize` CAS wrote nothing, so the
  transaction is healthy and FR21 applies on the same terms as the admission
  check. The defect was that the router discriminated on `exc.code` (making the
  behaviour accidental), not the behaviour itself. Decision 7's enumeration is
  extended by one site, with the reason recorded at both the raise site and the
  router.
- `getErrorDetail` was **deleted** rather than kept: D1 removed its only caller,
  and shipping it unused would be exactly the dead-vocabulary pattern the retro
  names as this repo's most expensive.

---

## Dev Notes

### Files being modified — read these before editing

| File | Current state | What this story changes | What must not break |
|---|---|---|---|
| `backend/application/use_cases/decide_approval.py` | admission checks → `revalidate_binding` → TX3; approve-and-valid raises `BaselinePromotionNotAvailableError` | one arm on `revalidate_binding`; the raise becomes a `promote_baseline` call; two `SCOPE_CONTROLS` keys removed | the fork's **two-arm** shape (business mismatch → `stale`; write fault → propagate); expiry checked **first**; `consequence_hash` recomputed from the **stored** summary, never regenerated; the `terminalize` compare-and-set as the concurrency closer |
| `backend/api/routers/approvals.py` | one POST create, one POST decision, two pure GETs; `_out` derives presented-expired | 503 removed from three places; denial audit on the error arm; post-commit resume drive | `_out`'s EAD-7 purity on **both** GETs; the replay re-derivation; `approval_not_granted` staying **403 at both sites**; the `AgentRunNotQueuedError` arm; Decision 9's return-for-TX3 semantics |
| `backend/adapters/postgres/approval.py` | reads + `terminalize`; every statement carries an explicit `site_id` predicate | `consume`, `get_pending_payload` | the explicit site predicate on **every** statement; the repository never commits; `terminalize` leaving `consumed_at` `NULL` |
| `backend/adapters/postgres/conversation.py` | `_append_approval_activity`, `pause_…`, `cancel_…`, `finish_agent_run`; lock order conversation → agent_run | `resume_agent_run_for_approval` | the lock order (ABBA, fixed at 4.1 review); `with_for_update()`; `resource_version + 1`; `max(sequence) + 1`; `APPROVAL_CANCELLATION_REASONS` staying closed to three; `ExecutedAgentRunV1.agent_run_status=None` on the planner path |
| `backend/adapters/postgres/site_baseline.py` | read-only | the writer | the reader's exact shape — `ScenarioOverviewV1.baseline_schedule_version` and `scenario_catalogue` both read through it |
| `backend/application/scheduling/comparison.py` | drains `get_baseline_assignments` (always `()`), computes `stale` | the EAD-8 guard + `SCOPE_CONTROLS` | `ComparisonIntegrityError`'s existing recomputation checks; `stale` staying a derived read-time value never written back |
| `backend/application/use_cases/execute_turn.py` | builds `AgentTurnRequestV1(prompt, history=rehydrate_history(history))` | one optional `approvals` parameter | `terminal_status`'s `"suspended" → "approval_required"` mapping; `_AGENT_TERMINAL_COPY`'s deliberate absence of `cancelled`; `rehydrate_history`'s 100-activity bound |
| `backend/api/main.py` | handlers registered for `RequestValidationError`, `HTTPException`, bare `Exception`; CORS `allow_methods=["GET","POST"]` | one handler for the rollback-required decision errors (Decision 5) | the existing three handlers and their ordering; the CORS method list (it is why every command is `POST`) |
| `backend/migrations/versions/` | 11 files, head `d4e5f6a7b8c9` | **exactly one** new file | `d4e5f6a7b8c9` is merged and applied — never edit it |
| `frontend/src/features/approvals/ApprovalDecisionPanel.tsx` | live-binding-driven, fail-closed, `!query.isSuccess` gate, presented-expired timer, focus restoration | `consumed` feedback; `promotion_not_available` case removed | the `!query.isSuccess` gate; `hasEntries`'s `{}` guard; the `setTimeout` 32-bit ceiling comment; the polite live region; `lastDecision`'s closing-dialog fix |
| `frontend/src/hooks/useDecideApproval.ts` | one idempotency holder **per decision intent** | two more invalidation keys | the per-intent holder (a shared holder was the defect 4.2's review caught) and the settle-on-server-answered rule |
| `docs/GATE-A-RUNBOOK.md` | row 44 claims the decision route never moves the pointer | that claim | every other approved-write-path row |

### Traps

1. **"Raise it and let the router catch it" does NOT roll back.** `get_site_context` is a
   generator dependency; it rolls back only when an exception escapes the **endpoint function**.
   A route that catches and `return`s a problem response commits everything written before the
   failure. TX3 relies on exactly that to commit (4.2 Decision 9); TX2 must avoid it. This is
   the story's single most dangerous line, it is **already latently wrong** on the shipped
   `except AgentRunNotQueuedError` arm whose comment claims otherwise, and Task 11 has the
   demonstrated-red for both directions. Decision 5.
2. **`revalidate_binding` is shared, so Decision 2's membership arm changes Story 4.2's
   behaviour.** A reject against a revoked initiator now stales. Every 4.2 revalidation test
   must be re-run and the cross-story consequence asserted, not discovered at review.
3. **`ck_audit_event_outcome` is a database CHECK.** An `approval_denied` row without Task 7's
   migration is a runtime error under `shiftmind_runtime`, **not** a test failure — the unit
   suite runs against fakes and never reaches the constraint. The same shape as 4.2's Trap 3.
4. **`effect_key` must be `binding.request_effect_key`.** A fresh `uuid4()` makes
   `uq_audit_event_success_effect` guarantee nothing, which is the exact defect 4.1's review
   caught, and it silently destroys AC3's "cannot create another … pointer movement" mechanism.
5. **`_append_approval_activity` defaults `agent_run_status` to `approval_required`** when an
   `agent_run_id` is passed. TX2 must state `agent_running` explicitly or the activity reports
   the state the same transaction just replaced.
6. **`status_reason` must be cleared on resume.** It names a *binding* outcome (EAD-5). Leaving
   a stale `approval_expired` on a run that was promoted makes Chat render a cancellation reason
   beside `agent_running`.
7. **The resume guard is `binding.agent_run_id is not None`, never "a pending payload exists".**
   The planner path has no run and no payload; conflating the two conditions makes the guard
   right by accident and wrong after the first edit.
8. **The first promotion is what makes `calculate_comparison` lie.** Decision 9's guard cannot
   be deferred to a follow-up story — the defect ships the moment the pointer moves.
9. **`get_baseline_assignments` is hardcoded `()`, not an empty fixture.** Do not "fix" it here
   and do not read the promoted version's assignments; the spine's Deferred table owns that and
   it also needs Story 3.8's wage and selected-shift prerequisites.
10. **Two concurrent approvals.** The read-then-write revalidation cannot close the race;
    `consume`'s compare-and-set on `state='pending' AND resource_version=?` and `promote`'s CAS
    on `site_baseline.resource_version` are what do. Treat a `None` from either as a conflict,
    never a 500.
11. **`_secure()` in `d4e5f6a7b8c9` REVOKES `UPDATE, DELETE` before line 118 re-grants four
    `site_baseline` columns.** Reading only the `GRANT` lines will mislead you about what is
    permitted. Prove privileges with `has_table_privilege` as `shiftmind_runtime` (Task 10).
12. **Regenerate the OpenAPI types; do not hand-author them.** `npm run codegen` runs the
    backend exporter first; a stale `openapi.json` produces types that typecheck and lie.
13. **`npm run typecheck` is inert.** The root `tsconfig.json` declares `"files": []`;
    `npx tsc -b` is what actually type-checks the tree.
14. **The consequence summary is hashed and is a contract.** Any edit to its text changes
    `consequence_hash` and marks every live pending binding `stale` at revalidation. 4.1 Trap 7
    and 4.2 Trap 6 both said this; do not "improve" the wording while promoting it into audit.

### Honest gaps this story ships with — state them in Completion Notes

- **A write fault inside TX2 writes no audit row.** The row would be inside the transaction that
  rolled back, and a second connection is out of scope. AC4's "failed" case is therefore covered
  by rollback correctness, not by an audit record. **Owner: Story 4.5**, whose AC2 names it.
- **The baseline assignment supply stays hardcoded empty.** EAD-8's guard fails closed instead
  (Decision 9). No comparison against a real promoted baseline is authoritative after this story;
  it is *refused*, which is the point.
- **`initiated_by_actor_id` and `decided_by_actor_id` still hold the same principal** in
  practice. The distinction is structural until a second real user exists (parent Deferred,
  EAD-9), and self-approval remains possible — no story owns separation of duties.
- **`AgentApprovalDecisionV1(approved=False)` still has no producer.** EAD-5 cancels rather than
  resuming with a denial.
- **The membership arm is proven against seeded revoked/absent rows.** The production supplier is
  real (`membership`, read in-transaction), but there is only one user, so a genuinely revoked
  initiator cannot arise outside a test.
- **`policy_version` mismatch is still proven by seeding a bumped value**, not by toggling
  `scheduling_baseline_enabled` mid-process: the setting is read at process start, and the
  feature being off also refuses at the `enabled_feature_policy` pre-check. 4.2's constraint,
  unchanged.
- **The resumed turn runs against the deterministic double in CI.** The seam is real and
  production-wired; the model behind it is stubbed, exactly as every other turn in the suite.

### Testing requirements

- Backend tests in `backend/tests/`, `test_*.py`, never co-located. PostgreSQL-dependent tests
  carry `@pytest.mark.postgres` (`pyproject.toml:52`).
- Keep 4.1/4.2's three-file split: fake-repository **use-case** tests in
  `test_promote_baseline.py` and `test_decide_approval.py`; **router/HTTP-contract** tests in
  `test_approvals_api.py`; **real-PostgreSQL** tests in `test_approval_governance_postgres.py`.
- Frontend tests co-located, Vitest + Testing Library; assert accessible names and roles, not
  class names — **except** the NFR19 distinctness assertion, which is explicitly about visual
  treatment.
- Accessibility is proven by automated coverage alone (`EXPERIENCE.md:196`).
- Every new guard needs a recorded demonstrated-red. This is the epic's single most-repeated
  process lesson: 4.1's review found two guards that could not fail, and 4.2's found a third.
- **Re-derive the baselines at Task 1; do not trust 4.2's numbers.** Story 4.2's post-review
  Completion Notes record backend 1395 passed / 2 skipped / 7 deselected (118 `postgres`-marked),
  frontend 571 across 82 files, Playwright 60. Both 2.7 and 2.8 found their inherited baselines
  stale, and 3.12's review found the pass/skip *split* environment-conditional while the total is
  the stable invariant — record the total alongside the split.
- The two `tests/test_openrouter_provider.py` failures under the full suite are **pre-existing
  test-order pollution** (they pass in isolation), recorded at 4.2's review. Do not attribute
  them to this story and do not "fix" them here.

### Project structure notes

Additive, matching the Epic 4 Structural Seed and AR26. New files:
`backend/application/use_cases/promote_baseline.py`,
`backend/application/ports/membership.py`, `backend/adapters/postgres/membership.py`,
`backend/tests/test_promote_baseline.py`, one migration under
`backend/migrations/versions/`. No renames. `SiteBaselineWriter` goes **beside** the reader in
the existing `application/ports/site_baseline.py`, not in a new module — one port file per
storage home is the convention `approval.py` already sets by holding both
`ApprovalRepository` and `AuditWriter`.

`application/queries/decision_provenance.py` (Story 4.4) is **not** created here, not even as a
stub.

### Open questions for Winston — raise before Story 4.4, not during implementation

1. **Does `approval_denied` want a sibling for a rolled-back write fault?** Decision 7 ships one
   member because only one has a writer. If Story 4.5's fault-injection work concludes that a
   post-rollback audit row is required, it will need both a second CHECK member and a
   second-connection write path — a shape no Epic 4 decision currently sanctions.
2. **Should the resumed turn be observable as a distinct activity?** Decision 8 reuses the
   `approval_request` discriminant carrying `approval_state="consumed"`, and the run's return to
   `agent_running` is read from the row (EAD-5's stated purpose for `status_reason`). If Story
   4.6's state matrix needs the resume to announce itself separately, that is a ninth
   `ActivityTypeV1` discriminant and therefore a spine change, not a story change.
3. **Carried forward from 4.1/4.2, still unanswered:** should a decision pin the *scenario*
   version as well as the binding's resource version? Decision 9's guard and the deferred
   candidate-drift entry both touch this from different sides; neither settles it.

### References

- Epic 4 spine:
  `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
  — EAD-1 (storage homes, 4.1 owns the migration), EAD-2 (**no-baseline / insert-vs-CAS**),
  EAD-3 (identity, two key shapes), EAD-5 (**resume through the existing seam**),
  EAD-6 (**TX2's six writes, effect key, closed outcome vocabulary**), EAD-7 (lazy expiry),
  EAD-8 (**baseline-supply guard binds 4.3's promotion**), EAD-9 (supplier table),
  EAD-10 (**one endpoint, 4.3 owns TX2, the revalidation fork, the membership referent**),
  EAD-11 (consequence-summary home), EAD-12 (policy derivation), *Consistency Conventions*,
  *Verification Obligations* 1, 2, 5, 6, 7, *Deferred*
- ADR-4: `.../architecture-epic-4-2026-08-27/ADR-4-consequential-workflow.md` — D5, D6, D7, D9
- Parent spine: `.../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-2 `:54`,
  AD-3 `:60`, AD-7 `:84-128`, AD-8 `:132`, AD-9 `:138`, AD-10 `:144`, AD-12 `:154-158`,
  AD-13 `:162`, AD-14, AD-20 `:208`, AD-22 + Amendment `:216-221`
- Epic and requirements: `_bmad-output/planning-artifacts/epics.md` — Story 4.3 `:1202-1228`,
  FR18 `:59`, FR19 `:61`, FR21 `:65`, NFR6, NFR8, NFR9, NFR31 `:135`, AR8/AR9/AR10/AR12/AR22
  `:153-168`, UX-DR13 `:202`, Release Gate `:1508-1527`
- UX: `.../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` Accessibility Floor `:185-196`
- Previous story: `_bmad-output/implementation-artifacts/4-2-review-and-decide-the-exact-approval.md`
  — **"What Story 4.3 inherits from this story"** (five verified inheritances), Decisions 2, 3,
  4, 5, 6, 9, 11, its Traps, its Review Findings, and its **Review Retrospective Input**
- Story 4.1: `.../4-1-request-approval-for-one-exact-feasible-candidate.md` — the ABBA
  deadlock, the audit `effect_key` defect, the fail-open `pendingApproval`, Open Question 1
  (answered here by Decision 7)
- Domain: `docs/DOMAIN-MODEL.md` §1–§2 — cited by Decision 9's assignment-side reasoning
- Conventions: `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md:42-49`, `docs/API.md`,
  `docs/TESTING.md`
- Process: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1, §3;
  `epic-1-2-retro-2026-08-16.md` §3.2 (A1), §6.1 (A3)
- Ledger: `_bmad-output/implementation-artifacts/deferred-work.md` — the 3.8 comparison-staleness
  entry, the 4.2-review membership entry, the 4.2-review candidate-drift entry, the
  `AgentApprovalDecisionV1(approved=False)` entry, the EAD-9 supplier entry

---

## Dev Agent Record

### Agent Model Used

GPT-5.4 (Codex)

### Debug Log References

- Membership revalidation: adding the required dependency before updating the fakes made all 24
  decision-use-case cases fail on the unexpected `memberships` argument; active/revoked/absent
  fixtures then made the shared fork green for approve and reject.
- Consume/promotion rollback: mutating the route to catch and return the lost-CAS problem made the
  real transaction retain the consumed row. Both the baseline-CAS and consume-CAS tests now require
  the exception to unwind the dependency before the 409 is rendered.
- Agent-run rollback: returning the inherited `AgentRunNotQueuedError` response inside the route
  committed a partial terminalization; the real-route test now proves pending state and zero audit.
- Runtime grants: transactionally revoking `site_baseline INSERT` makes the runtime-role write fail;
  the transaction rolls back the mutation and the shipped insert/CAS proof passes.
- Deferred decisions: omitting `approvals` from `execute_turn` made the resumed-turn test observe an
  empty tuple; forwarding the persisted approved call made it green.
- Comparison supply: deleting the new empty-supply guard made a pinned non-null baseline return a
  fabricated empty comparison; the backend 409 and frontend literal-only recovery tests caught it.
- Frontend terminal state: the consumed-copy test failed against the generic “baseline did not
  change” text, and the query-invalidation test failed until comparison and scenario keys were added.
- Full-suite mutations caught two integration omissions: detached `BackgroundTasks` violated the
  architecture guard, and the old migration-head assertion rejected `e5f6a7b8c9d0`. Both are fixed.

### Completion Notes List

- Implemented TX2 as one caller-owned transaction: consume binding, insert/CAS `site_baseline`,
  append the authoritative audit/event, and resume approval-backed runs. Rollback-required errors
  render only after dependency unwind; resumed turns run through a synchronous post-commit queue.
- Added the initiating actor's active-membership supplier to the one shared revalidation fork,
  denial audit rows, idempotent replay protection, and the EAD-8 fail-closed comparison guard.
- Regenerated OpenAPI types and updated the Results/approval UI with literal baseline-supply errors,
  version-specific consumed copy, cache invalidation, and automated terminal-state accessibility.
- Added the single `approval_denied` migration, updated API/Gate A docs, and reconciled the deferred
  ledger. No setting, route, dependency, evidence file, or golden case was added.
- No evidence file is warranted because this story has no measured threshold. The scheduling
  baseline golden set remains exactly four cases, meeting the existing per-capability floor.
- Re-derived pre-change baselines: backend 1402 passed / 3 failed / 7 skipped; PostgreSQL 117 passed /
  1 failed; frontend 571 passed; Playwright 60 passed. Final: backend 1426 passed / the same 3 failed /
  7 skipped; PostgreSQL 127 passed / the same 1 failed; frontend 575 passed; Playwright 62 passed.
  The three backend failures remain external/pre-existing: two live OpenRouter cases use a retired
  free model slug, and the temporary-database cleanup warning fixture imports the wrong conftest.
- `npx tsc -b`, lint, Alembic check, architecture/changed-surface tests, and all Story 4.3 tests pass.
  Gate A report generation correctly refused without fresh JUnit XML and a clean committed tree;
  no unmeasured or unbound report was written.

### File List

- `_bmad-output/implementation-artifacts/4-3-promote-the-baseline-atomically-with-audit.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/adapters/postgres/approval.py`
- `backend/adapters/postgres/schema.py` *(review patch: `ck_audit_event_outcome` widened to match the migration)*
- `backend/api/schemas.py` *(review patch: `ScheduleRunResultOut` gains `comparison_unavailable_reason` and `current_baseline_schedule_version`)*
- `backend/adapters/postgres/conversation.py`
- `backend/adapters/postgres/membership.py`
- `backend/adapters/postgres/site_baseline.py`
- `backend/api/deps.py`
- `backend/api/main.py`
- `backend/api/routers/approvals.py`
- `backend/api/routers/schedule_runs.py`
- `backend/application/ports/approval.py`
- `backend/application/ports/conversation.py`
- `backend/application/ports/membership.py`
- `backend/application/ports/site_baseline.py`
- `backend/application/scheduling/comparison.py`
- `backend/application/use_cases/decide_approval.py`
- `backend/application/use_cases/execute_turn.py`
- `backend/application/use_cases/promote_baseline.py`
- `backend/migrations/versions/e5f6a7b8c9d0_add_approval_denied_audit_outcome.py`
- `backend/tests/test_approval_governance_postgres.py`
- `backend/tests/test_approvals_api.py`
- `backend/tests/test_decide_approval.py`
- `backend/tests/test_evidence_binding.py`
- `backend/tests/test_execute_turn_use_case.py`
- `backend/tests/test_promote_baseline.py`
- `backend/tests/test_schedule_comparison.py`
- `backend/tests/test_schedule_runs_api.py`
- `docs/API.md`
- `docs/GATE-A-RUNBOOK.md`
- `frontend/e2e/accessibility.spec.ts`
- `frontend/openapi.json`
- `frontend/src/api/schema.d.ts`
- `frontend/src/features/approvals/ApprovalDecisionPanel.test.tsx`
- `frontend/src/features/approvals/ApprovalDecisionPanel.tsx`
- `frontend/src/hooks/useConversationStream.test.tsx`
- `frontend/src/hooks/useDecideApproval.test.tsx`
- `frontend/src/hooks/useDecideApproval.ts`
- `frontend/src/lib/errors.ts`
- `frontend/src/routes/ScenarioResults.tsx`
- `frontend/src/routes/ScenarioResultsWorkspace.test.tsx`

---

## Change Log

| Date | Change |
|---|---|
| 2026-08-30 | Story created from `epics.md:1202-1228`, the Epic 4 architecture spine (including the `32d9320` membership amendment), ADR-4, Story 4.2's inheritance section and review retrospective, and a live audit of the codebase at `946b5ec`. |
| 2026-08-31 | Implemented atomic baseline promotion, approval consumption/audit, post-commit agent resume, membership revalidation, fail-closed comparison supply, migration, frontend terminal behavior, documentation, ledger reconciliation, and complete automated proof. Status moved to review. |
