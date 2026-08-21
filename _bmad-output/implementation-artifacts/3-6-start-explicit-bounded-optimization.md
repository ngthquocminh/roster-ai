---
baseline_commit: 0545b35c6c6abacbac72fc21259e6da6ac16982b
---

# Story 3.6: Start Explicit Bounded Optimization

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want Run optimization to start only the exact reviewed computation,
So that drafting or ordinary chat never silently authorizes solver work.

**Planner-visible outcome: the first one since Story 3.1.** This is Epic 3's first full-stack
story. Stories 3.2–3.5 were all `[Technical Enabler]` with no planner-reachable surface; this
story ships the **Run optimization** control *and* its command together, in one increment
(`epics.md:847, 1542`). Story 3.1 deliberately shipped no control and no disabled placeholder
for one, so there is nothing to "activate" — the control is new.

**Depends on, and consumes:** Story 3.1's `ProposalV1`, `proposal`/`proposal_version` tables,
`command_idempotency` table, `/api/v1/proposals` router and its `_command_problem()` mapping,
`DraftCard.tsx`, and `frontend/src/lib/idempotency.ts`; Story 3.2's `create_run_snapshot`
(including its `stale_proposal` gate), `RunSnapshotV1`, `GovernedSolverConfigV1`; Story 3.3's
`workflow.job_queue`, `JobLeaseV1`, `lease_next_job`; Story 3.4's `schedule_run.resource_version`
and `PostgresScheduleRunRepository`; Story 3.5's `run.queued.v1` event write inside
`create_queued_run`, `GET /api/v1/schedule-runs/{run_id}` and `/events`; Story 2.5/2.6's
`CapabilityModuleV1`, `compose_granted_capabilities`, `CapabilityGrantContextV1`, and the
conformance suite; AD-2, AD-5, AD-6, AD-8, AD-9, AD-13, AD-22.

**Unblocks:** Story 3.7 (the Runs workspace finally has runs to list, and the Story 3.4
cancellation command finally has a reachable run to cancel), Story 3.8 (a candidate to compare),
Story 3.10/3.11/3.12 (the proof stories need a real run to drive).

**Scope summary:** One new POST route. One new `compute`-risk capability module (the first in
the repository). One settings hardening pass covering seven ceilings. One new per-site
concurrency gate. One new frontend control, its API wrapper and hook. **No new dependency.** No
migration. **No evidence file** — see Decision 8.

**This story is the first in the repository to:**

1. **call `enqueue_compute` from anything other than a test.** Verified by exhaustive grep at
   `0545b35`: the only non-test references are `test_enqueue_compute.py`,
   `test_job_leasing_postgres.py:398-475`, `test_postgres_integration.py:640`, and a prose
   comment at `adapters/postgres/schedule_run.py:263`. **No router calls it.** The entire chain
   HTTP → `enqueue_compute` → `create_run_snapshot` → `job_queue` → worker lease has never had
   its first link;
2. **register a `risk_class="compute"` capability.** `RiskClassV1`
   (`application/contracts/capability_manifest.py:20-22`) has reserved `"compute"` since Story
   2.5, and all four installed modules declare `inspect` (×2), `draft`, or `consequential`
   (`scheduling_compute.py:259`, `scheduling_inspect.py:147`, `scheduling_draft.py:217`,
   `demonstration.py:85`). Note `scheduling_compute` is **misleadingly named** — it is an
   `inspect`-risk grounding metric capability, not a solver capability, and it is **not** the
   module this story extends;
3. **make a capability grant conditional on something other than role, feature policy, site, and
   conversation.** AD-5's clause "compute needs the planner's current explicit run request"
   (`ARCHITECTURE-SPINE.md:76`) has no implementation anywhere — verified: `risk_class` is read
   only by manifest validation and eval-report accounting, never by runtime authorization, and
   `capability_tools.py:79` branches only on `approval_policy != "none"`;
4. **populate `JobLeaseV1.capability_version`**, closing the `"NOT COVERED:
   contracts:capability_version_unpopulated_until_story_3_6"` marker that
   `enqueue_compute.py:26` and `lease_and_execute_schedule_run.py:62` both carry **by name**;
5. **bound per-site concurrency.** Exhaustive grep for `concurrency|max_concurrent|
   site_concurrency` across `backend/` returns only `fastapi.concurrency` imports and two
   unrelated test comments. No limit of any kind exists;
6. **add a versioned write route since Story 3.1**, therefore the first since then to touch the
   Gate A write-surface literal (`test_gate_a_mutation_audit.py:257-269`) and
   `docs/GATE-A-RUNBOOK.md`. Story 3.5's two new routes were GET and correctly did not.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. Every rule below is recorded somewhere
