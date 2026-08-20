---
baseline_commit: 2d41ee8ff8dccb350dbba0a6cc6a12e1a5c5fc17
---

# Story 3.3: Lease Solver Jobs with Fencing [Technical Enabler]

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the scheduling platform,
we want accepted optimization work leased and fenced durably,
so that when runs become startable in Story 3.6, recovery can never lose a run or repeat its
effects.

**Planner-visible outcome: none.** No route, no capability, no frontend file. Accepted through
seeded enqueue, lease, and fencing tests at the application/port boundary and the worker boundary.
`frontend/**` must be a **zero-line diff**.

**Depends on, and consumes:** Story 3.2's `RunSnapshotV1`, `create_run_snapshot`,
`ScheduleRunRepository`, `execute_schedule_run`/`finalize_schedule_run`, the `run_snapshot` /
`schedule_run` / `schedule_version` / `schedule_assignment` tables; Story 3.1's `command_idempotency`
table and its `get_idempotent_result`/`_store_idempotent_result` pattern
(`adapters/postgres/proposal.py:98-203`); AD-6, AD-18, AD-23's PostgreSQL leasing design.

**Unblocks:** Story 3.4 (cancellation sets this story's `cancellation_requested` flag and observes it
cooperatively), Story 3.5 (the state machine this story's fencing protects, and the persisted-event
gap this story again defers), Story 3.6 (the run command enqueues through this story's bundle and
supplies a real HTTP idempotency key), Story 3.7 (a monitorable job).

**Scope summary:** One migration (new `workflow` schema, one table, two owner-held functions, one new
NOLOGIN role). One new contract (`JobLeaseV1`). One port extension
(`ScheduleRunRepository` gains job/lease methods) and its adapter, plus one small additive field on
`ProposalRepository`'s existing `ProposalRecordV1` (Decision 3). Two new use cases (enqueue-compute,
lease-and-execute). One new `backend/worker/` package — the first in the repository. **No new
dependency.** No router. No capability. No evidence file. No frontend change.

**This story is the first in the repository to:**

1. create a `workflow`-schema table. `schema.py` at `2d41ee8` defines two non-`public` schemas only:
   `auth` (`session_index`, `login_handshake`) and implicitly `public` for everything else. No
   `workflow` schema exists;
2. use `FOR UPDATE SKIP LOCKED`. Verified by exhaustive grep across `backend/**`: zero hits for
   `SKIP LOCKED`;
3. introduce a second runtime database role. Every migration through `f1a2b3c4d5e6` grants only
   `shiftmind_runtime` (`migrations/versions/d128d081ab48_establish_governed_fixture_history.py:230-238`);
   AD-23's "API, worker, and lease roles" are still one role today;
4. populate `AD-12`'s `attempt_id` concept anywhere in the schema. Verified by grep: `attempt_id`
   appears nowhere under `backend/adapters/**` or `backend/application/**`;
5. give `ScheduleRunRepository.mark_running` / `.finalize_run` a concurrency guard beyond a bare
   status compare-and-set. Today (`adapters/postgres/schedule_run.py:23-36, 125-140`) either method
   can be called by **anything holding the runtime role**, with no lease, no owner check, and no
   fencing — the exact gap this story exists to close;
6. create a `backend/worker/` package. The Structural Seed (`ARCHITECTURE-SPINE.md:296`) names it;
   nothing under that path exists yet.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. None of it may be re-derived from adapter
code (retro §3.2 — the single most expensive pattern of Epics 1–2).

| Fact | Where it is written |
|---|---|
| Accepted messages, agent runs, jobs, approvals, schedule runs, outcomes, and progress events are committed **before acknowledgement**; a lease has owner, expiry, heartbeat, and a **monotonically increasing fencing epoch**; checkpoint/effect commits require the **current** epoch; unique effect keys make expired-worker recomputation harmless | AD-6 (`ARCHITECTURE-SPINE.md:78-82`) |
| Lease PostgreSQL jobs with explicit concurrency and recovery; introduce SQS only after a measured need; a workflow engine is out of scope | AD-18 (`ARCHITECTURE-SPINE.md:192-196`) |
| NOLOGIN `shiftmind_owner` owns tables/functions; API/worker/lease roles are `NOINHERIT NOSUPERUSER NOBYPASSRLS` and **own no tables**; internal `workflow.job_queue` is **not a direct tenant query surface** and grants runtime roles no table access; the **lease role may only execute** owner-held `SECURITY DEFINER workflow.lease_next_job`, which uses `FOR UPDATE SKIP LOCKED` and returns job/site/actor/fencing context; that function revokes PUBLIC, grants EXECUTE only to its caller role, fixes `search_path`, and contains no dynamic SQL; domain work starts a **new** RLS-scoped transaction | AD-23 (`ARCHITECTURE-SPINE.md:222-226`) |
| `JobLeaseV1`'s required shape: job/type/status, site/actor/attempt IDs, contract/capability versions, payload ref, idempotency key, lease owner/expiry/fencing epoch, cancellation flag | AD-20 *Normative contract minimums* (`ARCHITECTURE-SPINE.md:328`) |
| `AgentRun`, `ScheduleRun`, and `ApprovalRequest` use **separate closed graphs**; adapters may project a combined timeline but never merge stored status types | AD-7 (`ARCHITECTURE-SPINE.md:84-88`) — a job's own status vocabulary is Workflow's, not `ScheduleRunStatusV1`'s |
| AD-22 aggregate ownership: **Workflow owns `job`, `persisted_event`**; only an application orchestrator crosses owners; the `enqueue-compute` bundle is fixed as **immutable run snapshot + job + event** | AD-22 (`ARCHITECTURE-SPINE.md:216-220`) |
| Each mutating command requires an idempotency key scoped to actor, site, operation, and canonical body hash **plus expected resource version**; a replay returns the original semantic result, a conflicting body fails | AD-8 (`ARCHITECTURE-SPINE.md:132-136`) |
| Each accepted attempt has a server-generated `attempt_id`; idempotent replay returns that attempt, a deliberate retry gets a **new** ID | AD-12 (`ARCHITECTURE-SPINE.md:160`) |
| Persisted events for `ScheduleRun` cannot be inserted today — `persisted_event` requires `conversation_id`/`agent_run_id` NOT NULL with FKs plus `CHECK (stream_id = conversation_id)`; Story 3.2 recorded the AD-22 "+event" clause as `NOT COVERED`, owned by Story 3.5 | Story 3.2 Decision 8 (`3-2-...md:242-257`); `schema.py:309-329` |
| `mark_running`/`finalize_run` today do a **bare status compare-and-set with no lease check at all** | `adapters/postgres/schedule_run.py:23-36, 125-140` (verified above) |
| The idempotent-replay pattern already exists and is reusable: `get_idempotent_result`/`_store_idempotent_result` against the shared `command_idempotency` table, keyed on `(site_id, actor_id, operation, idempotency_key)` with `body_hash` conflict detection | `adapters/postgres/proposal.py:98-203`; `application/use_cases/manage_proposal.py:89-138` |
| No hand-typed evidence file; commit code → measure → generate → commit evidence separately | `docs/EVIDENCE-CONVENTION.md` |
| Manual assistive-technology verification is out of scope; automated coverage is the recorded bar | `EXPERIENCE.md:196` |
| Every new guard must be **observed failing** with its structural assertion removed | retro §6.1 action A2 |

