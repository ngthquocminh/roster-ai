---
baseline_commit: 37371d3e146f99d0af5b6cb5c782cfc98c3e9de9
---

# Story 3.2: Produce a Deterministic Candidate from an Immutable Snapshot [Technical Enabler]

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the scheduling platform,
we want candidates constructed only by the deterministic scheduler from an immutable frozen snapshot,
so that once Story 3.6 makes optimization startable, no accepted assignment or feasibility claim can
originate from model prose.

**Planner-visible outcome: none.** No route, no capability, no frontend file. Accepted through
seeded snapshot and solver-adapter tests. `frontend/**` must be a **zero-line diff**.

**Depends on, and consumes:** Story 3.1's `ProposalV1`, `DraftConstraintV1` (the five kinds), the
`proposal`/`proposal_version` tables and `ProposalRepository`; Story 1.1's checksummed
`scenario_version` rows; Story 1.4/1.5's `ScenarioProjectionV1` and `EvidenceRefV1`; Story 2.7's
`application/contracts/canonical.py` digest helper.

**Unblocks:** Story 3.3 (leases a job against an existing `schedule_run`), Story 3.5 (emits events
for the state machine this story's status column encodes), Story 3.6 (the run command), Story 3.8
(`ComparisonV1` over this story's `ScheduleVersionV1`), Epic 4 (the baseline pointer moves to a
candidate this story created).

**Scope summary:** One migration (four tables). Four new contracts. One application port and its
`engine/` adapter. Two use cases. **No new dependency** — `ortools==9.11.4210` is already a
repository lock. No router. No capability. No evidence file. No frontend change.

**This story is the first in the repository to:**

1. reach `backend/engine/` from a **governed** path. Verified by exhaustive grep at
   `37371d3`: the only non-test importers of `engine.base` are `api/deps.py:34`,
   `api/routers/runs.py:11`, `services/run_service.py:21`, `run.py:10` and
   `scripts/calibrate_penalties.py` — all legacy SQLite or CLI. Nothing under `application/**` or
   `adapters/**` imports `engine` at all;
2. create the **`ScheduleRun` / `ScheduleVersion`** aggregates. `schema.py` at `37371d3` defines
   exactly `organization`, `site`, `scenario`, `scenario_version`, `fixture_lineage`,
   `evidence_reference`, `app_user`, `membership`, `session_index`, `conversation`, `message`,
   `agent_run`, `persisted_event`, `proposal`, `proposal_version`, `command_idempotency`,
   `login_handshake`. No run, snapshot, or schedule-version table exists;
3. produce a **non-null `EvidenceRefV1.producing_run_version`**. The single production producer,
   `application/grounding/calculators.py:243`, hardcodes `producing_run_version=None`;
4. give `baseline_schedule_version` a **real value supply** (`deferred-work.md:185` records the
   correction that both current producers return literal `None`). This story creates the aggregate;
   **Story 4.3 still owns the pointer move** — see Decision 7.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. Every rule below is recorded somewhere
citable; none of it may be re-derived from adapter code (retro §3.2 — the single most expensive
pattern of Epics 1–2).

| Fact | Where it is written |
|---|---|
| Demand family → unit mapping; `outbound`/`inbound` are `volume`, `indirect` is `headcount`; assignments carry **no** family; route a question by the **unit the answer is measured in** | `docs/DOMAIN-MODEL.md` §1–§3 |
| `volume` → minutes needs `QualificationRefV1.rate`, which is **per worker per task** — so it is a function of *who performs the work*, i.e. an assignment, and therefore **this story's** to supply | `docs/DOMAIN-MODEL.md` §4; `deferred-work.md:211` |
| `shortfall_minutes` returns only when four conditions hold, all four naming Epic 3 | `docs/DOMAIN-MODEL.md` §4 ("Before `shortfall_minutes` can return") |
| CP-SAT alone constructs or validates an accepted schedule; the model proposes typed intent only | AD-2 (`ARCHITECTURE-SPINE.md:54-58`); AR2 (`epics.md:148`) |
| Domain and application code must not import FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire, or concrete providers | AD-1 (`ARCHITECTURE-SPINE.md:48-52`) |
| Proposals, solver inputs and schedule versions are **immutable**; the baseline is a versioned pointer; stale inputs **fail closed without silent rebasing** | AD-9 (`ARCHITECTURE-SPINE.md:138-142`) |
| `RunSnapshotV1`'s required shape: scenario checksum/version, baseline/proposal versions, locks/constraints/objectives, solver name/config/seed/limit, component versions, accepted time, input evidence refs | AD-20 *Normative contract minimums* (`ARCHITECTURE-SPINE.md:323`) |
| `ScheduleVersionV1`'s required shape: schedule/run/scenario/proposal IDs and versions, feasible solver status, immutable `AssignmentV1[]`, `MetricSetV1`, `ConstraintResultV1[]`, warnings, evidence refs | AD-20 (`ARCHITECTURE-SPINE.md:327`) |
| `MetricSetV1`: interval/function coverage required/served minutes, overtime minutes, total cost, objective components, assignment/member counts | AD-20 (`ARCHITECTURE-SPINE.md:325`) |
| `ConstraintResultV1`: constraint ID/type, **hard-or-soft class**, satisfied flag, measured value/limit/unit, contributing assignment/evidence refs | AD-20 (`ARCHITECTURE-SPINE.md:326`) |
| `AssignmentV1`: assignment ID, worker/task/shift IDs, integer start/end minutes, **qualification refs, lock/source refs** | AD-20 (`ARCHITECTURE-SPINE.md:324`) — see Gap 3 |
| The `ScheduleRun` graph is closed and separate from `AgentRun`; **only feasible `ScheduleRun.completed` may reference a candidate `ScheduleVersion`**; wall-time exhaustion is `timed_out`, other ceiling exhaustion is `failed` with stable `budget_exhausted` | AD-7 (`ARCHITECTURE-SPINE.md:84-131`); AR7 (`epics.md:153`) |
| Budgets are explicit positive **application** configuration with safe defaults and are never chosen by the model | AD-7 (`ARCHITECTURE-SPINE.md:90`); NFR16 (`epics.md:107`) |
| Schedule intervals are integer-minute half-open `[start_minute, end_minute)` offsets from a UTC `horizon_start`; **only the solver adapter converts to float hours** | AD-20 (`ARCHITECTURE-SPINE.md:208, 255`) |
| Contract hashes are SHA-256 over RFC 8785 canonical JSON, carrying algorithm + schema version | AD-20 (`ARCHITECTURE-SPINE.md:208`); *Consistency Conventions* |
| Application calculators produce **or verify** every numerical claim against immutable snapshots; missing / unauthorized / version-mismatched evidence are **distinct** failures and never retarget | AD-11 (`ARCHITECTURE-SPINE.md:150-154`) |
| Atomic bundle `complete-compute = terminal run + evidence refs + event, plus candidate schedule version **only** for a feasible completed result`; only an application orchestrator crosses owners | AD-22 (`ARCHITECTURE-SPINE.md:216-220`) |
| Scheduling owns proposals, schedule runs, schedule versions and the baseline pointer; Workflow owns jobs and persisted events | AD-22 *Aggregate ownership* (`ARCHITECTURE-SPINE.md:401-412`) |
| Migration role rules: NOLOGIN owner, forced RLS on tenant tables, transaction-local trusted actor/site, narrowly granted SECURITY DEFINER | AD-23 (`ARCHITECTURE-SPINE.md:228-232`) |
| No hand-typed evidence file; commit code → measure → generate → commit evidence separately | `docs/EVIDENCE-CONVENTION.md` |
| Manual assistive-technology verification is out of scope; automated coverage is the recorded bar | `EXPERIENCE.md:196` |
| Every new guard must be **observed failing** with its structural assertion removed | retro §6.1 action A2 |

**Three rules this story needed and found unwritten are raised in Gaps 1–3 rather than assumed.**

---

## Eight decisions were made at story creation — do not re-litigate them

### Decision 1 — The snapshot freezes an **identity plus a checksum**, not a copy of the scenario

`RunSnapshotV1` carries `scenario_version_id` **and** `checksum_algorithm` /
`checksum_schema_version` / `checksum_digest`, exactly as `EvidenceRefV1` already does
(`application/contracts/evidence_ref.py:31-43`). It does **not** embed the fixture payload.

Why this satisfies AC1's "the model cannot alter the snapshot after acceptance" better than a copy
would: `scenario_version` is append-only and its digest is a CHECK-constrained column
(`schema.py:134-145`), so an identity + digest is *already* immutable by construction, and the
solver adapter **re-verifies the digest before building the model**. A copied payload would need its
own immutability proof and would double a 1547-demand-row fixture into every run.

**Rejected alternative:** embedding `ScenarioProjectionV1` in the snapshot. It cannot work — see
Gap 1: the projection carries no shift templates and no wage rates, so a `SchedulingProblem` cannot
be built from it.

### Decision 2 — The solver adapter reads the **raw checksummed fixture payload**, through a port, and is the only place hours exist

`scenario_version.payload` is the raw fixture JSON (`Team Member`, `Shift Schedule Template`,
`EBA Grade Rate`, …), canonicalized at import (`adapters/postgres/fixture_history.py:121`). The
normalized projection is a *read* over it (`_normalize_tasks`, `_normalize_workers`,
`_normalize_demand` in `adapters/postgres/scenario_projection.py`), not a replacement for it.

So the chain is:

```
application/use_cases/execute_schedule_run.py
  → application/ports/scheduler.py :: SchedulerPort.solve(snapshot) -> SolverOutcomeV1
      → engine/governed_adapter.py            (the ONLY module that may import ortools indirectly)
          → SolverInputSource.load(scenario_version_id, expected_digest) -> raw payload
          → ingest.input_adapter.build_problem(payload) -> SchedulingProblem   (hours appear here)
          → engine.base.create_engine("cpsat").solve(problem, SolverConfig(...))
          → translate SolveResult -> SolverOutcomeV1                            (hours end here)
```

`SolverOutcomeV1` is minute-based and OR-Tools-free. `application/**` never sees `SolveResult`,
`SchedulingProblem`, `ScheduleRow`, or a float hour. That is AC2's "domain/application code remains
independent of OR-Tools types" made structural rather than incidental, and it is asserted by a new
`tests/architecture/test_solver_boundaries.py` (Task 9).

**Rejected alternative:** having the application load the payload and pass it to the port. It puts a
fixture-shaped `dict[str, Any]` into an application signature, which is the untyped seam AD-1 exists
to prevent, and it would make the digest re-verification the application's job in a layer that
cannot re-derive it.

### Decision 3 — AC3's "recomputable" is delivered by an **application calculator over the frozen assignments**, not by re-solving

AC3's second clause — "all numerical result fields are recomputable from the frozen snapshot and
evidence" — has two possible readings, and only one of them is achievable.

**The reading this story implements** (AD-11's, verbatim: "Application calculators produce or verify
every numerical claim … against immutable snapshots"): `MetricSetV1` and `ConstraintResultV1[]` are
computed by `application/scheduling/candidate_metrics.py` from **`AssignmentV1[]` + the frozen
snapshot's demand and worker facts** — never read off the solver's own internal variables. The
solver returns assignments; the application derives every number. A test recomputes the whole
`MetricSetV1` from the persisted candidate alone and asserts equality.

**The reading this story explicitly does NOT claim:** that re-running CP-SAT on the same snapshot
returns a bit-identical assignment set. It cannot be claimed under the current configuration — see
Decision 4.

Why this matters beyond wording: computing metrics from `builder.unmet_vol` / `builder.coverage_terms`
(which `engine/cpsat/engine.py:63-110` does today for the legacy path) would make AC3's guard
**circular** — the solver would be verifying itself, and the assertion could not go red if the
solver were wrong. That is retro §3.1's dominant failure mode in its most expensive form.

### Decision 4 — Governed runs default to CP-SAT's **reproducible** configuration, and the trade is measured, not assumed

The repository's current defaults are `num_workers=8`, `seed=42`, `time_limit_s=30.0`
(`engine/base.py:14-16`) applied through `solver.parameters.max_time_in_seconds`
(`engine/cpsat/objective.py:46-48`). Verified against the OR-Tools source: with `num_workers > 1`
CP-SAT runs a **portfolio** of subsolvers (`cp_model_solver.cc` — `SolveCpModelParallel`), and
`max_time_in_seconds` is wall-clock, so which subsolver wins depends on thread timing and machine
load. `max_deterministic_time` exists precisely to remove that: *"limits the solve to a deterministic
time budget … based on solver operations rather than CPU clock, making solves reproducible regardless
of machine load"* (`ortools/sat/sat_parameters.proto`, field 67); `ortools/util/time_limit.h` states
*"the deterministic limit is used to ensure reproductibility"*.

**Decision:** the governed path adds a `GovernedSolverConfigV1` whose defaults are
`num_search_workers=1` and a `max_deterministic_time` ceiling, with `max_time_in_seconds` retained
as a wall-clock backstop. All four values are frozen into `RunSnapshotV1` (AD-20 requires "solver
name/config/seed/limit").

**The trade is measured at the Phase B checkpoint, not guessed.** Task 6 runs both configurations
against `data/sample_tiny_input.json` and reports six numbers (round-1 unmet hours, round-2 cost,
wall seconds, status, assignment count, scheduled members) for each. If single-worker is materially
worse, that is recorded with numbers in `SCOPE_CONTROLS` and the default is revisited with evidence —
it is not silently traded away, and it is not left as an open question for the reviewer.

**`SolverConfig`'s existing defaults do not change.** `engine/base.py` is consumed by the legacy
SQLite path and five test modules; the governed configuration is a separate value object translated
at the adapter boundary.

### Decision 5 — Hard-constraint validation is an **independent re-check over the assignments**, and it is what gates candidate creation

AC3's first clause: "every deterministic hard constraint and preserved lock passes **before** one
immutable candidate `ScheduleVersionV1` is created". The verified structural hard constraints in the
CP-SAT model (`engine/cpsat/builder.py`) are exactly six:

| # | Hard constraint | Built at |
|---|---|---|
| 1 | a task is assigned only inside a selected shift | `builder.py:222` |
| 2 | at most one task per working slot | `builder.py:235` |
| 3 | a selected shift is never empty | `builder.py:237` |
| 4 | a roster window holds exactly one shift (with unfill slack); an availability window at most one | `builder.py:263, :265` |
| 5 | per-employment-type max shifts **per day** | `builder.py:275` |
| 6 | per-employment-type weekly effective-hours cap, and a minimum gap between two shifts | `builder.py:278, :286` |

Plus one generation-time invariant: task variables exist only for tasks the member is **qualified**
for (`builder.py:192`).

`application/scheduling/hard_constraints.py` re-checks all seven **from `AssignmentV1[]` plus the
snapshot's worker facts**, with no CP-SAT object in scope. A violation raises and the run finalizes
`solver_failed` with reason `hard_constraint_violated` — **no candidate row is written**.

**A2 compliance is non-negotiable here:** each of the seven checks must be observed failing against a
deliberately corrupted assignment set (Task 8 supplies seven fixtures, one per check). A validator
that re-reads the model it is validating is the single most likely thing to ship green and prove
nothing.

### Decision 6 — The five proposal constraint kinds are **soft**, and `ConstraintResultV1.class` says so honestly

Verified: all five kinds Story 3.1 declared (`set_min_workers_per_task`, `scale_demand`,
`lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours`) are applied as **round-2 penalty
terms only** (`engine/cpsat/builder.py:334-417`), each with bounded slack, and round 1 is locked
before round 2 is minimised (`objective.py:63-65`). The builder's own comment states the guarantee:
*"an override can therefore never make the solve infeasible"*.

So each `DraftConstraintV1` becomes exactly one `ConstraintResultV1` with `constraint_class="soft"`,
`satisfied` measured post-solve from the assignments, and a `measured_value`/`limit`/`unit` triple.
The seven structural checks of Decision 5 become `ConstraintResultV1` entries with
`constraint_class="hard"`.

**Do not promote a proposal constraint to a hard constraint in this story.** FR9's safety rule —
NL-derived constraints are soft and can never make a solve infeasible — is a product invariant, not a
solver limitation, and AC3 says hard constraints must *pass*, not that proposal constraints must
*become* hard.

### Decision 7 — This story creates the `schedule_version` **aggregate**; Story 4.3 still owns the **pointer**

`ScheduleVersionV1` rows are created here. The `site.baseline_schedule_version_id` pointer, its move,
and its approval gate are Epic 4's (AD-10; `epics.md#Story-4.3`). Until then
`ScenarioOverviewV1.baseline_schedule_version` continues to return `None` and
`RunSnapshotV1.baseline_schedule_version` records that truthfully.

**Consequence to state plainly and not paper over:** a candidate produced by this story has no
baseline to be a candidate *against*. `ComparisonV1` is Story 3.8's and needs a baseline that does not
exist yet; that is 3.8's problem to raise, not this story's to pre-solve. Do **not** create a synthetic
baseline row to make a comparison demonstrable.

### Decision 8 — Status is persisted here; **events are not**

AD-7's `ScheduleRun` graph becomes a CHECK-constrained `status` column plus compare-and-set
transitions on `schedule_run`. Persisted events, SSE replay and the reconnect contract stay Story
3.5's.

This is not a preference — it is **structurally forced**. `persisted_event` at `37371d3` declares
`conversation_id` and `agent_run_id` `NOT NULL` with FKs, plus
`CheckConstraint("stream_id = conversation_id", name="ck_persisted_event_stream_is_conversation")`
(`schema.py:309-329`). A schedule run has no conversation until Story 3.6 and no agent run at all, so
a schedule-run event **cannot be inserted today** without widening that table — which is Story 3.5's
contract change, made against its own ACs.

`complete-compute`'s "+ event" clause (AD-22) is therefore recorded as `NOT COVERED` in
`SCOPE_CONTROLS` with Story 3.5 named as its owner, in the same form Story 2.6 used for
`AuditEnvelopeV1` and Story 3.1 used for the absent solver.

---

## Three honest gaps, raised rather than papered over

### Gap 1 — The normalized projection **cannot** build a `SchedulingProblem`

Measured at `37371d3` by exhaustive grep: the strings `ShiftTemplate`, `Shift Schedule Template`,
`EBA Grade Rate` and `wage` appear **nowhere** under `backend/adapters/**` or
`backend/application/**`. `ScenarioProjectionV1` has no shift-template group at all, and `WorkerV1`
(`application/contracts/scenario_projection.py:73-82`) carries `contracted_hours` but **no wage
rate**.

`SchedulingProblem` requires `templates: List[ShiftTemplate]` (`domain/problem.py`) and
`Member.wage_per_hour` (`domain/types.py`), both of which `ingest/input_adapter.py` reads from the
raw fixture (`Shift Schedule Template` + `Shift Schedule Template Break`; `EBA Grade Rate` filtered
to `RateType == "base rate"`, averaged as a fallback).

**Required posture:** Decision 2's `SolverInputSource` port over the raw checksummed payload. Do
**not** extend `ScenarioProjectionV1` with templates and wages to route the solver through it — that
is a Story 1.4-owned contract change, it would widen the planner-visible Scenario Data surface with
fields no AC asks for, and `data/contract/**` digests are Gate A bound (commits `7355492`, `1d32035`
exist because those bytes are load-bearing). Record the divergence in `SCOPE_CONTROLS` as
`inputs:solver_reads_raw_fixture`.

### Gap 2 — `MetricSetV1.overtime_minutes` has no source in the engine, and the fixture's per-type caps are vacuous

Two measured facts, both of which will otherwise be discovered mid-implementation:

**(a) Overtime does not exist in the engine.** Grep for `overtime` across `backend/**` returns one
hit — a comment in `config/constants.py:82`. The fixture has `Rate Type` rows named `Overtime 1.5`
and `Overtime 2.0`, and the engine ignores them entirely: cost is a flat base rate × effective hours
(`builder.py` cost terms; `ingest/input_adapter.py` reads only `RateType == "base rate"`).

**Required posture:** define `overtime_minutes` explicitly rather than invent a solver concept.
Definition: **assigned effective minutes above the worker's `WorkerV1.contracted_hours`, summed
across workers, floored at zero.** `contracted_hours` is real projection data and is currently unused
(noted at Story 3.1's review). Record the definition in `SCOPE_CONTROLS` as
`metrics:overtime_is_above_contracted_hours`, with `NOT COVERED: penalty rates — the engine prices
all hours at the base rate`. Do not silently emit `0` and do not silently emit a wage-weighted number
the engine cannot support.

**(b) Wiring per-employment-type caps from `Shift Constraint` would be a guard that cannot go red.**
Story 3.1's review resolution said "the real per-type cap arrives with the solver at Story 3.2".
Measured on both committed fixtures: the only employment types present are `Full Time` and
`Part Time`, and `Shift Constraint` gives **both** `Maximum Hours a Week = 56` — identical to
`config/constants.py:DEFAULT_MAX_HOURS_PER_WEEK = 56.0`. Wiring them changes nothing observable on
any committed fixture.

**Required posture:** wire `max_hours_per_week` from `Shift Constraint` in the *governed* adapter
only, and prove it with a **seeded** problem carrying a differing cap (the fixture's own
`Casual = 40` row is the natural case, with a seeded Casual worker). Do **not** assert
"per-type caps are honoured" against 56/56. `MinimumHoursBetweenShifts = 10` in the fixture versus
`DEFAULT_MIN_GAP_HOURS = 2.0` **is** a real divergence — it is explicitly **out of scope** here
(changing it changes every solve) and is recorded in `deferred-work.md` with Epic 3 named, not wired.

### Gap 3 — `AssignmentV1` does not carry AD-20's `qualification refs` or `lock/source refs`

`application/contracts/scenario_projection.py:98-104` defines `AssignmentV1` as
`record_id, worker_id, task_id, shift_id, start_minute, end_minute`. AD-20's required shape
(`ARCHITECTURE-SPINE.md:324`) additionally names *qualification refs* and *lock/source refs*.

**Required posture:** add both to the contract in **additive, defaulted** form
(`qualification_refs: tuple[QualificationRefV1, ...] = ()`, `source: str = "baseline"`,
`lock_ref: str | None = None`), so every existing construction site keeps compiling and
`tests/test_evidence_ref.py`-style field-order tests are updated once. The governed solver output
populates `qualification_refs` with the `(task_id, rate)` actually used for coverage
(`builder.py:223` — `member.rate_for(tid) or DEFAULT_TASK_RATE`) and `source="solver"`. Baseline
assignments keep the defaults. **This is what finally makes `docs/DOMAIN-MODEL.md` §4 condition 1 —
"a per-worker rate from the solver" — a real supply**; note it in the ledger entry at
`deferred-work.md:211` rather than reopening `shortfall_minutes`, which is Story 3.8's call at the
earliest.

`lock_ref` stays structurally `None` on every path in this story: `get_locks` returns a hardcoded
`()` (`adapters/postgres/scenario_projection.py:651-668`), so there is still **no lock supply at
all** (Story 3.1 Gap 1, unchanged at `37371d3`). Preserved-lock validation is therefore proved with a
**seeded** reader that returns real locks, following `evals/fixture_projection.py`'s precedent. Do
**not** write a test asserting "locks were preserved" against a supply of zero.

---

## Acceptance Criteria

Verbatim from `epics.md#Story-3.2`, each followed by what makes it demonstrably true here.

**AC1 — Given** a valid proposal and current authorized scenario/baseline
**When** the application creates `RunSnapshotV1`
**Then** it freezes scenario checksum/version, baseline/proposal versions, locks,
constraints/objectives, solver name/config/seed/limit, component versions, accepted time, and input
evidence references
**And** the model cannot alter the snapshot after acceptance. (FR11, FR14, AR20)

> Demonstrated by: `run_snapshot` rows are insert-only (no UPDATE grant to the runtime role); the
> snapshot's `canonical_hash` is recomputed on read and mismatch raises; a stale proposal or scenario
> version fails closed **before** a snapshot is written (AD-9, no silent rebase); no model-authored
> value reaches any snapshot field — the snapshot is built from the persisted `ProposalV1` and the
> `scenario_version` row only.

**AC2 — Given** an immutable run snapshot
**When** the `SchedulerEngine` executes CP-SAT
**Then** only the solver adapter constructs assignments or validates feasibility and returns typed
assignments, metrics, constraint results, warnings, and evidence
**And** domain/application code remains independent of OR-Tools types. (FR11, AR1, AR2)

> Demonstrated by: `tests/architecture/test_solver_boundaries.py` — an AST sweep asserting no module
> under `application/**`, `adapters/**` or `api/**` imports `ortools`, `engine`, `ingest`, or
> `domain.result`; and that `engine/governed_adapter.py` is the only module importing both
> `application.contracts.*` and `engine.base`.
>
> **Scope the sweep precisely or it fails on pre-existing, legitimate code.** Two exceptions are real
> and must be encoded rather than discovered: `adapters/postgres/scenario_projection.py:41` already
> imports `domain.types` (`DemandFamily`, `WindowKind`) — pure domain enums, which AD-1 permits — and
> `api/deps.py:34` / `api/routers/runs.py:11` import `engine.base` for the **legacy** SQLite route
> that AD-25 keeps offline behind the Gate A flag (`api/main.py:129-146`). Fence the *governed*
> boundary: forbid `ortools` everywhere outside `engine/**`, forbid `domain.result` and `ingest`
> outside `engine/**`, and allow-list the two legacy `engine.base` importers by name with a comment
> naming AD-25. An allow-list that grows silently is worse than no fence, so assert the allow-list's
> exact membership too.

**AC3 — Given** a feasible result
**When** completion is validated
**Then** every deterministic hard constraint and preserved lock passes before one immutable candidate
`ScheduleVersionV1` is created
**And** all numerical result fields are recomputable from the frozen snapshot and evidence.
(NFR11, NFR14)

> Demonstrated by: Decision 5's seven independent checks, each observed failing against a corrupted
> assignment set; Decision 3's calculator, with a test that recomputes the entire `MetricSetV1` from
> the persisted candidate + snapshot and asserts equality; a preserved-lock check driven by a seeded
> lock supply (Gap 3).

**AC4 — Given** infeasible, timed-out, cancelled, or failed execution
**When** the result is finalized
**Then** no candidate schedule version is created and the literal terminal status/reason is preserved
**And** no outcome is collapsed into completed or promotable. (NFR13, AR7)

> Demonstrated by: a **database** guarantee, not only application code — `schedule_run` carries a
> partial unique/CHECK pair making `candidate_schedule_version_id NOT NULL` legal only when
> `status = 'solver_completed'`; plus one test per terminal status asserting zero
> `schedule_version` rows and the exact persisted `(status, reason)` pair. See the status-mapping
> table in Dev Notes — four of the five terminal statuses need an explicit mapping decision because
> the current engine cannot produce them naturally.

---

## Tasks / Subtasks

Three phases with one reporting checkpoint — the 2.7 / 2.9 / 3.1 pattern, and for the same reason:
the phase boundary sits where the only clean split *would* be, so the Decision-4 trade can be settled
with numbers instead of guessed before any code exists.

**Retro action A2 is in force.** Every new guard, conformance assertion and architecture test must be
**observed failing** with its structural assertion removed, and the observation recorded in the Dev
Agent Record.

### Phase A — contracts and the frozen snapshot

#### Task 1 — Extend `AssignmentV1`; add the four new contracts (AC: 1, 2, 3)

- [x] `application/contracts/scenario_projection.py`: add `qualification_refs`, `source`, `lock_ref`
      to `AssignmentV1`, **all defaulted** (Gap 3). Update the field-order test that covers it.
- [x] New `application/contracts/run_snapshot.py` — `RunSnapshotV1` and `GovernedSolverConfigV1`,
      every AD-20 field present (Facts table row). `component_versions` is a
      `tuple[tuple[str, str], ...]` capturing at minimum `ortools`, `application`, and the
      `contract schema_version` — sorted, so the canonical hash is stable.
- [x] New `application/contracts/schedule_version.py` — `ScheduleVersionV1`, `MetricSetV1`,
      `ConstraintResultV1`, `SolverOutcomeV1`, `ScheduleRunStatusV1`.
- [x] `ScheduleRunStatusV1` is a closed `Literal` of exactly AD-7's **eight** `ScheduleRun` states —
      `solver_queued`, `solver_running`, `cancellation_requested`, `solver_completed`,
      `solver_infeasible`, `solver_timed_out`, `solver_cancelled`, `solver_failed` (five of which are
      terminal). Do **not** reuse `AgentRunStatusV1` and do not borrow a name from it; AD-7 says the
      stored status types are never merged, and `agent_run`'s own CHECK
      (`schema.py:306`) is a separate vocabulary.
- [x] **Unlike `ProposalV1`, the required shape is enforced at construction.** `deferred-work.md:231`
      names Story 3.2 as this item's owner precisely because a snapshot freezes a proposal: a
      `__post_init__` raises if any AD-20-required field is absent. Discharge the ledger entry.
- [x] Contract digests use `application/contracts/canonical.py :: contract_digest` — the **one**
      canonicalizer. Do not add a second pre-canonicalization shape (Story 3.1's review found two
      that agreed only by luck).

#### Task 2 — Migration: four tables (AC: 1, 3, 4)

- [x] `run_snapshot`, `schedule_run`, `schedule_version`, `schedule_assignment`. Copy the RLS /
      FORCE RLS / policy / composite-uniqueness / grant-then-revoke shape from
      `migrations/versions/a4f92d7c8e31_add_durable_conversations.py`; copy the digest/algorithm
      CHECK shape from `schema.py:134-145`.
- [x] `schedule_run.status` CHECK over the closed vocabulary from Task 1.
- [x] **The AC4 database guarantee:** `CHECK (candidate_schedule_version_id IS NULL OR status =
      'solver_completed')`. Application code may be wrong; this cannot be.
- [x] `run_snapshot` and `schedule_version` receive **INSERT and SELECT grants only** — no UPDATE, no
      DELETE for any runtime role (AD-9 immutability, AC1's "cannot alter after acceptance").
      `schedule_run` receives a narrow UPDATE grant on `status`, `reason`,
      `candidate_schedule_version_id`, `finished_at` only — copy
      `c7d6e5f4a3b2_grant_agent_run_status_update.py`.
- [x] `alembic check` must report zero operations. **Run it from the repository root** —
      `alembic.ini` is checked in at the root with `script_location = %(here)s/backend/migrations`
      (`deferred-work.md:138-147`).

#### Task 3 — `create_run_snapshot` use case + repository (AC: 1)

- [x] `application/ports/schedule_run.py` — `ScheduleRunRepository` Protocol with `connection: Any`
      (never the vendor type; copy `application/ports/scenario_projection.py:104`).
- [x] `adapters/postgres/schedule_run.py` — the implementation.
- [x] `application/use_cases/create_run_snapshot.py`: load the persisted `ProposalV1`; **fail closed**
      if the proposal is `rejected`, or if its `scenario_version_id` differs from the scenario's
      current version (AD-9, no silent rebase); build `RunSnapshotV1`; compute its canonical hash;
      insert `run_snapshot` + `schedule_run(status='solver_queued')` in **one** transaction.
- [x] Input evidence refs: one `EvidenceRefV1` per resolved entity and per preserved lock on the
      proposal, each carrying the scenario version + digest. `producing_run_version` stays `None`
      on *input* refs — they predate the run.
- [x] Solver config values come from `settings.py` (Task 4), never from a caller argument that a
      later story could route model output into.

#### Task 4 — Settings: positive application-owned solver ceilings (AC: 1, 4)

- [x] Add `solver_engine_name`, `solver_seed`, `solver_num_search_workers`,
      `solver_max_deterministic_time`, `solver_wall_time_limit_seconds` to `Settings`, following the
      existing `scheduling_*` field conventions and their comment style.
- [x] All must be **positive** (NFR16 / AD-7). A non-positive or unparseable value raises at process
      start, matching `settings.py`'s existing `InvalidFlagError` posture — it must never silently
      fall back, because a zero ceiling is an unbounded solve wearing a configured number.

### ⛳ Checkpoint — commit Phase A and report six numbers

Report, from a real run, before writing the adapter:

1. backend collected / passed / skipped, and `-m postgres` collected / passed;
2. `alembic check` output;
3. the four new tables' grants, dumped from the live database (`information_schema.role_table_grants`)
   — proving no UPDATE on `run_snapshot` / `schedule_version`;
4. the AC4 CHECK constraint observed **rejecting** an insert that pairs a candidate with a
   non-`solver_completed` status;
5. the `RunSnapshotV1.__post_init__` guard observed failing with a required field omitted;
6. the stale-proposal refusal observed, with the exact error code.

### Phase B — the governed solver adapter

#### Task 5 — `SchedulerPort`, `SolverInputSource`, and the governed adapter (AC: 2)

- [x] `application/ports/scheduler.py` — `SchedulerPort.solve(snapshot: RunSnapshotV1) ->
      SolverOutcomeV1` and `SolverInputSource.load(scenario_version_id, expected_digest) -> Any`.
- [x] `adapters/postgres/solver_input.py` — implements `SolverInputSource`; re-reads
      `scenario_version.payload`, **recomputes the RFC 8785 digest and compares** to the snapshot's,
      raising a distinct `SnapshotDigestMismatchError` on divergence (AD-11: missing, unauthorized
      and version-mismatched are distinct failures).
- [x] `engine/governed_adapter.py` — the translation boundary of Decision 2. Applies the five
      `DraftConstraintV1` kinds to `OverrideCall`s via `domain/overrides.py :: override_id`; converts
      minutes → hours **inbound** and hours → minutes **outbound**; wires `max_hours_per_week` from
      `Shift Constraint` (Gap 2b).
- [x] Minute↔hour conversion is one shared helper used by both directions, tested for round-trip
      stability at the grid the fixture uses. A half-open `[start, end)` minute interval must survive
      `→ hours → back`; `builder.py` snaps starts to a 1.0h grid (`SHIFT_START_GRID_H`), so
      a naive `int(h * 60)` is not automatically safe.

#### Task 6 — Measure the Decision 4 trade (AC: 2)

- [x] Solve `data/sample_tiny_input.json` under (a) `num_search_workers=8` + `max_time_in_seconds`
      and (b) `num_search_workers=1` + `max_deterministic_time`. Report round-1 unmet hours, round-2
      cost, wall seconds, status, assignment count, scheduled members for each.
- [x] Run (b) **three times** and assert identical assignments; run (a) three times and record what
      you observe. This is the evidence behind the story's title word "deterministic".
- [x] Record the outcome in `SCOPE_CONTROLS` under `solver:reproducibility` with the measured
      numbers, whichever way it lands.

#### Task 7 — The wall-time trap (AC: 4)

- [x] `objective.py:solve_lexicographic` passes `time_limit_s` to **each** of two `Solve()` calls
      (`:46-48` then `:63`), so total wall time is up to **2×** the configured limit. The governed
      ceiling must bound the **total**, or a "30 second" run takes 60 and `solver_timed_out` fires on
      a number nobody configured.
- [x] Implement in the governed adapter (budget the second round with the remaining time), **not** by
      editing `objective.py` — that file is on the legacy path and five test modules depend on its
      current behaviour.
- [x] Test: a snapshot with a small ceiling finalizes `solver_timed_out` within the ceiling, not
      double it.

### Phase C — validation, terminal outcomes, and fences

#### Task 8 — Hard-constraint validator and the candidate metrics calculator (AC: 3)

- [x] `application/scheduling/hard_constraints.py` — Decision 5's seven checks over `AssignmentV1[]`
      plus snapshot facts. **No CP-SAT object in scope.**
- [x] Seven corruption fixtures, one per check, each observed making its own check fail and only its
      own (A2).
- [x] Preserved-lock check driven by a **seeded** lock supply (Gap 3).
- [x] `application/scheduling/candidate_metrics.py` — `MetricSetV1` and the soft
      `ConstraintResultV1[]` from assignments + frozen demand.
- [x] **`docs/DOMAIN-MODEL.md` §5's checklist applies to every number here.** Name the unit before
      naming the metric. Coverage required/served minutes for `outbound`/`inbound` is a `volume`
      family converted through the **per-worker qualification rate** now available on
      `AssignmentV1.qualification_refs` — that conversion is legitimate *here* and nowhere else,
      because here the assignment supplies the "who". `indirect` is `headcount` and needs no
      conversion. Cite §1 and §4 in the module docstring.
- [x] The recomputation test: rebuild the full `MetricSetV1` from the persisted candidate + snapshot
      alone and assert equality with the stored one.

#### Task 9 — `finalize_schedule_run` and every terminal outcome (AC: 3, 4)

- [x] `application/use_cases/finalize_schedule_run.py` — the `complete-compute` bundle minus its
      event (Decision 8). Compare-and-set from `solver_running`; candidate written **only** when
      status is `solver_completed` **and** the Task 8 validator passed.
- [x] Implement the status mapping in Dev Notes' table, including the two non-obvious cases: a
      round-2 `UNKNOWN` carrying a usable round-1 snapshot is `solver_timed_out` **with no candidate**
      (AC4 is explicit), and a structurally-always-feasible model means `solver_infeasible` is
      reachable only through Task 8's validator or a `MODEL_INVALID` return.
- [x] One test per terminal status asserting `schedule_version` row count is zero and the exact
      persisted `(status, reason)` pair.
- [x] `solver_cancelled` is representable and **persisted-only** here — nothing requests it until
      Story 3.4. Record as `NOT COVERED` with 3.4 named; do not build a cancellation hook into
      `objective.py`.

#### Task 10 — Fences, ledger, regression (AC: 1, 2, 3, 4)

- [x] `tests/architecture/test_solver_boundaries.py` — AC2's structural proof (see AC2 above), each
      assertion observed failing.
- [x] `SCOPE_CONTROLS` for the new modules, in Story 2.5's `COVERS` / `NOT COVERED` form, carrying at
      minimum: `inputs:solver_reads_raw_fixture`, `metrics:overtime_is_above_contracted_hours`,
      `solver:reproducibility`, `events:owned_by_story_3_5`, `cancellation:owned_by_story_3_4`,
      `baseline:pointer_owned_by_epic_4`, `locks:seeded_supply_only`,
      `constraints:min_gap_not_wired`.
- [x] `deferred-work.md`: discharge `:231` (`ProposalV1` required shape → now enforced on
      `RunSnapshotV1`); update `:185` (`baseline_schedule_version` — aggregate now exists, pointer
      still Epic 4's); update `:211` (`shortfall_minutes` — condition 1 now satisfied, conditions 2–4
      still open); add the `MinimumHoursBetweenShifts` divergence from Gap 2b.
- [x] Gate A re-run: `gate_a_passed: true`, `blocking: []`.
- [x] Verify the mandated zero-line diffs with `git diff --stat` (list in Project Structure Notes).

---

## Dev Notes

### What this story is, and what it is not

**It is:** the deterministic-candidate boundary. Proposal → frozen immutable snapshot → CP-SAT
through one adapter → independently validated assignments → one immutable candidate, or a literal
terminal status and no candidate at all.

**It is not:**

| Not this | Owner |
|---|---|
| A job queue, lease, fencing epoch, or worker process | Story 3.3 |
| Cancellation of anything — the command, the cooperative check, the race resolution | Story 3.4 |
| Persisted run events, SSE replay, reconnect, the NFR35 5-second measurement | Story 3.5 |
| The Run optimization control, the compute capability, the run command, HTTP idempotency for it | Story 3.6 |
| The Runs workspace, progress cards, any frontend file whatsoever | Story 3.7 |
| `ComparisonV1`, candidate-vs-baseline deltas | Story 3.8 |
| The baseline pointer, approval, `AuditEnvelopeV1`, promotion | Epic 4 (AD-10) |
| Restoring `shortfall_minutes` or adding a headcount metric | Story 3.8 at the earliest (`deferred-work.md:209, :211`) |
| Changing `DEFAULT_MIN_GAP_HOURS`, or any legacy solve behaviour | Nobody yet — recorded, not wired (Gap 2b) |
| Editing a committed contract fixture or `data/**` | Story 1.1 owns fixture import; digests are Gate A bound |

### Terminal status mapping — decide from this table, do not re-derive it

`engine/cpsat/objective.py:33-39` maps CP-SAT to five strings: `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`,
`MODEL_INVALID`, `UNKNOWN`. AD-7's `ScheduleRun` graph has five **terminal** states. The mapping is
**not** one-to-one and three cases are easy to get wrong:

| Engine outcome | AD-7 status | Reason | Candidate? |
|---|---|---|---|
| `OPTIMAL` / `FEASIBLE`, validator passes | `solver_completed` | — | **yes**, exactly one |
| `OPTIMAL` / `FEASIBLE`, validator fails | `solver_failed` | `hard_constraint_violated` | no |
| `UNKNOWN` from round 2, round-1 snapshot present | `solver_timed_out` | `budget_exhausted` | **no** — AC4 is explicit; a usable schedule that arrived past the ceiling is still not promotable |
| `UNKNOWN` from round 1 (`round1_value` is NaN) | `solver_timed_out` | `budget_exhausted` | no |
| `INFEASIBLE` | `solver_infeasible` | `model_infeasible` | no |
| `MODEL_INVALID` | `solver_failed` | `model_invalid` | no |
| adapter/port raised | `solver_failed` | the specific error code | no |
| ceiling other than wall time exhausted | `solver_failed` | `budget_exhausted` | no (AD-7 splits wall-time from other ceilings) |
| cancellation observed | `solver_cancelled` | `cancelled` | no — representable, unreachable until 3.4 |

**`solver_infeasible` is near-unreachable from the current model, and that is a finding, not a bug to
hide.** Verified in `engine/cpsat/builder.py`: every coverage constraint carries a bounded `unmet`
slack variable (`:301`, `:311`), roster fill carries an `unfilled` slack (`:263`), and all five
override kinds use bounded slack (`:334-417`). The model is structurally satisfiable, so
`INFEASIBLE` essentially cannot be returned. In this story `solver_infeasible` therefore exists as a
persisted, tested status reachable through a **seeded** infeasible model, and NFR14's "planner locks
must remain satisfied or the run must return a clear infeasibility diagnosis" is satisfied by the
Task 8 validator's refusal path. Record it in `SCOPE_CONTROLS`; do not paper over it by mapping
validator failure to `solver_infeasible` — AD-7 and AC4 both forbid collapsing distinct outcomes.

### The traps, ranked by how quietly they fail

1. **A metrics calculator that reads the solver's own variables.** `engine/cpsat/engine.py:63-110`
   computes coverage from `builder.unmet_vol` / `builder.coverage_terms`. Reusing that shape for
   `MetricSetV1` produces numbers that always agree with the solver and prove nothing. Decision 3.
2. **A hard-constraint validator that re-reads the CP-SAT model.** Same failure, higher cost: it
   gates candidate creation, so a circular check makes AC3 unfalsifiable. Decision 5, and the reason
   Task 8 demands seven corruption fixtures.
3. **Asserting per-employment-type caps against 56/56.** Both committed fixtures give `Full Time` and
   `Part Time` the same 56 that `DEFAULT_MAX_HOURS_PER_WEEK` already supplies. Gap 2b.
4. **Asserting "locks were preserved" against a supply of zero.** `get_locks` returns a hardcoded
   `()`. Gap 3. This is retro §3.1's dominant failure mode — 19 findings in Epic 2.
5. **Double wall time.** Two `Solve()` calls each get the full limit. Task 7.
6. **Non-deterministic multi-worker search silently invalidating the story's title.** Decision 4.
7. **Trying to emit a persisted event.** It will fail on
   `ck_persisted_event_stream_is_conversation` and on two NOT NULL FKs. Decision 8 — that failure is
   the *correct* outcome; do not widen the table to get past it.
8. **`ProposalV1()` constructs an empty proposal.** Every field is defaulted
   (`application/contracts/proposal.py:76-95`). A snapshot built from an unvalidated proposal
   silently freezes `None`s. Task 1 enforces `RunSnapshotV1`'s shape at construction and discharges
   `deferred-work.md:231`.
9. **Minute↔hour rounding.** `builder.py` snaps shift starts to a 1.0-hour grid and the fixture
   carries a `20:04` shift-start value. Round-trip the conversion, don't assume it.

### Existing conventions to match, not reinvent

| Need | Copy from |
|---|---|
| Port with `connection: Any` (never the vendor type) | `application/ports/scenario_projection.py:104`; `application/ports/proposal.py` |
| Repository + use-case split, one transaction owned by the use case | `application/use_cases/manage_proposal.py` + `adapters/postgres/proposal.py` |
| An orchestrator that is the only place two aggregates meet | `application/use_cases/finalize_agent_run.py` |
| Migration: RLS, FORCE RLS, policy, index, composite uniqueness, grant-then-revoke | `migrations/versions/a4f92d7c8e31_add_durable_conversations.py` |
| A single narrow column UPDATE grant | `migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py` |
| Digest / algorithm CHECK constraints | `schema.py:134-145` (`scenario_version`) |
| RFC 8785 canonical hash + algorithm/schema triple | `application/contracts/canonical.py :: contract_digest` |
| `SCOPE_CONTROLS` in `COVERS` / `NOT COVERED` form | `application/capabilities/scheduling_draft.py:40-82` |
| Frozen contract field-order test | `tests/test_evidence_ref.py:63` |
| Architecture fence by AST import sweep | `tests/architecture/test_agent_runtime_boundaries.py:53, :151` |
| Seeded reader supplying facts the production reader does not | `evals/fixture_projection.py` |
| Solver test shape (build a small problem, solve, assert) | `tests/test_engine_small.py`, `tests/test_engine_min_workers.py` |
| Settings field + validation + comment style | `settings.py:75-100` (`scheduling_*`) |

### Latest technical information (verified against the repo at `37371d3`)

- **No new dependency.** `ortools==9.11.4210` is a repository lock (`backend/pyproject.toml`;
  architecture Stack table marks it "repository lock; validated machine-specific pin"), so no
  AR27 gate ceremony applies. Do not upgrade it — the pin is machine-validated and a version move
  would change every calibrated penalty constant's meaning.
- **OR-Tools determinism, verified against the OR-Tools source, not from memory.**
  `max_deterministic_time` (`sat_parameters.proto` field 67) is documented as making solves
  "reproducible regardless of machine load"; `TimeLimit` (`util/time_limit.h`) states "the
  deterministic limit is used to ensure reproductibility"; `cp_model_solver.cc` shows `num_workers > 1`
  entering `SolveCpModelParallel`, a portfolio whose winner depends on thread scheduling. Decision 4.
- **CI enforces counts.** `.github/workflows/ci.yml` runs backend pytest, the PostgreSQL suite, the
  evidence-convention sweep, `alembic check`, frontend lint/typecheck/build/vitest, and Playwright.
  `.github/scripts/assert_counts.py` enforces pass counts as **floors** and skip counts as
  **ceilings** — adding tests never reddens CI, but a silently skipped suite always does. The backend
  skip ceiling is `--max-skipped 1` (`ci.yml:179`). **Verify the current numbers before attributing a
  red CI to this story.**
- **`alembic check` must run from the repository root** (`deferred-work.md:138-147`).
- **Golden dataset at creation: 21 cases** (`demonstration` 2, `scheduling_compute` 4,
  `scheduling_draft` 4, `scheduling_inspect` 11). **This story contributes 0** — it ships no
  capability and no model-facing surface, so a golden case would be a case about nothing. Record the
  zero contribution and the unchanged running total; do not pad to look complete (`epics.md:1527`).
- **Fixture reality, measured on both `data/*.json` and `data/contract/*.projection-v1.json`:**
  tasks 6, workers 10 / 22, demand intervals 1547, constraints 14, shift templates 4, EBA rate rows
  8, employment types `{Full Time, Part Time}`, **locks 0, baseline assignments 0,
  `baseline_schedule_version` null**.

### Project Structure Notes

**New files** (AR26's structural seed):

```
backend/application/contracts/run_snapshot.py
backend/application/contracts/schedule_version.py
backend/application/ports/scheduler.py
backend/application/ports/schedule_run.py
backend/application/scheduling/__init__.py
backend/application/scheduling/hard_constraints.py
backend/application/scheduling/candidate_metrics.py
backend/application/use_cases/create_run_snapshot.py
backend/application/use_cases/finalize_schedule_run.py
backend/application/use_cases/execute_schedule_run.py
backend/adapters/postgres/schedule_run.py
backend/adapters/postgres/solver_input.py
backend/engine/governed_adapter.py
backend/migrations/versions/<rev>_add_schedule_run_aggregate.py
backend/tests/architecture/test_solver_boundaries.py
backend/tests/test_run_snapshot_contracts.py
backend/tests/test_governed_solver_adapter.py
backend/tests/test_candidate_validation.py
backend/tests/test_schedule_run_persistence.py
```

**Modified (UPDATE, not NEW) — read each completely before editing:**

`application/contracts/scenario_projection.py` (`AssignmentV1`, Gap 3) ·
`adapters/postgres/schema.py` (four tables) · `settings.py` (five solver fields) ·
`tests/test_evidence_ref.py` or whichever test pins `AssignmentV1`'s field order ·
`tests/test_scenario_projection.py` (if it constructs `AssignmentV1` positionally) ·
`_bmad-output/implementation-artifacts/deferred-work.md`

**Mandated zero-line diffs** — verify with `git diff --stat`:

```
frontend/**                                backend/domain/**
backend/engine/base.py                     backend/engine/cpsat/**
backend/ingest/**                          backend/llm/**
backend/store/**                           backend/services/**
backend/run.py                             backend/api/**
backend/agent/**                           backend/application/capabilities/**
backend/application/grounding/**           backend/application/clarification/**
backend/application/use_cases/execute_turn.py
backend/application/use_cases/finalize_agent_run.py
backend/application/use_cases/manage_proposal.py
backend/adapters/postgres/scenario_projection.py
backend/adapters/postgres/scenario_catalogue.py
backend/adapters/postgres/conversation.py  backend/adapters/postgres/proposal.py
backend/evals/**                           data/**
evidence/**                                docs/DOMAIN-MODEL.md
```

`backend/api/**` is fenced deliberately: this story mounts no route. If a task appears to need one,
it belongs to Story 3.6.

### References

- `_bmad-output/planning-artifacts/epics.md#Story-3.2` (ACs, verbatim), `#Epic-3` sequencing note,
  FR11–FR14, NFR11, NFR13, NFR14, NFR16, AR1, AR2, AR7, AR9, AR20, AR22, AR23, AR26, AR27
- `.../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-1, AD-2, AD-4,
  AD-6, AD-7 (state machines), AD-9, AD-11, AD-12, AD-20 (*Normative contract minimums*:
  `RunSnapshotV1`, `AssignmentV1`, `MetricSetV1`, `ConstraintResultV1`, `ScheduleVersionV1`), AD-22
  (*Aggregate ownership*, `complete-compute`), AD-23; *Consistency Conventions*; *Stack*
- `_bmad-output/implementation-artifacts/3-1-create-and-revise-a-reversible-repair-draft.md` — the
  `ProposalV1` contract, Decisions 1/3/5/7, Gap 1 (no baseline / no locks / no assignments), Gap 2
  ("fail before solver execution" inherited by this story), and the 31 review findings
- `docs/DOMAIN-MODEL.md` — §1 family/unit, §2 what an assignment carries, §3 question routing,
  §4 *Before `shortfall_minutes` can return*, §5 checklist
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`
- `_bmad-output/implementation-artifacts/deferred-work.md` — `:138-147`, `:185`, `:209`, `:211`,
  `:231`
- `_bmad-output/implementation-artifacts/epic-1-2-retro-2026-08-16.md` — §3.1, §3.2, §6.1 (A2, A3)
- OR-Tools: `ortools/sat/sat_parameters.proto` (`max_deterministic_time`),
  `ortools/util/time_limit.h`, `ortools/sat/cp_model_solver.cc` (`SolveCpModelParallel`)

### Baselines at creation — re-derive them, do not trust them

Story 2.7 found its inherited baseline stale by 100+ tests; Story 3.1 found a skip-count discrepancy
between local and CI.

| Suite | Collected at `37371d3` |
|---|---|
| backend default | 945 collected (952 total, 7 deselected) |
| backend `-m postgres` | 55 collected |
| evidence convention | 49 collected |
| golden cases | 21 files |
| frontend / Playwright | not re-measured — this story mandates a zero-line `frontend/**` diff |

`-m postgres` requires the local PostgreSQL service and was **collected, not executed**, at story
creation. Establish real pass numbers before attributing any failure to this story's changes.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Follow the story's three phases in task order with red-green-refactor gates; keep the solver and
  persistence boundaries transport-free and preserve every mandated zero-line diff.
- Freeze governed inputs as identity + checksum contracts, then persist them before introducing the
  engine adapter; independently validate assignments and recompute candidate numbers before finalization.

### Debug Log References

- 2026-08-19 Task 1 RED: `tests/test_run_snapshot_contracts.py` failed collection because the new
  contract modules did not exist. GREEN: targeted projection/contract regression 113 passed, 1 skipped.
- 2026-08-19 Task 1 full regression: 957 collected; 948 passed, 2 skipped, 7 deselected.
- 2026-08-19 Task 2 RED: metadata/migration tests failed on all four absent tables and migration.
  GREEN: fresh-database upgrade/downgrade plus Alembic `command.check` passed; live PostgreSQL
  grants and candidate/status CHECK passed. Full regression: 953 passed, 2 skipped, 7 deselected;
  PostgreSQL suite: 57 passed.
- 2026-08-19 Task 3 RED: `test_create_run_snapshot.py` failed collection before the use case existed.
  GREEN: 4 focused tests passed; full regression 957 passed, 2 skipped, 7 deselected. Exact stale
  refusal code: `stale_proposal`; exact rejected refusal code: `rejected_proposal`.
- 2026-08-19 Task 4 RED: 6 settings tests failed before the five governed solver settings existed.
  GREEN: 21 focused settings/snapshot tests passed; full regression 963 passed, 2 skipped, 7 deselected.
- 2026-08-19 Phase A checkpoint: backend 972 collected / 963 passed / 2 skipped / 7 deselected;
  PostgreSQL 57 collected / 57 passed; clean throwaway `alembic check` reported no operations;
  grants were run_snapshot=`SELECT,INSERT`, schedule_version=`SELECT,INSERT`,
  schedule_assignment=`SELECT,INSERT`, schedule_run=`SELECT,INSERT` plus column-scoped UPDATE on
  status/reason/candidate_schedule_version_id/finished_at; AC4 CHECK rejected the invalid row with
  `ck_schedule_run_candidate_completed`; required-field guard raised `snapshot_id is required`;
  stale proposal refused before write with code `stale_proposal`.
- 2026-08-19 Task 5 RED: governed adapter tests failed collection before the input source and engine
  boundary existed. GREEN: 8 focused digest/conversion/override/cap tests passed; full regression
  971 passed, 2 skipped, 7 deselected.
- 2026-08-19 Task 6 measurement: deterministic 1-worker / max deterministic time 1.0 produced the
  same 70 assignments and 10 members in 3/3 runs: 247.44352 unmet hours, round-2 objective 1118241,
  wall 6.22/7.24/6.71s, status UNKNOWN after exhausting round 2. Eight-worker / 3.0s wall runs
  produced two distinct assignment sets: 211.85190-211.85271 unmet hours, round-2
  1173123-1201002, wall 3.51/3.08/3.08s, 76-78 assignments, 10 members, status UNKNOWN.
- 2026-08-19 Task 7: 0.25s wall-budget test returned UNKNOWN within 0.40s, proving both rounds share
  one decreasing ceiling. Full Tasks 6-7 regression: 973 passed, 2 skipped, 7 deselected.
- 2026-08-19 Task 8 RED: candidate-validation tests failed collection before the independent
  scheduling modules existed. GREEN: seven corruption cases each triggered its named structural
  guard; a seeded non-empty lock triggered `preserved_lock`; volume/headcount/cost/overtime metrics
  recomputed without solver variables. Full regression: 983 passed, 2 skipped, 7 deselected.
- 2026-08-19 Task 9 RED: finalize and execute tests failed collection before their use cases existed.
  GREEN: all five terminal statuses preserve exact reasons; only completed+validated inserts a
  schedule version/assignment, validator failure and adapter failure insert none. Full regression:
  992 passed, 2 skipped, 7 deselected.
- 2026-08-19 Task 10 RED: the exhaustive AST boundary sweep first exposed the pre-existing legacy
  importers `api/deps.py`, `api/routers/runs.py`, and Story 1.4's
  `adapters/postgres/scenario_projection.py`; the final test records those exact AD-25 allowlists
  while rejecting any new governed importer. GREEN: 4 architecture cases passed. Pre-Gate full
  regression: 996 passed, 2 skipped, 7 deselected; PostgreSQL: 57 passed.
- 2026-08-19 final clean-tree verification: backend 997 passed / 1 expected skip / 7 live-provider
  deselected; evidence convention 49 passed; PostgreSQL 57 passed; Vitest 410 passed; Playwright
  48 passed across Chromium and Edge; frontend lint, typecheck, and production build passed. The
  regenerated Gate A report binds commit `6c95b9d`, records all eight checks passed,
  `gate_a_passed: true`, and `blocking: []`.

### Completion Notes List

- Task 1: Extended `AssignmentV1` additively with defaulted solver qualification/source/lock
  provenance; added immutable governed snapshot/config and schedule-output contracts; enforced the
  exact eight-state AD-7 vocabulary, UTC accepted time, sorted component versions, one RFC 8785
  canonical digest path, and a required-field construction guard.
- Task 2: Added the four-table schedule-run aggregate with site-scoped composite foreign keys,
  forced RLS, immutable snapshot/version/assignment grants, a four-column run-transition grant,
  closed status/feasible-status vocabularies, and a database-level prohibition on candidates for
  non-completed runs. A clean throwaway database reports zero Alembic operations.
- Task 3: Added the transport-free repository port, PostgreSQL atomic snapshot/run writer, and
  `create_run_snapshot` use case. It row-locks persisted proposal authority, refuses rejected or
  stale scenario/baseline inputs before any write, derives settings-owned solver config, freezes
  component versions and trusted evidence locators, and inserts the snapshot plus queued run on one
  caller-owned transaction connection.
- Task 4: Added application-owned `cpsat`/seed/single-worker/deterministic-time/wall-time settings.
  Every value is parsed strictly and must be non-empty, positive, and finite; malformed or zero
  values raise `InvalidFlagError` at settings construction instead of falling back.
- Task 5: Added solver-free application ports, a PostgreSQL raw-payload source that re-computes and
  compares the frozen RFC 8785 digest, and the sole governed engine adapter. It translates all five
  trusted constraints to existing soft overrides, wires per-employment-type weekly caps, preserves
  arbitrary fixture-minute offsets through one conversion pair, and emits deterministic solver
  assignment IDs with the qualification rate actually used.
- Task 6: Replaced the governed path's legacy wall-clock-only solve with a local two-round CP-SAT
  orchestrator that applies one single-worker deterministic budget. The short-ceiling measurement
  confirms exact reproducibility and quantifies its quality trade against the non-deterministic
  eight-worker portfolio; both outcomes are recorded in `SCOPE_CONTROLS`.
- Task 7: The governed two-round solve subtracts elapsed wall time before round 2, so its configured
  ceiling bounds the whole solve rather than each round independently. Legacy `objective.py` remains
  unchanged.
- Task 8: Added seven solver-independent hard checks plus seeded lock validation and a domain-model-
  compliant calculator. Candidate numbers are recomputed from immutable minute-based facts and the
  assigned worker's rate; overtime is assigned time above contracted hours and cost uses base wage.
- Task 9: Added execute/finalize orchestration and atomic PostgreSQL candidate persistence. Literal
  infeasible/timed-out/cancelled/failed reasons are retained with no candidate; feasible output is
  independently validated and recomputed before one immutable candidate and its assignments exist.
- Task 10: Added exhaustive import fences and explicit scope controls; reconciled all four deferred
  facts; verified every mandated path remains a zero-line diff. Candidate evidence now names its
  producing schedule version, and candidate metrics reproduce from assignments plus frozen source
  facts. Golden evaluation data remains unchanged at 21 cases because this story adds no model-facing
  capability. Gate A remains green with no blocking checks.

### File List

- backend/application/contracts/run_snapshot.py
- backend/application/contracts/scenario_projection.py
- backend/application/contracts/schedule_version.py
- backend/tests/test_run_snapshot_contracts.py
- backend/tests/test_scenario_projection.py
- backend/adapters/postgres/schema.py
- backend/migrations/versions/f1a2b3c4d5e6_add_schedule_run_aggregate.py
- backend/tests/test_evidence_binding.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_schedule_run_persistence.py
- backend/adapters/postgres/schedule_run.py
- backend/application/ports/schedule_run.py
- backend/application/use_cases/create_run_snapshot.py
- backend/tests/test_create_run_snapshot.py
- backend/settings.py
- backend/tests/test_settings.py
- backend/adapters/postgres/solver_input.py
- backend/application/ports/scheduler.py
- backend/engine/governed_adapter.py
- backend/tests/test_governed_solver_adapter.py
- backend/application/scheduling/__init__.py
- backend/application/scheduling/candidate_metrics.py
- backend/application/scheduling/hard_constraints.py
- backend/application/use_cases/execute_schedule_run.py
- backend/application/use_cases/finalize_schedule_run.py
- backend/tests/test_candidate_validation.py
- backend/tests/test_finalize_schedule_run.py
- backend/tests/architecture/test_solver_boundaries.py
- _bmad-output/implementation-artifacts/deferred-work.md
- evidence/story-1.11/gate-a-readiness-report.json
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-08-19: Implemented Story 3.2's immutable governed run snapshot, deterministic CP-SAT adapter,
  independent candidate validation/metrics, atomic terminal persistence, architecture fences, and
  Gate A evidence refresh; moved story to review.
