---
baseline_commit: 8623affe118a2312fc0bc6839ad5a75c64aa4f72
---

# Story 3.4: Provide the Safe Cancellation Command [Technical Enabler]

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the scheduling platform,
we want a versioned idempotent cancellation command for queued or running work,
so that when Story 3.7 exposes a reachable Cancel control, stopping work can never corrupt state or
duplicate effects.

**Planner-visible outcome: none.** This story delivers the command contract only — one HTTP route, no
UI. The Cancel control and the Runs workspace that reaches it are Story 3.7's. `frontend/src/**` is a
zero-line diff **except** the two generated artefacts (`frontend/openapi.json`,
`frontend/src/api/schema.d.ts`), which must be regenerated, never hand-edited.

**Depends on, and consumes:** Story 3.3's `workflow.job_queue`, its `cancellation_requested` flag,
`lease_next_job`/`renew_job_lease`, the fencing epoch, `lease_and_execute_schedule_run`, and
`PostgresScheduleRunRepository`; Story 3.2's `schedule_run`, `execute_schedule_run`,
`finalize_schedule_run`, `ScheduleRunStatusV1`; Story 3.1's `command_idempotency` table and the
`revise_proposal`/`reject_proposal` HTTP command shape (`api/routers/proposals.py`,
`application/use_cases/manage_proposal.py`); AD-6, AD-7, AD-8, AD-13, AD-20, AD-22, AD-23.

**Unblocks:** Story 3.5 (this story commits `solver_running` so a persisted event can observe it, and
narrows what the heartbeat still owes), Story 3.6 (the run-start command reuses this command's version
and idempotency shape), Story 3.7 (the Cancel control calls this route and renders
`cancellation_requested` as a distinct literal state).

**Scope summary:** One migration (one additive column, two narrow column grants). One new use case
(`cancel_schedule_run`). One new router (`schedule_runs.py`) and its two schemas. Port and adapter gain
three methods, two version bumps, and one widened predicate. `lease_and_execute_schedule_run` splits its
single long domain transaction into two committed ones and observes cancellation at two checkpoints.
**No new dependency.** No capability module. No evidence file of its own. No frontend source change.

**This story is the first in the repository to:**

1. give `schedule_run` a `resource_version`. Verified by grep against `adapters/postgres/schema.py` at
   `8623aff`: `resource_version` exists on `conversation`, `agent_run`, and `proposal` only
   (`schema.py:280, 316, 351`); `schedule_run` (`schema.py:431-443`) has none, so AD-20's "mutable
   aggregates carry `resource_version`" is currently unmet for this aggregate;
2. write `workflow.job_queue.cancellation_requested`. The column has existed since Story 3.3 and both
   lease functions read it, but `GRANT UPDATE (status, heartbeat_at)`
   (`migrations/versions/a2b3c4d5e6f7_...py:126`) is the only UPDATE the runtime role holds, so a write
   to it fails today with `InsufficientPrivilege`;
3. mount a `/api/v1` write route that is neither a proposal nor a conversation route. The versioned
   write surface is exactly six paths, asserted as a literal in
   `tests/test_gate_a_mutation_audit.py:260-271`;
4. commit `solver_running` where another session can read it. Today `mark_running` → solve →
   `finalize_run` → `complete_job` all sit inside one `engine.begin()`
   (`worker/lease_worker.py:runtime_context`), so `solver_running` is written but never observable —
   recorded at `deferred-work.md:287`;
5. exercise AD-7's `cancellation_requested` node. `ScheduleRunStatusV1` lists it
   (`application/contracts/schedule_version.py:23`) and the CHECK constraint permits it
   (`schema.py:441`), but grep confirms no code path writes or reads it.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. None of it may be re-derived from adapter code
(retro §3.2 — the single most expensive pattern of Epics 1–2).

| Fact | Where it is written |
|---|---|
| The `ScheduleRun` closed graph has **no `solver_running → solver_cancelled` edge**. Cancelling running work goes `solver_running → cancellation_requested`, and only `cancellation_requested` reaches `solver_cancelled`. Cancelling queued work goes `solver_queued → solver_cancelled` directly. `cancellation_requested` also has edges to `solver_completed`, `solver_infeasible`, `solver_timed_out`, and `solver_failed` | AD-7 state diagram (`ARCHITECTURE-SPINE.md:84-131`, `ScheduleRun` block at `:106-122`) |
| Adapters may project a combined timeline but **never merge stored status types** across `AgentRun`, `ScheduleRun`, `ApprovalRequest`; only a feasible `ScheduleRun.completed` may reference a candidate | AD-7 (`ARCHITECTURE-SPINE.md:87-88`) |
| Cancellation is **persisted and cooperative** — the worker observes it; nothing pre-empts it | AD-6 (`ARCHITECTURE-SPINE.md:82`) |
| Each mutating **HTTP** command requires an idempotency key scoped to actor, site, operation, and canonical body hash **plus expected resource version**; a replay returns the original semantic result, a conflicting body fails | AD-8 (`ARCHITECTURE-SPINE.md:136`) |
| Every contract carries `schema_version`; site-owned resources carry `site_id`; **mutable aggregates carry `resource_version`** | AD-20 *Normative contract minimums*, preamble (`ARCHITECTURE-SPINE.md:314`) |
| `JobLeaseV1` must carry a **cancellation flag** | AD-20 minimums table (`ARCHITECTURE-SPINE.md:328`) |
| FastAPI publishes versioned REST/JSON commands; application errors map to RFC 7807 problem details with **stable code, correlation ID, resource ID, and current version when relevant**; business commands remain durable without SSE | AD-13 (`ARCHITECTURE-SPINE.md:166`) |
| Workflow owns `job`/`persisted_event`; Scheduling owns proposals/runs/schedule versions; **only an application orchestrator crosses owners**. The fixed atomic bundles are accept-turn, enqueue-compute, complete-compute, request-approval, promote-baseline — **cancellation is not one of them**, so no bundle is being widened | AD-22 (`ARCHITECTURE-SPINE.md:220`) |
| `workflow.job_queue` grants runtime roles narrow, column-scoped UPDATE only; owner-held `SECURITY DEFINER` functions exist for lease/fencing fields, must fix `search_path`, and carry no dynamic SQL | AD-23 (`ARCHITECTURE-SPINE.md:226`); Story 3.3 Decision 2 |
| FR16: accept **cooperative cancellation for queued or running work**, and make command replay, retry, and worker lease recovery return the same semantic effect without duplicate work or promotion | `epics.md` FR16 |
| AR8: mutating HTTP idempotency keys scoped to actor/site/operation/body-hash **plus expected resource version**; stable job effect keys and database uniqueness for replay safety | `epics.md` AR8 |
| The idempotent-replay pattern is established twice and must be copied, not reinvented: `get_idempotent_result`/`_store_idempotent_result` against the shared `command_idempotency` table keyed `(site_id, actor_id, operation, idempotency_key)` with `body_hash` conflict detection | `adapters/postgres/proposal.py:98-203`; `application/use_cases/manage_proposal.py:89-138`; `application/use_cases/enqueue_compute.py:80-136` |
| The expected version is part of the command's **identity**, not merely a concurrency guard — replaying one key against a different expected version must conflict, not replay | `manage_proposal.py:_body_hash` docstring (resolved at review 2026-08-18) |
| The operation string is what the command *does*, never who asked for it — folding the key into `operation` makes the uniqueness constraint unable to fire | `manage_proposal.py:_operation` docstring |
| `command_idempotency.idempotency_key` is `String(40)`; the HTTP header is bounded to the same width | `schema.py:390`; `api/routers/proposals.py:IdempotencyKey` |
| The single long domain transaction is why the heartbeat is inert **and** why `solver_running` is unobservable; owner is Story 3.5 | `deferred-work.md:287` (Minh, 2026-08-20, D1 option c) |
| `job_queue` has **no terminal-failure status** — a job failing between lease and completion is re-leased forever; owner is Story 3.5 | `deferred-work.md` (3.3 review defer); `application/contracts/job_lease.py:JobStatusV1` |
| `AgentRun` cancellation is **explicitly not this story's** — Story 3.4 is a `ScheduleRun` enabler and does not cancel agent turns | `deferred-work.md:223` |
| Every new versioned write route must be added to the write-surface literal **and** recorded in `docs/GATE-A-RUNBOOK.md`; two separate tests enforce the two halves | `tests/test_gate_a_mutation_audit.py:243-271` and `:507+` |
| `docs/API.md` documents the **legacy pre-Gate-A SQLite API only** — zero occurrences of `/api/v1`. The versioned surface is documented by OpenAPI and the Gate A runbook | `docs/API.md` (verified by grep: 0 matches) |
| No hand-typed evidence file; commit code → measure → generate → commit evidence separately | `docs/EVIDENCE-CONVENTION.md` |
| Manual assistive-technology verification is out of scope; automated coverage is the recorded bar | `.../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`, Accessibility Floor |
| Every new guard must be **observed failing** with its structural assertion removed | retro §6.1 action A2 |