citable; none of it may be re-derived from adapter code (retro §3.2 — the single most expensive
pattern of Epics 1–2, and the source of five of Story 2.7's nine decision-grade findings).

| Fact | Where it is written |
|---|---|
| Risk classes are exactly `inspect`, `draft`, `compute`, `consequential`, `prohibited`; **`compute` needs the planner's current explicit run request**, `consequential` needs exact-action approval, `prohibited` capabilities are absent. Loading or naming a module never grants authority | AD-5 (`ARCHITECTURE-SPINE.md:72-76`); AR5 (`epics.md:150`) |
| The model interprets intent and proposes typed calls; **application code owns identity, site scope, authorization, policy, risk, versions, budgets, approvals, idempotency, state transitions, persistence, and audit**; CP-SAT alone constructs or validates an accepted schedule. No model output, model memory, browser value, or client approval flag grants authority | AD-2 (`ARCHITECTURE-SPINE.md:54-58`); AR2 (`epics.md:147`) |
| **Application configuration — not the model — sets maximum iterations, model/tool calls, tokens, retries, wall time, site concurrency, and solver duration** | AD-7 (`ARCHITECTURE-SPINE.md:88`) |
| Agent and solver budgets are **explicit positive application configuration with safe defaults**, never chosen by the model | NFR16 (`requirements-inventory.md:37`; `epics.md:107`) |
| FR12's literal ceiling list: **solver time, iterations, model/tool calls, retries, tokens, concurrency, and elapsed time**, each with a positive application-owned ceiling in release configuration, and exceeding any ceiling ends in a **distinct bounded state**. Optimization starts as a durable asynchronous job **only from the planner's current explicit request or Run optimization transition**, and returns a durable run ID | FR12 (`prd.md`, mirrored `epics.md:47`); verification wording, `implementation-readiness-report-2026-07-22.md:82` |
| **Validate environment configuration at process start** | *Consistency Conventions*, Config and secrets row (`ARCHITECTURE-SPINE.md:259`) |
| Each mutating HTTP command requires an idempotency key **scoped to actor, site, operation, and canonical body hash plus expected resource version**; database uniqueness protects it; **a replay returns the original semantic result and a conflicting body fails** | AD-8 (`ARCHITECTURE-SPINE.md:132-136`); AR8 (`epics.md:154`) |
| Every mutating tool call uses current authorization, expected resource version, idempotency protection, deterministic invariants, and authoritative audit evidence | NFR2 (`requirements-inventory.md:23`; `epics.md:79`) |
| Proposals/solver inputs/schedule versions are immutable; the site baseline is a versioned pointer; **stale inputs fail closed and require refresh/recompute — no silent rebase** | AD-9 (`ARCHITECTURE-SPINE.md:138-142`); AR9 (`epics.md:155`) |
| `enqueue-compute` is a **fixed atomic bundle**: immutable run snapshot + job + event. **Repositories and adapters may not widen a bundle**; only an application orchestrator crosses aggregate owners. Scheduling owns proposals/runs/schedule versions; Workflow owns jobs/persisted events | AD-22 (`ARCHITECTURE-SPINE.md:216-220`); AR22 (`epics.md:168`) |
| Application errors map to **RFC 7807 problem details with stable code, correlation ID, resource ID, and current version when relevant**; denied, stale, missing, invalid, timed-out, cancelled and failed remain **distinct** | AD-13 (`ARCHITECTURE-SPINE.md:162-166`); *Consistency Conventions*, Errors row (`:258`) |
| Unsafe methods require same-origin validation **plus** CSRF token; every request re-resolves actor/site from the server-side session and current PostgreSQL membership | AD-3 (`ARCHITECTURE-SPINE.md:60-64`); AR3 (`epics.md:148`) |
| **Review, Run optimization, and Approve as baseline remain distinct in language, control, consequence, and visual treatment** | NFR19 (`requirements-inventory.md:40`; `epics.md:111`) |
| Draft cards carry **separate revise, reject, and Run optimization controls**; Send, Run optimization and Approve as baseline stay **visually discontinuous** so no single "AI action" treatment spans authority levels | UX-DR9 (`epics.md:194`); UX-DR35 (`epics.md:246`); `DESIGN.md` "Chat composer" row ("Send and Run optimization cannot share the same primary control treatment") |
| Scenario/baseline drift **marks affected Draft/Approval request stale and disables consequential actions**; message-send failure retains draft text and offers retry | `EXPERIENCE.md:123` (Chat states row) |
| An accepted trigger **immediately yields a run ID/state**; a repeated Run optimization request returns the **existing semantic response/run** | `EXPERIENCE.md:125` (Runs states row), `:274-280` (Flow 5) |
| Use operational, bounded copy naming literal states and versions; **no confidence scores, anthropomorphic waiting, hidden reasoning, celebration, urgency, or unsupported benefit claims** | UX-DR5 (`epics.md:186`) |
| Manual assistive-technology verification is **out of scope**; automated coverage is the only accepted proof | `EXPERIENCE.md` Accessibility Floor (`:196`) |
| Every new guard must be **observed failing** with its structural assertion removed before being trusted | retro §6.1 action A2 (applied by Stories 3.3/3.4/3.5 to their own guards) |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |

`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments. **This story touches no
metric, no demand row, and no assignment** — it authorizes and enqueues a solver job and renders
a control. The families/units rule is cited for completeness and deliberately **not**
re-derived. The one adjacent trap it does warn about applies to Story 3.8's comparison work, not
here.

---

## Acceptance Criteria

Verbatim from `epics.md:979-1006`.

1. **Given** a current valid draft and the Run optimization control introduced by this story,
   **When** the planner activates Run optimization or makes an equivalent explicit current
   request, **Then** the compute capability validates trusted actor/site, proposal and baseline
   versions, policy, risk, invariants, budget, and idempotency before enqueueing one durable
   job, **And** merely sending, reviewing, or accepting draft parameters does not start
   computation; every mutating tool call carries current authorization, expected version,
   idempotency protection, and authoritative audit evidence, **And** the control, accessible
   sequencing copy, command contract, and enabled/disabled states are delivered together in this
   story. (FR12, NFR2, AR5)

2. **Given** release configuration, **When** the compute command is accepted, **Then** positive
   application-owned ceilings exist for solver time, agent iterations, model/tool calls,
   retries, tokens, site concurrency, and total elapsed time, **And** no ceiling originates from
   model output. (FR12, NFR16)

3. **Given** the same actor/site/operation/idempotency key and canonical body hash, **When** the
   command is replayed, **Then** it returns the original semantic run response and run ID,
   **And** a conflicting body hash or expected version fails without a second job. (FR16, AR8)

4. **Given** current site concurrency is exhausted or the draft is stale, **When** the planner
   requests a run, **Then** the command returns a stable bounded/stale problem response and
   creates no job, **And** Chat retains the draft and offers only valid recovery actions.
   (FR6, FR12)

---

## Nine decisions were made at story creation — do not re-litigate them

### Decision 1 — AC1's "compute capability" is a real registered `CapabilityModuleV1`, and its grant is what enforces "explicit run request"

This is the largest judgement in the story, so the reasoning is recorded in full.

AC1 names "the compute capability" and lists **risk** among the things it validates. Validating
risk is meaningless without a risk class to validate. AD-5 reserves `compute` and states its
gate — *"compute needs the planner's current explicit run request"* — and **that gate has never
been implemented**: `risk_class` is read only by `validate_manifest` and by
`evals/evaluators.py:290-299` for report accounting; `capability_tools.py:79` branches solely on
`approval_policy != "none"`. `enqueue_compute.py:26` and `lease_and_execute_schedule_run.py:62`
both carry `"NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6"` — the code
is already waiting for a capability version this story must supply.

So: ship a new module, **`scheduling_optimize`**, `risk_class="compute"`.

**The grant is the mechanism.** `CapabilityGrantContextV1` gains one trusted boolean —
`explicit_run_request` — and `compose_granted_capabilities` refuses to grant any
`compute`-risk module unless it is `True`. Only the HTTP command path sets it. An ordinary chat
turn composes its grant with `explicit_run_request=False`, so the module is **absent from the
agent's toolset entirely** — not present-and-denied. That is the shape
`test_an_ungranted_module_is_absent_from_the_tool_set`
(`test_capability_conformance.py:306-321`) already enforces for every other module, and it is
literally the story's own "So that" clause made structural: *drafting or ordinary chat never
silently authorizes solver work*, because during drafting or ordinary chat **the tool does not
exist**.

**The handler validates; the application enqueues.** This is Story 3.1 Decision 1 applied
unchanged, and it is forced, not chosen: `AgentDepsV1` carries a projection reader, a clock, a
budget and a result sink — **no writer, no repository, no unit of work** — and
`test_handler_module_has_no_adapter_or_framework_import`
(`test_capability_conformance.py:145-148`) forbids a handler module from importing `adapters`,
`sqlalchemy`, `fastapi` or `pydantic_ai` at all. The handler therefore returns a trusted
`SchedulingOptimizeResultV1`; the route's use case performs the enqueue on the connection it
owns.

**Rejected alternative — ship the HTTP command alone and register no module.** Tempting, and
roughly 30% cheaper. Rejected on three counts: AC1 names the capability and names *risk* among
its validations; `capability_version` would stay unpopulated, leaving two `SCOPE_CONTROLS`
markers that name **this story by name** still open; and AD-5's `compute` clause would remain
the one risk class in the architecture with no implementation anywhere, in the exact story whose
title is "Start Explicit Bounded Optimization". A reduction that leaves the story's own named
markers open is a decision-grade review finding waiting to happen.

**Rejected alternative — grant `compute` to the agent whenever the planner's message looks like
a run request.** That is intent inference by the model deciding its own authority, which AD-2
forbids in its first clause. `explicit_run_request` is set by the application from the transport
(an authenticated, CSRF-validated POST carrying a deliberate gesture), never from message text.

### Decision 2 — The route is `POST /api/v1/schedule-runs`, a collection POST on the existing schedule-runs router

The aggregate created is a `ScheduleRun`, which AD-22 gives to Scheduling and which
`api/routers/schedule_runs.py` already owns. `_not_found()`, `_view_out()`, `_command_problem()`
and every schedule-run response model live there; mounting elsewhere would fork the run-problem
mapping into a second router. Precedent for a bare collection POST creating an aggregate is
`POST /api/v1/conversations`.

Body: `{ "proposal_id": UUID, "expected_resource_version": int }` — matching
`ScheduleRunCancellationIn`/`ProposalRevisionIn`'s existing `expected_resource_version:
Field(ge=1)` shape (`api/schemas.py:242-262`). Header: `Idempotency-Key`, `max_length=40`,
exactly as the three shipped commands declare it.

**Rejected alternative — `POST /api/v1/proposals/{proposal_id}/schedule-runs`.** It matches the
sub-resource shape of the other three versioned POSTs and matches
`enqueue_compute`'s existing proposal-scoped `operation` string. Rejected because it would put
schedule-run problem mapping and response models in `proposals.py`, and because Story 3.7's Runs
workspace will add `GET /api/v1/schedule-runs` — a collection that then has a POST sibling on a
different router is worse than either alternative alone.

`POST` and not `PUT`/`PATCH`: `api/main.py:251-256` sets `allow_methods=["GET", "POST"]`, so any
other unsafe method passes same-origin locally and fails CORS preflight cross-origin — a defect
visible only in a deployed topology (Story 3.1 Decision 4 established this).

### Decision 3 — `enqueue_compute` gains an `actor_id` parameter; the requester owns the idempotency scope

`deferred-work.md:273` names this story by name. Today `enqueue_compute.py:85` sets
`actor_id = record.created_by_actor_id` — the **proposal's author** — and uses that same value
as the actor component of the `(site_id, actor_id, operation, idempotency_key)` scope, because
Story 3.2 had no live HTTP actor at that boundary. This story supplies one.

Thread the session actor from `Depends(get_session)` through the route into `enqueue_compute` as
an explicit keyword argument, and use it for **both** the `command_idempotency` actor column and
the `create_queued_run` actor. This is a behavioural change to an existing use case: the three
tests in `test_enqueue_compute.py` currently rely on the implicit default and must be updated to
pass an actor rather than have the change absorbed silently.

Close `deferred-work.md:273` in the same commit. Do **not** close `deferred-work.md:361` (Story
3.5's "no event identifies the worker that acted") — that is Epic 4's and is a different actor
question.

### Decision 4 — All seven ceilings become positive-validated at process start; two of them are new

AC2 says positive ceilings **exist**. The audit at `0545b35` is:

| AC2 ceiling | Today | This story |
|---|---|---|
| Solver time | `solver_wall_time_limit_seconds` (30.0), `solver_max_deterministic_time` (30.0) — **already `_positive_float`** | unchanged |
| Agent iterations | `agent_runtime_request_limit` (8) — `_optional_int`, **unvalidated** | harden |
| Model/tool calls | `agent_runtime_tool_calls_limit` (8) — `_optional_int`, **unvalidated** | harden |
| Retries | **does not exist anywhere** | **new** |
| Tokens | `AgentBudgetV1.total_tokens_limit` declared (`agent_runtime.py:81`) but **no setting wires it** (`deferred-work.md:128`) | **new setting**, closes `:128` |
| Site concurrency | **does not exist anywhere** | **new** |
| Total elapsed time | `agent_runtime_deadline_seconds` (60.0) — `_optional_float`, **unvalidated**; plus `lease_seconds`, unbound (`deferred-work.md:289`) | harden + bind |

"Harden" means switching `_optional_int`/`_optional_float` to `_positive_int`/`_positive_float`
for the four `agent_runtime_*` settings. **This is a deliberate semantic change, not a
refactor**, and it is the whole point of AC2:

- `_optional_int` (`settings.py:161-172`) documents that an explicit **empty** value means *"no
  limit" (None)* — so `AGENT_RUNTIME_TOOL_CALLS_LIMIT=` today yields an **unbounded** run. AC2
  says a positive ceiling must exist. Unbounded is not positive.
- The `_optional_int(...) or 200` idiom used by the four `scheduling_*` settings
  (`settings.py:272-292`) falls back only on falsy `0`; a **negative** override is truthy and
  reaches runtime intact.

Both paths must be closed and both must be **observed failing** before the fix (retro A2). The
`scheduling_*` row limits and timeouts are not in AC2's list but share the same broken idiom and
are hardened in the same pass — cheap, and leaving a known-broken parser beside a fixed one
invites the next story to copy the wrong one.

`lease_seconds` (`deferred-work.md:289`, **Owner: Story 3.6**) becomes a validated setting whose
default is derived from `solver_wall_time_limit_seconds`, preserving
`default_lease_seconds()`'s existing `≥ 4 ×` relationship (`worker/lease_worker.py:53-66`) and
**validating the relationship at process start**, not just the magnitude. Close `:289`.

### Decision 5 — `solver_wall_time_limit_seconds` stays at 30.0, so mid-solve preemption does **not** become this story's

Story 3.5 Decision 6 re-pointed mid-solve preemption to *"the first story that raises
`wall_time_limit_seconds` materially above the current default — most plausibly Story 3.6"*
(`deferred-work.md` and the four `SCOPE_CONTROLS` markers). AC2 requires ceilings to **exist and
be positive**, not to be larger. This story changes no solver budget magnitude, so the trigger
condition does not fire and the four markers stay pointed where Story 3.5 left them.

State this explicitly in Completion Notes. Without it, a reviewer reading "Story 3.6 owns the
real ceiling" in `deferred-work.md:289`'s prose will reasonably read the preemption item as
inherited too, and raise it as an unshipped obligation.

### Decision 6 — Site concurrency is counted under a transaction-scoped advisory lock, and counted **after** the idempotency replay

Two independent correctness traps, both silent:

**Ordering.** The concurrency check must run **after** `enqueue_compute`'s existing idempotency
lookup and **before** any write. Check it first and a replay of an already-accepted run is
refused by the very run it is replaying — AC3 ("returns the original semantic run response") and
AC4 ("creates no job") would then contradict each other on the same request.

**Race.** Two concurrent POSTs both counting `n < limit` both proceed. Rows that do not exist
yet cannot be locked, so the count must be serialized per site by
`pg_advisory_xact_lock(...)` keyed on the site UUID, taken inside the caller-owned transaction
`enqueue_compute` already runs in.

**Rejected alternative — `SELECT 1 FROM site WHERE id = :site_id FOR UPDATE`.** Simpler and uses
an existing row, but PostgreSQL requires `UPDATE`/`DELETE`/`SELECT FOR UPDATE` privilege for a
row lock, and `a4f92d7c8e31:94-100` revokes `UPDATE` and `DELETE` on every table from the
runtime roles, granting back only named columns. **Verify the grant before choosing** — do not
assume either way from this note; if the advisory-lock function turns out to need a grant the
runtime role lacks, that is a finding to record, not to route around.

Count non-terminal runs from `schedule_run.status` (`schema.py:437-450`), not from
`workflow.job_queue`: AD-23 makes `job_queue` an internal control table that runtime roles have
no table access to, and `schedule_run` is the site-scoped aggregate with RLS already forced.
Non-terminal is `solver_queued`, `solver_running`, `cancellation_requested` — enumerate them
from the closed vocabulary, never by negating the terminal set, so a future status member fails
loudly instead of silently counting as "running".

### Decision 7 — Two new stable problem codes; stale reuses Story 3.2's existing gate

AC4 needs two distinct responses, and AD-13 requires denied/stale/missing/invalid to stay
distinct:

- **`site_concurrency_exhausted` → HTTP 429.** New. 429 rather than 409: this is a bounded
  capacity condition that will succeed later unchanged, not a version conflict the caller must
  resolve. Every existing 409 in this repo (`idempotency_key_conflict`,
  `stale_resource_version`) requires the caller to *change* something first.
- **`stale_proposal` → HTTP 409.** **Already exists and already fires.**
  `create_run_snapshot.py:88-95` raises `SnapshotCreationError("stale_proposal", "proposal is
  stale; silent rebasing is forbidden")` when the proposal's `scenario_version_id` or
  `expected_baseline_schedule_version` differs from the live context, and `enqueue_compute`
  calls it. The code string is also already used by `proposals.py`. This story maps it in
  `schedule_runs.py`'s `_command_problem()`; it does **not** build a second staleness check.

Both codes must appear in `docs/GATE-A-RUNBOOK.md`'s approved-write-path row for the new route
and in the route's `responses=` declaration so they reach the generated OpenAPI.

### Decision 8 — No evidence file, and NFR35 is **not** re-measured here

NFR35's four thresholds are allocated to Stories 1.4, 1.5, 2.4 and 3.5 (`epics.md:1317`,
AD-26); this story has no NFR35 acceptance criterion and owes no evidence file.

Story 3.5's Honest Gap says *"Once Story 3.6 ships the real route, its own acceptance should
re-measure end-to-end"*, and its review disclosed that
`evidence/story-3.5/nfr35-first-run-event.json` measures only read-path delivery — an HTTP
connect plus one indexed row read — not queue-to-visible latency, which is gated by worker lease
acquisition. That re-measurement is now *possible* for the first time. It is deliberately **not
taken**, because no AC requires it and the measurement that would actually be informative
(`run.running.v1`, requiring a lease worker in the test loop) is the same one Story 3.5's review
put out of MVP scope with owner **Story 3.11**.

Record this in `deferred-work.md` rather than dropping it silently: the route now exists, so
Story 3.11 can measure from a real API acknowledgement instead of a seeded bundle.

### Decision 9 — The Draft card acknowledges the run ID; it does **not** render progress

AC1 and `EXPERIENCE.md:125` require an accepted trigger to *"immediately yield a run ID/state"*.
`epics.md:1008-1029` gives **Run progress cards and the Runs workspace to Story 3.7**, and
`epics.md:1017-1021` gives it the literal terminal states.

So on success the Draft card renders one `role="status"` acknowledgement naming the run ID and
the literal status the command returned (`solver_queued`). **No polling, no SSE subscription, no
`run_progress` renderer, no navigation.**

This is structurally clean rather than a compromise: Story 3.5 Decision 1 gave schedule runs
their **own** event stream (`stream_id = schedule_run_id`), so `run.queued.v1` never reaches the
conversation timeline `ActivityTimeline.tsx` renders. There is nothing to suppress. Leave
`ActivityTimeline.test.tsx:431-444`'s use of `run_progress` as its *unknown activity type*
fixture untouched — it stays accurate until Story 3.7.

---

## Honest gaps — raised rather than papered over

### Gap 1 — "proposal **and baseline** versions" has only one drivable half

AC1 requires validating "proposal and baseline versions". `create_run_snapshot.py:88-95` does
compare `expected_baseline_schedule_version` — but Story 3.1 Decision 7 and its Gap 1 recorded
that this field is populated from `ScenarioOverviewV1.baseline_schedule_version`, **which
returns `None` today**: `adapters/postgres/scenario_projection.py` returns literal `None` and
`scenario_catalogue.py` selects `literal(None, type_=String)`. Story 3.2 created the
`schedule_version` aggregate but the **baseline pointer is Epic 4's** (AD-10, Story 4.3).

So the comparison is `None != None` → never trips. **The baseline half of AC1 is structurally
unexercisable at `0545b35`.** Do not fabricate a baseline version to make a test pass, and do
not delete the comparison — it is correct code awaiting a supply.

The drivable half is scenario-version drift, exactly as Story 3.1 proved it: import a second
`scenario_version` for the same scenario and the pinned proposal goes stale immediately. That is
AC4's stale test path. State the reduction in `SCOPE_CONTROLS` "NOT COVERED" form and route it
to Epic 4 in the ledger.

### Gap 2 — "authoritative audit evidence" (AC1, NFR2) has no implementation to call

`AuditEnvelopeV1` is named by AD-20 (`ARCHITECTURE-SPINE.md:208, 330`) and **does not exist in
`backend/` at all** — exhaustive grep returns zero hits across every `.py` file. No code path
writes an audit record anywhere. Every shipped mutating use case says so explicitly:
`cancel_schedule_run.py:22` carries `"NOT COVERED: audit:owned_by_epic_4"`,
`demonstration.py:43` carries `"NOT COVERED: audit envelope emission (Epic 4)."`

This story follows the established precedent and does **not** build the audit contract — that is
Epic 4's (FR21, AD-12), and inventing a partial envelope here would produce a second competing
shape for Story 4.4 to reconcile. What this story *does* owe is the same explicit marker:
`"NOT COVERED: audit:owned_by_epic_4"` in the new module's `SCOPE_CONTROLS` and in the new use
case, plus the manifest's `audit_mapping` free-text declaring what a future envelope would carry.

**AC1's audit clause is therefore satisfied at the same level as every prior mutating story and
no higher.** Recorded here so nobody reports it as newly complete, and so a reviewer does not
raise it as a regression unique to this story.

### Gap 3 — The first route to create `schedule_run` rows has no upgrade path for pre-existing rows

`deferred-work.md:281` (**Owner: Story 3.6**): `a2b3c4d5e6f7` created `workflow.job_queue`
empty with no backfill, so a `schedule_run` row already in `solver_queued`/`solver_running` at
upgrade time has no job row, `_has_current_epoch` is false for every epoch, and both
`mark_running` and `finalize_run` raise `StaleLeaseError` reading *"current is None"*. It was
deferred as structurally unreachable **precisely because no route created such rows** — this
story removes that protection.

Resolution: a **documented drain**, not a backfill. The portfolio is single-instance local (Gate
B) and single-task hosted (Gate C) per AD-24's scope note, and AD-25's cutover already
establishes a maintenance-window drain as the supported procedure. Record the drain step in
`docs/GATE-A-RUNBOOK.md` beside the new write route. A backfill would have to invent a lease
epoch and an attempt for work no worker ever leased.

---

## Tasks / Subtasks

### ⛳ Phase A — the governed command (Tasks 1–6)

- [x] **Task 1 — Harden every ceiling at process start** (AC: 2)
  - [x] `backend/settings.py`: switch `agent_runtime_request_limit`,
        `agent_runtime_tool_calls_limit`, `agent_runtime_deadline_seconds` and the four
        `scheduling_*` limit/timeout settings from `_optional_int`/`_optional_float` (and the
        `... or <default>` idiom) to `_positive_int`/`_positive_float`.
  - [x] Add `agent_runtime_total_tokens_limit` (`AGENT_RUNTIME_TOTAL_TOKENS_LIMIT`) and wire it
        into `create_agent_runtime`'s `AgentBudgetV1` (`agent/runtime.py:480-486`), which
        currently never populates `total_tokens_limit`. Closes `deferred-work.md:128`.
  - [x] Add `agent_runtime_retries_limit` (`AGENT_RUNTIME_RETRIES_LIMIT`) — AC2's only ceiling
        with no field of any kind today — and bound `ModelRetry` re-drives with it.
  - [x] Add `site_max_concurrent_runs` (`SITE_MAX_CONCURRENT_RUNS`), positive-validated.
  - [x] Add `lease_seconds` as a validated setting defaulting from
        `solver_wall_time_limit_seconds`; validate the **relationship**
        (`lease_seconds >= 4 × solver_wall_time_limit_seconds`, the invariant
        `default_lease_seconds()` already encodes), not just positivity. Closes
        `deferred-work.md:289`.
  - [x] Tests, each **observed failing first** (retro A2): an empty `AGENT_RUNTIME_*` value is
        rejected rather than silently meaning "no limit"; a **negative** `SCHEDULING_*_ROW_LIMIT`
        is rejected rather than surviving the `or` fallback; a `lease_seconds` below the solver
        budget is rejected at process start.
  - [x] Add one guard asserting **every** AC2 ceiling is present and positive-validated, driven
        from a named list — so an eighth ceiling added later without validation fails loudly.

- [x] **Task 2 — `compute` risk becomes real in the grant registry** (AC: 1)
  - [x] `CapabilityGrantContextV1` gains `explicit_run_request: bool = False`.
  - [x] `compose_granted_capabilities` (`application/capabilities/registry.py`) refuses to grant
        any module whose `manifest.risk_class == "compute"` unless
        `context.explicit_run_request` is `True`. Keep it a rule about the **risk class**, not
        about a capability name — `test_core_is_capability_name_agnostic`
        (`test_capability_conformance.py:379-393`) forbids naming an installed capability in
        registry code.
  - [x] Test: with `explicit_run_request=False` the module is **absent** from the composed
        toolset (not present-and-denied), matching
        `test_an_ungranted_module_is_absent_from_the_tool_set`.
  - [x] Observe this guard failing with its predicate removed before trusting it.

- [x] **Task 3 — The `scheduling_optimize` capability module** (AC: 1)
  - [x] New `backend/application/capabilities/scheduling_optimize.py`: request/result contracts,
        handler, and `scheduling_optimize_manifest()` with `risk_class="compute"`,
        `approval_policy="none"` (approval is Epic 4's; a compute run changes no baseline),
        budget/timeout from the Task 1 settings, `idempotency_semantics` describing the
        `(actor, site, operation, key)` scope, `audit_mapping`/`evidence_mapping`, a **complete**
        `errors` tuple, and `evaluation_fixtures` pointing at **real files** —
        `test_installed_module_conforms` asserts `(BACKEND_ROOT / path).is_file()` for each.
  - [x] The handler **validates and returns**; it must not write. `AgentDepsV1` carries no
        writer and `test_handler_module_has_no_adapter_or_framework_import` forbids importing
        `adapters`/`sqlalchemy`/`fastapi`/`pydantic_ai`.
  - [x] Declare `SCOPE_CONTROLS` including at least: `"NOT COVERED: audit:owned_by_epic_4"`,
        `"NOT COVERED: versions:baseline_schedule_version_unsupplied_until_epic_4"` (Gap 1), and
        `"NOT COVERED: progress:run_progress_surface_owned_by_story_3_7"`.
        `test_installed_module_records_its_scope_controls` requires at least one `NOT COVERED`.
  - [x] Register in `installed.py:_INSTALLED_FACTORIES`. Declared error codes must **exactly**
        equal the `CapabilityError` subclasses defined in the handler's module — conformance
        asserts set equality, not containment.
  - [x] Golden cases: **NFR28 requires ≥4 per allowed capability**
        (`requirements-inventory.md:49`), and `backend/evals/golden/` is already organised one
        directory per capability (`demonstration`, `scheduling_compute`, `scheduling_draft`,
        `scheduling_inspect`). Add `backend/evals/golden/scheduling_optimize/` with **at least
        four** cases; the dataset total moves 21 → ≥25. This is the one place in the story where
        a count is a floor rather than a ceiling — meet it, then stop. Do not pad, and do not add
        consequential/prohibited cases: this module is `compute`, and NFR28's separate ≥10
        consequential/prohibited floor is Epic 4's.

- [x] **Task 4 — Thread the requesting actor through `enqueue_compute`** (AC: 1, 3)
  - [x] `enqueue_compute` gains an explicit `actor_id: UUID` keyword argument; use it for the
        `command_idempotency` actor column **and** the `create_queued_run` actor, replacing
        `record.created_by_actor_id` (`enqueue_compute.py:85`).
  - [x] Populate `JobLeaseV1.capability_version` from the new manifest, removing
        `"NOT COVERED: contracts:capability_version_unpopulated_until_story_3_6"` from
        `enqueue_compute.py:26` **and** `lease_and_execute_schedule_run.py:62`. **No migration
        is owed** — verified: `job_queue.capability_version` already exists as
        `Column("capability_version", String(80), nullable=True)`
        (`adapters/postgres/schema.py:521`), and `JobLeaseV1.capability_version` is already
        `str | None = None` (`job_lease.py:48`). The column is nullable and 80 characters wide;
        the manifest's version string must fit.
  - [x] Update the three existing tests in `test_enqueue_compute.py` to pass an actor explicitly.
  - [x] Test: two different actors with the **same** idempotency key and the same proposal get
        two distinct runs — the defect `deferred-work.md:273` describes. Close `:273`.

- [x] **Task 5 — Site concurrency gate** (AC: 4)
  - [x] In `enqueue_compute`, **after** the idempotency replay lookup and **before** any write
        (Decision 6): take `pg_advisory_xact_lock` keyed on the site, count `schedule_run` rows
        whose status is in the explicitly enumerated non-terminal set, and raise a new
        `SiteConcurrencyExhaustedError` when the count reaches `settings.site_max_concurrent_runs`.
  - [x] Verify the runtime role can execute the advisory-lock function before relying on it; if
        it cannot, record the finding rather than routing around the grant model.
  - [x] Test: a replay of an accepted run **succeeds** even when concurrency is exhausted (this
        is the ordering trap — assert it, do not assume it).
  - [x] Test: two concurrent enqueues against a limit of 1 produce exactly one run.
  - [x] Test: the enumerated non-terminal set is exhaustive against `ScheduleRunStatusV1` — a new
        status member must fail this test, not silently count as terminal.

- [x] **Task 6 — The route** (AC: 1, 3, 4)
  - [x] `POST /api/v1/schedule-runs` on `api/routers/schedule_runs.py` (Decision 2). Body
        `{proposal_id, expected_resource_version}`, header `Idempotency-Key` (`max_length=40`),
        response the created run's id + literal status + resource version.
  - [x] Compose the grant with `explicit_run_request=True`, resolve the module, invoke its
        handler to validate, then call `enqueue_compute` on the request transaction.
  - [x] Extend `_command_problem()` with `site_concurrency_exhausted` → **429** and
        `stale_proposal` → **409**; keep `idempotency_key_conflict` → 409 and
        `stale_resource_version` → 409 consistent with `proposals.py`.
  - [x] Register the route in `test_gate_a_mutation_audit.py`'s `versioned` literal
        (`:257-269`) **and** in `docs/GATE-A-RUNBOOK.md`'s approved-write-path table — both, or
        `test_gate_a_write_surface_is_exactly_the_approved_paths` and
        `test_runbook_records_every_versioned_write_path` fail independently.
  - [x] Add the Gap 3 drain step to `docs/GATE-A-RUNBOOK.md` beside the new route. Close
        `deferred-work.md:281`.

- [x] **⛳ Checkpoint — commit Phase A and report five numbers.** Backend test count before and
      after; number of `SCOPE_CONTROLS` markers naming Story 3.6 remaining (target: zero);
      number of `deferred-work.md` entries closed (target: four — `:128`, `:273`, `:281`,
      `:289`); Gate A verdict. Do not start Phase B on a red Phase A.

### ⛳ Phase B — the planner-facing control (Tasks 7–10)

- [x] **Task 7 — Codegen and the typed client** (AC: 1)
  - [x] `npm run codegen` from `frontend/` (`codegen:export` then `codegen:types`). Both
        `frontend/openapi.json` and `frontend/src/api/schema.d.ts` change. **Never hand-edit
        either.**
  - [x] New `frontend/src/api/scheduleRuns.ts` — no such file exists today. Derive every type
        through the `paths["/api/v1/schedule-runs"]["post"][...]` idiom
        (`api/proposals.ts:4-16`); hand-author no interfaces. Keep the wrapper's
        `if (error) throw { ...error, status: response.status }; return data;` shape.
  - [x] New `frontend/src/hooks/useStartScheduleRun.ts`, copying `useReviseProposal.ts` **line
        for line** including `createIdempotencyKeyHolder()` in a `useRef` and `settle()` **only**
        in `onSuccess` — the key must survive `onError` so a retry after a lost response replays
        rather than minting a second key. That comment in `lib/idempotency.ts:1-13` is
        load-bearing, not decoration.

- [x] **Task 8 — The Run optimization control** (AC: 1, 4)
  - [x] `DraftCard.tsx` gains a **Run optimization** button in the footer beside Revise and
        Reject. It is **visually discontinuous from Send** (UX-DR35, NFR19,
        `DESIGN.md` "Send and Run optimization cannot share the same primary control
        treatment"). Introduce no new palette (UX-DR33), no glow/gradient/pulse (UX-DR32).
        `min-h-11` like every other Chat control.
  - [x] Disabled when the proposal is `stale` or `rejected` or a mutation is pending, with
        `aria-describedby` pointing at a visible explanation — the exact pattern
        `DraftCard.tsx:231-238` already uses for Revise. `Button` has **no built-in busy
        variant**; the house convention is `disabled={mutation.isPending}` with static label
        text and no spinner (`DraftCard.tsx:240`, `Composer.tsx:84`). Follow it.
  - [x] **Accessible sequencing copy** (AC1): text stating that running optimization starts a
        computation and changes no baseline. Operational and bounded — no ETA, no percentage, no
        anthropomorphic waiting, no celebration (UX-DR5).
  - [x] On success render one `role="status"` acknowledgement naming the run ID (in
        `{typography.identifier}` monospace) and the literal returned status. **No progress, no
        polling, no navigation** (Decision 9).
  - [x] Extend `commandMessage()` for **429** (`site_concurrency_exhausted`) with copy that says
        the site is at its run limit and to try again shortly. Note the existing helper branches
        on HTTP `status` only; `getErrorCode()` exists in `lib/errors.ts` but nothing uses it
        yet — if you branch on the RFC 7807 `code`, do it consistently, do not half-migrate.
  - [x] Stale path (AC4): the card keeps the draft, keeps its values, and offers only Refresh
        proposal — the control already shipped by Story 3.1. Never silently refetch into a
        rebased draft.
  - [x] **Invert `DraftCard.test.tsx:90`**, which currently asserts
        `queryByRole("button", { name: /run optimization/i })` is **not** in the document. Change
        the assertion; do not add a second one beside a now-false one.

- [x] **Task 9 — Accessibility proof and the UX-DR35 assertion** (AC: 1)
  - [x] Extend `frontend/src/test/accessibility-contract.test.tsx` — **not** a sibling file.
        `deferred-work.md:206` records that Story 2.8's sibling sits outside the
        `accessibility_component_layer` Gate A check's hand-written file list, so its assertions
        are protected by CI but invisible to Gate A. Do not create a second orphan.
  - [x] Assert: Run optimization has a distinct accessible name from Send, Revise and Reject; the
        disabled state carries an accessible explanation; the run-ID acknowledgement is
        announced through the existing polite live-region pattern; status meaning never depends
        on colour alone (UX-DR32, NFR18).
  - [x] **Ship the automated Send-versus-Run discontinuity assertion** that
        `deferred-work.md:181` names this story as owner of. `EXPERIENCE.md`'s Accessibility
        Floor makes automated coverage the only accepted proof here. Close `:181`.
  - [x] **Add no new Playwright spec.** Story 3.12 owns the end-to-end repair journey, and a new
        spec inside a Gate A check trips `deferred-work.md:208`'s reporter-truncation item.

- [x] **Task 10 — Fences, ledger, regression, Gate A** (AC: 1, 2, 3, 4)
  - [x] Verify every zero-line fence in *Project Structure Notes* with `git diff --stat`.
  - [x] Ledger: close `:128`, `:181`, `:273`, `:281`, `:289`. Add the Decision 8 (NFR35
        re-measurement now possible, owner Story 3.11) and Gap 1 (baseline version unsupplied,
        owner Epic 4) entries. **Leave Story 3.5's mid-solve-preemption re-pointing untouched**
        (Decision 5) and say so in Completion Notes.
  - [x] Full regression: backend default, `pytest -m postgres`,
        `pytest tests/test_evidence_convention.py`, `alembic check` from the repository root,
        `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npx playwright test`,
        refreshed Gate A verdict.

## Dev Notes

### The traps, ranked by how quietly they fail

1. **Checking concurrency before the idempotency replay.** Silently turns AC3 and AC4 into a
   contradiction: the replay of an accepted run is refused by the run it is replaying. Every
   test still passes if you only test them separately (Decision 6).
2. **Trusting `_optional_int`'s "empty means no limit" as safe.** It is documented, deliberate,
   and directly violates AC2. An operator setting `AGENT_RUNTIME_TOOL_CALLS_LIMIT=` gets an
   unbounded run and no error anywhere.
3. **Fixing the `or <default>` idiom by changing the default.** The bug is that a **negative**
   value is truthy and survives; a new default does not touch that path.
4. **Fabricating a baseline schedule version to exercise AC1's "baseline versions".** It is
   `None` everywhere by design until Epic 4 (Gap 1). A test that invents one proves nothing and
   will contradict Story 4.3.
5. **Granting `compute` by inspecting message text.** That is the model deciding its own
   authority (AD-2). `explicit_run_request` comes from the transport, never from content.
6. **Making the registry rule name `scheduling_optimize`.** `test_core_is_capability_name_agnostic`
   forbids it. Branch on `manifest.risk_class`.
7. **Giving the capability handler a repository or connection so it can enqueue.** Structurally
   forbidden — `AgentDepsV1` has no writer and the conformance import fence blocks `adapters`.
   Story 3.1 Decision 1 already settled this shape.
8. **Rendering a run progress card or subscribing to the SSE stream.** That is Story 3.7's whole
   acceptance boundary (Decision 9).
9. **Declaring manifest `errors` that do not exactly match the handler module's
   `CapabilityError` subclasses.** Conformance asserts **set equality** — an extra declared code
   fails just as loudly as a missing one.
10. **Adding the new POST to only one of `test_gate_a_mutation_audit.py` and
    `docs/GATE-A-RUNBOOK.md`.** They are checked by two independent tests.
11. **Negating the terminal status set to find "running" runs.** Enumerate the non-terminal
    members explicitly so a future `ScheduleRunStatusV1` addition fails loudly.
12. **Minting a fresh idempotency key per attempt on the frontend.** `settle()` belongs in
    `onSuccess` only. A key minted per attempt can never replay a lost-response success and
    produces spurious 409s (`lib/idempotency.ts:1-13`).

### Testing requirements

- `pytest -m postgres` for the concurrency gate, the advisory lock, the actor-scoped idempotency
  change, and the new route — this repository's live-PostgreSQL suite is where CAS, race and
  constraint behaviour is actually proven, not the SQLite-fallback path.
- Capability conformance runs automatically over `installed_modules()`; the new module inherits
  every assertion in `test_capability_conformance.py` the moment it is registered. Run that file
  early — it fails on manifest shape long before the route exists.
- **Observe each new guard failing** with its assertion removed before trusting it green (retro
  A2), and record the observation in Completion Notes — the pattern Stories 3.3, 3.4 and 3.5 all
  followed.
- Frontend: mock hooks directly rather than the API client, matching `DraftCard.test.tsx`'s
  `vi.mock("@/hooks/useProposal")` convention; assert by role and accessible name.

### Project Structure Notes

- **Touches:** `backend/settings.py`, `backend/agent/runtime.py`,
  `backend/application/capabilities/{registry,installed,scheduling_optimize}.py`,
  `backend/application/contracts/{capability_manifest,job_lease}.py` (if the grant context or
  capability-version field moves), `backend/application/use_cases/{enqueue_compute,
  lease_and_execute_schedule_run}.py`, `backend/api/routers/schedule_runs.py`,
  `backend/api/schemas.py`, `backend/api/deps.py`, `backend/worker/lease_worker.py`,
  `backend/evals/` (new golden cases), `backend/tests/**`, `docs/GATE-A-RUNBOOK.md`,
  `_bmad-output/implementation-artifacts/deferred-work.md`,
  `frontend/src/api/scheduleRuns.ts` (new), `frontend/src/hooks/useStartScheduleRun.ts` (new),
  `frontend/src/features/chat/DraftCard.tsx`, `frontend/src/test/accessibility-contract.test.tsx`,
  `frontend/openapi.json`, `frontend/src/api/schema.d.ts`.
- **Zero-line diff fences** (verify with `git diff --stat` before claiming): `backend/domain/**`,
  `backend/engine/**`, `backend/llm/**`, `backend/ingest/**`, `backend/store/**`,
  `backend/services/**`, `backend/migrations/**` (**no migration** — every new ceiling is
  configuration, and the concurrency gate reads an existing table),
  `backend/application/capabilities/scheduling_compute.py` (the similarly-named `inspect`-risk
  module is **not** this story's), `frontend/src/features/chat/ActivityTimeline.tsx`,
  `frontend/src/features/chat/Composer.tsx`, `frontend/e2e/**`.
- Naming matches existing conventions exactly: capability modules
  `application/capabilities/<snake_case>.py` with a `<name>_manifest()` factory; use cases
  imperative in `application/use_cases/`; contracts PascalCase + `V1` in
  `application/contracts/`; frontend hooks `use<Verb><Noun>.ts`, API wrappers `camelCase.ts`,
  components `PascalCase.tsx`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.6, lines 979-1006] — story statement and all four ACs, verbatim.
- [Source: _bmad-output/planning-artifacts/epics.md, lines 47, 79, 107, 111, 150, 154, 168, 186, 194, 246, 847, 1542] — FR12, NFR2, NFR16, NFR19, AR5, AR8, AR22, UX-DR5, UX-DR9, UX-DR35, Epic 3 sequencing.
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md, lines 54-58, 60-64, 72-76, 84-88, 132-136, 138-142, 162-166, 216-220, 258-259, 328] — AD-2, AD-3, AD-5, AD-7, AD-8, AD-9, AD-13, AD-22, Consistency Conventions, `JobLeaseV1` shape.
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md, lines 23, 37, 40] — NFR2, NFR16, NFR19.
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md, lines 123, 125, 196, 274-280] — Chat/Runs states, Accessibility Floor, Flow 5.
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md] — Chat composer and Draft card visual contracts.
- [Source: backend/application/use_cases/enqueue_compute.py, whole file] — the bundle this story finally calls; `:26` and `:85` are the two lines it changes.
- [Source: backend/application/use_cases/create_run_snapshot.py, lines 88-95] — the existing `stale_proposal` gate AC4 reuses.
- [Source: backend/application/capabilities/{registry,installed,module,scheduling_draft}.py] — grant composition and the module shape to copy.
- [Source: backend/application/contracts/capability_manifest.py, lines 20-33] — `RiskClassV1` and `INSTALLABLE_RISK_CLASSES`.
- [Source: backend/tests/test_capability_conformance.py, lines 114-148, 258-341, 379-393] — every assertion a new module must satisfy.
- [Source: backend/settings.py, lines 161-210, 272-292] — the two broken parser idioms and the correct `_positive_*` helpers.
- [Source: backend/api/routers/{schedule_runs,proposals}.py] — route, problem-mapping and idempotency-header patterns.
- [Source: backend/tests/test_gate_a_mutation_audit.py, lines 243-272, 508-544] — the write-surface literal and the runbook cross-check.
- [Source: frontend/src/features/chat/DraftCard.tsx and DraftCard.test.tsx, line 90] — the card this story extends and the assertion it inverts.
- [Source: frontend/src/hooks/useReviseProposal.ts, frontend/src/lib/idempotency.ts] — the mutation-hook and idempotency-key templates.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, lines 128, 181, 206, 208, 273, 281, 289] — the five items this story closes and the two traps it must avoid.
- [Source: _bmad-output/implementation-artifacts/3-1-create-and-revise-a-reversible-repair-draft.md] and [Source: .../3-5-persist-literal-run-state-and-replay-progress.md] — prior-story decisions this story inherits rather than re-litigates.
- [Source: docs/DOMAIN-MODEL.md] — cited per project convention; this story touches no metric, demand row, or assignment.

