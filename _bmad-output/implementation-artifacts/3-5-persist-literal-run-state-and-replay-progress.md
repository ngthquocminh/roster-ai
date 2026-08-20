---
baseline_commit: 1d24cb5d72c627e7921c61cacc95626f2c8544f2
---

# Story 3.5: Persist Literal Run State and Replay Progress [Technical Enabler]

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the scheduling platform,
we want durable literal state and replayable progress events for each run,
So that once runs are startable and monitorable, reconnecting shows the same work instead of an
invented restart or ETA.

**Planner-visible outcome: none at this position.** This story ships persistence and replay
plumbing only — no route a planner triggers by hand, no UI. The progress surface that consumes
these events (Run progress cards, the Runs workspace) is delivered by Story 3.7.
`frontend/src/**` is a zero-line diff **except** the two generated artefacts
(`frontend/openapi.json`, `frontend/src/api/schema.d.ts`), which must be regenerated, never
hand-edited, once the new GET routes exist.

**Depends on, and consumes:** Story 3.4's `schedule_run.resource_version`, the split
transition/execution transactions in `lease_and_execute_schedule_run`, the two committed
cooperative-cancellation checkpoints, and `PostgresScheduleRunRepository`; Story 3.3's
`workflow.job_queue`, fencing epoch, `lease_next_job`/`renew_job_lease`; Story 3.2's
`schedule_run`, `execute_schedule_run`, `finalize_schedule_run`; Story 2.4's `persisted_event`
table, `StreamCursorV1`/`parse_stream_cursor`/`format_event_id`, `EventStreamResponse`,
`get_site_context_opener`, and the whole SSE transport shape in
`backend/api/routers/conversations.py`; AD-6, AD-7, AD-8, AD-18, AD-20, AD-21, AD-22, AD-26.

**Unblocks:** Story 3.6 (the run-start command can enqueue knowing every transition it triggers
is observable), Story 3.7 (the Runs workspace and progress cards render this story's events —
and Story 3.4's `ScheduleRunOut.created_at`/`finished_at` gap, already deferred to 3.7, stays
3.7's), Story 4.1 (approval-required replay reuses this story's stream mechanics, per FR13's
split ownership below).

**Scope summary:** One migration (`persisted_event` widened to admit a schedule-run-owned
stream alongside its existing conversation-owned one; `workflow.job_queue` gains a terminal
`failed` status). One new contract (`RunProgressActivityV1`, closing the `ActivityTypeV1`
reservation `activity.py` already carries). `ScheduleRunRepository`/`PostgresScheduleRunRepository`
gain one event-writing responsibility on every transition method, plus a heartbeat-renewal
caller around the solve. Two new GET routes on the existing `schedule_runs.py` router (one SSE
stream, one plain polling-fallback read) — no new POST, so the write-surface literal in
`test_gate_a_mutation_audit.py` and `docs/GATE-A-RUNBOOK.md` are untouched. One new evidence
generator script and its first evidence file. **No new dependency.** No capability module. No
frontend source change.

**This story is the first in the repository to:**

1. write a `persisted_event` row whose `stream_id` is not a `conversation_id`. Verified by grep
   against `backend/adapters/postgres/schedule_run.py` and every use case that calls it
   (`enqueue_compute.py`, `execute_schedule_run.py`, `finalize_schedule_run.py`,
   `cancel_schedule_run.py`, `lease_and_execute_schedule_run.py`): zero occurrences of
   `persisted_event` or `PersistedEventV1` today, and three separate `SCOPE_CONTROLS` strings
   say so explicitly (`"NOT COVERED: events:owned_by_story_3_5"` in `enqueue_compute.py:20` and
   `lease_and_execute_schedule_run.py:19`, plus the parallel note in `governed_adapter.py:51`);
2. implement `ActivityTypeV1`'s `"run_progress"` member. The literal has been reserved since
   `activity.py:16`, but the `ActivityItemV1` union at `activity.py:121-127` only contains five
   of the eight reserved discriminants;
3. call `workflow.renew_job_lease` (`adapters/postgres/schedule_run.py:429-452`, added by Story
   3.3, has never had a caller — confirmed dead code, `deferred-work.md:287`);
4. reopen the closed `JobStatusV1` vocabulary Story 3.3 froze at `queued|leased|completed`
   (`application/contracts/job_lease.py:11`), adding a fourth, terminal-failure member;
5. widen `persisted_event.conversation_id`/`agent_run_id` from `NOT NULL` to nullable — the
   first schema change to those two columns since Story 2.3 created them.

---

## Facts this story depends on — each one written down and citable

