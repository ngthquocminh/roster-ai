---
baseline_commit: 6314b378f4e7247682395c04ee3fe1f520fd5250
---

# Story 3.11: Prove Recovery and Idempotency

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the product team,
we want interruption and replay proven before release,
so that accepted work is never lost, duplicated, or silently rebased by a failure.

## Acceptance Criteria

1. **Given** worker kill, lease expiry, browser reconnect, command replay, cancellation race, stale draft, and conflicting idempotency fixtures **When** recovery tests execute on the Story 2.2 harness **Then** accepted work remains discoverable and every semantic effect occurs at most once **And** the same run/evidence lineage is retained. (NFR6, NFR7) [Source: epics.md:1108-1111]
2. **Given** any recovery or idempotency case above **When** it regresses **Then** release is blocked regardless of aggregate helpfulness **And** the failure names the exact gate and artifact versions. (NFR29) [Source: epics.md:1113-1116]

## Facts This Story Depends On

Named explicitly, per this project's "facts this story depends on" pass (`sprint-status.yaml` action item, epic 1-2, "Story creation adds a 'facts this story depends on' pass"). Every fact below is written down somewhere citable before any Decision below relies on it.

- **AD-6 — Persisted workflow is the recovery boundary [ADOPTED].** "Accepted messages, agent runs, tool calls, jobs, approvals, schedule runs, outcomes, and progress events are committed before acknowledgement. A separately runnable worker advances jobs through compare-and-set transitions. Each lease has owner, expiry, heartbeat, and monotonically increasing fencing epoch; checkpoint/effect commits require the current epoch, while unique effect keys make expired-worker recomputation harmless. Cancellation is persisted and cooperative. Persisted monotonic event sequences feed SSE replay using `Last-Event-ID`; neither process memory nor the stream is authoritative." [Source: `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:78-82`]
- **AD-8 — Idempotent commands and effects [ADOPTED].** "Each mutating HTTP command requires an idempotency key scoped to actor, site, operation, and canonical body hash plus expected resource version. Tool/worker effects use stable `(agent_run_id, tool_call_id)` or job-effect keys. Database uniqueness protects both; a replay returns the original semantic result and a conflicting body fails." [Source: `ARCHITECTURE-SPINE.md:132-136`]
- **AD-9 — Immutable schedule versions and isolated drafts [ADOPTED].** Stale inputs fail closed and require refresh/recompute — this is why `revise_proposal` refuses on scenario-version drift and `reject_proposal` does not. [Source: `ARCHITECTURE-SPINE.md:138-142`]
- **NFR6:** "Worker termination, lease expiry, replay, and recovery must create zero duplicate effects." [Source: `_bmad-output/planning-artifacts/epics.md:85`]
- **NFR7:** "Accepted work must remain discoverable after browser, API, stream, or worker interruption." [Source: `epics.md:87`]
- **NFR29:** "Any regression in authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, or rollback must block release regardless of aggregate helpfulness." [Source: `epics.md:131`] — this story shares NFR29 with almost every other proof story; it is not exclusive owner.
- **`JobStatusV1` is a closed four-member vocabulary:** `queued | leased | completed | failed`, matching `ck_job_queue_status`. [Source: `backend/application/contracts/job_lease.py:11`, verified live at story creation]
- **`MAX_IDEMPOTENCY_KEY_LENGTH = 40`**, bound by `command_idempotency.idempotency_key`'s `String(40)` column, validated in application code rather than left to a raw driver truncation error. [Source: `backend/application/contracts/job_lease.py:21-24`]
- **The AD-7 terminal-status mapping table** (reused verbatim from Stories 3.2/3.10 — do not re-derive):

  | Engine outcome | AD-7 status | Reason | Candidate? |
  |---|---|---|---|
  | OPTIMAL/FEASIBLE, validator passes | `solver_completed` | — | yes, exactly one |
  | OPTIMAL/FEASIBLE, validator fails | `solver_failed` | `hard_constraint_violated` | no |
  | UNKNOWN (round 2, round-1 snapshot present) | `solver_timed_out` | `budget_exhausted` | no |
  | INFEASIBLE | `solver_infeasible` | `model_infeasible` | no |
  | MODEL_INVALID | `solver_failed` | `model_invalid` | no |
  | adapter/port raised | `solver_failed` | specific error code | no |
  | cancellation observed | `solver_cancelled` | `cancelled` | no |