### Baselines at creation — re-derive them, do not trust them

Collected at `0545b35`. Re-derive before attributing any failure to this story: backend suite
counts (Story 3.5 finished at 1111 passed, 1 skipped, 7 deselected), frontend Vitest (410
passed), Playwright (48 cases), installed capability modules (**4** — `scheduling_compute`,
`scheduling_draft`, `scheduling_inspect`, `shiftmind_demonstration`), versioned write routes
(**7**), golden case files (**21** across **4** `backend/evals/golden/` directories).

Expected after this story: installed modules **5**, versioned write routes **8**, golden case
files **≥25** across **5** directories. If any of those three lands on a different number,
something was added or missed that this story did not intend.

## Dev Agent Record

### Agent Model Used

OpenAI GPT-5 Codex

### Debug Log References

- Task 1 RED: the focused suite failed at collection because `AC2_CEILING_FIELDS` did not exist;
  the new settings/retry assertions therefore could not pass against the baseline.
- Task 1 GREEN: 105 focused tests passed (1 skipped); the correctly scoped backend regression
  passed with 1126 tests, 2 skipped, and 7 deselected.
- Task 2 RED: the explicit-run grant test failed because the trusted grant context had no
  `explicit_run_request` field; after the risk-class predicate was added, conformance passed.