| Fact | Where it is written |
|---|---|
| `AgentRun`, `ScheduleRun`, `ApprovalRequest` use **separate closed graphs**; adapters may project a combined timeline but never merge stored status types; wall-time exhaustion becomes `timed_out`, other ceiling exhaustion becomes `failed`/`budget_exhausted`; **both persist and emit once without implicit retry** | AD-7 (`ARCHITECTURE-SPINE.md:84-88`); `ScheduleRun` graph exactly `solver_queued → solver_running → {cancellation_requested, solver_completed, solver_infeasible, solver_timed_out, solver_failed}`, `solver_queued → {solver_cancelled, solver_timed_out, solver_failed}`, `cancellation_requested → {solver_cancelled, solver_completed, solver_infeasible, solver_timed_out, solver_failed}` (`ARCHITECTURE-SPINE.md:106-122`, already mirrored byte-for-byte in `tests/architecture/test_schedule_run_state_machine.py:AD7_EDGES`) |
| Persisted monotonic event sequences feed SSE replay using `Last-Event-ID`; neither process memory nor the stream is authoritative; each lease has owner, expiry, **heartbeat**, and a monotonically increasing fencing epoch | AD-6 (`ARCHITECTURE-SPINE.md:78-82`) |
| `PersistedEventV1` carries `stream_id`, decimal `sequence`, `event_type`, `occurred_at`, `resource_version`, **correlation IDs** (plural, generic — not "conversation_id and agent_run_id specifically"), and one typed `ActivityItemV1` payload; SSE `id` is `<stream_uuid>:<sequence>`; `Last-Event-ID` must match the URL stream and replay returns only greater sequences; 15s heartbeat comments have no ID and are not persisted | AD-21 (`ARCHITECTURE-SPINE.md:210-214`); also the Structural Seed's `PersistedEventV1` minimum-shape row (`ARCHITECTURE-SPINE.md:332`), which says "correlation IDs" generically — the current Python dataclass and table hard-require `conversation_id`/`agent_run_id` specifically, which is narrower than the architecture's own minimum |
| Workflow owns `job`/`persisted_event`; Scheduling owns proposals/runs/schedule versions; Conversation owns messages/agent runs; **only an application orchestrator crosses owners**. Fixed atomic bundles include `enqueue-compute = immutable run snapshot + job + event` and `complete-compute = terminal run + evidence refs + event, plus candidate schedule version only for a feasible completed result` — the architecture already specifies both bundles include an event, which is exactly what is missing today | AD-22 (`ARCHITECTURE-SPINE.md:216-220`) |
| `application/contracts` owns `PersistedEventV1`/`ActivityItemV1`/`JobLeaseV1` as versioned schemas; adapters translate only at the edge; schema fixtures/compatibility tests gate change | AD-20 (`ARCHITECTURE-SPINE.md:204-208`, `Normative contract minimums` table `:312-333`) |
| NFR35 allocates **first persisted run event within 5s of API acknowledgement** to the persisted workflow boundary (AD-6) — this story's threshold, distinct from SSE reconnect replay (AD-21, Story 2.4's threshold, already shipped) | AD-26 (`ARCHITECTURE-SPINE.md:241-245`); allocation line, `requirements-inventory.md:71`: "Story 3.5 (first persisted run event), Story 2.4 (SSE reconnect replay)" |
| NFR35 measurement protocol: largest Gate A fixture at full size; CI reference / equivalent local machine, not AWS; warm process + warm pool, one discarded warm-up; **3 consecutive runs, every run must meet the threshold** (not a percentile); client-observed measures run from API acknowledgement to **client receipt**; evidence is a dated record binding dataset/evaluator/model/prompt/tool/policy/application/scenario/solver/code/image versions | `requirements-inventory.md:58-69` (normative table) |
| FR13: show persisted queued/running/approval-required/completed/infeasible/timed-out/cancelled/failed states and resume event delivery after reconnect; **FR13 has two independently acceptable ownership boundaries: Story 3.5 owns optimization progress/recovery behavior, Story 4.1 owns approval-required state, presentation, and replay** | PRD FR-13 (`prds/prd-ShiftMind-2026-07-21/prd.md:155-156`); `requirements-inventory.md:75` |
| FR12: durable job with explicit limits for solver time, agent iterations, model/tool calls, retries, tokens, concurrency, total elapsed time; exceeding any ceiling ends in a distinct bounded state | PRD FR-12 (`prd.md:152-153`) |
| NFR16: agent and solver budgets are explicit positive application configuration, never chosen by the model | `requirements-inventory.md:37` |
| UX-DR10 / UX-DR23 (behavioral contract only — Story 3.5 ships no UI): Run progress cards show run ID and literal persisted state, no invented percentage/ETA, recovery retains the same run ID; Reconnect banner pattern, saved content stays visible, replay never duplicates an activity | `epics.md:196, 222` |
| The `ScheduleRunStatusV1`/`ck_schedule_run_status` closed vocabulary is already fully AD-7-compliant, including `cancellation_requested` (Story 3.4) | `application/contracts/schedule_version.py:20-29`; `adapters/postgres/schema.py:442` |
| `finalize_schedule_run._terminal()` **already implements AC3's status mapping**: `deterministic_budget_exhausted` → `solver_failed`/`budget_exhausted`; `solver_status == "UNKNOWN"` (wall-time exhaustion) → `solver_timed_out`/`budget_exhausted` — this predates this story (shipped in 3.2) and is not to be rebuilt, only wrapped with an event | `application/use_cases/finalize_schedule_run.py:30-45` |
| `enqueue_compute`, `mark_running`, `_cancel_transition`, and `finalize_run` are each already a single compare-and-set gated by `status`/`resource_version` (or the idempotency table for `enqueue_compute`); a lost CAS already raises **before** any write happens | `adapters/postgres/schedule_run.py` (`mark_running:279-319`, `_cancel_transition:72-105`, `finalize_run:555-643`); `enqueue_compute.py:88-103` |
| `RunSnapshotV1` carries **no `conversation_id` or `agent_run_id` field** — a schedule run's identity is scenario/proposal/site-scoped only | `application/contracts/run_snapshot.py:56-81` (verified: no such fields exist) |
| `proposal.conversation_id` is `NOT NULL` **today** — every schedule_run is reachable to a conversation via `schedule_run.run_snapshot_id → run_snapshot.proposal_id → proposal.conversation_id` — but Story 3.9 (FR8/AR15) ships a manual deterministic solver flow that explicitly "does not invoke AgentRuntime," i.e. a future schedule_run with no live conversation at all | `adapters/postgres/schema.py:347` (`proposal.conversation_id nullable=False`); `epics.md:1072-1075` (Story 3.9 AC2) |
| `workflow.job_queue.status`/`ck_job_queue_status` is closed at `queued\|leased\|completed` — **no failure member**; a job failing between lease and `complete_job` stays `leased`, expires, and is re-leased ahead of newer work forever (`lease_next_job` orders `ORDER BY q.created_at, q.id`) | `application/contracts/job_lease.py:11`; `adapters/postgres/schema.py:551-554`; `deferred-work.md:291`, **Owner: Story 3.5** |
| The AD-6 heartbeat is inert: `renew_job_lease` has no caller; `lease_seconds` is a fixed value spanning the whole solve unrenewed | `deferred-work.md:287` (Minh, 2026-08-20, D1 option c), **Owner: Story 3.5**; `worker/lease_worker.py:54` |
| A `solver_running` cancellation with no `job_queue` row would park a run non-terminal with no observer — but is **structurally unreachable under every current caller**: `enqueue_compute` always creates the job row atomically with the run, and `mark_running`'s `_has_current_epoch` predicate requires a `status='leased'` job row to exist before a run can ever reach `solver_running` | `deferred-work.md:301`, **Owner: Story 3.5**; `adapters/postgres/schedule_run.py:177-191` (`_has_current_epoch`) |
| Mid-solve preemption of an in-flight CP-SAT call is **not named by any of this story's four ACs** (verified against `epics.md:959-977`); `SCOPE_CONTROLS` comments in `enqueue_compute.py`, `lease_and_execute_schedule_run.py`, `cancel_schedule_run.py`, and `governed_adapter.py` all speculatively assign it to "Story 3.5," but that assignment predates this story's own creation and is corrected below (Decision 6) | `governed_adapter.py:51-53`; `cancel_schedule_run.py:17-23`; solve is bounded today by `wall_time_limit_seconds=30.0` (`settings.py:94`), enforced inside `_solve_lexicographic_governed` (`governed_adapter.py:184-256`) |
| `default_lease_seconds()` already guarantees `lease_seconds ≥ 4 × solver_wall_time_limit_seconds` (currently `≥120s` for a `≤30s`-bounded solve) | `worker/lease_worker.py:53-66` |
| The idempotent per-stream sequence allocation pattern (`coalesce(max(sequence), 0) + 1`, unique on `(stream_id, sequence)`) is established twice already and must be copied, not reinvented | `adapters/postgres/conversation.py:229-230, 378-379`; `application/contracts/stream_cursor.py:15-18` |
| The SSE transport — cursor precedence (header over query), foreign-stream rejection by string comparison alone (zero queries, non-disclosing), one short transaction per poll via `get_site_context_opener` (never `get_site_context`, which would hold one pooled connection for a stream's whole lifetime), `EventStreamResponse` fixing `media_type`, 15s heartbeat comments (never persisted), 1s poll interval, 200-event replay batch cap — is fully built and is "the shape Story 3.5 reuses" | `api/routers/conversations.py:94-99` (comment naming this story explicitly), `:344-511` |
| `docs/EVIDENCE-CONVENTION.md`'s ordering is load-bearing: commit code → clean tree → measure → generate via script (refuses a dirty tree) → commit evidence separately. Never hand-type an evidence file | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |
| Story 2.4's own generator (`scripts/generate_sse_replay_evidence.py`) is the direct template: hardcoded non-tunable `THRESHOLD_MS`, a `NFR35_..._MEASUREMENTS=` stdout marker parsed from a captured pytest run, `resolve_bindings()` (refuses dirty tree, derives `code.git_commit` — never hardcoded), atomic write, self-audit via `audit_evidence_file()` | `scripts/generate_sse_replay_evidence.py` (whole file) |
| New GET routes do **not** enter the write-surface literal — `_versioned_write_routes()` only collects unsafe HTTP methods (POST/PATCH/PUT/DELETE); `docs/GATE-A-RUNBOOK.md` registration is a write-route obligation only | `tests/test_gate_a_mutation_audit.py:243-271` (the exact approved list, all POST) |
| Manual assistive-technology verification is out of scope; automated coverage is the recorded bar. This story ships no UI, so the floor is inapplicable in practice, cited for completeness | `.../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`, Accessibility Floor |
| Every new guard must be **observed failing** with its structural assertion removed before being trusted | retro §6.1 action A2 (applied by Stories 3.3/3.4 to their own AD-7/role guards) |

`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments. **This story touches no
metric, no demand row, and no assignment** — it persists run status transitions and events. Cited
for completeness and deliberately not re-derived.

---

## Acceptance Criteria

1. **Given** an agent run and schedule run before any approval request exists, **When** each
   aggregate transitions, **Then** queued, running, completed, infeasible, timed-out, cancelled,
   failed, and cancellation-requested behavior follows the applicable separate closed
   architecture state machine and emits one monotonic persisted event with stable
   reason/resource version, **And** adapters may project a combined timeline but never merge
   stored status types; approval-request behavior is outside this story's acceptance boundary.
   (FR13, AR7)

2. **Given** a browser disconnect or page reload during queued/running work, **When** the
   browser reconnects with the last matching event ID, **Then** only unseen persisted events
   replay, the same run ID and prior content remain visible, and duplicate activities are
   suppressed, **And** an unavailable stream falls back to labelled polling/manual refresh
   without changing authority. (FR13, UX-DR10, UX-DR23)

3. **Given** a budget or time ceiling is exhausted, **When** the state machine terminates the
   run, **Then** wall-time exhaustion becomes timed-out and other ceiling exhaustion becomes
   failed with stable `budget_exhausted` reason, **And** the event persists once with no
   implicit retry. (FR12, NFR16, AR7)

4. **Given** the NFR35 measurement fixture and protocol used by prior NFR35 stories (Story 1.4's
   protocol; Story 2.4's client-observed variant), **When** a run is accepted and acknowledged,
   **Then** every run delivers the first persisted run event to a connected browser within 5
   seconds, measured from API acknowledgement to client receipt of that event, **And** the
   measured values are recorded as release evidence and a miss blocks implementation acceptance
   of this story. (NFR35)

## Tasks / Subtasks

- [x] **Task 1 — Widen `persisted_event` for a schedule-run-owned stream** (AC: 1)
  - [x] Migration (`down_revision = "b3c4d5e6f7a8"`): make `persisted_event.conversation_id` and
        `agent_run_id` nullable; add nullable `schedule_run_id UUID` with
        `ForeignKeyConstraint(["schedule_run_id", "site_id"], ["schedule_run.id", "schedule_run.site_id"], ondelete="RESTRICT")`.
        Replace `ck_persisted_event_stream_is_conversation` with a CHECK admitting exactly two
        shapes: `(conversation_id IS NOT NULL AND schedule_run_id IS NULL AND stream_id = conversation_id)`
        OR `(schedule_run_id IS NOT NULL AND conversation_id IS NULL AND stream_id = schedule_run_id)`.
        Additive-only; existing rows (all conversation-shaped) satisfy the new CHECK unchanged.
  - [x] `alembic check` from the repository root: zero autogenerate operations, exactly one new
        migration file.
  - [x] `PersistedEventV1` dataclass: make `conversation_id`/`agent_run_id` `UUID | None`, add
        `schedule_run_id: UUID | None`. Widening a dataclass field is additive; existing callers
        that always pass both conversation fields are unaffected.
  - [x] Do **not** reuse `conversation_id` as the schedule-run stream identity (rejected
        alternative — see Decision 1 below).

- [x] **Task 2 — Add `RunProgressActivityV1`** (AC: 1, 2)
  - [x] New frozen dataclass in `application/contracts/activity.py`: `activity_id`,
        `activity_type: Literal["run_progress"]`, `schedule_run_id: UUID`,
        `status: ScheduleRunStatusV1`, `reason: str | None`, `resource_version: int`,
        `occurred_at: datetime`, `schema_version`. Add to the `ActivityItemV1` union. Deliberately
        carries no `conversation_id`/`scenario_id` — see Decision 2.
  - [x] Extend `conversations.py`'s `_activity()` (or its equivalent used by the new route) to
        render `RunProgressActivityV1` into an `ActivityItemOut` union member; add the
        corresponding response-schema case in `api/schemas.py`.

- [x] **Task 3 — Emit one persisted event per `ScheduleRun` transition** (AC: 1, 3)
  - [x] `ScheduleRunRepository` port gains an implicit responsibility (no new protocol method is
        required — each existing transition method writes its own event in the same statement's
        transaction): `create_queued_run` (queued), `mark_running` (running),
        `request_cancellation` (cancellation_requested), `cancel_queued_run` (cancelled, from
        queued), `finalize_run` (completed/infeasible/timed_out/cancelled/failed).
  - [x] Reuse the `coalesce(max(sequence), 0) + 1` per-`stream_id` allocation subquery already
        established in `adapters/postgres/conversation.py:229-230`. `resource_version` on the
        event equals the schedule_run row's own post-increment `resource_version`.
  - [x] `event_type` follows the Consistency Conventions naming pattern (`ARCHITECTURE-SPINE.md:254`,
        `run.<status>.v1`, e.g. `run.queued.v1`, `run.running.v1`, `run.cancellation_requested.v1`,
        `run.completed.v1`, `run.infeasible.v1`, `run.timed_out.v1`, `run.cancelled.v1`,
        `run.failed.v1`).
  - [x] Prove AC3's "persists once with no implicit retry": a test that replays
        `enqueue_compute`'s idempotency-hit path and asserts no second `queued` event is written;
        a test that a lost CAS in `mark_running`/`finalize_run` raises before any event row
        exists (assert zero rows, not just that the visible status is unchanged).

- [x] **Task 4 — Reopen `JobStatusV1` for a terminal failure state** (AC: 1, 3)
  - [x] Add `"failed"` to `JobStatusV1`/`JOB_STATUSES` and `ck_job_queue_status` (same migration
        as Task 1).
  - [x] In `lease_and_execute_schedule_run`, wrap the currently-unguarded body between lease
        acquisition and `complete_job` (missing snapshot, an exhausted `mark_running` retry
        raising `RunTransitionConflictError` on the second attempt, and any other exception
        surfaced before a terminal status is reached) so it drives the **job** to `status="failed"`
        and the **schedule run** to `solver_failed`/reason `"job_execution_failed"` in one
        transaction, instead of leaving the job `leased` to expire and be re-leased at the queue
        head forever.
  - [x] Test: an injected repository/scheduler fake that raises after lease acquisition; assert
        the job reaches `failed`, the run reaches `solver_failed`, and the run is never re-leased
        by a subsequent `lease_next_job` call.

- [x] **Task 5 — Heartbeat renewal caller** (AC: 1)
  - [x] Around `scheduler.solve(snapshot)` in `execute_schedule_run`, run a background thread
        that calls `repository.renew_job_lease` every `lease_seconds // 3` seconds (its own
        short-lived connection, never the solve's own runtime connection), stopped via a
        `threading.Event` in a `finally` block once `solve()` returns.
  - [x] Scope this call to lease liveness only — it must never set `SolverOutcomeV1.reason =
        "cancelled"` or otherwise influence the terminal status (see Decision 5/6: mid-solve
        preemption stays out of this story).
  - [x] Test with a fake scheduler that sleeps past what an unrenewed lease would survive; assert
        the fencing epoch/lease stays current through the sleep and the eventual `finalize_run`
        is not fenced out.

- [x] **Task 6 — SSE replay route for one schedule run** (AC: 2, 4)
  - [x] New `GET /api/v1/schedule-runs/{run_id}/events` on `schedule_runs.py`, mirroring
        `conversations.py`'s `/{conversation_id}/events` route byte-for-byte in mechanics: cursor
        precedence (`Last-Event-ID` header over `?last_event_id=`), foreign-stream rejection by
        string comparison alone (zero queries), one short transaction per poll via
        `get_site_context_opener`, `EventStreamResponse`, 15s heartbeat comments (not persisted),
        1s poll interval, non-disclosing `stream_cursor_invalid` rejection shape.
  - [x] `ScheduleRunRepository` needs an `events_after(connection, *, stream_id, after, limit)`
        method mirroring `ConversationRepository.events_after`, plus a lightweight "does this run
        exist for this site, what is its current max sequence" pre-flight (mirrors `_head()`'s
        `timeline(limit=1)` use, scoped to `schedule_run`/`persisted_event` instead).
  - [x] Reject a foreign or malformed cursor with the same `stream_cursor_invalid` shape
        `conversations.py` already defines (reuse `parse_stream_cursor`/`StreamCursorV1`, do not
        duplicate the parser).