`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments. **This story touches no metric,
no demand row, and no assignment** — it writes a run status, a resource version, and a boolean flag. It
is cited for completeness and is deliberately not re-derived.

---

## Nine decisions were made at story creation — do not re-litigate them

### Decision 1 — `schedule_run` gains `resource_version`, and it is the race arbiter

AD-8 requires an **expected resource version** on every mutating HTTP command, and AD-20's preamble
requires every mutable aggregate to carry one. `schedule_run` is a mutable aggregate with no such
column, so the word "versioned" in this story's own AC has nothing to bind to today.

Add `resource_version BIGINT NOT NULL DEFAULT 1` to `schedule_run`, and **bump it in every UPDATE that
changes the row** — `mark_running`, `finalize_run`, and both new cancellation transitions. A bump
applied on only some transitions is worse than no column: a client's expected version would then match a
row that had already moved.

This column also resolves the AC's race with no extra machinery:

* worker finalized first → `resource_version` moved → the cancel command's guard fails →
  `409 stale_resource_version`;
* cancel landed first → the worker's `finalize_run` finds `cancellation_requested` and lands on a
  terminal AD-7 permits from that node.

**Do not** invent an `expected_status` parameter instead. AD-8 names the version, the proposal command
already uses one, and Story 3.5's `PersistedEventV1` requires a `resource_version` per AD-21 — it would
have to exist there anyway, and adding it twice under two names is the failure mode.

### Decision 2 — The cancellation flag is written by a narrow column GRANT, never a new `SECURITY DEFINER` function

`GRANT UPDATE (cancellation_requested) ON workflow.job_queue TO shiftmind_runtime`, copying the shape of
`migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py` exactly.

AD-23's reason for owner-held functions is that **lease and fencing fields** must not be writable by a
runtime-role holder. `cancellation_requested` is not one of them: a holder who sets it can only *stop*
work, never steal, extend, or fabricate a lease. A `SECURITY DEFINER` alternative would be strictly
worse here — the owner carries `BYPASSRLS`, so the function would need its own site predicate, which is
precisely the defect Story 3.3's review found in `renew_job_lease`. A plain column UPDATE is covered by
RLS with no extra code.

`resource_version` likewise needs adding to `schedule_run`'s existing column grant
(`f1a2b3c4d5e6_...py:124`, currently `status, reason, candidate_schedule_version_id, finished_at`).

### Decision 3 — One HTTP POST route, no GET, no list

`POST /api/v1/schedule-runs/{run_id}/cancellation`, mirroring `POST /api/v1/proposals/{id}/rejection`
(a noun-terminal command, not a verb). Body `{"expected_resource_version": int}`; `Idempotency-Key`
header, `min_length=1, max_length=40`, identical to `api/routers/proposals.py:IdempotencyKey`.

The router module **must** be named `schedule_runs.py`. `api/routers/runs.py` already exists and is the
legacy pre-Gate-A SQLite router mounted **without** the `/api/v1` prefix (`api/main.py:262`); reusing
that name or that router is the single most likely wrong turn in this story.

**No `GET` route.** The epic's own sequencing note says Story 3.7 "introduces the Runs workspace that
makes the Story 3.4 cancellation command reachable" — the read surface that supplies
`expected_resource_version` to a client is 3.7's. Tests read state through the repository and the
database, which is what "Accepted through API-level cancellation, race, and idempotency tests" asks for.

### Decision 4 — The command writes both aggregates in one transaction; the run's status is the only authority

One transaction commits the `schedule_run` status edge, `job_queue.cancellation_requested = true`, and
the `command_idempotency` row. Nothing is acknowledged before that commit (AD-6).

The job flag is written because AD-20 requires `JobLeaseV1` to carry it and because Story 3.5's
heartbeat will read it through `renew_job_lease`. But **every worker decision reads
`schedule_run.status`, never the flag.** Two sources of truth that can disagree is exactly the state
corruption this story exists to prevent; the flag is a carrier, the status is the authority.

A run created directly by `create_run_snapshot` has no `job_queue` row (Story 3.2's tests do this). The
flag UPDATE then matches zero rows. **That is not an error** — cancel the run and continue.

### Decision 5 — The cancellation edges are exactly AD-7's, and Story 3.3's illegal edge is removed

| Current status | Command writes | Reason string |
|---|---|---|
| `solver_queued` | → `solver_cancelled` (terminal, sets `finished_at`) | `cancelled` |
| `solver_running` | → `cancellation_requested` (**not** terminal, `finished_at` stays NULL) | `cancellation_requested` |
| `cancellation_requested` | no write; return current state, 200 | — |
| any terminal | no write; `409 run_not_cancellable` | — |

`lease_and_execute_schedule_run.py:80-96` currently does `mark_running` then
`finalize_run(status="solver_cancelled")` for a cancelled job — a `solver_running → solver_cancelled`
transition that **does not exist in AD-7's graph**. Delete that branch and replace it with Decision 7's
checkpoints. Its reason string `cancellation_requested_before_execution` is replaced by the stable
`cancelled`, which is the string `finalize_schedule_run._terminal` already produces for
`outcome.reason == "cancelled"` (`finalize_schedule_run.py:31`) — one vocabulary, so Story 3.7 renders
one label.

`finalize_run`'s compare-and-set predicate widens from `status == "solver_running"` to
`status IN ("solver_running", "cancellation_requested")`. That is the whole mechanism behind "a race
with completion resolves through the closed state machine": a worker already solving when the
cancellation landed finishes and lands on `solver_completed`, `solver_infeasible`, `solver_timed_out`,
or `solver_failed` — all four are legal edges out of `cancellation_requested`.

### Decision 6 — The worker's single long domain transaction splits in two; `execute_schedule_run` stops calling `mark_running`

**This is the load-bearing decision of the story. Without it the AC is unimplementable.**

Today one `engine.begin()` spans `mark_running` → solve → `finalize_run` → `complete_job`
(`lease_and_execute_schedule_run.py:72-111`). `mark_running` takes a row-exclusive lock on
`schedule_run` and holds it for the entire solve. Any cancellation UPDATE against that row — queued
branch or running branch — **blocks until the solve finishes**, which is the opposite of cancelling it.
A plain `SELECT` would not block, but it would read the pre-`mark_running` snapshot and route the
command down the wrong branch. There is no version of this command that works while that transaction
stays open.

The split:

* **Transaction A (short):** `load_snapshot`, `get_run_state`, branch (Decision 7), `mark_running` if
  the run is `solver_queued`. Commit.
* **Transaction B (long):** cooperative re-check, then solve, `finalize_run`, `complete_job`. Commit.

`execute_schedule_run` (`application/use_cases/execute_schedule_run.py:30-59`) **loses its
`mark_running` call**; the caller performs it in Transaction A. The use case's remaining responsibility —
solve one already-running run and finalize it literally — still matches its name, its
`_FencedFinalizationRepository` wrapper is unchanged, and `finalize_schedule_run` is untouched. Adapt
`tests/test_finalize_schedule_run.py:37` and `tests/test_lease_next_job.py:66`, which assert the call.

This is a **partial** pull-forward of the debt deferred to Story 3.5 at Story 3.3's review
(`deferred-work.md:287`). It closes the "`solver_running` is unobservable" half, because that half is a
hard prerequisite for cancelling running work. It closes **none** of the heartbeat half:
`renew_job_lease` still has no caller and the lease is still a fixed `default_lease_seconds` window.
Update the ledger entry to say exactly that — **do not close it**.

The split creates one new reachable path: a crash between A and B leaves the run `solver_running` with
no job terminal state. Decision 8 handles it.

### Decision 7 — Cooperative observation happens at two committed checkpoints; mid-solve pre-emption is out of scope

The worker branches on the run status read inside each transaction.

**Checkpoint 1 (Transaction A), after `get_run_state`:**

| Status read | Action |
|---|---|
| `solver_queued` | `mark_running`; continue to B |
| `solver_running` | this worker holds the current epoch, so this is its own recovered attempt — continue to B **without** marking (Decision 8) |
| `cancellation_requested` | `finalize_run(status="solver_cancelled", reason="cancelled")`, `complete_job`, return |
| any terminal | `complete_job`, return that status; solve nothing |

**Checkpoint 2 (Transaction B), before `scheduler.solve`:** re-read the status. If it is
`cancellation_requested`, finalize to `solver_cancelled` and `complete_job` without calling the solver.
This checkpoint catches a cancellation arriving in the window between A and B, and it works because
PostgreSQL's READ COMMITTED default takes a fresh snapshot per statement, so a committed cancellation is
visible inside B.

**`NOT COVERED: cancellation:mid_solve_preemption_owned_by_story_3_5`.** Interrupting a solve already
inside `scheduler.solve` needs either a CP-SAT callback wired to a second thread or the heartbeat Story
3.5 owns. It is not required by this AC: AD-6 says cancellation is "persisted and **cooperative**", and
the race the AC names is with *completion*, which Decision 5 resolves. Do **not** add a thread, a
`threading.Timer`, or an OR-Tools callback to `engine/governed_adapter.py` — `engine/**` outside one
`SCOPE_CONTROLS` string is a zero-line diff for this story.

### Decision 8 — `solver_running` is resumable, not stranded

Checkpoint 1's `solver_running` row is not a defensive nicety; it is what keeps Decision 6's split from
creating a permanently stuck run. A worker that crashes between A and B leaves `solver_running`; its
lease expires; `lease_next_job` re-leases the job under a **new** epoch; the recovered worker reads
`solver_running`, skips `mark_running` (whose `solver_queued` predicate would reject it anyway), and
proceeds. That is Story 3.3's AC3 — "a recovered worker may safely recompute under a newer epoch" —
reached for the first time by a real path.

Holding the lease's current epoch is the proof of ownership, and `finalize_run`'s `_claim_epoch` is what
rejects a worker that does not hold it. No extra guard is needed and none should be added.

### Decision 9 — Terminal and already-requested runs are refused with problems, not silently accepted

* Already `cancellation_requested`, correct expected version → **200**, current state, no write. A second
  cancel of work already being cancelled is the same requested effect, not an error.
* Terminal, correct expected version → **409 `run_not_cancellable`**. FR16 scopes cancellation to
  "queued or running work"; reporting success over completed work would be a lie the planner acts on.
* Terminal, stale expected version → **409 `stale_resource_version`** (that guard fires first). This is
  the common race and it needs no special branch.
* Unknown run, or a run in another site → **404 `schedule_run_not_found`**, the same non-disclosing
  shape `api/routers/proposals.py:_not_found` uses (AD-3).

Reuse the existing problem codes `stale_resource_version` and `idempotency_key_conflict` verbatim —
`api/routers/proposals.py:_command_problem` already publishes both, and a second spelling of the same
failure would fragment the frontend's error handling.

---

## Two honest gaps, raised rather than papered over

### Gap 1 — Nothing sets `job_queue.status` to a terminal value when a queued run is cancelled

The cancel command writes only `cancellation_requested` on the job (Decision 4). A cancelled queued run
therefore leaves a `queued` job that a worker will still lease once, observe as terminal at Checkpoint 1,
and `complete_job` without solving. That is correct but wasteful, and if no worker ever runs, the row
sits `queued` forever.

Deliberately not fixed here. The alternative — a compare-and-set `queued → completed` inside the cancel
command — adds a second write path into Workflow's status column with its own race against
`lease_next_job`, for a saving of one no-op lease. The real fix is `job_queue`'s missing terminal-failure
vocabulary, already deferred to **Story 3.5** with a named owner. Record
`NOT COVERED: job_terminal_state:owned_by_story_3_5` and prove the no-op lease path with a test rather
than leaving it as an assumption.

### Gap 2 — "Observed cooperatively by the worker" is proven at the `run_once` boundary, not by a live process

There is still no worker daemon; Story 3.3 shipped `run_once`, not a loop, and process supervision
remains external (`worker/lease_worker.py:run_once` docstring). Both checkpoints are therefore
demonstrated by calling `lease_and_execute_schedule_run` / `run_once` directly against live PostgreSQL
with a cancellation committed from a second session — the same acceptance boundary Story 3.3's AC2 and
AC3 used, and the one the epic's sequencing note describes. Do not build a daemon to close this; it
belongs with Story 3.6/3.7's operational surface.

---

## Acceptance Criteria

Verbatim from `epics.md#Story-3.4`, followed by what makes it demonstrably true here.

**AC1 — Given** an explicit cancellation request for queued or running work
**When** the versioned idempotent command is accepted
**Then** cancellation is persisted once and observed cooperatively by the worker
**And** a race with completion resolves through the closed state machine without impossible or duplicate
states. (FR16, AR7, AR8)

> **Versioned** — Decision 1's `schedule_run.resource_version`, supplied as `expected_resource_version`
> and folded into the idempotency body hash. A test replays one key against a *different* expected
> version and asserts `IdempotencyKeyConflictError`, not a replay.
>
> **Idempotent** — Decision 3's route with the `Idempotency-Key` header against `command_idempotency`,
> operation `cancel_schedule_run:{run_id}`. A replay returns the original response payload and writes no
> second row; a conflicting body hash raises. Copied from `manage_proposal.py:89-138`, not reinvented.
>
> **Persisted once** — one transaction carrying the status edge, the job flag, and the idempotency row. A
> live test asserts exact row counts after commit and after a forced rollback, covering **all three**
> writes. Story 3.3's equivalent test asserted one of four and that was a review finding
> (`test_job_leasing_postgres.py:437`); do not repeat it.
>
> **Queued or running** — Decision 5's two edges, each asserted against a live database:
> `solver_queued → solver_cancelled` and `solver_running → cancellation_requested`.
>
> **Observed cooperatively by the worker** — Decision 7's two checkpoints. Checkpoint 1: cancel a queued
> run, then lease and run it; assert the solver was never called, the run is `solver_cancelled`, and the
> job is `completed`. Checkpoint 2: commit a cancellation from a second session after Transaction A
> commits and before B starts; assert the run lands `solver_cancelled` with reason `cancelled` and no
> `schedule_version` row exists.
>
> **A race with completion resolves through the closed state machine** — two live tests, both directions.
> (a) Commit the cancellation while the worker is inside Transaction B past Checkpoint 2, let the solve
> finish, and assert `finalize_run` succeeds from `cancellation_requested` onto `solver_completed` with
> exactly one `schedule_version` row. (b) Finalize first, then issue the cancel command and assert
> `409 stale_resource_version`, with `schedule_run` unchanged and `command_idempotency` carrying no new
> row.
>
> **Without impossible states** — an architecture test enumerates every `(from_status, to_status)` pair
> the adapter can write and asserts the set is a subset of AD-7's `ScheduleRun` edge list, transcribed as
> data from `ARCHITECTURE-SPINE.md:106-122`. Removing `finalize_run`'s status predicate must turn it red
> (A2).
>
> **Without duplicate states** — `uq_schedule_version_run` (Story 3.2) plus an assertion that a cancelled
> run has `candidate_schedule_version_id IS NULL`, which `ck_schedule_run_candidate_completed` already
> enforces at the database level.

---

## Tasks / Subtasks

**Retro action A2 is in force.** Every new guard must be **observed failing** with its structural
assertion removed, recorded in the Dev Agent Record with the command and the counts.

### Phase A — the aggregate version, the grants, and the command

#### Task 1 — Migration: `resource_version` and two column grants (AC: 1)

- [x] New revision with `down_revision = "a2b3c4d5e6f7"` (current head, verified at `8623aff`). Add
      `schedule_run.resource_version BIGINT NOT NULL` with `server_default=text("1")`. Mirror it in
      `adapters/postgres/schema.py`'s `schedule_run` table so `alembic check` stays clean.
- [x] `GRANT UPDATE (resource_version) ON schedule_run TO shiftmind_runtime` — additive to
      `f1a2b3c4d5e6_...py:124`'s existing column grant, not a replacement.
- [x] `GRANT UPDATE (cancellation_requested) ON workflow.job_queue TO shiftmind_runtime` (Decision 2).
- [x] `downgrade()` reverses both grants and drops the column, in that order.
- [x] `alembic check` reports zero operations, **run from the repository root**
      (`deferred-work.md:138-147`).

#### Task 2 — Port and adapter: run state, the two edges, and the version bumps (AC: 1)

- [x] `application/ports/schedule_run.py`: add a frozen
      `ScheduleRunStateV1(status: ScheduleRunStatusV1, resource_version: int)` and three methods —
      `get_run_state(connection, *, run_id, site_id) -> ScheduleRunStateV1 | None`,
      `cancel_queued_run(...)`, `request_cancellation(...)`. Add `RunNotCancellableError(ValueError)`
      beside the existing `StaleLeaseError`.
- [x] `adapters/postgres/schedule_run.py`: implement all three as compare-and-set UPDATEs, each carrying
      `resource_version=schedule_run.c.resource_version + 1` and the expected-version predicate.
      `cancel_queued_run` requires `status == "solver_queued"` and sets `finished_at`;
      `request_cancellation` requires `status == "solver_running"` and leaves `finished_at` NULL.
- [x] Add `resource_version + 1` to `mark_running` and `finalize_run`'s `.values()` (Decision 1). Widen
      `finalize_run`'s predicate to `status.in_(("solver_running", "cancellation_requested"))`.
      `_claim_epoch` and `_has_current_epoch` are unchanged — do not touch the fencing guard.
- [x] `set_job_cancellation_requested(connection, *, run_id, site_id) -> None`:
      `UPDATE workflow.job_queue SET cancellation_requested = true WHERE schedule_run_id = :run_id AND
      site_id = :site_id`. A zero-row result is **not** an error (Decision 4).

#### Task 3 — `cancel_schedule_run` use case (AC: 1)

- [x] New `application/use_cases/cancel_schedule_run.py`. Signature mirrors `enqueue_compute`:
      `(run_repository, connection, *, run_id, site_id, actor_id, expected_resource_version,
      idempotency_key) -> ScheduleRunCancellationV1 | None`. Define
      `ScheduleRunCancellationV1` as a frozen dataclass **in this module**, beside the use case,
      the way `EnqueueComputeResultV1` sits in `enqueue_compute.py` — it is a command result, not a
      cross-epic contract, so it does not belong in `application/contracts/`.
- [x] Order of operations, matching `manage_proposal.py:_replay_or_conflict` exactly: bound-check the key
      against `MAX_IDEMPOTENCY_KEY_LENGTH`; read state; `None` → return `None`; replay check (stored hit
      with matching hash → return the stored payload; mismatched hash → `IdempotencyKeyConflictError`);
      expected-version guard; Decision 5's status branch; then `_store_idempotent_result`.
- [x] The stored `response_payload` is JSONB and must be plain JSON — a flat dict of strings and ints
      (`schedule_run_id`, `status`, `reason`, `resource_version`), mirroring
      `enqueue_compute.py:127-133`. Replay reconstructs the result from it; never store a dataclass or
      a `datetime`.
- [x] `_operation(run_id)` returns `f"cancel_schedule_run:{run_id}"` — the key never enters the operation
      string (`manage_proposal.py:_operation`). `_body_hash` covers
      `{run_id, expected_resource_version}` via `contract_digest`.
- [x] Define `CancelScheduleRunError(ValueError)`, `IdempotencyKeyConflictError`,
      `StaleResourceVersionError(expected, current)`, and `RunNotCancellableError` **locally**. Do not
      import `manage_proposal.ProposalCommandError` — Story 3.3 Task 4 established that a schedule-run
      failure raised under a proposal base class misattributes the owning aggregate.
- [x] `SCOPE_CONTROLS`: `COVERS: cancellation:queued_and_running`;
      `NOT COVERED: cancellation:mid_solve_preemption_owned_by_story_3_5`;
      `NOT COVERED: job_terminal_state:owned_by_story_3_5`;
      `NOT COVERED: heartbeat:owned_by_story_3_5`;
      `NOT COVERED: audit:owned_by_epic_4`.

#### Task 4 — Route, schemas, dependency, and the two Gate A records (AC: 1)

- [x] `api/schemas.py`: `ScheduleRunCancellationIn(expected_resource_version: int)` and
      `ScheduleRunOut(schedule_run_id, status, reason, resource_version, cancellation_requested,
      created_at, finished_at)`. Follow the neighbouring models' field style.
- [x] `api/deps.py`: `get_schedule_run_repository()` returning `PostgresScheduleRunRepository()`, copying
      `get_proposal_repository`'s Depends-overridable shape (`api/deps.py:123`). Do **not** add a second
      trusted-site-context opener — reuse `get_site_context`.
- [x] New `api/routers/schedule_runs.py` — **not** `runs.py` (Decision 3). Copy
      `api/routers/proposals.py`'s structure: `_PROBLEMS` mapping, `IdempotencyKey` annotated header,
      `_not_found()`, and a `_command_problem()` mapping the four exception types onto
      `idempotency_key_conflict`, `stale_resource_version`, `run_not_cancellable`, and
      `invalid_cancellation_command`. Omit the handler's return annotation for the reason stated in that
      file's comment.
- [x] `api/main.py`: `app.include_router(schedule_runs.router, prefix="/api/v1")`, added to the existing
      versioned block.
- [x] `tests/test_gate_a_mutation_audit.py:260-271`: append
      `("POST", "/api/v1/schedule-runs/{run_id}/cancellation")` to the `versioned` literal, in sorted
      position.
- [x] `docs/GATE-A-RUNBOOK.md`: add the path to the approved-write-path table (lines 42-47) with the
      reason it touches no governed scenario data and no baseline pointer.
- [x] Regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts`
      (`uv run python scripts/export_openapi.py` from `backend/`, then `npm run codegen:types` from
      `frontend/`). Both are generated artefacts — never hand-edited, and no other `frontend/src/**` file
      changes.

### ⛳ Checkpoint — commit Phase A and report five numbers

1. backend collected / passed / skipped / deselected, and `-m postgres` collected / passed;
2. `alembic check` output, plus a `downgrade a2b3c4d5e6f7` → `upgrade head` round-trip on a fresh
   database;
3. the live column grants on `schedule_run` and `workflow.job_queue`, dumped from
   `information_schema.column_privileges`, proving `shiftmind_runtime` gained exactly `resource_version`
   and `cancellation_requested` and **no** lease or fencing column;
4. the versioned write-route list as OpenAPI reports it, showing exactly seven paths;
5. an idempotent-replay test observed passing, and observed **failing** with the replay branch removed
   (A2).

### Phase B — cooperative observation and the transaction split

#### Task 5 — Split the worker's domain transaction (AC: 1)

- [x] `application/use_cases/execute_schedule_run.py`: remove the `repository.mark_running` call and its
      `assert`. The use case now solves and finalizes an already-running run. Keep `fencing_epoch` and
      `_FencedFinalizationRepository` unchanged.
- [x] `application/use_cases/lease_and_execute_schedule_run.py`: open **two** runtime transactions via
      the existing `runtime_connection_factory` (Decision 6). Delete the current
      `lease.cancellation_requested` branch (`:80-96`) — the illegal AD-7 edge — and replace it with
      Checkpoint 1's table (Decision 7).
- [x] Transaction B opens with Checkpoint 2's re-read before `scheduler.solve`. `complete_job` stays in
      Transaction B.
- [x] Update `SCOPE_CONTROLS` in `lease_and_execute_schedule_run.py`: `cancellation:owned_by_story_3_4`
      is now covered — replace it with `COVERS: cancellation:cooperative_checkpoints` plus the mid-solve
      non-coverage. Narrow the `heartbeat:owned_by_story_3_5` note to state that `solver_running` is now
      committed and only the renewal itself remains outstanding. `job_failure_state:owned_by_story_3_5`
      and `ceilings:lease_seconds_owned_by_story_3_6` stay verbatim —
      `tests/test_lease_worker.py:283` asserts both.
- [x] `application/use_cases/enqueue_compute.py` and `engine/governed_adapter.py`: update their
      `cancellation:owned_by_story_3_4` `SCOPE_CONTROLS` strings to name what is now covered and what is
      not. These are one-line string edits; `engine/governed_adapter.py` changes in no other way.
- [x] `worker/lease_worker.py`: verify `run_once` needs no change — `runtime_context` is already a
      factory invoked per call. If it does change, say why in the Dev Agent Record.

#### Task 6 — The AD-7 edge guard (AC: 1)

- [x] New `tests/architecture/test_schedule_run_state_machine.py`. Transcribe AD-7's `ScheduleRun` edge
      list from `ARCHITECTURE-SPINE.md:106-122` as a literal frozenset of `(from, to)` pairs, with the
      spine line range in the docstring. Assert that every status predicate/target pair the adapter can
      write — parsed from `adapters/postgres/schedule_run.py` by AST, in the style of
      `tests/architecture/test_solver_boundaries.py` — is a member.
- [x] Observe it red by widening `finalize_run`'s predicate to include a terminal status, and record the
      failure output (A2). A guard that cannot go red is the exact defect that produced 19 Epic 2
      findings.

### ⛳ Checkpoint — commit Phase B and report four numbers

1. full regression pass / skip / deselect counts;
2. the AD-7 edge guard observed passing and observed **failing** (A2);
3. a Checkpoint-2 cancellation test observed passing and observed failing with the re-read removed (A2);
4. confirmation that `mark_running` now commits before the solve — the number of distinct transactions
   the worker opens per job, asserted rather than asserted in prose.

### Phase C — race proof, API proof, and ledger reconciliation

#### Task 7 — Live PostgreSQL race and idempotency suite (AC: 1)

- [x] New `tests/test_cancellation_race_postgres.py`, `@pytest.mark.postgres`, reusing
      `governed_postgres_engine`, the `lease_ids` module fixture, and the `_queue_jobs` / `_lease` /
      `_only_leasable` helpers from `tests/test_job_leasing_postgres.py:43-186, 471`. Read those helpers
      before writing new ones — `_only_leasable` exists because `lease_next_job` orders by `created_at`
      and a module-scoped fixture leaves earlier tests' rows behind (Story 3.3's Debug Log).
- [x] Both race directions from AC1, both cooperative checkpoints, the exact-row-count commit/rollback
      assertion over all three writes, and the replay/conflict pair.
- [x] A negative-privilege assertion: `shiftmind_runtime` still cannot UPDATE `lease_owner`,
      `lease_expires_at`, or `fencing_epoch` on `workflow.job_queue` after this story's grant.
- [x] New `tests/test_schedule_runs_api.py` for the route: the four problem responses, the 200 replay,
      and the header bounds. Follow `tests/test_gate_a_mutation_audit.py:200-242`'s `TestClient` +
      `app.dependency_overrides` fixture pattern; the three central denial tests pick the new route up
      automatically from `_versioned_write_routes()`.

#### Task 8 — Ledger, scope declarations, and Gate A (AC: 1)

- [x] `deferred-work.md:287`: **update, do not close.** Record that Story 3.4 split the transaction and
      made `solver_running` observable, that the heartbeat and `renew_job_lease`'s missing caller remain
      open, and keep the owner as Story 3.5.
- [x] `deferred-work.md`: the `job_queue` terminal-failure entry gains Gap 1's no-op-lease consequence.
      Add any new item this story's own review surfaces — do not pre-write findings that have not
      happened.
- [x] `tests/test_lease_worker.py`: extend `test_deferred_owners_are_named_in_scope_controls` to assert
      the new declarations, keeping the three existing assertions intact.
- [x] Gate A re-run per `docs/GATE-A-RUNBOOK.md`: `gate_a_passed: true`, `blocking: []`, regenerating
      `evidence/story-1.11/gate-a-readiness-report.json` **through**
      `backend/scripts/evidence_binding.py` in a separate commit (`docs/EVIDENCE-CONVENTION.md`). This
      story produces no new evidence file of its own.
- [x] Verify the mandated zero-line diffs with `git diff --stat` (Project Structure Notes).

### Review Findings

Code review 2026-08-20 — three layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor), full diff
`main...HEAD`, all layers completed. Suite green at review time (1077 passed / 1 skipped; 72 postgres).

- [x] [Review][Patch] `finalize_run` rejects `solver_running → solver_cancelled` while `finalize_schedule_run._terminal` still produces it, and the resulting failure is an anonymous zero-row `ValueError` [backend/adapters/postgres/schedule_run.py:238] — **D1 resolved (Minh, 2026-08-20): patch adapter-side, do not breach the zero-line-diff fence on `finalize_schedule_run.py`.** Add `IllegalTransitionError` to `application/ports/schedule_run.py`; widen `_raise_transition_failure` to read the actual current status and name the forbidden AD-7 edge; pass `target_status` at the call sites (`:584`, `:262`). Root cause stays open and is owned by Story 3.5 — this makes it self-diagnosing, not fixed.

- [x] [Review][Patch] Cancel command and `finalize_run` take the two row locks in opposite order — ABBA deadlock [backend/application/use_cases/cancel_schedule_run.py:154]
- [x] [Review][Patch] Checkpoint 1 reads run state unlocked, then loses the `mark_running` compare-and-set and raises a bare `ValueError` out of the worker [backend/application/use_cases/lease_and_execute_schedule_run.py:88]
- [x] [Review][Patch] A lost cancellation compare-and-set is reported as `run_not_cancellable` when the real cause is a moved `resource_version` [backend/adapters/postgres/schedule_run.py:99]
- [x] [Review][Patch] A concurrently replayed `Idempotency-Key` returns `409 run_not_cancellable` instead of the stored result [backend/application/use_cases/cancel_schedule_run.py:100]
- [x] [Review][Patch] Every "race" test is strictly sequential — no test holds two transactions open at once [backend/tests/test_cancellation_race_postgres.py:285]
- [x] [Review][Patch] Checkpoint 2 has no terminal-status short-circuit, so a fenced-out worker runs a full duplicate solve before failing [backend/application/use_cases/lease_and_execute_schedule_run.py:142]
- [x] [Review][Patch] Transaction A now commits `mark_running` without claiming the fence under a row lock [backend/adapters/postgres/schedule_run.py:240]
- [x] [Review][Patch] `ScheduleRunOut.cancellation_requested` is a hard-coded `True` published as a required contract field [backend/api/routers/schedule_runs.py:48]
- [x] [Review][Patch] The route's tests monkeypatch the use case away, so router↔use-case wiring is never exercised [backend/tests/test_schedule_runs_api.py:66]
- [x] [Review][Patch] The AD-7 guard inspects three hard-coded function names with no assertion they are the only `update(schedule_run)` sites [backend/tests/architecture/test_schedule_run_state_machine.py:118]
- [x] [Review][Patch] `enqueue_compute.SCOPE_CONTROLS` claims `COVERS: cancellation:queued_and_running`, which that module does not implement [backend/application/use_cases/enqueue_compute.py:21]
- [x] [Review][Patch] `deferred-work.md` rewrites dropped their `file:line` anchors [_bmad-output/implementation-artifacts/deferred-work.md]
- [x] [Review][Patch] Dead `cancelled=` parameter left on the `_lease` test helper after the cancellation branch was replaced [backend/tests/test_lease_next_job.py:33]
- [x] [Review][Patch] Phase A checkpoint item 3 (live column-privilege dump) was never reported in the Dev Agent Record [_bmad-output/implementation-artifacts/3-4-provide-the-safe-cancellation-command.md:750]

- [x] [Review][Defer] `finished_at` is written from two different clocks — `func.now()` on the cancel path, a Python clock in `finalize_run` [backend/adapters/postgres/schedule_run.py:577] — deferred, pre-existing (the new path follows the stated DB-clock rule; the deviating side is the older one)
- [x] [Review][Defer] `getattr(result, "rowcount", 1) != 1` defaults a missing rowcount to success, so the guards fail open [backend/adapters/postgres/schedule_run.py:99] — deferred, pre-existing (same pattern at `:207`, `:261`, `:441`, `:583`)
- [x] [Review][Defer] `ScheduleRunOut.created_at` / `finished_at` are declared in the published contract but never populated [backend/api/routers/schedule_runs.py:43] — deferred, pre-existing (dev scoped them to Story 3.7 with an in-file comment)
- [x] [Review][Defer] A `solver_running` cancellation with no `job_queue` row parks the run non-terminal with no observer [backend/application/use_cases/cancel_schedule_run.py:130] — deferred, incidentally safe today (`mark_running` requires a leased job row); belongs with Story 3.5's orphan handling
- [x] [Review][Defer] `execute_schedule_run` lost `mark_running` and its "must already be `solver_running`" precondition now lives only in a docstring [backend/application/use_cases/execute_schedule_run.py:38] — deferred, no live consequence
- [x] [Review][Defer] AD-13's correlation ID and resource ID are absent from the new RFC 7807 problems [backend/api/routers/schedule_runs.py:64] — deferred, pre-existing repo-wide shape; the spec instructed copying `proposals.py`

**Dismissed as noise (3):** the empty-`idempotency_key` guard is *not* untested — `tests/test_cancel_schedule_run.py:290` parametrizes `("", "x"*41)`; the state-read-before-replay ordering that turns an invisible run into a 404 is defensible (the alternative leaks across sites); `JobLeaseV1.cancellation_requested` being written-but-unread is Decision 4 working as designed ("the flag is a carrier, the status is the authority") and AD-20 requires the lease contract to carry it.


---

## Dev Notes

### What this story is, and what it is not

**It is:** the versioned, idempotent cancellation command for `ScheduleRun`, the two AD-7 edges it
writes, and the two committed worker checkpoints that observe it — plus the transaction split without
which none of that is reachable.

**It is not:**

| Not this | Owner |
|---|---|
| The Cancel control, the Runs workspace, run list/read routes, any `frontend/src/**` source | Story 3.7 |
| The `Run optimization` control, the compute capability, the run-start route, real ceilings | Story 3.6 |
| Persisted run events, SSE replay, the heartbeat, `job_queue`'s terminal-failure status, NFR35 | Story 3.5 |
| Mid-solve pre-emption of a running CP-SAT solve | Story 3.5's heartbeat at the earliest — Decision 7 |
| `AgentRun` cancellation | nobody — `deferred-work.md:223` says explicitly that this story does not cover it |
| Audit envelopes for cancelled actions (FR21) | Epic 4; no `AuditEnvelopeV1` contract exists yet |
| Any solver, metric, demand, or assignment logic | untouched; `docs/DOMAIN-MODEL.md` governs none of it |

### The traps, ranked by how quietly they fail

1. **Writing `solver_running → solver_cancelled`.** It reads as obvious and AD-7 has no such edge. It is
   in the codebase today (`lease_and_execute_schedule_run.py:80-96`) and removing it is part of this
   story. Cancelling running work always passes through `cancellation_requested`.
2. **Keeping the single long transaction.** Every cancellation UPDATE would block behind
   `mark_running`'s row lock for the whole solve, and the story would appear to work in unit tests with
   fakes while being unusable against a real database. Decision 6 is not optional.
3. **Reusing `api/routers/runs.py`.** That is the legacy SQLite router mounted outside `/api/v1`
   (`api/main.py:262`). A route added there is unauthenticated, un-CSRF-guarded, and invisible to every
   Gate A guard.
4. **Bumping `resource_version` only in the new cancellation paths.** A version some writers skip is
   worse than none: `expected_resource_version` would then match a row that had already moved under
   `mark_running` or `finalize_run`.
5. **Deriving the idempotency key from anything server-side.** The caller supplies it, exactly as
   `revise_proposal`, `reject_proposal`, and `enqueue_compute` require — Story 3.3 Decision 3 explains
   why a derived key defeats AD-8 the moment a caller retries.
6. **Trusting `job_queue.cancellation_requested` for a worker decision.** The run status is the
   authority (Decision 4). Two readable sources that can disagree is how impossible states get built.
7. **Adding a `SECURITY DEFINER` function for the flag.** The owner carries `BYPASSRLS`; the function
   would need its own site predicate — exactly the defect Story 3.3's review found in `renew_job_lease`.
   A column grant is covered by RLS for free.
8. **Forgetting the second Gate A guard.** A new versioned write route turns
   `test_gate_a_write_surface_is_exactly_the_approved_paths` and
   `test_runbook_records_every_versioned_write_path` red together. Fixing only the test literal and not
   `docs/GATE-A-RUNBOOK.md` leaves the record incomplete — which is what that second test exists to
   catch.
9. **Editing `docs/API.md`.** It documents the legacy pre-Gate-A SQLite surface and contains zero
   `/api/v1` paths. The versioned surface is documented by OpenAPI and the Gate A runbook.
10. **Hand-editing `frontend/src/api/schema.d.ts`.** It is generated from `frontend/openapi.json`, which
    is generated from the app. Regenerate both; change nothing else under `frontend/`.

### Existing conventions to match, not reinvent

| Need | Copy from |
|---|---|
| Versioned idempotent HTTP command handler | `api/routers/proposals.py:revise` / `reject` |
| RFC 7807 problem mapping and non-disclosing not-found | `api/routers/proposals.py:_command_problem`, `_not_found`; `api/problems.py` |
| Idempotent replay / conflict against `command_idempotency` | `application/use_cases/manage_proposal.py:89-138`; `application/use_cases/enqueue_compute.py:80-136` |
| Local command exception hierarchy for one aggregate | `manage_proposal.py:26-53`; `enqueue_compute.py:32-38` |
| Column-scoped `GRANT UPDATE` migration | `migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py` |
| Compare-and-set repository method raising a distinct exception | `adapters/postgres/schedule_run.py:mark_running`, `complete_job` |
| Depends-overridable repository dependency | `api/deps.py:get_proposal_repository` |
| Architecture fence by AST inspection | `tests/architecture/test_solver_boundaries.py`; `tests/architecture/test_lease_role_boundaries.py` |
| Live-PostgreSQL test with module fixture and seeded ids | `tests/test_job_leasing_postgres.py:43-186` |
| `TestClient` + `dependency_overrides` API test | `tests/test_gate_a_mutation_audit.py:200-242` |
| `SCOPE_CONTROLS` in `COVERS` / `NOT COVERED` form | `enqueue_compute.py:19-29`; `lease_and_execute_schedule_run.py:14-38` |

### Latest technical information (verified against the repo at `8623aff`)

- **No new dependency.** Everything here is SQLAlchemy Core, FastAPI, and Alembic at their existing pins
  (`sqlalchemy==2.0.51`, `alembic==1.18.5`, `psycopg[binary]==3.3.4`). Nothing in
  `backend/pyproject.toml` or `frontend/package.json` changes.
- **READ COMMITTED is what makes Checkpoint 2 work.** PostgreSQL's default isolation takes a fresh
  snapshot per statement, so a cancellation committed by another session between Transaction A and the
  re-read inside Transaction B is visible. It is also why a plain `SELECT` never blocks on a
  concurrently-updated row while an `UPDATE` does — the asymmetry Decision 6 turns on.
- **CI enforces counts.** `.github/scripts/assert_counts.py` enforces pass-count floors and skip-count
  ceilings; the backend skip ceiling is `--max-skipped 1` (`ci.yml:179`). Story 3.3 finished at **2**
  skipped because `test_evidence_binding` skips on a dirty tree — re-verify the current numbers before
  attributing a red CI to this story. Stories 2.7, 3.1, and 3.3 all found their inherited baseline stale.
- **There is no OpenAPI drift gate in CI** (verified: `.github/workflows/ci.yml` has no `openapi` step).
  Regenerating `frontend/openapi.json` and `schema.d.ts` is a task obligation, not something a red build
  will remind you about.
- **`-m postgres` requires the local PostgreSQL service** (docker compose). Establish real pass numbers
  before attributing any failure to this story's changes.
- **Golden dataset:** unchanged at 21 cases. This story ships no capability and no model-facing surface,
  matching Stories 3.2 and 3.3. Record the zero contribution; do not pad it.

### Baselines at creation — re-derive them, do not trust them

| Suite | Reported at Story 3.3 completion (`2026-08-20`, post-review) |
|---|---|
| backend default | 1040 passed, 2 skipped, 7 live-provider deselected |
| backend `-m postgres` | 66 passed |
| golden cases | 21 files |
| frontend Vitest / Playwright | 410 / 48 passed — only the two generated API artefacts change here, so these counts must not move |

### Project Structure Notes

**New files** (AR26's structural seed):

```
backend/api/routers/schedule_runs.py
backend/application/use_cases/cancel_schedule_run.py
backend/migrations/versions/<rev>_add_schedule_run_resource_version_and_cancellation_grant.py
backend/tests/test_cancel_schedule_run.py
backend/tests/test_schedule_runs_api.py
backend/tests/test_cancellation_race_postgres.py
backend/tests/architecture/test_schedule_run_state_machine.py
```

**Modified (UPDATE, not NEW) — read each completely before editing:**

`backend/adapters/postgres/schema.py` (`schedule_run.resource_version`) ·
`backend/adapters/postgres/schedule_run.py` (three new methods, two version bumps, one widened
predicate) · `backend/application/ports/schedule_run.py` (`ScheduleRunStateV1`, three methods, one
error) · `backend/application/use_cases/execute_schedule_run.py` (`mark_running` removed) ·
`backend/application/use_cases/lease_and_execute_schedule_run.py` (two transactions, two checkpoints,
`SCOPE_CONTROLS`) · `backend/application/use_cases/enqueue_compute.py` (`SCOPE_CONTROLS` string only) ·
`backend/engine/governed_adapter.py` (`SCOPE_CONTROLS` string only) · `backend/api/deps.py`
(`get_schedule_run_repository`) · `backend/api/main.py` (one `include_router`) ·
`backend/api/schemas.py` (two models) · `backend/tests/test_gate_a_mutation_audit.py` (write-surface
literal) · `backend/tests/test_lease_worker.py` · `backend/tests/test_lease_next_job.py` ·
`backend/tests/test_finalize_schedule_run.py` · `backend/tests/test_job_leasing_postgres.py` ·
`backend/tests/test_fencing_recovery.py` · `backend/tests/test_postgres_schema.py` (only if it asserts
`schedule_run`'s columns) · `docs/GATE-A-RUNBOOK.md` ·
`_bmad-output/implementation-artifacts/deferred-work.md`

**Regenerated, never hand-edited:** `frontend/openapi.json`, `frontend/src/api/schema.d.ts`,
`evidence/story-1.11/gate-a-readiness-report.json`.

**Mandated zero-line diffs** — verify with `git diff --stat`:

```
frontend/src/**  (except api/schema.d.ts)   backend/domain/**
backend/engine/cpsat/**                     backend/ingest/**
backend/llm/**                              backend/store/**
backend/run.py                              backend/agent/**
backend/application/capabilities/**         backend/application/grounding/**
backend/application/clarification/**        backend/application/scheduling/**
backend/application/drafting/**             backend/evals/**
backend/application/use_cases/create_run_snapshot.py
backend/application/use_cases/finalize_schedule_run.py
backend/application/use_cases/manage_proposal.py
backend/application/use_cases/execute_turn.py
backend/application/use_cases/finalize_agent_run.py
backend/application/contracts/job_lease.py  backend/application/ports/proposal.py
backend/adapters/postgres/proposal.py       backend/adapters/postgres/conversation.py
backend/adapters/postgres/scenario_projection.py
backend/adapters/postgres/scenario_catalogue.py
backend/adapters/postgres/solver_input.py   backend/api/routers/runs.py
backend/api/routers/proposals.py            backend/api/routers/conversations.py
backend/worker/lease_worker.py              data/**
docs/API.md                                 docs/DOMAIN-MODEL.md
backend/migrations/versions/a2b3c4d5e6f7_add_job_queue_and_lease_functions.py
```

`backend/application/contracts/job_lease.py` is fenced: `JobLeaseV1` already carries
`cancellation_requested`, and `JobStatusV1`'s closed vocabulary is Story 3.5's to reopen (Gap 1).
`backend/migrations/versions/a2b3c4d5e6f7_...py` is fenced because
`tests/architecture/test_lease_role_boundaries.py:67` asserts its grant string literally — the new grants
belong in the new revision. `backend/worker/lease_worker.py` is fenced on the expectation that
`runtime_context` already supports being called twice; if that turns out to be false, unfence it and say
why. If a task appears to need anything else in this list, it belongs to a later story.

### References

- `_bmad-output/planning-artifacts/epics.md#Story-3.4` (ACs, verbatim), `#Epic-3` sequencing note,
  `#Story-3.5`, `#Story-3.6`, `#Story-3.7`, FR12, FR13, FR16, AR6, AR7, AR8, AR13, AR22, AR23
- `.../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-3, AD-6, AD-7 (the
  `ScheduleRun` diagram at `:105-119`), AD-8, AD-13, AD-20 (`JobLeaseV1`, the `resource_version`
  preamble), AD-22, AD-23
- `_bmad-output/implementation-artifacts/3-3-lease-solver-jobs-with-fencing.md` — `workflow.job_queue`,
  the lease functions, fencing, Decisions 2/3/5/7, and its Review Findings list
- `_bmad-output/implementation-artifacts/3-2-produce-a-deterministic-candidate-from-an-immutable-snapshot.md`
  — `RunSnapshotV1`, `ScheduleRunRepository`, the terminal-status mapping
- `_bmad-output/implementation-artifacts/3-1-create-and-revise-a-reversible-repair-draft.md` — the
  `command_idempotency` table and the `revise`/`reject` HTTP command shape this story copies
- `docs/GATE-A-RUNBOOK.md` (approved write paths, §2), `docs/EVIDENCE-CONVENTION.md`,
  `docs/DOMAIN-MODEL.md` (cited; governs nothing here)
- `_bmad-output/implementation-artifacts/deferred-work.md:223` (AgentRun cancellation — explicitly not
  this story), `:287` (the heartbeat and the long transaction — updated, not closed)
- `_bmad-output/implementation-artifacts/epic-1-2-retro-2026-08-16.md` — §3.2, §6.1 (A2, A3)
- PostgreSQL: transaction isolation (READ COMMITTED per-statement snapshots) and explicit row-level
  locking

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Phase A: add the versioned aggregate column and grants, implement repository/use-case/API command
  boundaries, and lock behavior down with unit, API, schema, migration, and Gate A tests.
- Phase B: split worker execution into committed transition/solve transactions and enforce AD-7 edges
  structurally.
- Phase C: prove races and atomicity against live PostgreSQL, reconcile deferred scope, regenerate Gate
  A evidence, and run all release-level validation.

### Debug Log References

- 2026-08-20 Phase A RED: `test_schedule_run_resource_version_revision_is_narrow_and_reversible`
  failed on the absent `resource_version`; Task 2 and Task 3 suites then failed at their missing port
  and use-case imports; the API suite failed at its missing repository dependency.
- 2026-08-20 A2 replay mutation: disabling the stored-result branch made both queued and running replay
  cases fail with `StaleResourceVersionError`; restored branch passes 14/14 command tests.
- 2026-08-20 Phase A checkpoint: backend 1075 collected / 1066 passed / 2 skipped / 7 deselected;
  PostgreSQL 66 collected / 66 passed; `alembic check` reported no operations; downgrade to
  `a2b3c4d5e6f7` and upgrade to head succeeded; OpenAPI reported seven versioned write routes.
- 2026-08-20 Phase A checkpoint item 3 (omitted at the time, measured at code review from
  `information_schema.column_privileges` against the governed test database at migration head
  `b3c4d5e6f7a8`). `shiftmind_runtime` holds:
  - `schedule_run` — `UPDATE: candidate_schedule_version_id, finished_at, reason, resource_version,
    status`
  - `job_queue` — `UPDATE: cancellation_requested, heartbeat_at, status`
  The two additive grants are exactly `schedule_run.resource_version` and
  `job_queue.cancellation_requested`. No lease or fencing column is present: `lease_owner`,
  `lease_expires_at` and `fencing_epoch` appear under `SELECT`/`INSERT` only, never `UPDATE` — the
  negative half asserted by `test_runtime_grant_cannot_write_lease_or_fencing_columns`.
- 2026-08-20 Phase B RED: six worker tests failed against the inherited single transaction and the
  execution use case's inherited `mark_running` call. After the split, 31 focused worker/finalization
  tests passed.
- 2026-08-20 A2 state-machine mutation: admitting `solver_completed` as a `finalize_run` source made
  the AST guard fail on four forbidden terminal-to-terminal edges. A2 Checkpoint-2 mutation: removing
  the second cancellation branch made its focused test fail `solver_failed != solver_cancelled`.
- 2026-08-20 Phase B checkpoint: backend 1079 collected / 1070 passed / 2 skipped / 7 deselected;
  the worker transaction-count test observed exactly two runtime transactions per solving job.
- 2026-08-20 Phase C PostgreSQL proof: 6/6 cancellation race tests passed, including exact three-write
  rollback, both cooperative checkpoints, both completion-race directions, replay conflict, and the
  negative lease/fencing privilege set.
- 2026-08-20 Phase C pre-evidence validation: backend 1085 collected / 1076 passed / 2 skipped / 7
  deselected; frontend Vitest 410/410; TypeScript typecheck passed; oxlint passed with three inherited
  Fast Refresh warnings. Mandated zero-line diff paths remained unchanged.
- 2026-08-20 clean-tree Gate A measurement at `7ac7012`: backend 1085 collected / 1077 passed / 1
  skipped / 7 deselected; Vitest 410/410; Playwright XML 48/48. The generator wrote
  `gate_a_passed: true`, `blocking: []`, and evidence-convention validation passed 49/49.

### Completion Notes List

- Phase A complete: `schedule_run` now has a monotonically bumped resource version, cancellation uses
  the two legal AD-7 compare-and-set edges, and the job flag plus idempotency result share the caller's
  transaction.
- Added the authenticated, CSRF-protected, site-scoped cancellation endpoint with stable RFC 7807
  mappings and regenerated API contracts.
- Phase B complete: the worker commits `solver_running` before solving, observes cancellation at both
  committed checkpoints, resumes recovered running work under the current epoch, and never writes the
  illegal `solver_running -> solver_cancelled` edge. `worker/lease_worker.py` required no change because
  its runtime context is already a factory invoked once per transaction.
- Phase C implementation complete: live PostgreSQL proves the cancellation bundle is atomic and
  idempotent, cancellation/completion races remain inside AD-7, and runtime UPDATE privileges do not
  include lease ownership, expiry, or fencing columns. Gate A evidence was regenerated from the clean
  Phase C commit and committed separately.
- Story complete: all eight tasks and AC1 are satisfied. The cancellation command is ready for code
  review; no solver, metric, demand, assignment, frontend source, or baseline-pointer behavior changed.

### File List

- _bmad-output/implementation-artifacts/3-4-provide-the-safe-cancellation-command.md
- _bmad-output/implementation-artifacts/deferred-work.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/adapters/postgres/schedule_run.py
- backend/adapters/postgres/schema.py
- backend/api/deps.py
- backend/api/main.py
- backend/api/routers/schedule_runs.py
- backend/api/schemas.py
- backend/application/ports/schedule_run.py
- backend/application/use_cases/cancel_schedule_run.py
- backend/application/use_cases/enqueue_compute.py
- backend/application/use_cases/execute_schedule_run.py
- backend/application/use_cases/lease_and_execute_schedule_run.py
- backend/engine/governed_adapter.py
- backend/migrations/versions/b3c4d5e6f7a8_add_schedule_run_resource_version.py
- backend/tests/test_cancel_schedule_run.py
- backend/tests/test_cancellation_race_postgres.py
- backend/tests/architecture/test_schedule_run_state_machine.py
- backend/tests/test_evidence_binding.py
- backend/tests/test_gate_a_mutation_audit.py
- backend/tests/test_finalize_schedule_run.py
- backend/tests/test_lease_next_job.py
- backend/tests/test_lease_worker.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_schedule_run_persistence.py
- backend/tests/test_schedule_runs_api.py
- docs/GATE-A-RUNBOOK.md
- evidence/story-1.11/gate-a-readiness-report.json
- frontend/openapi.json
- frontend/src/api/schema.d.ts

## Change Log

- 2026-08-20: Regenerated and separately committed Gate A readiness evidence; marked Story 3.4 ready
  for review.
- 2026-08-20: Completed Phase C live PostgreSQL race/atomicity proof, deferred-scope reconciliation,
  and pre-evidence regression validation.
- 2026-08-20: Completed Phase B cooperative transaction split, recovery path, cancellation checkpoints,
  and executable AD-7 edge guard.
- 2026-08-20: Completed Phase A cancellation aggregate, command, API, migration, generated contracts,
  and validation checkpoint.
- 2026-08-20: Story drafted via `/bmad-create-story 3.4` from `epics.md#Story-3.4`, Story 3.3's as-built
  state at commit `8623aff`, and `ARCHITECTURE-SPINE.md` AD-6/7/8/13/20/22/23.