- Task 2 GREEN: 44 conformance tests and the 1127-test backend regression passed.
- Task 3 RED: the module tests failed at import because `scheduling_optimize` did not exist.
- Task 3 GREEN: 132 focused tests passed; the backend regression passed with 1142 tests, 2
  skipped, and 7 deselected. Installed modules are now 5 and golden files 25 across 5 folders.
- Task 4 RED: all four enqueue tests rejected the new explicit `actor_id` argument against the
  baseline signature.
- Task 4 GREEN: 4 focused enqueue tests and the 1143-test backend regression passed.
- Phase A checkpoint review RED: the actor-scope regression exposed that snapshot/queued-run
  attribution still used the proposal author while job and idempotency attribution used the
  requester.
- Phase A checkpoint review GREEN: enqueue now passes the requester through snapshot creation;
  11 focused snapshot/enqueue tests, 1154 default backend tests, and all 84 PostgreSQL tests pass.
- Task 5 RED: the unit suite could not import the concurrency contract; separately, removing the
  advisory-lock body made the real two-session race fail with two created runs.
- Task 5 GREEN: 7 unit tests, the PostgreSQL race/advisory-role proof, the inherited NFR35 test,
  and the 1147-test backend regression passed.
- Task 6 RED: all start-route tests failed because the schedule-runs router exposed no enqueue
  command.