- [x] **Task 7 — Polling fallback route** (AC: 2)
  - [x] New `GET /api/v1/schedule-runs/{run_id}` returning the existing `ScheduleRunOut` shape
        (`schedule_run_id`, `status`, `reason`, `resource_version`, `cancellation_requested`) —
        the same fields `cancel()`'s `_out()` already produces. Do **not** add `created_at`/
        `finished_at` to `ScheduleRunOut`; that gap is already deferred to Story 3.7
        (3.4 review Defer finding) and is not this story's to close.
  - [x] 404 via the same `_not_found()` helper `cancel()` uses, for an unknown or cross-site run.

- [x] **Task 8 — NFR35 evidence for AC4** (AC: 4)
  - [x] New measuring test (mirrors `test_postgres_integration.py`'s
        `test_nfr35_sse_reconnect_replay_meets_five_second_threshold`): commit an
        `enqueue_compute` bundle directly (standing in for "API acknowledgement" — Story 3.6 has
        not yet shipped the live HTTP creation command) as the timing origin, drive the real ASGI
        `app` object directly (never `TestClient`, which buffers the whole streaming body) over
        the new `/schedule-runs/{run_id}/events` route, time to the `send` call carrying the
        first `run_progress` (queued) frame. One discarded warm-up run, then 3 consecutive
        measured runs, all must meet 5000 ms. Print an
        `NFR35_RUN_EVENT_LATENCY_MEASUREMENTS=[...]` marker.
  - [x] New `backend/scripts/generate_run_event_latency_evidence.py`, structured exactly like
        `generate_sse_replay_evidence.py` (hardcoded `THRESHOLD_MS = 5_000`, `resolve_bindings()`
        refusing a dirty tree, atomic write, `audit_evidence_file()` self-audit). Register the
        new file in `regenerate_evidence.py`'s `EVIDENCE_FILES`/`_MEASUREMENT_MARKERS`.
  - [x] Follow `docs/EVIDENCE-CONVENTION.md`'s order exactly: commit code → confirm clean tree →
        measure → generate → commit `evidence/story-3.5/nfr35-first-run-event.json` separately.
        Never hand-type it.