This story's own numbers, not demand/metrics, are the load-bearing facts here — `docs/DOMAIN-MODEL.md`
governs no table this story touches, so it is cited for completeness only and not re-derived.

---

## Eight decisions were made at story creation — do not re-litigate them

### Decision 1 — The job lives in a new `workflow.job_queue` table, not a column bolted onto `schedule_run`

AD-22 names `job` and `persisted_event` as **Workflow**-owned aggregates, distinct from Scheduling's
`schedule_run`. Folding lease/fencing columns onto `schedule_run` would let one Scheduling-owned row
carry Workflow's authority, which is exactly the "two modules owning one entity" AD-22 forbids.
`workflow.job_queue` carries:

| Column | Purpose |
|---|---|
| `id`, `site_id` | identity, RLS predicate |
| `job_type` | closed `Literal["schedule_run_execute"]` — one member today, extensible later |
| `status` | closed `Literal["queued","leased","completed"]` — **Workflow's own vocabulary**, never `ScheduleRunStatusV1` (AD-7 forbids merging stored status types) |
| `schedule_run_id` | the **payload reference** AD-20 requires — this job's `schedule_run` row; also the FK target, so no separate `payload_ref` column is needed |
| `actor_id` | sourced from `proposal.created_by_actor_id` (Decision 3) |
| `attempt_id` | NULL until first lease; regenerated (new UUID) on **every** lease acquisition (AD-12) |
| `contract_version` | `RunSnapshotV1.SCHEMA_VERSION` at enqueue time |
| `capability_version` | **NULL in this story** — see Decision 7 |
| `lease_owner`, `lease_expires_at`, `heartbeat_at`, `fencing_epoch` | AD-6's lease shape; **written only by owner-held functions**, never by a granted UPDATE (Decision 2) |
| `cancellation_requested` | boolean flag; representable now, set by nobody until Story 3.4 (Decision 7) |
| `created_at` | enqueue time |

`schedule_run_id` gets a `UniqueConstraint` — exactly one job per schedule run, matching Story 3.2's
1:1 `schedule_run` → `schedule_version` pattern (`uq_schedule_version_run`).

### Decision 2 — Two owner-held `SECURITY DEFINER` functions, and a new role that can execute only one of them

AD-23 names `workflow.lease_next_job` explicitly and says the lease role "may only execute" it —
**never direct table access**. That sentence is only true if the role that leases is *different* from
the role that later does the domain work inside the leased job, because the domain work needs real
table grants (`SELECT`/`INSERT` on `run_snapshot`/`schedule_version`/`schedule_assignment`, narrow
`UPDATE` on `schedule_run`) that a lease-only role must not have.