- Task 6 GREEN: 56 route/Gate A/enqueue tests and the 1154-test backend regression passed.
- Phase A checkpoint: commit `02ab5e6`; backend count 1111 before and 1155 after; zero Story 3.6
  scope-control markers remain; four named deferred-work entries are closed/resolved; all 84
  PostgreSQL tests and the freshly bound Gate A evidence pass.
- Task 7 RED: focused Vitest could not resolve the absent `scheduleRuns` client and
  `useStartScheduleRun` hook.
- Task 7 GREEN: 3 focused tests, TypeScript, and the full 413-test frontend suite pass; the retry
  regression proves a failed command keeps its key and a successful command rotates it.
- Task 8 RED: five Draft-card assertions failed because no Run control, disabled explanation,
  acknowledgement, or 429 copy existed.
- Task 8 GREEN: all 9 focused card tests, the 24-test accessibility contract, TypeScript, and the
  full 415-test frontend suite pass.
- Task 9 RED proof: temporarily replacing Run's secondary variant with default and its polite
  live-region setting with `off` made the Gate A-visible contract fail on both exact guards.
- Task 9 GREEN: all 25 accessibility-contract tests and the full 416-test frontend suite pass;
  no Playwright file was added.
- Task 10 GREEN: zero fenced files changed; five named ledger items are closed/resolved; the
  evidence convention has 55 passing tests; Alembic reports no new upgrade operations; lint,
  typecheck, and production build pass; final backend is 1155 passed/1 skipped/7 deselected;
  PostgreSQL is 84 passed; Vitest is 416 passed; Playwright is 48 passed; refreshed Gate A is
  true across every AR28, NFR29, and AC2 category.