- [ ] **Task 9 — AD-7 structural guards and regression** (AC: 1, 3)
  - [ ] Extend `tests/architecture/test_schedule_run_state_machine.py`'s pattern (or add a
        sibling test) so the event-emitting code paths are covered by the same
        "every writer is a known, named function" AST-exhaustiveness style already used for
        `_SCHEDULE_RUN_WRITERS` — a fifth transition-writing function added later without
        updating the guard must fail loudly, not pass silently.
  - [ ] Observe each new guard failing with its assertion removed before trusting it green
        (retro action A2); record the observation in Completion Notes.
  - [ ] Full regression: `pytest` (all markers), `alembic check` from the repository root,
        Gate A re-run, `npm run build && npm test` if the generated OpenAPI/schema types moved
        (they will — two new GET paths).

## Dev Notes

### Decisions Made at Creation

1. **`ScheduleRun` gets its own event-stream identity (`stream_id = schedule_run_id`), not the
   owning conversation's.** Rejected alternative: since `proposal.conversation_id` is `NOT NULL`
   today (`schema.py:347`), every schedule_run *could* be traced to a conversation and its
   progress events folded into that conversation's existing stream — reusing the shipped SSE
   route entirely. Rejected because `RunSnapshotV1` itself carries no `conversation_id` (Scheduling
   does not depend on Conversation identity, per AD-22's aggregate ownership), and Story 3.9's
   manual deterministic solver flow explicitly "does not invoke AgentRuntime" (FR8/AR15,
   `epics.md:1072-1075`) — a future schedule_run created by that path has no conversation at all.
   Coupling ScheduleRun's event lifecycle to Conversation's identity today would need undoing the
   moment 3.9 ships. AD-7's "adapters may project a combined timeline" is read as permission for
   a future query-layer join (Story 3.7's problem), not a requirement that the two aggregates
   share one physical stream.

2. **`RunProgressActivityV1` carries no `conversation_id`/`scenario_id`/`scenario_version_id`,
   unlike the other five `ActivityItemV1` variants.** Those fields exist on
   `PlannerMessageActivityV1` etc. because a conversation-scoped activity always has one; a
   schedule-run-scoped activity, per Decision 1, does not. The Structural Seed's minimum shape
   for this discriminant is exactly "agent/solver refs/status/reason" (`ARCHITECTURE-SPINE.md:331`)
   — nothing wider is owed.

3. **Every transition method writes its own event inside its own existing CAS/insert, not as a
   separate post-hoc write.** `mark_running`, `_cancel_transition`, and `finalize_run` are
   already gated by a `status`/`resource_version` (or epoch) predicate that raises before any
   effect is written on a lost race. Piggy-backing the event insert on that same guarded write —
   rather than issuing it afterward, unconditionally — is what makes AC3's "persists once with no
   implicit retry" true by construction instead of by a second, separately-fallible check.

4. **`JobStatusV1` gains `"failed"`, not a richer retry/attempt-count vocabulary.** AC1 names
   `failed` as a required literal state and `deferred-work.md:291` names this story as the one
   that must reopen the closed vocabulary — a fourth member is the minimum that satisfies both;
   a dead-letter queue or attempt counter is not asked for by any AC and is not built.

5. **Heartbeat renewal is lease-liveness only, decoupled from mid-solve preemption.** The
   background thread's only job is to keep `job_queue.fencing_epoch`/`lease_expires_at` current
   during a solve that runs close to (but under) `lease_seconds`; it never inspects or sets
   `cancellation_requested` and never influences `SolverOutcomeV1`. This closes
   `deferred-work.md:287` without building the interruption mechanism Decision 6 explicitly
   defers.

6. **Mid-solve preemption is corrected off this story's scope, not silently absorbed.**
   `SCOPE_CONTROLS` comments written by Stories 3.3/3.4's authors assign
   `"cancellation:mid_solve_preemption_owned_by_story_3_5"` in three files
   (`enqueue_compute.py`, `lease_and_execute_schedule_run.py`, `cancel_schedule_run.py`,
   `governed_adapter.py`), but none of this story's four ACs (`epics.md:959-977`, verified at
   creation) require interrupting an in-flight `cp_model.CpSolver.Solve()` call. The existing
   two cooperative checkpoints already bound cancellation latency to one solve's wall-time budget
   (`≤30s` today, `settings.py:94`), and that budget is itself an AD-7 ceiling already fully
   handled by `_terminal()`/`apply_remaining_budget()`. Per the established re-annotate-in-place
   pattern (Stories 2.4/2.5/2.6/3.4), this story leaves the four `SCOPE_CONTROLS` comments'
   assignment corrected in place rather than deleted, and restates the owner as **the first story
   that raises `wall_time_limit_seconds` materially above the current default** — most plausibly
   Story 3.6, which owns the real ceiling (`deferred-work.md:289`).

7. **The `IllegalTransitionError` guard at `schedule_run.py:266-274` is left unchanged, verified
   still unreachable.** Its comment ("Root cause is owned by Story 3.5") reads as a bug to fix,
   but `SolverOutcomeV1.reason` is only ever set to `"cancelled"` by a mid-solve preemption
   mechanism — which Decision 6 confirms this story does not build. The guard remains correct
   defensive code against a caller that does not exist yet; deleting it as "dead code" would be
   the disaster, not fixing a live bug. This is stated explicitly so a future story does not
   remove it by mistake.

8. **The orphaned `solver_running`-with-no-job-row concern (`deferred-work.md:301`) is recorded
   as verified-safe-today, not defended against with new code.** Every current caller makes it
   structurally unreachable (Decision detail in the Facts table above). Building a guard against
   a caller that does not exist adds an untestable branch. The next story that creates a
   schedule_run without a job row (candidate: Story 3.9's manual flow) must re-verify this
   invariant before relying on it — restated here so that story's author does not have to
   re-derive it from adapter code.

9. **AgentRun's own transitions are treated as already AC1-compliant and are not touched.**
   `agent_queued` (via `accept_turn`'s planner-message event) and every terminal state (via
   `finalize_agent_run`'s terminal-outcome event) already get exactly one persisted event each,
   shipped in Epic 2. `agent_queued → agent_running` has no dedicated `ActivityTypeV1` discriminant
   and no `deferred-work.md`/`SCOPE_CONTROLS` reference assigns it to this story — AC1's literal
   state list (`queued, running, completed, infeasible, timed-out, cancelled, failed,
   cancellation-requested`) matches `ScheduleRunStatusV1`'s eight members exactly, not
   `AgentRun`'s seven-member vocabulary, confirming AC1's new work is the `ScheduleRun` side.

10. **AC4 is measured against a directly-committed `enqueue_compute` bundle, not a live HTTP
    create route.** Story 3.6 (which ships the "Run optimization" HTTP command) has not shipped;
    epics.md's own framing ("Planner-visible outcome: none... Accepted through seeded
    state-machine... tests") confirms the measurement is seeded, exactly as Story 2.4 measured
    SSE replay against a directly-seeded event backlog rather than a live agent turn.

### Honest Gaps

- **No live HTTP path creates a schedule run yet.** AC4's "API acknowledgement" is necessarily
  simulated by a direct `enqueue_compute` commit (Decision 10). Once Story 3.6 ships the real
  route, its own acceptance should re-measure end-to-end; this story's evidence remains valid for
  the mechanism it actually tests (persisted-event commit → SSE delivery latency), not for the
  full HTTP round trip.
- **Mid-solve preemption remains unbuilt** (Decision 6) — cancellation of a running solve is
  still bounded by the wall-time ceiling, not by an interrupt. Not a defect against this story's
  ACs; recorded so it is not silently assumed solved.
- **The heartbeat renewal caller is a correctness improvement for a scenario that cannot occur
  under today's settings** (`lease_seconds ≥ 4× wall_time_limit_seconds` always holds via
  `default_lease_seconds()`), built now because Story 3.6 will raise ceilings and because this
  story's own ACs already require touching the exact same code paths. Proportional effort: the
  renewal call itself, not a general-purpose heartbeat framework.

### Traps

- Do not reuse `conversation_id` as the schedule-run stream identity (Decision 1) — it is the
  path of least resistance and it is wrong for Story 3.9.
- Do not add a new `ScheduleRunRepository` protocol method for "write an event" — each transition
  method writes its own, inline, inside its own existing CAS (Decision 3). A separate
  `emit_event()` call issued after the CAS reopens the exact race AC3 forbids.
- Do not let the heartbeat thread touch `cancellation_requested` or `SolverOutcomeV1.reason`
  (Decision 5) — that would silently reintroduce mid-solve preemption through the back door and
  reawaken the `IllegalTransitionError` guard (Decision 7) for real.
- Do not add the two new GET routes to `test_gate_a_mutation_audit.py`'s write-surface literal or
  `docs/GATE-A-RUNBOOK.md` — that registration is for unsafe-method routes only; these are GET.
- Do not hand-type `evidence/story-3.5/nfr35-first-run-event.json` — generate it via the new
  script, following `docs/EVIDENCE-CONVENTION.md`'s ordering exactly (this is the exact mistake
  that produced an unreproducible `git_commit` in all four Epic 1 evidence files).
- Do not widen `ScheduleRunOut` with `created_at`/`finished_at` — already deferred to Story 3.7;
  adding it here duplicates ownership of a field this story does not need.
- `persisted_event.sequence` is `Decimal`, never a string — the per-stream allocation subquery
  and any comparison must go through `Decimal`, exactly as `stream_cursor.py`'s docstring warns
  (`"10" < "9"` as strings).

### Testing Requirements

- `pytest -m postgres` for every new adapter/repository behavior (event writes, `events_after`,
  the widened CHECK constraint, the new terminal job status) — this repository's live-PostgreSQL
  suite is where CAS/race/constraint behavior is actually proven, not the SQLite-fallback path.
- Architecture guard: extend or add to `tests/architecture/test_schedule_run_state_machine.py`
  so a sixth writer (an event insert bypassing the known transition methods) cannot land
  unnoticed — mirror the existing exhaustiveness pattern (`_SCHEDULE_RUN_WRITERS`).
- Negative-privilege / RLS: the new `schedule_run_id` FK and the widened CHECK do not change any
  role grant; no new privilege test is owed unless a new column write path is added to a role
  that did not have it (verify before assuming none is needed).
- NFR35 evidence: 3 consecutive runs, all must pass, against `sample_tiny_input_more_tm.json`
  (the same largest Gate A fixture Stories 1.4/1.5/2.4 used).
- Observe each new structural guard failing with its assertion removed (retro action A2) and
  record the observation in Completion Notes, per the pattern Stories 3.3/3.4 both followed.

### Project Structure Notes

- Touches: `backend/adapters/postgres/schema.py`, `backend/adapters/postgres/schedule_run.py`,
  `backend/adapters/postgres/conversation.py` (only if `_activity()`'s dispatch is shared —
  otherwise a sibling renderer in `schedule_runs.py`), `backend/application/contracts/activity.py`,
  `backend/application/contracts/persisted_event.py`,
  `backend/application/contracts/job_lease.py`, `backend/application/ports/schedule_run.py`,
  `backend/application/use_cases/{enqueue_compute,execute_schedule_run,finalize_schedule_run,
  lease_and_execute_schedule_run,cancel_schedule_run}.py`, `backend/api/routers/schedule_runs.py`,
  `backend/api/schemas.py`, `backend/api/deps.py` (if the new route needs a dependency not
  already exposed), `backend/migrations/versions/<new>_widen_persisted_event_and_job_status.py`,
  `backend/scripts/generate_run_event_latency_evidence.py` (new),
  `backend/scripts/regenerate_evidence.py`, `evidence/story-3.5/nfr35-first-run-event.json` (new).
- **Zero-line diff fences** (verify before touching, matching the pattern every prior Epic 3
  story records): `backend/domain/**`, `backend/engine/cpsat/**` (only `governed_adapter.py`'s
  `SCOPE_CONTROLS` comment changes, not solver logic), `backend/llm/**`, `backend/ingest/**`,
  `backend/store/**`, `backend/services/**`, `test_gate_a_mutation_audit.py`,
  `docs/GATE-A-RUNBOOK.md` (Task 6/7's routes are GET, not write routes — see Facts table),
  `frontend/src/**` except the two generated artefacts.
- Naming/layout matches existing conventions exactly: use cases in
  `application/use_cases/*.py` (snake_case, imperative), contracts in
  `application/contracts/*.py` (PascalCase + `V1` suffix), Postgres adapters in
  `adapters/postgres/*.py`, migrations named `<revision>_<imperative_description>.py` with
  `down_revision = "b3c4d5e6f7a8"` (the current chain tail).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.5, lines 949-977] — story statement
  and all four ACs, verbatim.
- [Source: _bmad-output/planning-artifacts/epics.md#Requirements Inventory, lines 152-154, 196, 222] — AR7, AR8, UX-DR10, UX-DR23.
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-6, AD-7, AD-18, AD-20, AD-21, AD-22, AD-26, lines 78-245] — state machines, event contract, aggregate ownership, NFR35 allocation.
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md, lines 33-71, 75] — NFR16, NFR35 and its normative measurement protocol, FR13's split ownership.
- [Source: _bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md, lines 151-156] — FR-12, FR-13 normative wording.
- [Source: backend/adapters/postgres/schema.py, lines 298-330, 431-444, 499-557] — `agent_run`, `persisted_event`, `schedule_run`, `job_queue` table definitions as they exist today.
- [Source: backend/adapters/postgres/schedule_run.py, whole file] — every transition method this story must instrument with an event write.
- [Source: backend/application/use_cases/{enqueue_compute,lease_and_execute_schedule_run,finalize_schedule_run,execute_schedule_run,cancel_schedule_run}.py] — SCOPE_CONTROLS markers naming this story; existing budget-exhaustion mapping.
- [Source: backend/application/contracts/{activity,persisted_event,job_lease,schedule_version,run_snapshot}.py] — contract shapes to extend.
- [Source: backend/api/routers/conversations.py, lines 79-511] — the SSE transport this story reuses; `_frame`, `_event_frames`, cursor precedence, non-disclosure pattern.
- [Source: backend/application/contracts/stream_cursor.py, whole file] — cursor parsing/formatting, reused as-is.
- [Source: backend/scripts/generate_sse_replay_evidence.py, whole file] — the NFR35 evidence-generator template.
- [Source: evidence/story-2.4/nfr35-sse-reconnect-replay.json] — the sibling evidence file's exact shape.
- [Source: docs/EVIDENCE-CONVENTION.md] — evidence-generation ordering, binding via `evidence_binding.py`.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, lines 287, 289, 291, 301] — the four ledger items this story owns or explicitly re-points.
- [Source: _bmad-output/implementation-artifacts/3-3-lease-solver-jobs-with-fencing.md] and [Source: _bmad-output/implementation-artifacts/3-4-provide-the-safe-cancellation-command.md] — prior-story decisions, file lists, review findings this story inherits.
- [Source: docs/DOMAIN-MODEL.md] — cited per project convention; this story touches no metric/demand/assignment.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