**Decision:** introduce exactly one new role, `shiftmind_lease` (`NOLOGIN NOINHERIT NOSUPERUSER
NOBYPASSRLS`, owns no tables), granted `EXECUTE` on `workflow.lease_next_job` and nothing else. The
worker's domain transaction — reading the leased snapshot, calling the solver, finalizing the run —
**reuses `shiftmind_runtime`**, the same role the API already uses. This is a deliberate
simplification, not an oversight: `shiftmind_runtime` already carries exactly the grants that domain
work needs (Story 3.2's migration), a second `shiftmind_worker` role would need the identical grant
set duplicated for no behavioral difference, and the Deferred table's "Multiple roles and separation
of duties" entry (`ARCHITECTURE-SPINE.md:455`) — "one seeded planner may self-approve," revisited only
at a second user or security review — already establishes that duplicating roles ahead of a measured
need is out of scope for this milestone. **State this in `SCOPE_CONTROLS` as
`roles:worker_reuses_shiftmind_runtime`.**

A second owner-held function, `workflow.renew_job_lease(job_id, fencing_epoch, extension_seconds) ->
boolean`, is added alongside `lease_next_job`. AD-23 names only `lease_next_job` explicitly, but AD-6
requires a **heartbeat**, and a heartbeat that merely UPDATEs `heartbeat_at`/`lease_expires_at`
through a granted column privilege would let any `shiftmind_runtime` holder extend *any* lease,
including one it does not own — defeating fencing. `renew_job_lease` re-checks the caller-supplied
`fencing_epoch` against the current row before extending, exactly like `lease_next_job` re-checks it
before accepting a commit (Decision 4). Both functions revoke PUBLIC, grant EXECUTE only to their
caller role (`lease_next_job` → `shiftmind_lease`; `renew_job_lease` → `shiftmind_runtime`), fix
`search_path`, and contain no dynamic SQL, matching AD-23's literal requirements for the one function
it does name.

### Decision 3 — `create_run_snapshot` is wrapped, not rewritten, by a new `enqueue_compute` use case that adds the job row and idempotency

Story 3.2's `create_run_snapshot` (`application/use_cases/create_run_snapshot.py:58-134`) already
inserts `run_snapshot` + `schedule_run(status='solver_queued')` atomically, but takes no actor and no
idempotency key — it was never meant to be the full AD-22 `enqueue-compute` bundle, only the immutable
snapshot half of it. **This story does not change its signature.** A new
`application/use_cases/enqueue_compute.py :: enqueue_compute` wraps it:

1. Resolve `actor_id` from the proposal's creator. **This needs a small additive port change first:**
   `ProposalRecordV1` (`application/ports/proposal.py:11-14`) currently exposes only `proposal:
   ProposalV1` and `version_ordinal: int` — `created_by_actor_id` lives in the `proposal` table
   (`schema.py:347`, NOT NULL) but is **not** on `ProposalV1` or `ProposalRecordV1` today (verified by
   grep: zero hits for `created_by_actor_id` under `application/contracts/proposal.py` or
   `application/ports/proposal.py`). Add `created_by_actor_id: UUID` to `ProposalRecordV1` and extend
   `PostgresProposalRepository.get_current`'s existing `SELECT` (`adapters/postgres/proposal.py:64+`)
   to include it — a same-row column addition, not a new query. There is no live HTTP actor context at
   this call boundary yet, since Story 3.6 owns the route, so the proposal's own creator is the only
   available actor identity.
2. Check `command_idempotency` via a `ScheduleRunRepository.get_idempotent_result` method that copies
   `adapters/postgres/proposal.py:98-203`'s pattern verbatim (same table, same conflict semantics) —
   operation `f"enqueue_compute:{proposal_id}"`, body hash over `{proposal_id,
   expected_proposal_resource_version}`. A stored hit replays the original `(schedule_run_id,
   job_id)` pair; a body-hash mismatch raises the same `IdempotencyKeyConflictError` shape
   `manage_proposal.py` raises.
3. On a fresh key: call `create_run_snapshot` unchanged, then insert one `workflow.job_queue` row
   (`schedule_run_id`, `actor_id`, `status='queued'`, `contract_version`, `fencing_epoch=0`,
   `attempt_id=None`) in the **same transaction**, then store the idempotent result.

**Why the caller must supply the idempotency key rather than this story deriving one from
`RunSnapshotV1.canonical_hash`:** the snapshot's `accepted_at` timestamp is part of the canonical
payload (AD-20), so two calls against the *same* unchanged proposal at different instants produce
*different* hashes — reusing the hash as the key would silently defeat AD-8's "a replay returns the
original result" guarantee the moment a caller retries a second later. `enqueue_compute` therefore
takes `idempotency_key: str` as an explicit parameter, seeded directly in this story's tests and
supplied from an HTTP header once Story 3.6 builds the route — the exact shape `revise_proposal`/
`reject_proposal` already establish (`manage_proposal.py:157-168, 243-252`).

### Decision 4 — Fencing is enforced by re-checking the job's *current* epoch inside the same compare-and-set that used to check only status

`ScheduleRunRepository.mark_running` and `.finalize_run` (`adapters/postgres/schedule_run.py:23-36,
125-140`) both gain a required `fencing_epoch: int` parameter. Their `UPDATE ... WHERE` clause adds
`AND EXISTS (SELECT 1 FROM workflow.job_queue WHERE schedule_run_id = schedule_run.id AND
fencing_epoch = :fencing_epoch)` alongside the existing status predicate. A worker that leased under
epoch 3 and is still trying to commit after a reaper (Task 8) re-leased the same job under epoch 4
fails this predicate — `rowcount != 1` — and its `ValueError` is treated as "stale lease, abandon," not
retried. **This is the literal mechanism behind AC3**: "fencing rejects the commit" is not a separate
check bolted on before the write, it is the same atomic `UPDATE` the status guard already used,
carrying one more `AND`.

`execute_schedule_run` (`application/use_cases/execute_schedule_run.py`) gains a `fencing_epoch: int`
parameter threaded straight through to both repository calls; the caller (the new worker driver, Task
7) supplies the epoch `lease_next_job` returned.

### Decision 5 — `attempt_id` is per-lease-acquisition, not per-job

AD-12: "idempotent replay returns that attempt, a deliberate retry gets a new ID." A job leased once,
lost to a crashed worker, and re-leased by a recovered worker is a **deliberate retry** of the
*attempt* even though it is the same job — so `lease_next_job` generates a fresh `attempt_id` on every
successful lease, not only on the first. The job's own identity (`id`) never changes; only its current
`attempt_id` does. This is what makes "the same run/evidence lineage is retained" (Story 3.11's future
AC) compatible with "every semantic effect occurs at most once": the job is one lineage, each lease is
a distinguishable attempt within it.

### Decision 6 — The `enqueue-compute` bundle's "event" clause stays `NOT COVERED`, same reasoning as Story 3.2 Decision 8, one level deeper

AC1 says the bundle is "schedule-run, job, initial persisted event, actor/site/attempt IDs...". The
`persisted_event` schema fence Story 3.2 found (`ck_persisted_event_stream_is_conversation`, NOT NULL
`conversation_id`/`agent_run_id`) is unchanged by this story — nothing here creates a conversation or
an agent run. Widening that table is Story 3.5's contract change, made against Story 3.5's own ACs,
not this one's. **The `job_queue` row's own committed existence is this story's answer to AD-6's
"committed before acknowledgement"** — durability does not require going through the SSE/timeline
mechanism; it requires the row to exist in the same transaction as everything else, which
`enqueue_compute` guarantees. Record `events:owned_by_story_3_5` in `SCOPE_CONTROLS` again, and do
**not** attempt to satisfy the literal word "event" by writing to `persisted_event` — it will fail on
the same CHECK Story 3.2 hit, for the same reason.

### Decision 7 — Cancellation and capability-version stay structurally present and semantically inert

`cancellation_requested` exists as a column and `lease_next_job`/`renew_job_lease` must **read** it
(Task 6) so a leased-but-cancelled job can be surfaced to the worker without inventing new plumbing
later — but **nothing in this story sets it to true**. That is Story 3.4's command. Mirrors Story 3.2
Task 9's `solver_cancelled` posture exactly: representable, tested only via a seeded row, `NOT
COVERED: cancellation:owned_by_story_3_4` (already present in Story 3.2's `SCOPE_CONTROLS`; this story
adds the job-side half of the same note).

`capability_version` is `NULL` on every job this story creates, because no `CapabilityManifestV1`
governs schedule-run compute yet — that arrives with Story 3.6's `scheduling_compute` capability
module. Record `contracts:capability_version_unpopulated_until_story_3_6` in `SCOPE_CONTROLS`. Do
**not** invent a placeholder capability name to fill the column; a fabricated version string would be
indistinguishable from a real one in an audit trail.

### Decision 8 — The worker driver is a plain synchronous polling loop, split across an application use case and a thin adapter

Structural Seed names `backend/worker/` as "job leasing and resumable execution **adapter**" —
AD-1 forbids business logic living in an adapter, so leasing/executing/finalizing one job is a new
`application/use_cases/lease_and_execute_schedule_run.py :: lease_and_execute_schedule_run(...) ->
LeaseOutcomeV1 | None`, framework-free and testable with plain fakes, exactly like
`execute_schedule_run` already is. `backend/worker/lease_worker.py` (the actual first file in the new
package) is a **thin** adapter: it resolves the two role-scoped connections (Task 7) and calls the use
case — no leasing, fencing, or finalization logic of its own. Together they are this story's second
new use case (the Scope Summary's "enqueue-compute, lease-and-execute").

The use case itself: leases at most one job, executes it, and returns — no `asyncio`, no thread
pool, no signal handling. AD-6 says "a separately runnable worker advances jobs through
compare-and-set transitions"; it does not mandate a specific process model, and Story 3.2's own
`execute_schedule_run` is already synchronous. A real long-running process (`while True:
lease_and_execute_schedule_run(); sleep(...)`) is a five-line wrapper the adapter can add later; this
story proves the leasing and fencing mechanism is correct in isolation, matching the "Accepted through
seeded... tests at the
API and worker boundary" acceptance language — "worker boundary" means the use case's own signature,
not a deployed daemon.

---

## Two honest gaps, raised rather than papered over

### Gap 1 — `deferred-work.md:189` expected this story to drain `AgentRun` rows stranded in `agent_running`; it does not, and should not through this mechanism

The Story 2.7-era ledger entry reads: *"Owner/revisit trigger: Story 3.3 (job leasing and fencing) —
whoever builds the lease must also drain runs stranded by this story's request path."* Verified against
AD-22's aggregate ownership table: `AgentRun` belongs to **Conversation**, not Workflow, and
`claim_queued_run` (`adapters/postgres/conversation.py:279-321`) claims it with a plain row lock —
there is no `job` row backing an agent turn today, and this story's `workflow.job_queue` is scoped to
`ScheduleRun` compute (`schedule_run_id` is a required, non-null column). Generalizing `job_queue` to
also lease agent turns would mean either widening it with a nullable, mutually-exclusive
`agent_run_id`/`schedule_run_id` pair (a payload-reference union AD-20's `JobLeaseV1` shape does not
describe) or building a second, parallel lease table — both are unasked-for scope expansions with no
AC in this story or `epics.md#Story-3.3` naming `AgentRun` at all.

**Required posture:** do not touch `claim_queued_run` or `conversation.py`. Update
`deferred-work.md:189` to record that Story 3.3 built lease/fencing infrastructure for `ScheduleRun`
compute jobs only, that `AgentRun` claiming remains a separate, unfenced mechanism, and re-point the
owner/revisit trigger to **the first story that needs `AgentRun` recovery specifically** (a candidate
future story, or a generalized "job" abstraction if one is ever justified by measured need — not
assumed here).

### Gap 2 — `schedule_run_id` uniqueness on `job_queue` assumes Story 3.2's 1:1 snapshot-to-run shape holds; it is not yet a database-enforced fact one level up

`create_run_snapshot` always mints a fresh `schedule_run_id` per call (`uuid4()`,
`create_run_snapshot.py:103`), so today exactly one `schedule_run` row exists per accepted call and the
`UniqueConstraint("schedule_run_id")` on `job_queue` (Decision 1) is trivially satisfiable. **This
story's idempotent replay (Decision 3) is what keeps it that way**: a repeated `enqueue_compute` call
with the same key returns the *original* `schedule_run_id` rather than minting a second one, so a
retried enqueue can never produce two `job_queue` rows racing for the same unique constraint. Record
this explicitly rather than let a reviewer wonder whether the unique constraint is redundant with
`schedule_run`'s own PK — it is not; it is the thing that would catch a Decision-3 regression that
skipped the idempotency check.

---

## Acceptance Criteria

Verbatim from `epics.md#Story-3.3`, each followed by what makes it demonstrably true here.

**AC1 — Given** an accepted immutable run snapshot
**When** compute is enqueued
**Then** schedule-run, job, initial persisted event, actor/site/attempt IDs, contract/capability
versions, idempotency key, and payload reference commit in one enqueue-compute bundle
**And** acknowledgement occurs only after commit using PostgreSQL leasing rather than a broker or
workflow engine. (FR12, AR6, AR18, AR22)

> Demonstrated by: `enqueue_compute` (Decision 3) commits `run_snapshot` + `schedule_run` + one
> `job_queue` row + one `command_idempotency` row in a single transaction; a test asserts all four
> rows exist after commit and none exist after a forced rollback. The "event" clause is `NOT COVERED`
> per Decision 6, cited in the same test's docstring so a reviewer does not need to rediscover the
> reasoning. Replaying the same `(actor, site, operation, idempotency_key, body_hash)` returns the
> original `(schedule_run_id, job_id)` pair and inserts no second row; a conflicting body hash raises
> `IdempotencyKeyConflictError`.

**AC2 — Given** one or more queued jobs
**When** the worker leases the next authorized job
**Then** the owner-held `workflow.lease_next_job` function uses `FOR UPDATE SKIP LOCKED` and returns
job/site/actor context with lease owner, expiry, heartbeat, and monotonically increasing fencing epoch
**And** the runtime lease role cannot directly query tenant/control tables. (AR23)

> Demonstrated by: a live-PostgreSQL test that queues N jobs, leases concurrently from two sessions,
> and asserts no job is leased twice and every job is eventually leased (`SKIP LOCKED` proof); a
> second test asserts `fencing_epoch` strictly increases across repeated leases of the same
> re-expired job; a **negative** test connects `AS shiftmind_lease` and asserts `SELECT * FROM
> workflow.job_queue` raises `InsufficientPrivilege`, proving "cannot directly query tenant/control
> tables" is enforced by grants, not by convention.

**AC3 — Given** a worker loses or exceeds its lease
**When** a stale worker attempts checkpoint or effect commit
**Then** fencing rejects the commit while a recovered worker may safely recompute under a newer epoch
**And** stable job/effect uniqueness prevents duplicate terminal evidence or candidate creation.
(FR16, NFR6)

> Demonstrated by: Decision 4's epoch-checked `mark_running`/`finalize_run` — a test leases a job
> (epoch 1), forces a second lease of the same expired lease (epoch 2), then attempts
> `finalize_run(..., fencing_epoch=1)` and asserts it raises without writing a `schedule_version` row;
> a second test then finalizes under epoch 2 and asserts exactly one `schedule_version`/
> `schedule_assignment` set exists — proving the stale attempt did not also leave partial evidence
> behind it. `uq_schedule_version_run` (Story 3.2) is the database-level backstop against a double
> candidate even if the epoch check were bypassed.

---

## Tasks / Subtasks

**Retro action A2 is in force.** Every new guard must be **observed failing** with its structural
assertion removed, recorded in the Dev Agent Record.

### Phase A — the job contract, the `workflow` schema, and the enqueue bundle

#### Task 1 — `JobLeaseV1` contract (AC: 1)

- [ ] New `application/contracts/job_lease.py`: `JobLeaseV1` with every AD-20-required field
      (Decision 1's column list). Closed `Literal` for `job_type` and `status`. A `__post_init__`
      guard mirroring `RunSnapshotV1`'s (Story 3.2 Task 1) requiring `job_id`, `site_id`, `job_type`,
      `schedule_run_id`, `actor_id`, `contract_version` — the fields that must exist before any lease,
      leaving lease/attempt/heartbeat fields nullable until `lease_next_job` populates them.

#### Task 2 — Migration: `workflow` schema, `job_queue` table, `shiftmind_lease` role (AC: 1, 2)

- [ ] Create schema `workflow`. Create `workflow.job_queue` per Decision 1's column list, with
      `UniqueConstraint("schedule_run_id")`, `UniqueConstraint("id", "site_id")`, status/job_type
      CHECKs, and an index supporting `lease_next_job`'s query (`status`, `lease_expires_at`).
      Copy the RLS/FORCE RLS/policy shape from `migrations/versions/a4f92d7c8e31_...py:94-99`.
- [ ] `GRANT SELECT, INSERT ON workflow.job_queue TO shiftmind_runtime` (the enqueue path);
      `REVOKE UPDATE, DELETE`; a later narrow `GRANT UPDATE (status, heartbeat_at) ON
      workflow.job_queue TO shiftmind_runtime` for completion/heartbeat bookkeeping the domain
      transaction itself performs (not lease/fencing fields — those are owner-function-only, Decision
      2).
- [ ] Create role `shiftmind_lease` (`NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOBYPASSRLS`), copying `d128d081ab48`'s `DO $$ ... IF NOT EXISTS` idempotent-create shape. Grant
      it **no** table privileges at all — verify with `information_schema.role_table_grants` in Task
      8's checkpoint.
- [ ] `alembic check` must report zero operations, run from the repository root.

#### Task 3 — `lease_next_job` and `renew_job_lease` (AC: 2, 3)

- [ ] `CREATE FUNCTION workflow.lease_next_job(p_lease_owner text, p_lease_seconds int) RETURNS
      workflow.job_queue` (or a narrower composite) — `SECURITY DEFINER`, fixed `search_path`, no
      dynamic SQL. Body: `SELECT ... FROM workflow.job_queue WHERE (status = 'queued') OR (status =
      'leased' AND lease_expires_at < now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`, then
      `UPDATE ... SET status='leased', lease_owner=p_lease_owner, lease_expires_at=now() +
      p_lease_seconds * interval '1 second', heartbeat_at=now(), fencing_epoch=fencing_epoch+1,
      attempt_id=gen_random_uuid() WHERE id = <selected> RETURNING *`.
- [ ] `CREATE FUNCTION workflow.renew_job_lease(p_job_id uuid, p_fencing_epoch bigint,
      p_extension_seconds int) RETURNS boolean` — `SECURITY DEFINER`; `UPDATE ... SET
      lease_expires_at = now() + ..., heartbeat_at = now() WHERE id = p_job_id AND fencing_epoch =
      p_fencing_epoch`; returns whether a row was updated (i.e., the caller still holds the current
      epoch).
- [ ] `REVOKE EXECUTE ... FROM PUBLIC` on both; `GRANT EXECUTE ON FUNCTION
      workflow.lease_next_job TO shiftmind_lease`; `GRANT EXECUTE ON FUNCTION
      workflow.renew_job_lease TO shiftmind_runtime`.

#### Task 4 — `ScheduleRunRepository` gains job/idempotency methods; `enqueue_compute` use case (AC: 1)

- [ ] `application/ports/proposal.py`: add `created_by_actor_id: UUID` to `ProposalRecordV1`.
      `adapters/postgres/proposal.py`: extend `get_current`'s `SELECT` to include
      `proposal.c.created_by_actor_id`. Update any test that constructs `ProposalRecordV1`
      positionally.
- [ ] `application/ports/schedule_run.py`: extend `ScheduleRunRepository` with
      `enqueue_job(connection, *, job: JobLeaseV1, site_id) -> None`,
      `get_idempotent_result(...)`/`_store_idempotent_result(...)` matching
      `adapters/postgres/proposal.py:98-203`'s signature and semantics against the **same**
      `command_idempotency` table.
- [ ] `adapters/postgres/schedule_run.py`: implement both against `workflow.job_queue` /
      `command_idempotency`.
- [ ] New `application/use_cases/enqueue_compute.py :: enqueue_compute` per Decision 3: resolve actor
      from the proposal, check idempotency, call `create_run_snapshot` unchanged, insert the job row,
      store the idempotent result — all inside the caller-owned transaction.
- [ ] Define a local `EnqueueComputeError(ValueError)` and `IdempotencyKeyConflictError
      (EnqueueComputeError)` in `enqueue_compute.py`, matching `manage_proposal.py`'s **shape**
      (conflict detected via `stored.body_hash != body_hash`) but **not** importing
      `manage_proposal.ProposalCommandError` — that base class names the proposal aggregate
      specifically, and a schedule-run/job command failing under a `ProposalCommandError` would
      misattribute which aggregate owns the failure.

### ⛳ Checkpoint — commit Phase A and report five numbers

1. backend collected / passed / skipped, and `-m postgres` collected / passed;
2. `alembic check` output;
3. `workflow.job_queue`'s grants, dumped live — proving `shiftmind_lease` has zero table grants and
   `shiftmind_runtime` has no UPDATE beyond `(status, heartbeat_at)`;
4. `EXECUTE` privileges on both new functions, dumped from `information_schema.role_routine_grants`;
5. an idempotent-replay test observed passing, and observed **failing** with the idempotency check
   temporarily removed (A2).

### Phase B — leasing, fencing, and the worker driver

#### Task 5 — Thread `fencing_epoch` through `mark_running`/`finalize_run` (AC: 3)

- [ ] `ScheduleRunRepository.mark_running` and `.finalize_run`: add required `fencing_epoch: int`;
      extend the `UPDATE ... WHERE` predicate per Decision 4. Raise a distinct
      `StaleLeaseError` (not the existing generic `ValueError`) when the epoch predicate is what
      failed versus when the status predicate was what failed — a caller needs to tell "someone else
      already finished this run" apart from "my lease was revoked," and today's bare `ValueError`
      cannot.
- [ ] `execute_schedule_run`: add `fencing_epoch: int`, pass through to both calls.

#### Task 6 — `lease_and_execute_schedule_run` use case, and the thin worker adapter (AC: 2, 3)

- [ ] New `application/use_cases/lease_and_execute_schedule_run.py :: lease_and_execute_schedule_run`
      (Decision 8): takes the lease-role connection, the runtime-role connection factory, the
      `ScheduleRunRepository`, and the `SchedulerPort` as parameters (framework-free, testable with
      fakes exactly like `execute_schedule_run`). Calls `lease_next_job` (via a repository/port method
      wrapping the `SECURITY DEFINER` function call); if a job was returned, loads the
      `RunSnapshotV1` payload and calls `execute_schedule_run` with the leased `fencing_epoch`.
- [ ] Read `cancellation_requested` before executing; if true, finalize immediately as
      `solver_cancelled` without calling the solver (Decision 7 — representable, not yet
      reachable in tests beyond a seeded row, since nothing sets the flag until Story 3.4).
- [ ] No job found: return `None` without opening a domain transaction or touching `shiftmind_runtime`
      at all.
- [ ] New `backend/worker/lease_worker.py` (first file in this package): a thin adapter —
      opens the `shiftmind_lease` connection and a `shiftmind_runtime` connection factory (Task 7),
      calls `lease_and_execute_schedule_run`, commits. No leasing, fencing, or finalization logic of
      its own lives here.

#### Task 7 — Two-role connection handling (AC: 2)

- [ ] Wherever the current codebase establishes a trusted-role connection for `shiftmind_runtime`
      (`api/deps.py` or equivalent — read it before adding a sibling, do not duplicate the pattern
      blind), add the equivalent for `shiftmind_lease`, scoped to the worker process only. Do **not**
      let `shiftmind_lease` ever open an RLS-scoped domain transaction — it has no table grants to do
      anything with one.

### ⛳ Checkpoint — commit Phase B and report four numbers

1. full regression pass/skip/deselect counts;
2. a fencing-rejection test observed passing, and observed **failing** with the epoch predicate
   removed (A2);
3. `lease_next_job` concurrency test result (N jobs, two leasing sessions, zero double-leases);
4. `shiftmind_lease` negative-privilege test result (direct table query denied).

### Phase C — recovery proof and ledger reconciliation

#### Task 8 — Recovery and idempotency test suite (AC: 1, 2, 3)

- [ ] Worker-kill simulation: lease a job, do not finalize, let the lease expire, lease again from a
      second simulated worker, finalize under the new epoch, assert exactly one terminal outcome and
      the stale attempt's late finalize call is rejected.
- [ ] Idempotent `enqueue_compute` replay (same key, same body) returns the identical
      `(schedule_run_id, job_id)` pair with no new rows; conflicting body hash raises.
- [ ] `SCOPE_CONTROLS` for the new modules: `roles:worker_reuses_shiftmind_runtime` (Decision 2),
      `events:owned_by_story_3_5` (Decision 6), `cancellation:owned_by_story_3_4` (Decision 7),
      `contracts:capability_version_unpopulated_until_story_3_6` (Decision 7).
- [ ] `deferred-work.md`: re-point `:189`'s owner per Gap 1 — do not close it, redirect it. Add any
      new items this story's own review surfaces once implementation is real (do not pre-write
      findings that have not happened yet).
- [ ] Gate A re-run: `gate_a_passed: true`, `blocking: []`.
- [ ] Verify the mandated zero-line diffs with `git diff --stat` (Project Structure Notes).

---

## Dev Notes

### What this story is, and what it is not

**It is:** the durable job/lease/fencing boundary between an accepted `RunSnapshotV1` and its
eventual solve — PostgreSQL leasing with `SKIP LOCKED`, a monotonic fencing epoch, and a worker driver
proven to recover correctly from a lost lease.

**It is not:**

| Not this | Owner |
|---|---|
| The `Run optimization` control, the compute capability, the HTTP command, real HTTP idempotency keys | Story 3.6 |
| The cancellation command itself — this story only reads the flag it defines | Story 3.4 |
| Persisted run events, SSE replay, reconnect, the NFR35 5-second measurement | Story 3.5 |
| `AgentRun` recovery / stranded-turn draining | nobody yet — see Gap 1; explicitly **not** retrofitted onto `job_queue` |
| Any solver, metrics, or hard-constraint logic — those are Story 3.2's, untouched here except for the two repository methods Decision 4 extends | Story 3.2 |
| A long-running worker daemon / process supervisor | later ops work; this story ships `run_once`, not a `while True` loop |
| A second `shiftmind_worker` role distinct from `shiftmind_runtime` | deliberately not built — Decision 2 |

### The traps, ranked by how quietly they fail

1. **Deriving the idempotency key from `RunSnapshotV1.canonical_hash`.** It changes on every call
   because `accepted_at` is inside the hashed payload — Decision 3 explains why this defeats AD-8 the
   moment a caller retries.
2. **Granting `shiftmind_runtime` UPDATE on `lease_owner`/`lease_expires_at`/`fencing_epoch`
   directly.** It looks convenient for heartbeat renewal and quietly deletes the whole point of
   fencing — any holder of the runtime role could then renew or fabricate a lease it does not own.
   Decision 2's `renew_job_lease` function exists specifically to keep that mutation
   epoch-checked and owner-held.
3. **A bare `ValueError` on both the status guard and the new fencing guard.** A caller cannot tell
   "the run already finished" from "my lease was revoked" without a distinct exception (Task 5).
4. **Reusing `ScheduleRunStatusV1` for the job's own `status` column.** AD-7 forbids merging stored
   status types across separately owned graphs; `job_queue.status` is a new, smaller, Workflow-owned
   vocabulary.
5. **Trying to close `deferred-work.md:189` outright.** It named this story as owner for a mechanism
   (`AgentRun` draining) that this story's own AC never asks for and that does not fit
   `job_queue`'s shape — closing it would misrepresent scope. Re-point it (Gap 1); do not close it.
6. **Trying to emit a `persisted_event` for the enqueue.** Same schema fence Story 3.2 hit
   (`ck_persisted_event_stream_is_conversation`); Decision 6 is the second time this has to be
   deferred, for the identical structural reason — do not attempt a workaround inside this story.
7. **Skipping the negative-privilege test for `shiftmind_lease`.** AD-23's "cannot directly query
   tenant/control tables" is a grant fact, not a code-review fact — it is only proven by actually
   connecting as that role and observing the denial.

### Existing conventions to match, not reinvent

| Need | Copy from |
|---|---|
| Idempotent command replay against `command_idempotency` | `adapters/postgres/proposal.py:98-203`; `application/use_cases/manage_proposal.py:89-138` |
| Idempotent-create role via `DO $$ ... IF NOT EXISTS` | `migrations/versions/d128d081ab48_...py:226-239` |
| RLS/FORCE RLS/policy shape for a new table | `migrations/versions/a4f92d7c8e31_...py:94-99` |
| A narrow column-scoped `GRANT UPDATE` | `migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py` |
| Port with `connection: Any` (never the vendor type) | `application/ports/scenario_projection.py:104`; `application/ports/schedule_run.py` |
| Repository + use-case split, one transaction owned by the use case | `application/use_cases/create_run_snapshot.py` + `adapters/postgres/schedule_run.py` |
| Frozen contract with a required-field `__post_init__` guard | `application/contracts/run_snapshot.py` (Story 3.2 Task 1) |
| `SCOPE_CONTROLS` in `COVERS`/`NOT COVERED` form | `application/scheduling/candidate_metrics.py` and Story 3.2's own `SCOPE_CONTROLS` entries |
| Architecture fence by AST/negative-privilege proof | `tests/architecture/test_solver_boundaries.py` (Story 3.2) |
| Compare-and-set repository method that raises a distinct exception on guard failure | `adapters/postgres/schedule_run.py:23-36` (extend, do not replace, its shape) |

### Latest technical information (verified against the repo at `2d41ee8`)

- **No new dependency.** `FOR UPDATE SKIP LOCKED` and `SECURITY DEFINER` functions are native
  PostgreSQL (18.4 per the Stack table); nothing in `backend/pyproject.toml` needs to change.
- **CI enforces counts.** `.github/scripts/assert_counts.py` enforces pass-count floors and skip-count
  ceilings; backend skip ceiling is `--max-skipped 1` (`ci.yml:179`). Re-verify current numbers before
  attributing a red CI to this story — Story 2.7 and 3.1 both found their inherited baseline stale.
- **`alembic check` must run from the repository root** (`deferred-work.md:138-147`).
- **Golden dataset:** unchanged at 21 cases — this story ships no capability and no model-facing
  surface, matching Story 3.2's precedent of contributing zero. Record the zero contribution; do not
  pad to look complete.
- **`-m postgres` requires the local PostgreSQL service.** Establish real pass numbers before
  attributing any failure to this story's changes — it was collected-not-executed at Story 3.2's own
  creation baseline.

### Baselines at creation — re-derive them, do not trust them

| Suite | Reported at Story 3.2 completion (`2026-08-19`) |
|---|---|
| backend default | 997 passed, 1 expected skip, 7 live-provider deselected |
| backend `-m postgres` | 57 passed |
| evidence convention | 49 passed |
| golden cases | 21 files |
| frontend / Vitest / Playwright | 410 / 48 passed — this story mandates a zero-line `frontend/**` diff, so re-verify only that these counts have not silently moved for unrelated reasons |

### Project Structure Notes

**New files** (AR26's structural seed; first use of `backend/worker/`):

```
backend/application/contracts/job_lease.py
backend/application/use_cases/enqueue_compute.py
backend/application/use_cases/lease_and_execute_schedule_run.py
backend/worker/__init__.py
backend/worker/lease_worker.py
backend/migrations/versions/<rev>_add_job_queue_and_lease_functions.py
backend/tests/test_job_lease_contracts.py
backend/tests/test_enqueue_compute.py
backend/tests/test_lease_next_job.py
backend/tests/test_fencing_recovery.py
backend/tests/architecture/test_lease_role_boundaries.py
```

**Modified (UPDATE, not NEW) — read each completely before editing:**

`application/ports/schedule_run.py` (new methods) · `adapters/postgres/schedule_run.py`
(`mark_running`/`finalize_run` fencing param, new job/idempotency methods) ·
`adapters/postgres/schema.py` (`workflow` schema, `job_queue` table) ·
`application/use_cases/execute_schedule_run.py` (`fencing_epoch` param) ·
`application/ports/proposal.py` (`ProposalRecordV1.created_by_actor_id`) ·
`adapters/postgres/proposal.py` (`get_current`'s `SELECT` gains one column) ·
`_bmad-output/implementation-artifacts/deferred-work.md` (`:189` re-pointed, Gap 1)

**Mandated zero-line diffs** — verify with `git diff --stat`:

```
frontend/**                                backend/domain/**
backend/engine/**                          backend/ingest/**
backend/llm/**                             backend/store/**
backend/run.py                             backend/api/**
backend/agent/**                           backend/application/capabilities/**
backend/application/grounding/**           backend/application/clarification/**
backend/application/scheduling/**          backend/application/use_cases/create_run_snapshot.py
backend/application/use_cases/finalize_schedule_run.py
backend/application/use_cases/execute_turn.py
backend/application/use_cases/finalize_agent_run.py
backend/application/use_cases/manage_proposal.py
backend/adapters/postgres/scenario_projection.py
backend/adapters/postgres/scenario_catalogue.py
backend/adapters/postgres/conversation.py
backend/adapters/postgres/solver_input.py  backend/evals/**
backend/engine/governed_adapter.py         data/**
evidence/**                                docs/DOMAIN-MODEL.md
```

`backend/api/**` is fenced deliberately: this story mounts no route (Decision 8's "worker boundary"
is the `run_once` port, not HTTP). `backend/application/scheduling/**` and
`backend/application/use_cases/create_run_snapshot.py`/`finalize_schedule_run.py` are fenced because
Decision 3 wraps, not edits, Story 3.2's use cases. `backend/adapters/postgres/proposal.py` and
`backend/application/ports/proposal.py` are **not** fenced this time — Task 4's additive
`created_by_actor_id` field is a real, necessary dependency (see Decision 3), unlike Story 3.2, which
had no such need. If a task appears to need anything else in this list, it belongs to a later story.

### References

- `_bmad-output/planning-artifacts/epics.md#Story-3.3` (ACs, verbatim), `#Epic-3` sequencing note,
  FR12, FR16, AR6, AR18, AR22, AR23
- `.../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-6, AD-7, AD-8,
  AD-12, AD-18, AD-20 (`JobLeaseV1`), AD-22 (aggregate ownership, `enqueue-compute`), AD-23; Structural
  Seed (`backend/worker/`); Deferred table ("Multiple roles and separation of duties")
- `_bmad-output/implementation-artifacts/3-2-produce-a-deterministic-candidate-from-an-immutable-snapshot.md`
  — `RunSnapshotV1`, `ScheduleRunRepository`, Decision 8 (persisted-event fence), the terminal-status
  mapping table this story's fencing guard sits in front of
- `_bmad-output/implementation-artifacts/3-1-create-and-revise-a-reversible-repair-draft.md` — the
  `command_idempotency` table and its `revise_proposal`/`reject_proposal` idempotency pattern
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`
- `_bmad-output/implementation-artifacts/deferred-work.md:189` (the `AgentRun`-draining note this
  story re-points, Gap 1)
- `_bmad-output/implementation-artifacts/epic-1-2-retro-2026-08-16.md` — §3.2, §6.1 (A2, A3)
- PostgreSQL: `FOR UPDATE SKIP LOCKED` (row locking docs), `SECURITY DEFINER` function docs (fixed
  `search_path` requirement)

## Dev Agent Record

### Agent Model Used

_To be filled by the dev agent._

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-08-20: Story drafted via `/bmad-create-story 3.3` from `epics.md#Story-3.3`, Story 3.2's
  as-built state at commit `2d41ee8`, and `ARCHITECTURE-SPINE.md` AD-6/7/8/12/18/20/22/23.