### Implementation Plan

- Implement each story task in order using focused red/green tests, then run the backend or
  frontend regression surface required by that task before checking it complete.

### Completion Notes List

- Task 1: all seven FR12 ceilings are positive application settings; malformed empty/negative
  values fail at startup, retries and token limits reach AgentRuntime, and the lease duration is
  validated to cover at least four solver wall-time budgets.
- Task 2: compute-risk modules are absent unless trusted transport context explicitly marks the
  request as a run request; the registry rule remains capability-name agnostic.
- Task 3: registered `scheduling_optimize` as a write-free compute validator with trusted result
  identity, exact declared errors, explicit scope reductions, and four genuine golden cases.
- Task 4: idempotency, queued-run, and queued-job identity now use the requesting actor,
  different actors may reuse a key independently, and queued jobs persist the optimize manifest
  version.
- Task 5: replay is resolved before capacity, new work is serialized per site with a PostgreSQL
  transaction advisory lock, and the explicit non-terminal status set enforces the configured
  site limit without races.
- Task 6: `POST /api/v1/schedule-runs` validates the transport-owned compute grant and command,
  returns a durable queued run identity, maps stable bounded/stale problems, and is recorded in
  both Gate A write-surface controls with the required pre-upgrade drain.
- Phase A checkpoint: committed as `02ab5e6`; all five reported measures meet their targets and
  Gate A is green against evidence regenerated from that clean commit.