- 2026-08-21 — Task 1 plan/verification: added failing contract and schema tests first (3 observed failures), then widened the event envelope and SQLAlchemy metadata, added the single `c4d5e6f7a8b9` migration, upgraded the local test database, and confirmed `alembic check` reports no new operations.
- 2026-08-21 — Task 2 plan/verification: observed the missing `RunProgressActivityV1` import fail, then added the frozen contract and discriminated response model; the existing generic `_activity()` projection now validates the new union member without conversation fields.
- 2026-08-21 — Task 3 plan/verification: observed empty-event failures for enqueue and transition paths, then inserted run progress inside each existing transaction after its successful CAS/insert. Event resource versions come from SQL `RETURNING`; lost CAS paths emit nothing. Updated legacy SQL test doubles to model the returning rows.
- 2026-08-21 — Task 4 plan/verification: observed three red failures for the closed job vocabulary, missing failure wrapper, and schema CHECK. Added fenced `fail_job`, allowed the AD-7 queued-to-failed/timed-out terminal edges, and persisted run failure plus job failure in one recovery transaction. The architecture edge guard was observed failing when its old AST assumption no longer represented the expanded legal mapping, then upgraded to inspect the explicit mapping.
- 2026-08-21 — Task 5 plan/verification: observed the slow-solve test complete with zero renewals, then added a daemon heartbeat thread around `scheduler.solve`. It waits `max(1, lease_seconds // 3)`, renews through independent runtime transactions, stops in `finally`, and ignores the cancellation carrier. A live 3.1-second solve under a 2-second lease retained epoch 1 and finalized normally.
- 2026-08-21 — Task 6 plan/verification: observed the missing schedule-run event-head contract at collection, then added typed head/replay reads and the SSE route by reusing the shipped conversation transport generator. Cursor precedence, foreign-stream zero-query rejection, maximum-sequence validation, immediate/15-second comment heartbeats, 200-event batches, and one short site transaction per poll remain shared mechanics.
- 2026-08-21 — Task 7 plan/verification: observed the missing polling read contract at collection, then added a site-scoped schedule-run view joining the optional job carrier and exposed it through `GET /schedule-runs/{run_id}`. The route projects only the existing response fields and reuses `_not_found()`.
- 2026-08-21 — Task 8 plan/verification: committed the implementation, confirmed a clean tree, then ran the largest Gate A fixture with one discarded warm-up and three measured ASGI-stream runs. Generated and self-audited the evidence from captured stdout before committing it separately; measured first-event latencies were 14.377 ms, 18.190 ms, and 15.687 ms.