- **`docs/DOMAIN-MODEL.md` does not apply to this story.** This story touches no demand row, metric calculation, or assignment family — it is entirely about job-queue lease/fencing, HTTP idempotency, and SSE replay. Recorded explicitly so nobody re-derives the family/unit rule where it does not belong.
- **`GovernedSchedulerAdapter.solve()` is fully synchronous with no cancellation hook of any kind.** Verified live at story creation (not inherited belief): `backend/engine/governed_adapter.py:269-291` calls `solver.Solve(model)` twice sequentially inside `_solve_lexicographic_governed` (lines 184-256), with no `CpSolverSolutionCallback`, no cross-thread signal, and no polling of `cancellation_requested` anywhere in the module. Its own `SCOPE_CONTROLS` already states this: `"NOT COVERED: cancellation:mid_solve_preemption_owned_by_first_story_raising_wall_time_limit — an in-flight CP-SAT call is not interrupted."` [Source: `backend/engine/governed_adapter.py:53`]

## Decisions

**1. This story ships two small production mechanisms, not zero, because `deferred-work.md` names Story 3.11 as owner of five open items, and "worker kill" cannot be proven non-vacuously without a real killable process.**

- **1a. Build a minimal worker entry-point script, `backend/worker/main.py`.** A poll loop: `while running: outcome = run_once(engine, repository, scheduler, lease_owner=..., lease_seconds=default_lease_seconds(settings)); if outcome is None: sleep(poll_interval_seconds)`. Graceful shutdown on `SIGTERM` (let the in-flight `run_once` call finish, then exit the loop) so a hard `SIGKILL` and a graceful stop are two distinguishable, separately testable behaviors — the former is what leaves a job `leased` for `lease_next_job`'s expiry predicate to reclaim (the actual "worker kill" fixture), the latter is ordinary deploy/restart. **Do not deploy this to Docker/systemd/App Runner in this story** — that packaging and process-supervision is Epic 5/6's concern. This story proves the mechanism recovers correctly when the process dies; it does not stand up a production deployment. Closes `deferred-work.md:402` ("No production worker entrypoint exists"), enables `:396` (NFR35 can be genuinely re-measured against a live worker loop rather than a directly-invoked `run_once`), and gives `:404`/`:426` (concurrency lockout and the "flag set, status not yet moved" window) a real object to test against for the first time.
- **1b. Close `deferred-work.md:330` (orphaned `solver_running` cancellation with no `job_queue` row) by proof, not new code.** Add a real-Postgres test proving the invariant the ledger entry itself already names as "safe today only incidentally": `mark_running`'s `_has_current_epoch` precondition requires a leased job row, so a job-less `solver_running` row is unreachable through any current caller. This is the same move Story 3.5 made for a comparable invariant ("recorded as verified-safe-today rather than defended with new code"). **If the new test finds the invariant does NOT hold, stop and escalate — do not silently patch around a real orphan path.**
- **1c. Do NOT build `deferred-work.md:316`'s mid-solve CP-SAT preemption hook.** The Facts section above confirms `GovernedSchedulerAdapter.solve()` has zero cancellation wiring today. OR-Tools' own documented pattern for interrupting a search (`CpSolverSolutionCallback.stop_search()`, verified via Context7 at story creation) fires only from *inside* a solution callback — i.e. on every improving solution — so a search that finds no improving solution before the wall-time ceiling would never observe a stop signal. That is exactly the "guard that cannot go red" failure mode this project's Epic 1-2 retrospective names as its most expensive pattern (`epic-1-2-retro-2026-08-16.md` §3.2). This story's own frozen AC1 text lists **"cancellation race"** as the fixture — the cooperative, pre/at-boundary case, already fully proven (see Decision 2) — not "mid-solve preemption." The ledger's owner string predates and is broader than the frozen epic text. **Re-point `deferred-work.md:316` again, owner left honestly open** (no story in the current roadmap claims it — the same posture Story 3.10 used for its own Gap 2), rather than silently absorbing new solver-integration scope this story's AC does not require, or silently dropping a named ledger item without comment.