- Task 7: OpenAPI was regenerated from the backend route; the exclusively schema-derived client
  and mutation hook preserve idempotency identity through errors and settle only on success.
- Task 8: the Draft card exposes a secondary, bounded Run optimization command; it preserves
  stale/rejected drafts, serializes mutations, reports stable errors, and acknowledges only the
  durable queued run identity and literal status.
- Task 9: the existing Gate A-visible accessibility contract proves distinct command names,
  visible disabled reasoning, polite identifier/status acknowledgement, literal non-colour
  status meaning, and Send-versus-Run visual discontinuity; deferred item `:181` is closed.
- Task 10: all structural fences, ledger obligations, regressions, migration drift checks, and
  clean-commit Gate A evidence pass. Decision 8's NFR35 re-measurement remains owned by Story
  3.11; Gap 1's baseline-version supply remains owned by Epic 4. Story 3.5's mid-solve
  preemption re-pointing was deliberately left untouched because the solver wall-time default
  remains 30 seconds.

### File List

- backend/agent/runtime.py
- backend/application/use_cases/lease_and_execute_schedule_run.py
- backend/application/use_cases/enqueue_compute.py
- backend/application/use_cases/create_run_snapshot.py
- backend/application/ports/schedule_run.py
- backend/adapters/postgres/schedule_run.py
- backend/api/routers/schedule_runs.py
- backend/api/schemas.py
- backend/tests/test_schedule_runs_api.py
- backend/tests/test_gate_a_mutation_audit.py
- docs/GATE-A-RUNBOOK.md
- _bmad-output/implementation-artifacts/deferred-work.md
- backend/application/capabilities/registry.py
- backend/application/capabilities/installed.py
- backend/application/capabilities/scheduling_optimize.py
- backend/evals/README.md
- backend/evals/golden/scheduling_optimize/key-boundary.json
- backend/evals/golden/scheduling_optimize/replay.json
- backend/evals/golden/scheduling_optimize/valid.json
- backend/evals/golden/scheduling_optimize/version-bound.json
- backend/tests/test_capability_conformance.py
- backend/tests/test_evaluation_harness.py
- backend/tests/test_scheduling_optimize.py
- backend/tests/architecture/test_execute_turn_boundaries.py
- backend/settings.py
- backend/tests/test_agent_runtime_adapter.py
- backend/tests/test_lease_worker.py
- backend/tests/test_enqueue_compute.py
- backend/tests/test_job_leasing_postgres.py
- backend/tests/test_postgres_integration.py
- backend/tests/test_scheduling_inspect.py
- backend/tests/test_settings.py
- backend/worker/lease_worker.py
- _bmad-output/implementation-artifacts/3-6-start-explicit-bounded-optimization.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- frontend/src/api/scheduleRuns.ts
- frontend/src/api/scheduleRuns.test.ts
- frontend/src/hooks/useStartScheduleRun.ts
- frontend/src/hooks/useStartScheduleRun.test.tsx
- frontend/src/features/chat/DraftCard.tsx
- frontend/src/features/chat/DraftCard.test.tsx
- frontend/src/test/accessibility-contract.test.tsx

## Change Log

- 2026-08-21: Implemented explicit bounded optimization start end-to-end: hardened operational
  ceilings, compute-risk transport grants, actor-scoped idempotent enqueue with per-site
  concurrency, the versioned start route, generated typed client/hook, accessible Run control,
  ledger closures, and complete Gate A verification.