### Completion Notes List

- Task 1 complete: schedule-run streams now use `stream_id = schedule_run_id`; conversation identifiers are nullable without overloading them. Focused tests: 18 passed. Full backend regression from `backend/`: 1085 passed, 2 skipped, 7 deselected.
- Task 2 complete: literal run progress serializes through `ActivityItemOut` with stable status, reason, resource version, occurrence time, and string sequence. Focused tests: 9 passed. Full backend regression: 1086 passed, 2 skipped, 7 deselected.
- Task 3 complete: every ScheduleRun edge emits one monotonic `run.<literal>.v1` event, enqueue replay remains single-effect, and stale/lost transitions write no event. PostgreSQL transition suites: 19 passed. Full backend regression: 1087 passed, 2 skipped, 7 deselected.
- Task 4 complete: exceptions after leasing now terminate both job and run as `failed`/`solver_failed` with `job_execution_failed`, and failed jobs are excluded from future leases. Focused suites: 35 passed. Full backend regression: 1090 passed, 2 skipped, 7 deselected.
- Task 5 complete: solve-time heartbeat renewal keeps the active fencing epoch current without changing cancellation or terminal semantics. Focused suites: 45 passed. Full backend regression: 1092 passed, 2 skipped, 7 deselected.
- Task 6 complete: schedule-run progress is replayable from `Last-Event-ID`/query cursors with no duplicate frames and non-disclosing invalid-cursor handling. Stream/PostgreSQL focused suites: 37 passed. Full backend regression: 1098 passed, 2 skipped, 7 deselected.
- Task 7 complete: polling/manual refresh returns authoritative literal state and the cancellation carrier without adding timestamps or changing authority. Focused API/PostgreSQL tests: 13 passed. Full backend regression: 1100 passed, 2 skipped, 7 deselected.
- Task 8 complete: the committed NFR35 record binds the clean implementation commit and proves all three client-observed first-event deliveries below 5,000 ms (maximum 18.190 ms). Evidence convention/generator suites: 57 passed.