**2. Reuse the existing real-Postgres scaffolds and already-passing tests as the backbone; do not reinvent test infrastructure.** Six of the seven named AC1 failure modes already have a real mechanism *and* existing, currently-passing tests (verified live at story creation, file:line/test-name level):

| Failure mode | Real mechanism | Already covered by |
|---|---|---|
| Worker kill / lease expiry | `workflow.lease_next_job` fencing-epoch reclaim (`backend/migrations/versions/a2b3c4d5e6f7_add_job_queue_and_lease_functions.py:132-176`); `PostgresScheduleRunRepository.lease_next_job` (`backend/adapters/postgres/schedule_run.py:820-857`); heartbeat renewal via `renew_job_lease`, now a real caller inside `execute_schedule_run`'s background thread (`backend/application/use_cases/execute_schedule_run.py:120-151`) | `backend/tests/test_job_leasing_postgres.py`: `test_expired_worker_is_fenced_and_recovered_worker_finishes_once` (:220), `test_a_stale_worker_writes_no_candidate_and_the_current_epoch_writes_exactly_one` (:642), `test_transient_failure_after_lease_stays_leasable_for_recovery` (:1060), `test_fatal_failure_after_lease_is_terminal_and_never_released` (:805) |
| Browser reconnect | `StreamCursorV1`/`parse_stream_cursor` (`backend/application/contracts/stream_cursor.py`), consumed by both `schedule_runs.py:482-489` and `conversations.py:454-476` | `backend/tests/test_schedule_run_stream_api.py` (:128, :144, :157, :170); `backend/tests/test_conversation_stream_api.py` (:191, :266, :279, :294, :365, :407) |
| Command replay | `get_idempotent_result` → body-hash compare → replay-or-conflict, on every mutating use case | `test_job_leasing_postgres.py::test_enqueue_replay_and_rollback_have_exact_row_counts` (:361); `test_cancellation_race_postgres.py::test_concurrent_replay_of_one_idempotency_key_returns_the_stored_result` (:545) |
| Cancellation race | `cancel_schedule_run.py` (cooperative, `SCOPE_CONTROLS` lines 17-23), lock-order-matched against `finalize_run` | `backend/tests/test_cancellation_race_postgres.py` — whole file, 9 tests |
| Stale draft | `ProposalViewV1.stale`, `revise_proposal` raising `StaleProposalError` on scenario-version drift while `reject_proposal` is deliberately permitted while stale (Story 3.1 Decision 7) | `backend/tests/test_conversations_postgres.py:1012-1041`; golden case `backend/evals/golden/scheduling_draft/stale-version.json` |
| Conflicting idempotency (enqueue/proposal routes) | Same body-hash-conflict mechanism as command replay | `test_job_leasing_postgres.py:448`; `test_cancellation_race_postgres.py:172`; `test_cancel_schedule_run.py:269`; `test_enqueue_compute.py:212`; `test_conversations_postgres.py:856,959`; `test_schedule_runs_api.py:625` (API 409 mapping) |

This story's job is **not** to write dozens of new tests duplicating this coverage. Following Story 3.10's own reinterpretation of "runs on the Story 2.2 harness" (its Decision C: reuse the harness's shared, story-agnostic machinery — deterministic-double discipline, `resolve_bindings()`, the dual-track CI pattern — not the `Evaluator`/`AgentRunOutcomeV1` extension point, which fits scriptable LLM turns, not process-kill/lease-timing/HTTP-race scenarios), this story's job is to:
(a) assemble the table above into one deterministic, versioned, NFR27-bound evidence artifact the Release Gate can point to as "recovery/idempotency is proven" (AC2's "names the exact gate and artifact versions"),
(b) close the one identified real coverage gap (Decision 3), and
(c) add the real-process worker-kill fixture Decision 1a's new entry point makes possible for the first time — every test in the table above only ever calls `run_once()` in-process; none of them kills a real separate OS process.

**3. One genuinely new Postgres-level test is owed: conflicting `cancel_schedule_run` idempotency-key replay against a differing `expected_resource_version` under real contention.** Existing tests prove the *design* is version-aware (`manage_proposal.py`'s own comment: "replaying one key against a different expected version is a semantically different command and must conflict") and prove body-hash conflicts for `enqueue_compute`/`manage_proposal`, but no test drives `cancel_schedule_run` itself through a same-key/different-expected-version race at the Postgres layer. Add it to `backend/tests/test_cancellation_race_postgres.py`, reusing that file's own `_key`/`_running_run`/`_wait_for_blocked_backend` helpers rather than inventing new ones.

**4. Evidence file follows the exact Story 3.10 mechanical precedent — no new pattern invented.** New report generator `backend/evals/recovery_idempotency_report.py`, mirroring `backend/evals/repair_correctness_report.py`'s shape: `subprocess.run` each relevant `-m postgres` test node with `timeout=180`, collect every verdict (never raise mid-loop — a report missing a node is a `"failed"` entry, not a crash), reuse `resolve_bindings()` from `backend/scripts/evidence_binding.py` for all eleven NFR27 keys. Evidence path: `evidence/story-3.11/recovery-idempotency.json`. `dataset` = this story's own fixture/test set, bound through the *existing* generic non-golden artifact binding path Story 3.10 already added to `resolve_bindings()` — do not add a second such path. `scenario` = `"not applicable"` unless a real `data/**` Gate A fixture is genuinely touched (it should not be — nothing here needs the frozen fixture). Follow `docs/EVIDENCE-CONVENTION.md` exactly: commit code → confirm clean tree → run the measurement → generate via `resolve_bindings()` → run `test_evidence_convention.py` → commit evidence separately.

**5. Zero new `backend/evals/golden/**` cases, matching Story 3.10's Decision D precedent exactly.** None of the seven failure modes are LLM-scriptable turns — `GoldenCase` requires `prompt` + `scripted_turns` against a deterministic model double (`backend/evals/cases.py`), and process-kill/lease-timing/HTTP-replay/DB-race scenarios have no agent or model surface at all. `backend/evals/README.md`'s "Stories 2.9, 3.10–3.12, and 4.5–4.6 contribute their own real cases" line is restated as unmet by this story for the same structural reason Story 3.10 already recorded against itself — not silently ignored. NFR28's floor stays wherever Story 3.10 left it (26 files at last measurement, 5 of the ≥10 consequential/prohibited floor) — **re-derive, do not cite this number as current.**

## Honest Gaps

- **(a) Mid-solve CP-SAT preemption remains genuinely open after this story.** Decision 1c re-points `deferred-work.md:316` with the owner left open. If a future story needs true in-flight-solve interruption, it must design a polling mechanism that does not depend on an improving-solution callback (e.g., a fixed-interval `threading.Timer` calling a solver-side stop, verified thread-safe against the installed OR-Tools version) — this story does not attempt it.
- **(b) The strength of the "worker kill" proof depends on Decision 1a actually landing.** A `run_once()`-only in-process test (what every existing test in Decision 2's table already does) proves fencing/reclaim SQL correctness but never proves a real OS process death recovers cleanly. If Decision 1a's entry point turns out too large for this story's budget, do not silently claim AC1's "worker kill" clause is proven the strong way — re-annotate the gap honestly and name the real scope reduction, the same posture Story 3.1/3.10 used for their own honest gaps.
- **(c) Real production `get_locks`/`get_baseline_assignments` supply remains empty.** This is Story 3.10's own Gap 2, unrelated to this story's scope, still open, owner still unassigned in the roadmap. Not this story's to close; do not attempt it here.

## Traps

The quietest first:

1. **A worker-kill test that only ever calls `run_once()` in-process "proves" recovery without ever killing a process.** The new entry-point test (Task 3) must `SIGKILL` a real subprocess mid-lease and assert the DB-level fencing recovers it — not merely assert `run_once` returns cleanly twice in the same test process.
2. **Silently absorbing `deferred-work.md:316`'s mid-solve-preemption scope because the ledger's owner string literally says "Story 3.11."** The ledger entry was written 2026-08-21, before this story's frozen AC text existed and independent of it. Cite the actual AC (epics.md:1108-1111), not the ledger string, when they disagree; escalate the mismatch (Decision 1c) rather than quietly building unrequested solver logic or quietly dropping a named ledger item without comment.
3. **Treating "conflicting idempotency fixtures" as fully covered by inherited enqueue/proposal test coverage** without adding the one identified `cancel_schedule_run` gap (Decision 3). The AC's Given clause names cancellation race and conflicting idempotency as two separate items; neither may borrow the other's proof.
4. **Padding the golden dataset toward `evals/README.md`'s stated per-story expectation.** Decision 5 forbids this explicitly, matching Story 3.10's own precedent almost verbatim (`epics.md:1527`: "never pad the dataset to reach it").
5. **Hand-constructing a killed-worker scenario (mocking process death) instead of driving it through a real OS-level kill.** The same "hand-construct vs. drive through the real seam" trap Story 3.10's Decision B named for `RunSnapshotV1.preserved_locks`; a mocked death proves nothing about the real fencing/reclaim SQL this story exists to prove.
6. **Reusing `evidence/story-3.5/nfr35-first-run-event.json`'s "cannot fail by construction" scope-limit note verbatim without re-checking it.** That framing was set before a live worker loop existed. If Decision 1a lands, a genuine end-to-end measurement (API accept → real worker picks it up → `run.running.v1`) may no longer share that boundary — verify before copying the note forward.

## What This Story Is, And Is Not

| Area | This story |
|---|---|
| New capability, route, or contract | None |
| New migration | None — the worker entry point is a script, not a schema change; confirm zero new migration files at Task 9 |
| Mid-solve CP-SAT preemption | Not this story (Decision 1c) — re-pointed, owner left open |
| Real production `get_locks`/`get_baseline_assignments` supply | Not this story (Story 3.10's Gap 2) — still open, no owner |
| New `backend/evals/golden/**` cases | Zero, and that is correct (Decision 5) |
| Frontend changes | None expected — confirm a zero-line `frontend/` diff at Task 9 |
| Production worker deployment (Docker/systemd/App Runner) | Not this story — Epic 5/6's operational concern. This story proves the recovery mechanism via test, not via a deployed daemon |
| Frontend/browser proof of the repair journey | Story 3.12 |

## Tasks / Subtasks

- [x] **Task 1 — Re-derive baselines before attributing any failure (AC1, AC2)**
  - [x] Confirm current HEAD is clean and note the commit hash (do not trust this story's own cited numbers — re-run and record fresh: backend default suite pass/skip/deselect counts, `-m postgres` pass count, frontend file/test counts, golden dataset file count and consequential+prohibited count).
- [x] **Task 2 — Build the minimal worker entry point (AC1, Decision 1a)**
  - [x] Add `backend/worker/main.py`: poll loop calling `run_once(engine, repository, scheduler, lease_owner=..., lease_seconds=default_lease_seconds(settings))`; sleep on `None` outcome; graceful shutdown on `SIGTERM`/`SIGINT` that lets an in-flight `run_once` call finish before exiting.
  - [x] Unit test the loop's shutdown behavior directly (no subprocess needed for pure loop logic — signal handling and the run/sleep branch).
- [x] **Task 3 — Real-process worker-kill test (AC1, Decision 1a, Trap 1)**
  - [x] Spawn `backend/worker/main.py` as a real subprocess against `governed_postgres_engine`; queue a job; `SIGKILL` the process mid-lease (use a deliberately slow fixture double to guarantee the kill lands mid-lease, not before or after).
  - [x] Assert the job is later reclaimed by `lease_next_job`'s expiry predicate and reaches a terminal outcome exactly once (candidate row count == 1, no duplicate `schedule_version`, fencing epoch advanced).
  - [x] Demonstrate this test observed RED first (temporarily skip the kill, or weaken the fencing-epoch check) before finalizing — this repo's established red-then-green convention (Story 2.1 Task 9 and every architecture guard since); record the observation in Completion Notes.
- [x] **Task 4 — Orphan-safety invariant proof for `deferred-work.md:330` (AC1, Decision 1b)**
  - [x] Add a real-Postgres test proving a job-less `solver_running` row is unreachable through any current caller of `mark_running`.
  - [x] If the invariant does not hold, STOP and escalate rather than patching around it silently.
- [x] **Task 5 — New conflicting-idempotency test for `cancel_schedule_run` (AC1, Decision 3)**
  - [x] Add a test to `test_cancellation_race_postgres.py`: same idempotency key, differing `expected_resource_version`, under real contention — assert `IdempotencyKeyConflictError`/409, reusing the file's own `_key`/`_running_run`/`_wait_for_blocked_backend` helpers.
- [x] **Task 6 — Assemble the recovery/idempotency proof (AC1)**
  - [x] For each of the seven AC1 failure modes, enumerate which existing test(s) (Decision 2's table) plus which new test(s) (Tasks 3-5) prove it. Do not write redundant tests duplicating already-passing coverage.
  - [x] Re-run each enumerated node individually to confirm still-green against this story's baseline.
- [x] **Task 7 — Re-measure NFR35 against the live worker loop, if Decision 1a landed (AC1, AC2, Trap 6)**
  - [x] Extend or supplement `evidence/story-3.5/nfr35-first-run-event.json`'s own re-measurement invitation (`deferred-work.md:396`) using the new entry point in the loop; confirm whether the "cannot fail by construction" scope-limit framing still holds, and update the note if it does not.
- [x] **Task 8 — Generate evidence (AC1, AC2, Decision 4)**
  - [x] Build `backend/evals/recovery_idempotency_report.py` mirroring `repair_correctness_report.py`'s shape.
  - [x] Commit code on a clean tree, run the measurement, generate `evidence/story-3.11/recovery-idempotency.json` via `resolve_bindings()`, run `test_evidence_convention.py`, commit evidence separately per `docs/EVIDENCE-CONVENTION.md`.
- [ ] **Task 9 — Regression and Gate A**
  - [ ] Full backend suite (default + `-m postgres`); confirm zero new migration files (`alembic check`); confirm zero-line `frontend/` diff; re-run the evidence convention suite; re-run Gate A and record `gate_a_passed`/`blocking`.
- [ ] **Task 10 — Ledger and sprint-status update**
  - [ ] Close `deferred-work.md:402`, `:404` (worker entry point lands); close `:330` (proven-safe invariant, Task 4); close or update `:396` (NFR35 re-measured or scope re-confirmed, Task 7); re-annotate `:316` with owner left open per Decision 1c — do not delete the entry, re-point it.
  - [ ] Add a dense creation/completion note to `sprint-status.yaml` matching this project's established convention (see Stories 3.1, 3.5, 3.6, 3.10 for shape).

## Dev Notes

- This is a backend-only story. No frontend route, component, or hook is expected to change (confirm at Task 9).
- Reuse fixtures/helpers rather than duplicating them: `governed_postgres_engine` (`backend/conftest.py:84`), `test_job_leasing_postgres.py`'s `_only_leasable`/`_runtime` helpers (already imported directly by `test_repair_correctness_postgres.py:52` — follow that exact import pattern rather than re-implementing), and `test_cancellation_race_postgres.py`'s `_key`/`_running_run`/`_wait_for_blocked_backend` helpers.
- Every new Postgres-marked test file must set `pytestmark = pytest.mark.postgres` at module scope, matching every existing `*_postgres.py` file.
- `models.ALLOW_MODEL_REQUESTS = False` module-scope discipline (Story 2.2) does not apply here — this story has no model-facing surface at all, unlike 3.10 which still touched the AgentRuntime evaluation fixture indirectly. Do not import or extend `backend/evals/doubles.py`.

### Project Structure Notes

- New files expected: `backend/worker/main.py`, `backend/evals/recovery_idempotency_report.py`, new test(s) added to `backend/tests/test_cancellation_race_postgres.py` and a new orphan-invariant test file (or added to an existing `*_postgres.py` file — dev's call, follow existing file boundaries by topic), `evidence/story-3.11/recovery-idempotency.json`.
- No new directories, no new top-level packages.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1100-1116`] — Story 3.11 text (this story's frozen AC).
- [Source: `_bmad-output/planning-artifacts/epics.md:85-131`] — NFR6, NFR7, NFR29 exact text.
- [Source: `_bmad-output/planning-artifacts/epics.md:1508-1527`] — Release Gate table and NFR28 dataset-floor re-verification caveat.
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:78-82,132-136,138-142`] — AD-6, AD-8, AD-9.
- [Source: `docs/EVIDENCE-CONVENTION.md`] — evidence generation order and `resolve_bindings()` requirement.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md:316,330,396,402,404,406,416,426`] — every ledger item this story closes or re-points.
- [Source: `_bmad-output/implementation-artifacts/3-10-prove-repair-correctness.md`] — previous story; established the evidence-generation pattern, the "runs on the Story 2.2 harness" reinterpretation, and the seeded-reader-swap-back red-then-green discipline this story reuses.
- [Source: `backend/worker/lease_worker.py`, `backend/application/use_cases/lease_and_execute_schedule_run.py`, `backend/application/use_cases/cancel_schedule_run.py`, `backend/application/use_cases/enqueue_compute.py`, `backend/application/use_cases/manage_proposal.py`, `backend/adapters/postgres/schedule_run.py`, `backend/application/contracts/job_lease.py`, `backend/application/contracts/stream_cursor.py`, `backend/engine/governed_adapter.py`] — mechanisms this story proves or extends.
- [Source: `backend/tests/test_job_leasing_postgres.py`, `backend/tests/test_cancellation_race_postgres.py`, `backend/tests/test_conversations_postgres.py`, `backend/tests/test_schedule_run_stream_api.py`, `backend/tests/test_conversation_stream_api.py`] — existing coverage this story assembles rather than duplicates.
- [Source: `backend/evals/repair_correctness_report.py`, `backend/scripts/evidence_binding.py`] — evidence report generator precedent to mirror.
- Baselines at Story 3.10's completion (`3-10-prove-repair-correctness.md`, post-review): backend default suite 1238 passed / 2 skipped / 7 deselected; `-m postgres` 91 passed; frontend 77 files / 521 tests; golden dataset 26 files (5 of ≥10 consequential/prohibited). **Re-derive at Task 1 — do not cite these as current.** Current repo HEAD at story creation: `5b87655` (clean tree, merge of Story 3.10 into `main`).

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Establish a clean, freshly measured baseline before changing behavior.
- Add the worker loop through red-green-refactor unit coverage, then prove hard-process death and lease reclamation through PostgreSQL.
- Add only the two missing invariant/idempotency tests identified by the story, reuse all inherited recovery nodes, and bind the complete proof into one release-blocking report.
- Re-measure NFR35, run all regression and release gates, then reconcile the deferred-work ledger and story records.

### Debug Log References

- 2026-08-25 baseline at `6314b378f4e7247682395c04ee3fe1f520fd5250`: backend 1238 passed / 2 skipped / 7 deselected; PostgreSQL 91 passed; frontend 77 files / 521 tests; golden dataset 26 files, including 5 consequential/prohibited cases.
- 2026-08-25 Task 2 RED: `tests/test_worker_main.py` failed collection because `worker.main` did not exist; GREEN: 3 focused tests passed, then backend regression 1241 passed / 2 skipped / 7 deselected.
- 2026-08-25 Task 3 RED: letting the subprocess finish instead of killing it produced `recovered is None`; GREEN: hard process termination left the leased/running row reclaimable and the focused PostgreSQL proof passed.
- 2026-08-25 Task 4 invariant proof: the existing `_claim_epoch`/`_has_current_epoch` fence rejected `mark_running` after its job row was removed; backend regression 1243 passed / 2 skipped / 7 deselected.
- 2026-08-25 Task 5 RED/GREEN: the first contention fixture named the wrong table schema and failed before the behavioral assertion; corrected to the live `schedule_run` table, then the focused proof and backend regression passed (1244 passed / 2 skipped / 7 deselected).
- 2026-08-25 Task 6: ten exact recovery/idempotency nodes were executed in ten isolated pytest processes; all passed.
- 2026-08-25 Task 7 live-worker NFR35 measurement: 59.155 ms, 57.947 ms, and 118.579 ms from committed queue acknowledgement to persisted `run.running.v1`, all below 5000 ms. This path includes process polling, lease acquisition, and the queued-to-running transition, so Story 3.5's narrower queued-event "cannot fail by construction" note does not apply.
- 2026-08-25 Task 8 clean measurement bound to `8901cf4d9d31fd829a376db0fb04e9c0a0a8987d`: all 11 exact gates passed; recorded live-worker runs were 56.611 ms, 58.084 ms, and 122.426 ms; evidence convention 67 passed. Code and evidence were committed separately (`8901cf4`, `96e2743`).

### Completion Notes List

- ✅ Task 1: re-derived all requested baselines from a clean tree; no pre-existing regression was found.
- ✅ Task 2: added a separately runnable, dependency-composed worker poll loop with cooperative SIGTERM/SIGINT shutdown and direct loop/signal coverage.
- ✅ Task 3: killed the real worker subprocess while its job was leased/running, forced lease expiry, and proved a new epoch completed exactly one candidate on the original run/evidence stream; full backend regression passed (1242 passed / 2 skipped / 7 deselected).
- ✅ Task 4: proved a job-less `solver_running` row is unreachable through `mark_running`; no production workaround was required.
- ✅ Task 5: proved a same-key cancellation replay with a differing expected version is rejected after an observed real PostgreSQL lock wait, preserving one idempotency row and one cancellation effect.
- ✅ Task 6: assembled the seven named AC1 failure modes into exact, independently rerunnable proof gates without padding the golden dataset.
- ✅ Task 7: supplemented Story 3.5's read-path latency evidence with a real worker-loop measurement; full backend regression passed (1245 passed / 2 skipped / 7 deselected).
- ✅ Task 8: generated the release-blocking, exact-gate recovery/idempotency report with all NFR27 bindings and separately committed evidence.

### File List

- _bmad-output/implementation-artifacts/3-11-prove-recovery-and-idempotency.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/tests/fixtures/worker_process.py
- backend/evals/recovery_idempotency_report.py
- backend/tests/test_cancellation_race_postgres.py
- backend/tests/test_job_leasing_postgres.py
- backend/tests/test_recovery_idempotency_report.py
- backend/tests/test_worker_main.py
- backend/tests/test_worker_process_recovery_postgres.py
- backend/worker/main.py
- evidence/story-3.11/recovery-idempotency.json