### File List

- _bmad-output/implementation-artifacts/3-5-persist-literal-run-state-and-replay-progress.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/adapters/postgres/schema.py
- backend/adapters/postgres/conversation.py
- backend/adapters/postgres/schedule_run.py
- backend/api/schemas.py
- backend/api/routers/schedule_runs.py
- backend/application/contracts/activity.py
- backend/application/contracts/job_lease.py
- backend/application/contracts/persisted_event.py
- backend/application/ports/schedule_run.py
- backend/application/use_cases/cancel_schedule_run.py
- backend/application/use_cases/create_run_snapshot.py
- backend/application/use_cases/execute_schedule_run.py
- backend/application/use_cases/lease_and_execute_schedule_run.py
- backend/migrations/versions/c4d5e6f7a8b9_widen_persisted_event_and_job_status.py
- backend/tests/test_conversation_contracts.py
- backend/tests/test_cancel_schedule_run.py
- backend/tests/test_cancellation_race_postgres.py
- backend/tests/test_create_run_snapshot.py
- backend/tests/test_enqueue_compute.py
- backend/tests/test_evidence_binding.py
- backend/tests/test_fencing_recovery.py
- backend/tests/test_finalize_schedule_run.py
- backend/tests/test_job_leasing_postgres.py
- backend/tests/test_job_lease_contracts.py
- backend/tests/test_lease_next_job.py
- backend/tests/test_lease_worker.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_schedule_runs_api.py
- backend/tests/test_schedule_run_stream_api.py
- backend/tests/architecture/test_schedule_run_state_machine.py
- backend/engine/governed_adapter.py
- backend/worker/lease_worker.py
