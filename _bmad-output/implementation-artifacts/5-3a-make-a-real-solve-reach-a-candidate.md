---
baseline_commit: 167cd29
---

# Story 5.3a: Make a Real Solve Reach a Candidate [Technical Enabler]

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer of this portfolio,
I want a real schedule run to produce a candidate I can approve,
So that the approval, baseline-promotion and provenance features are demonstrable rather than
merely unit-tested.

**This is a corrective prerequisite, inserted between 5.3 and 5.4**, and it is the first story in
this repository whose subject is *solver search behaviour*. Story 5.3 assembled the composition;
its code review was the first review able to **build the images and drive the running stack**, and
two assertions that had been tightened by reading went red under measurement. Neither was a defect
in the patch being reviewed:

1. `status == "solver_completed"` → actual `solver_timed_out` / `budget_exhausted`
2. `agent_run_status == "agent_completed"` → actual `agent_failed` / `invalid_output`

The first blocks Story 5.4 outright. `finalize_schedule_run` creates a candidate **only** when the
run reaches `solver_completed` (`application/use_cases/finalize_schedule_run.py:60`), so a
timed-out run carries none, `POST /approvals` has nothing to act on, and Flow 1's tail — request
approval → approve as baseline → read the Provenance timeline — is unreachable from a real solve.

**Scope summary:** a round-2 solution hint on both lexicographic implementations, a solver
configuration change so round 2 is reachable at all, a re-measured `SCOPE_CONTROLS` block, a
runtime-selectable deterministic agent double that completes a turn keylessly, and the restored
compose-proof assertions plus Flow 1's approval leg. **No migration, no new API field, no new
route, no new golden case, no new runtime dependency, no new registered evidence file, and no
frontend diff.**

**Depends on, and consumes:** Story 3.2's `GovernedSchedulerAdapter` and `CpSatBuilder`; Story
3.5's `finalize_schedule_run` and the `require_hard_constraints` gate; Story 4.2/4.3's approval and
promotion routes; Story 4.4's provenance query; Story 5.3's composed stack, `compose_proof.py` and
`worker/composition.py`; Story 2.2's `evals/doubles.py` as the *shape* reference for a
`FunctionModel` (never imported — see Decision 7).

**Blocks:** Story 5.4's walkthrough, whose AC1 requires the Wednesday-coverage journey be walked
*"with real output"* and that *"every claim it makes about behavior is reproducible by the Story
5.3 command"* (`epics.md:1455-1456`).

**Also closes:** Story 5.3. Its AC1 clause *"the primary journey is completable end to end against
deterministic model doubles"* becomes true when this story's assertions are green in 5.3's own
`compose_proof.py`; 5.3 flips to `done` in the same pass (Task 8).

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **AC text for this story, verbatim** | `epics.md:1445-1473` |
| **NFR21, verbatim:** "Every environment must be reproducible from reviewed infrastructure code and immutable application images." | `epics.md:115` |
| **NFR26, verbatim:** "Normal CI must be deterministic-first; live-provider tests are explicit, gated, budgeted, and never the sole release evidence." | `epics.md:125` |
| **AR1, verbatim:** "Implement a hexagonal modular monolith with durable workflow state machines; API and worker are separately runnable from one backend image, dependencies point inward, and domain/application code cannot import FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire, or concrete model providers." | `epics.md:147` |
| **AD-7, verbatim on budgets:** "Application configuration—not the model—sets maximum iterations, model/tool calls, tokens, retries, wall time, site concurrency, and solver duration. Wall-time exhaustion becomes `timed_out`; other limit exhaustion becomes `failed` with stable `budget_exhausted` reason." Also: "Only feasible `ScheduleRun.completed` can reference a candidate `ScheduleVersion`." | `ARCHITECTURE-SPINE.md:84-90` (AD-7) |
| **The primary journey is Flow 1 — "Repair Wednesday outbound coverage"**, ending at step 8: "Terminal outcome confirms candidate and new operational-baseline versions, while Provenance timeline links the request, cited evidence, draft, run, approval, and before/after versions." | `EXPERIENCE.md:228-238` — *Flow 1* |
| **This story owns the three ledger entries** under *"Deferred from: code review of story-5.3 (2026-09-06) — measured by running the composed stack"*, all with owner **Story 5.3a** and trigger *"before Story 5.4 writes its walkthrough"*. | `deferred-work.md:719-806` |
| **The blocking defect is in `governed_adapter.py`, not `objective.py`.** The worker composes `GovernedSchedulerAdapter` (`worker/composition.py:21`); `objective.py` is reached only by `api/deps.py:68 create_engine("cpsat")` — the legacy routes, the `run.py` CLI and `scripts/calibrate_penalties.py`. Patching `objective.py` alone leaves the compose proof, the worker and Story 5.4 exactly as blocked. | `sprint-change-proposal-2026-09-06.md` §2.1; `deferred-work.md:726-736` |
| **The ledger's measurement table does not transfer to the governed path.** It was taken through `objective.py` at 30s *per* `Solve()` with 8 workers. `_solve_lexicographic_governed` shares one decreasing wall budget across both rounds. **Story 5.3a must re-measure**, and must not assume a hint alone suffices. | `deferred-work.md:738-748`; `sprint-change-proposal-2026-09-06.md` §2.3 |
| **The `CORRECTED` note inside `SCOPE_CONTROLS` is wrong in the opposite direction.** `SCOPE_CONTROLS` documents `governed_adapter.py`, whose budget *is* shared and decreasing (`:217`, `:220-227`); the original `solver:wall_total` claim at `:47-48` was accurate for the module it describes. Reconciling means correcting the correction, not deleting the original line. | `sprint-change-proposal-2026-09-06.md` §2.2 |
| **`SCOPE_CONTROLS` in `governed_adapter.py` is asserted by no test and is not an `evidence/**/*.json` file**, so the evidence convention's *measure → generate* rule does not literally bind it — only its spirit does. Nothing in the suite will catch a stale measured claim there. | `sprint-change-proposal-2026-09-06.md` §2.5; verified: `test_capability_conformance.py:148` requires `SCOPE_CONTROLS` only of capability-handler modules, and `governed_adapter` is not one |
| **Story 5.3's Decision 12 is superseded by §3.5, on this story's authority, not the dev's.** 5.3 rejected a runtime-selectable double; the change proposal reverses that and assigns the deterministic double to 5.3a. 5.4 keeps only the *illustrative* half. | `sprint-change-proposal-2026-09-06.md` §3.5; `5-3-….md` Decision 12 |
| **Commit the code, then measure on a clean tree, then generate, then commit the evidence separately.** Hand-typing an evidence file is the defect the whole convention exists to prevent. | `docs/EVIDENCE-CONVENTION.md` — *The rule*; `.claude/CLAUDE.md` — *Evidence files* |
| **Every rule over a committed artifact must be monotone.** Not invoked here — this story adds no audit rule — but it is why no new digest or count assertion may be attached to committed evidence as a side effect. | `docs/EVIDENCE-CONVENTION.md` — *Every rule over a committed artifact must be monotone* |
| **CI `--min-passed` / `--max-skipped` are floors and ceilings and are not edited.** The backend job asserts `--min-passed 864 --max-skipped 1 --min-deselected 7`; the single permitted skip is the unconditional one at `test_scheduling_inspect.py:323`. | `.github/workflows/ci.yml:168-179`; `sprint-change-proposal-2026-09-06.md` §3.3 |
| **A demonstrated red must come from mutating code that is already green**, and the Dev Agent Record must carry a mutation table (mutation, guard, before, after) before review; the reviewer independently re-runs at least one row. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml` |
| `outbound`/`inbound` demand is measured in **volume**, `indirect` in **headcount**; assignments carry worker identity but **no `family`**; a metric reading assignments must not accept a `family` argument. **This story computes no metric and adds none.** It changes solver search and a test double; it must not introduce a field derived from, or shaped like, a demand or coverage figure. `calculate_candidate_metrics` is *called* at Task 1's verification but is not modified. | `docs/DOMAIN-MODEL.md` §1, §2, §3 |
| **Manual assistive-technology verification is descoped**; accessibility is proven by automated coverage alone. Not exercised here — this story adds no component and no route the planner sees. | `EXPERIENCE.md` — *Accessibility Floor*; `.claude/CLAUDE.md` |

---

## Acceptance Criteria

Verbatim from `epics.md:1465-1473`.

**AC1.**
**Given** a governed schedule run on either shipped fixture at the default solver budget
**When** the worker executes it through `GovernedSchedulerAdapter`
**Then** the run reaches `solver_completed` and `finalize_schedule_run` creates a candidate
**And** the round-2 search is seeded from the round-1 solution rather than restarted from zero, and
the resulting reproducibility characteristics are re-measured and recorded in
`engine/governed_adapter.py`'s `SCOPE_CONTROLS` from that measurement, never hand-edited. (NFR21)

**AC2.**
**Given** the composed stack started by the Story 5.3 command
**When** `backend/tests/compose_proof.py` runs
**Then** it asserts `solver_completed` for the schedule run and `agent_completed` for the agent
turn, driven by a deterministic model double that requires no provider credential
**And** it exercises Flow 1's tail end to end — request approval, approve as baseline, read the
provenance timeline — against the candidate that real solve produced. (NFR21, NFR26, AR1)

> **AC1 binds the *default* solver budget, not a compose-only override.** "at the default solver
> budget" is the *Given*. A fix that works only because `docker-compose.yml` sets an environment
> variable leaves the default unable to produce a candidate and does not satisfy this AC. See
> Decision 3.

---

## Measured at creation — `167cd29`, clean tree, Docker PostgreSQL 18 up, 16-core host

Do not re-derive these from code. Re-verify them at Task 1 and record any drift.

### Suite baselines

| Suite | Measurement |
|---|---|
| `uv run --frozen pytest -q` (backend default) | **1615 passed, 1 skipped, 7 deselected** (181.76s) |
| `uv run --frozen pytest -q -m postgres` | **160 passed, 1463 deselected** (72.61s) — and 160+1463 = 1615+1+7, so postgres-marked tests do run in the default suite |
| `pytest -q tests/test_evidence_convention.py` | 93 passed |
| `pytest -q tests/architecture` | **79 passed** |
| `pytest -q tests/test_gate_a_readiness.py` | 44 passed |

**The change proposal's stated baseline of "1614 passed, 2 skipped, 7 deselected" was taken on a
dirty tree and is wrong by one in both columns.** Reproduced here: with an untracked scratch file
present, `test_evidence_binding.py:570` skips ("binding realism check needs a clean tree") and the
totals read 1614/2/7; with the tree genuinely clean it runs and they read 1615/1/7. **1615/1/7 is
the baseline. Use it, and keep the tree clean while measuring** — CI's `--max-skipped 1` ceiling is
exactly one skip wide and a dirty tree spends it.

Frontend was **not** measured (this story has a zero-line frontend diff). Story 5.3's Vitest 648 /
85 files and Playwright 80 stand.

### The load-bearing measurement — taken on the *governed* path, at the shipped defaults

Round 1's own convergence, not round 2's hint, is what blocks the shipped configuration. Measured
through `_solve_lexicographic_governed`'s exact budget arithmetic (shared decreasing wall,
`max_deterministic_time`), seed 42, both shipped fixtures:

| workers | wall / det | fixture | round 1 | round 2 | terminal |
|---|---|---|---|---|---|
| **1** (shipped default) | 30 / 30 | `sample_tiny_input` | **never converges** — 30.06s, all of it | **never entered** (`apply_remaining_budget` → `"wall"`) | `UNKNOWN` → `solver_timed_out` |
| **1** | 30 / 30 | `sample_tiny_input_more_tm` | never converges — 30.05s | never entered | `UNKNOWN` |
| **1** | **120 / 120** | `sample_tiny_input` | still never converges — 120.03s | never entered | `UNKNOWN` |
| **1** | 120 / 120 | `sample_tiny_input_more_tm` | still never converges — 120.05s | never entered | `UNKNOWN` |
| **2** | 30 / 30 | both | never converges — 29.8s / 30.06s | entered with 0.21s left, or not at all | `UNKNOWN` |
| **4** | 30 / 30 | both | never converges — 30.08s / 30.10s | never entered | `UNKNOWN` |
| **8** | 30 / 30 | `sample_tiny_input` | **converges, 13.9s** | entered, **no hint** → `UNKNOWN` (16.2s) | `UNKNOWN` |
| **8** | 30 / 30 | `sample_tiny_input_more_tm` | converges, 4.6s | entered, no hint → `UNKNOWN` (23.9s) | `UNKNOWN` |
| **8 + hint** | 30 / 30 | `sample_tiny_input` | converges, 11.3s | **`FEASIBLE`**, r2 = 1154971 (18.8s) | **`solver_completed`** |
| **8 + hint** | 30 / 30 | `sample_tiny_input_more_tm` | converges, 5.2s | **`FEASIBLE`**, r2 = 1954456 (25.0s) | **`solver_completed`** |
| **8 + hint** | **60 / 60** | both | converges, 11.2s / 3.9s | `FEASIBLE`, r2 = **1154971 / 1954456** — *identical to the 30s runs* | `solver_completed` |

Four conclusions, each measured rather than argued:

1. **At the shipped `num_search_workers=1`, round 2 does not exist.** Round 1 consumes the whole
   shared wall budget and `apply_remaining_budget` returns `"wall"` at
   `governed_adapter.py:251-257`. A round-2 hint is a change to code that never runs.
2. **Raising the wall budget does not help at 1 worker.** 120s was measured and round 1 still did
   not converge. The change proposal's escalation step 2 ("raise
   `solver_wall_time_limit_seconds`") is **measured insufficient on its own** — do not spend a
   cycle on it.
3. **Neither lever works alone.** 8 workers *without* the hint → `UNKNOWN` on both fixtures.
   1 worker *with* the hint → round 2 unreachable. Both changes are required.
4. **Extra budget buys nothing beyond `FEASIBLE`.** At 60s, round 2 spent 48.7s / 56.3s and
   returned the *same* `round2_value` as the 30s runs. Neither fixture reaches `OPTIMAL`. So the
   wall budget stays at 30 (Decision 4).

### The candidate gate — `solver_completed` is necessary, not sufficient, and it was verified

`finalize_schedule_run` does not create a candidate merely because the status is
`solver_completed`: it then runs `require_hard_constraints`, and a violation downgrades the run to
`("solver_failed", "hard_constraint_violated")` (`finalize_schedule_run.py:64-78`). **That gate has
never run against a real governed solve** — every `solver_completed` in the suite is fabricated.
Measured at creation, driving the real `GovernedSchedulerAdapter` with the Task-1 patch applied:

| fixture | status | assignments | distinct workers | selected shifts | `require_hard_constraints` | `total_cost` |
|---|---|---|---|---|---|---|
| `sample_tiny_input` | `FEASIBLE` | 76 | 10 | 40 | **PASS** | 11549.69 |
| `sample_tiny_input_more_tm` | `FEASIBLE` | 125 | 22 | 76 | **PASS** | 19544.45 |

`calculate_candidate_metrics` also succeeded on both, returning zero soft results (the snapshot
carried no constraints). **A candidate really is produced.** This was the largest unnamed risk in
the change proposal and it is now closed by measurement — re-verify it at Task 1, do not re-derive
it, and do not treat a hard-constraint violation as expected.

### The hint API, verified present in the pinned OR-Tools

`ortools==9.11.4210` (`backend/pyproject.toml:8`). Probed directly at creation:
`CpModel.ClearHints`, `CpModel.AddHint`, `CpModel.GetIntVarFromProtoIndex` and the solver
parameters `fix_variables_to_their_hinted_value`, `repair_hint`, `debug_crash_on_bad_hint`,
`hint_conflict_limit` **all exist**. No version bump, no fallback, no contingency needed for the
API itself.

`len(round-1 snapshot) == len(model.Proto().variables)` measured equal on both fixtures
(3493/3493 and 5689/5689). The shipped `_GovernedLexResult.value()` already assumes this alignment
(`governed_adapter.py:189-192` indexes the snapshot by `variable.Index()`), so the guard Task 2
adds is new rigour, not a contradiction of existing code.

### The agent-turn failure

`AGENT_RUNTIME_MODEL` defaults to `"test"` (`settings.py:94,305`), resolved by
`agent/runtime.py:527-528` to pydantic-ai's `TestModel` — keyless, no network. Measured 2026-09-06
through the composed stack's public HTTP route: `POST
/conversations/{id}/agent-runs/{id}/execute` returns `agent_run_status: "agent_failed"`,
`reason: "invalid_output"`. `TestModel` synthesises schema-shaped values, so its generated tool
arguments cannot name governed fixture record IDs and the turn produces nothing usable.

`docker-compose.yml:44-45` already passes `AGENT_RUNTIME_MODEL` and `AGENT_RUNTIME_API_KEY`
through to `api` and `worker`, so a new model value needs **no compose edit**.

---

## Ten decisions were made at story creation — do not re-litigate them

---

### Decision 1 — The fix is two changes, and the change proposal named only one

The change proposal's Task 1 calls the hint "the blocking fix". It is not, at the shipped
defaults. The measurement table above shows round 1 consuming the entire shared wall budget at
`num_search_workers=1`, so `apply_remaining_budget` returns `"wall"` and round 2 never runs.

**Decision: this story delivers both the round-2 hint and a solver-configuration change that makes
round 2 reachable. Neither is optional and neither is sufficient alone**, and the story carries the
measurement proving each half necessary (8 workers without hint → `UNKNOWN`; 1 worker with hint →
round 2 unreachable).

**What this does not cover:** it does not unify the two lexicographic implementations, and it does
not change *how* round 1 searches. Round 1 still may not prove optimality — it returns `FEASIBLE`
at its ceiling — and that is accepted, because round 2 locks against `round1_value` whatever it is.

### Decision 2 — The hint is added to `governed_adapter.py:249-251` first, and to `objective.py:63-64` for consistency with no measured claim attached

Between `model.Minimize(builder.round2_cost)` and the second `solver.Solve(model)`:
clear any existing hints, then add one hint per model variable from the round-1 snapshot taken at
`:245`.

```python
model.Add(builder.round1_unmet <= int(round(round1_value)))
model.Minimize(builder.round2_cost)
if len(snapshot) == len(model.Proto().variables):
    model.ClearHints()
    for index, value in enumerate(snapshot):
        model.AddHint(model.GetIntVarFromProtoIndex(index), value)
```

Guarded on the length equality rather than assuming index alignment — a mismatched hint is worse
than no hint, because CP-SAT would silently search from a wrong point. `ClearHints()` first because
the hint is added inside a loop-free path that runs once, but the model object is mutated across
rounds and a second hint set must not accumulate.

`objective.py:63-64` gets the same change, per the change proposal §4.1. **No new measured claim is
attached to that path**: `SCOPE_CONTROLS` does not describe it and the compose proof does not drive
it. Its one real-solve consumer is `test_penalty_calibration.py`, which builds synthetic problems
and solves at `time_limit_s=10` through `create_engine` — see Task 6.

**What this does not cover:** the hint does not make round 2 *optimal*. Measured, round 2 returns
`FEASIBLE` and never `OPTIMAL` on either fixture at 30s or 60s. `_terminal` maps both to
`solver_completed` (`finalize_schedule_run.py:43-44`), so `FEASIBLE` is sufficient — but any claim
that the candidate is cost-optimal would be false and must not be written anywhere.

### Decision 3 — The worker count moves in `settings.py`, not in `docker-compose.yml`

AC1's *Given* is "at the **default** solver budget". `GovernedSolverConfigV1` is frozen into
`RunSnapshotV1` from `settings` at enqueue time (`create_run_snapshot.py:117-123`), and
`solver_num_search_workers` defaults to `1` (`settings.py:133`, `settings.py:384-388`, env
`SOLVER_NUM_SEARCH_WORKERS`).

**Decision: change the default in `settings.py`.** Setting `SOLVER_NUM_SEARCH_WORKERS` only in
`docker-compose.yml` would make the compose proof green while leaving the default configuration —
the one AC1 names, the one every test and every non-compose caller uses — still unable to produce a
candidate. That is passing the AC's letter by moving its subject.

**Starting value: 8, measured working on both fixtures.** 2 and 4 were measured and do **not**
converge round 1 within 30s. The dev re-measures at Task 3 and records the value from that
measurement; if 8 does not converge on the dev's machine the value goes up, not the wall budget
(Decision 4), and the machine's core count is recorded alongside it.

**The honest risk, named rather than discovered at review:** this was measured on a **16-core**
host, where 8 search workers is half the cores. A 4-core CI runner or a CPU-limited container may
not converge round 1 in 30s at any worker count. The compose proof is the place that would surface
it, and it is opt-in and non-required (`.github/workflows/ci.yml`'s `compose-proof` job), so a
regression there would not redden a PR. **If Task 7's proof cannot reach `solver_completed` inside
a container, stop and report** — that is a genuine finding about the fixture and the environment
class, not a licence to widen scope.

**What this does not cover:** it does not make the solve time-bounded on unknown hardware, and it
does not touch `solver_seed`, `solver_engine_name`, or `max_deterministic_time`.

### Decision 4 — The wall budget stays at 30 seconds

Measured: at 8 workers with the hint, a 60-second wall produced the **same** `round2_value` on both
fixtures as the 30-second wall (1154971 and 1954456), with round 2 spending 48.7s and 56.3s to find
nothing better. Extra budget buys latency, not quality.

Leaving `solver_wall_time_limit_seconds = 30.0` also avoids a chain the change proposal flagged:
`minimum_lease_seconds = ceil(wall × 4)` (`settings.py:399`) and `lease_seconds` must be at least
that or `InvalidFlagError` is raised at startup (`settings.py:405-409`). At 30 the derived minimum
is 120, which is the shipped `lease_seconds` default. Moving the wall to 60 would silently require
a 240-second lease.

**What this does not cover:** it does not claim 30s is enough on every machine. It claims that on
the machine where the fix was measured, more wall time changed nothing — so *wall time is not the
lever*, and a dev who finds round 2 short of budget should re-read Decision 3 before reaching for
this one.

### Decision 5 — Reaching `solver_completed` is proven end to end through the candidate gate, not assumed

`require_hard_constraints` re-checks seven invariants independently of CP-SAT (AD-11), and a single
failure turns `solver_completed` into `solver_failed` / `hard_constraint_violated`. Until this
story, that gate had never seen a real governed solve.

**Decision: Task 1 verifies the gate before any other work, and the story records the result rather
than leaving it to be discovered when the compose proof fails.** Measured at creation: **PASS on
both fixtures** (table above). The reason it passes is structural and worth knowing — `CpSatBuilder`
enforces every constraint the validator re-checks: `sum(shift_task_vars) >= sv.var` for
non-empty selected shifts (`builder.py:237`), `sum(vars_) <= max_day` per day (`:275`), the weekly
effective-hours cap (`:278`), and `a.var + b.var <= 1` for any shift pair closer than
`DEFAULT_MIN_GAP_HOURS` (`:285-286`).

**What this does not cover:** the only seam left between model and validator is **rounding** — the
builder compares `int(round(eff_h × VOL_SCALE))` while the validator sums
`_hours_to_minutes(eff_h)` against `cap × 60`. It did not bite on either fixture. A different
fixture, or a changed cap, could put a boundary case on the wrong side, and the symptom would be a
`solver_failed` / `hard_constraint_violated` run that looks like a solver bug. Do not chase it
speculatively; recognise it if it appears.

### Decision 6 — `SCOPE_CONTROLS` is reconciled by measurement, and the `CORRECTED` note is corrected rather than deleted

`governed_adapter.py:38-68` carries four defects at once: a `solver:wall_total` claim that was
disputed against the wrong module, a `CORRECTED` note that is itself wrong, and two measured
reproducibility claims that this story's changes invalidate.

**Decision, four parts:**

1. **Restore** the `solver:wall_total` claim at `:47-48`. Per §2.2 of the change proposal it was
   accurate for the module it describes: `apply_remaining_budget` recomputes
   `wall_time_limit_seconds - elapsed` before each round (`:217`, `:220-227`). Verified again here
   — at 1 worker the second call returned `"wall"` and round 2 never ran, which is only possible
   under a shared decreasing budget.
2. **Rewrite** the `NOT COVERED: any terminal status other than UNKNOWN` entry at `:51-61`. After
   Tasks 1-2 it is false, and it is the entry naming Story 5.3a as owner.
3. **Re-measure and rewrite** `solver:reproducibility` (`:40-43`) and `solver:multi_worker_trade`
   (`:44-46`) from Task 2's runs. **Every number is replaced by a measured one. No value is
   carried forward, adjusted, or estimated.**
4. **Record the module distinction** — `objective.py` vs `governed_adapter.py`, which reaches
   which, and that their budget semantics differ — inside the block, so the next reader does not
   repeat the conflation that produced both the original wrong correction and the ledger's wrong
   cause line.

**A measured fact that reframes part 3, and must be stated in the rewritten block:** the existing
`solver:reproducibility` claim was measured at `max_deterministic_time=1.0`, where the
*deterministic* ceiling binds first — and that is what makes it reproducible. **At the shipped
30/30 configuration the wall binds first** (`det_used` was only ~3.6 of 30 at 1 worker), and two
runs of `sample_tiny_input` in that configuration produced *different* round-1 values
(25843341 and 25255815). So single-worker running is **not** reproducible at the shipped budget
today. Raising the worker count therefore does not sacrifice a reproducibility the running system
has; it changes a configuration that was already wall-bound. Say that in the block, with both
numbers.

**What this does not cover:** nothing asserts `SCOPE_CONTROLS` and nothing will after this story
either — no test is added for it. The discipline is procedural: measure first, paste second. Adding
a conformance test for this tuple is deliberately out of scope; it would be a new guard in a story
already changing a hot path, and `test_capability_conformance.py:148`'s scope (capability handlers)
is a deliberate boundary, not an oversight.

### Decision 7 — The deterministic agent double is a `FunctionModel` under `backend/agent/`, selected by configuration, and it becomes the keyless default

This **reverses Story 5.3's Decision 12**, on the authority of
`sprint-change-proposal-2026-09-06.md` §3.5, which assigns the double to 5.3a and leaves 5.4 only
the illustrative half. Do not re-argue it.

Placement is legal and was verified, not assumed: `test_application_and_domain_never_import_evals`
guards `REVERSE_GUARDED_ROOTS = (domain, application)` only
(`tests/architecture/test_evaluation_boundaries.py:9,104`), and
`test_agent_may_import_application_and_domain` asserts `agent/` is the layer that *may* touch the
framework. `evals/doubles.py` is the **shape** reference and is never imported by runtime code — a
runtime that reaches into the eval harness is wrong independently of what the guard checks.

**Selection:** `_configured_model` (`agent/runtime.py:525-547`) resolves `"test"` to
`infer_model("test")` today; add one more literal value that returns the new `FunctionModel`, and
make **that** value the default of `settings.agent_runtime_model`. `"test"` stays selectable —
`tests/test_agent_runtime_adapter.py` passes it explicitly and `evals` uses it via
`test_evaluation_harness.py:77`. Measured blast radius of moving the default: **no test asserts the
default literal**; three documented mentions must move with it (`docs/CONFIGURATION.md:29`,
`docs/GETTING-STARTED.md:28,31`).

**Why the default and not an opt-in:** Story 5.3's AC1 requires the journey be completable from
the one command "with no provider credential required", and AC2 here requires the proof assert
`agent_completed` "driven by a deterministic model double". An opt-in double leaves the
one-command default at `TestModel`, which is measured to fail. `docker-compose.yml:44` already
passes the variable through, so nothing in compose changes.

**What this does not cover:** it does not make the agent's prose a real analysis of Wednesday
outbound coverage. Story 5.4 still owns whether the walkthrough *displays* live-provider output,
and Decision 12's recommended split still applies there.

### Decision 8 — `agent_completed` alone is too weak an assertion; the proof asserts a grounded answer

`terminal_status` returns `agent_completed` when **any** of `grounded_response`, `clarification`,
`resolved_clarification`, `refusal` or `resolved_draft` is present
(`execute_turn.py:115-128`). A double that refuses, or that asks a clarifying question, greens
`agent_run_status == "agent_completed"` while proving nothing about the journey.

**Decision: the double must reach a grounded answer, and the compose proof asserts the activity
kind, not only the status.** `ExecutedTurnOut.activity` is a discriminated union
(`api/schemas.py:367-374`), so the assertion is
`executed.json()["activity"]["activity_type"] == "agent_response"` alongside
`agent_run_status == "agent_completed"`.

**The double's shape, constrained by what is verified:**

* It must call at least one **real governed capability tool** — otherwise it proves the model seam
  and not the loop. `scheduling_inspect` is the fixture-independent choice: its request is
  `SchedulingInspectRequestV1(group=…)` with a defaulted cursor/limit
  (`application/capabilities/scheduling_inspect.py:110-117`) and it names **no record IDs**, which
  is exactly the failure `TestModel` cannot avoid.
* Its final turn calls the answer output tool — `ANSWER_OUTPUT_TOOL = "final_result"`
  (`agent/runtime.py:74`) — with a `GroundedAnswerV1`.
* **Its prose must contain no numeric characters at all**, unless carried by a cited claim.
  `numeric_prose_violation` flags *any* character for which `str.isnumeric()` is true
  (`application/grounding/gate.py:83`), and `ground_answer` raises `UncitedNumericProseError` —
  a `ValueError` subclass that lands on `invalid_output` (`execute_turn.py:252-258`). A zero-claim
  answer of numeral-free prose is accepted by `ground_answer` and is the smallest honest thing that
  reaches `agent_response`.

**What this does not cover:** it does not prove the *draft* path through the model. The compose
proof keeps `_create_deterministic_draft`, which drives the real capability and repository boundary
directly (`compose_proof.py:58-115`); Decision 7 does not replace it and Task 7 does not delete it.

### Decision 9 — No new registered evidence file, and no evidence regeneration unless a recorded count moves

AC2 names no evidence path — contrast Story 5.2's AC2, which named one. So this story does **not**
pay the two-pass three-runner Gate A regeneration that Story 5.2's Decision 9 costed and Story
5.3's Decision 9 avoided.

**But `evidence/story-1.11/gate-a-readiness-report.json` records per-test-file `total`/`passed`/
`skipped`/`failed` counts under each test-backed check** — settled by measurement in Story 5.3's
Debug Log, not assumed. This story adds tests, so counts under
`evidence_convention_and_gate_machinery` and any other affected check **will** move, and a
**single-pass** regeneration is then owed. Task 8 measures whether they moved rather than assuming
either way; if they did, the regeneration follows `docs/EVIDENCE-CONVENTION.md` — code committed
first, measured on a clean tree, generated through the runner, evidence committed separately.

**What this does not cover:** it does not register anything new in `gate_a_checks.py`, so the
registered-evidence set stays at 8 and `test_every_registered_evidence_file_exists_on_disk`'s
ordering trap (Story 5.2's Decision 9, sequencing trap A) does not apply here.

### Decision 10 — Story 5.3 flips to `done` in this story's final commit, and the ledger entries close with it

`sprint-status.yaml` records 5.3 as `in-progress` as an explicit, bounded exception. The mechanism
that ends it is this story restoring the assertions to 5.3's **own** `compose_proof.py`; when they
are green, 5.3's AC1 is satisfied as originally written.

**Decision: one commit flips `5-3-…` to `done`, removes the bounded-exception note, flips `5-3a-…`
to `done`, and closes the three ledger entries** — because splitting them would leave a window in
which the status file and the ledger disagree about whether the composition is proven.

**What this does not cover:** it does not amend Story 5.3's AC1 or any PRD, architecture or UX
artifact, and it does not touch the other open ledger rows.

---

## Tasks / Subtasks

- [ ] **Task 1 — Re-verify the creation measurements and the candidate gate before changing anything (AC: #1)**
  - [ ] Re-run the suite baselines on a **clean tree** at `167cd29` with Docker PostgreSQL up: backend default, `-m postgres`, `tests/architecture`, `tests/test_evidence_convention.py`, `tests/test_gate_a_readiness.py`. Record drift in the Dev Agent Record; do not silently adopt different numbers. **Keep the tree clean while measuring** — an untracked file spends the one permitted skip (see *Measured at creation*).
  - [ ] Confirm the blocking mechanism still holds at the shipped defaults: a governed solve at `num_search_workers=1`, wall 30, det 30 leaves round 2 unentered because round 1 consumes the wall. If it converges on this machine, **stop and re-plan** — Decision 1's premise has changed.
  - [ ] Confirm `ClearHints`, `AddHint` and `GetIntVarFromProtoIndex` exist on the pinned `ortools==9.11.4210`, and that `len(round-1 snapshot) == len(model.Proto().variables)` on both fixtures.
  - [ ] Re-verify the candidate gate: apply Task 2's hint locally **without committing it**, drive `GovernedSchedulerAdapter` on both fixtures and confirm `require_hard_constraints` **passes** and `calculate_candidate_metrics` returns. Record assignment/worker/shift counts and `total_cost`. Per Decision 5 a violation here is a re-plan signal, not an expected outcome.

- [ ] **Task 2 — Seed round 2 from the round-1 snapshot, on both implementations (AC: #1, per Decision 2)**
  - [ ] `backend/engine/governed_adapter.py:249-251` — the blocking fix. Clear existing hints and add the round-1 snapshot as a solution hint before the second `solver.Solve(model)`, guarded on the snapshot/variable-count equality.
  - [ ] `backend/engine/cpsat/objective.py:63-64` — the same change, for consistency. **Attach no measured claim to this path.**
  - [ ] Add a focused test proving round 2 is hinted: on `sample_tiny_input` at a worker count where round 1 converges, the hinted solve reaches `OPTIMAL`/`FEASIBLE` where the unhinted one returns `UNKNOWN`. This is the story's central behaviour and it must have a test that fails without the hint.

- [ ] **Task 3 — Move the solver default so round 2 is reachable, and measure the pair (AC: #1, per Decisions 3 and 4)**
  - [ ] Raise `solver_num_search_workers` in `backend/settings.py` (both the dataclass default at `:133` and the `_positive_int` fallback at `:384-388`) to the value Task 3's measurement supports. Start at **8**; 2 and 4 were measured non-convergent. Leave `solver_wall_time_limit_seconds`, `solver_max_deterministic_time`, `solver_seed` and `solver_engine_name` untouched (Decision 4).
  - [ ] Measure through `GovernedSchedulerAdapter` at the new defaults, on **both** shipped fixtures, **≥3 runs each**. Record: terminal status, `round1_value`, `round2_value`, assignment count, distinct-member count, wall time, and **the assignment set** (not just the counts — that is what `SCOPE_CONTROLS`' reproducibility claim is about). Record the host's core count beside the worker count.
  - [ ] **If round 2 still does not reach `OPTIMAL`/`FEASIBLE`**, escalate in this order and record why each step was taken or skipped: (1) raise the worker count further; (2) `solver.parameters.fix_variables_to_their_hinted_value` or `repair_hint`, so round 2 starts from a known-feasible point rather than a suggested one; (3) **stop and report**. Do **not** reach for a larger wall budget — 60s and 120s were both measured and neither helped (Decision 4).

- [ ] **Task 4 — Reconcile `SCOPE_CONTROLS` from Task 3's measurements (AC: #1, per Decision 6)**
  - [ ] `backend/engine/governed_adapter.py:38-68`: restore `solver:wall_total`; rewrite the `NOT COVERED: any terminal status other than UNKNOWN` entry; rewrite `solver:reproducibility` and `solver:multi_worker_trade` from Task 3's runs with **no value carried forward**.
  - [ ] State in the block that the shipped 30/30 configuration is **wall-bound, not deterministic-bound**, and that single-worker running was measured non-reproducible there (two round-1 values on the same fixture) — so the reproducibility claim belongs to the deterministic-ceiling configuration, not to the worker count.
  - [ ] Record the `objective.py` / `governed_adapter.py` distinction and which caller reaches which.

- [ ] **Task 5 — A deterministic agent double that completes the turn (AC: #2, per Decisions 7 and 8)**
  - [ ] Add a `pydantic_ai` `FunctionModel` double under `backend/agent/`, shaped on `evals/doubles.py` but **not importing it**. It calls a real fixture-independent capability tool (`scheduling_inspect`, whose request names no record IDs), then answers through `ANSWER_OUTPUT_TOOL` with a `GroundedAnswerV1` whose prose carries **no numeric characters**.
  - [ ] Extend `_configured_model` (`agent/runtime.py:525-547`) with one new literal value returning it, and make that value the default of `settings.agent_runtime_model` (`settings.py:94`, `:305`). Keep `"test"` selectable.
  - [ ] Update `docs/CONFIGURATION.md:29` and `docs/GETTING-STARTED.md:28,31`, which document `test` as the keyless default.
  - [ ] Correct Story 5.3's Decision 12 **in place** in `5-3-run-shiftmind-reproducibly-from-one-command.md`: `TestModel` does not synthesise usable values here, and the runtime-selectable double it rejected is now shipped by this story on the change proposal's authority.
  - [ ] Test the double directly through `PydanticAIAgentRuntime` — not only through the compose proof, which is opt-in and would leave this untested in CI.

- [ ] **Task 6 — Run the blast radius empirically, and investigate rather than expect (AC: #1)**
  - [ ] Full backend suite. Baseline **1615 passed / 1 skipped / 7 deselected** on a clean tree.
  - [ ] `backend/tests/test_governed_solver_adapter.py:215` (`wall_time_limit_seconds=0.25`, 1 worker) — expected unaffected: round 1 cannot converge at 0.25s, so the early return at `governed_adapter.py:239-243` fires before the hint. **Verify, do not assume.**
  - [ ] `backend/tests/test_governed_solver_adapter.py:144` — the reproducibility test at `max_deterministic_time=1.0`, 1 worker. Expected unaffected: round 2 is never entered at that ceiling, so the hint is unreachable and the snapshot path it asserts is unchanged. It passes `num_search_workers=1` explicitly, so Task 3's default move does not reach it. **Verify.**
  - [ ] `backend/tests/test_penalty_calibration.py` — the only real-solve consumer of `objective.py`, at `SolverConfig(time_limit_s=10)` on synthetic problems. Its prose documents non-convergent `UNKNOWN`; the hint may change that. Update the prose if the behaviour changed; do not weaken an assertion to keep it green.
  - [ ] Every other `round2` / `UNKNOWN` / `total_cost` match feeds a synthetic `SolverOutcomeV1` (`test_finalize_schedule_run.py:150-153`, `test_job_leasing_postgres.py:1091`, `test_run_snapshot_contracts.py:62`, `test_schedule_runs_api.py:100`, `test_lease_next_job.py:164`, `architecture/test_schedule_run_state_machine.py`) and should be indifferent. **The expectation is "investigate any breakage", not "expect breakage".**
  - [ ] **CI `--min-passed` and `--max-skipped` are floors and ceilings and are not edited.** If the suite cannot meet them, the fix is wrong.

- [ ] **Task 7 — Restore the compose proof and Flow 1's tail (AC: #2)**
  - [ ] `backend/tests/compose_proof.py:279-283` — tighten the run assertion from `{solver_completed, solver_timed_out, solver_infeasible}` to **`solver_completed`**, and remove the inline deferral comment at `:258-272`.
  - [ ] `:206-209` — tighten the agent assertion to **`agent_completed`**, add `activity["activity_type"] == "agent_response"` (Decision 8), and remove the deferral comment at `:197-205`. Keep the existing `reason != "provider_error"` assertion.
  - [ ] `:285-292` — re-add the approval leg against the candidate the real solve produced. Decision 5 of Story 5.3 records that this was written and removed; recover it from that work. The routes and their required inputs, verified at creation:
    - `POST /api/v1/approvals` with an `Idempotency-Key` header and `{schedule_run_id, expected_resource_version, expected_baseline_schedule_version}`. `expected_resource_version` comes from the run GET the poll loop already performs (`ScheduleRunOut.resource_version`, `api/schemas.py:464`); `expected_baseline_schedule_version` is **`null`** on a fresh stack and must be sent explicitly — `ApprovalRequestIn` gives it no default on purpose (`api/schemas.py:220-223`).
    - `POST /api/v1/approvals/{approval_id}/decision` with an `Idempotency-Key` and `{"decision": "approve", "expected_resource_version": …}` from `ApprovalOut.resource_version` (`api/schemas.py:250`).
    - `GET /api/v1/approvals/provenance?schedule_run_id=…` returns `DecisionProvenanceOut` with `items` — assert the timeline is non-empty and links the run.
    - Both write routes require `scheduling_baseline_enabled` in the feature policy (`api/routers/approvals.py:343`, `:381`); it defaults `True` (`settings.py:153`) and compose sets nothing, so no configuration change is needed — but a 403 here means that flag, not the candidate.
  - [ ] Leave `TERMINAL` (`:36-42`) as the full terminal set — it ends the poll loop; the assertion below it discriminates. Its docstring already says so.
  - [ ] Re-check the 120s poll deadline (`:248`) and the proof's 60.54s runtime against Task 3's timings. A 30s solve plus lease pickup fits; record the new runtime.
  - [ ] Assess whether `docs/TESTING.md` / `docs/DEVELOPMENT.md` need updating — only if the proof's runtime or invocation changed materially.

- [ ] **Task 8 — Close out (AC: #1, #2, per Decisions 9 and 10)**
  - [ ] Measure whether `evidence/story-1.11/gate-a-readiness-report.json`'s recorded per-file counts moved. If they did, one **single-pass** regeneration is owed: commit the code, measure on a clean tree, generate through the runner, commit the evidence **separately**.
  - [ ] Close the three `deferred-work.md` entries at `:719-806` using the strikethrough + **CLOSED `<date>` (Story 5.3a)** convention already used at `:90`, `:94`, `:106`, `:188`. Correct the first entry's cause statement once more: the measured cause at the shipped defaults is that **round 1 never converges**, so round 2 is never entered — the missing hint is the second half, not the first.
  - [ ] In one commit: flip `5-3-run-shiftmind-reproducibly-from-one-command` to `done`, remove the bounded-exception note above it in `sprint-status.yaml`, and flip `5-3a-make-a-real-solve-reach-a-candidate` to `done`.
  - [ ] Record the mutation table (Epic 4 retro A1) in the Dev Agent Record before review.

---

## Dev Notes

### Traps — the quietest first

1. **The hint is code that never runs at the shipped defaults.** This is the trap that would cost
   the most: implement Task 2, watch the compose proof still report `solver_timed_out`, and
   conclude the hint does not work. It works — measured `FEASIBLE` on both fixtures — but only once
   round 1 converges, which needs Task 3. Do Task 3 before drawing any conclusion from Task 2.

2. **More wall time is the obvious lever and it is measured wrong.** 120s at 1 worker still did not
   converge round 1; 60s at 8 workers returned the identical `round2_value` as 30s. The change
   proposal lists raising the wall budget as escalation step 2; that guidance predates this
   measurement. Raising it also silently raises the required `lease_seconds` floor
   (`settings.py:399`, `:405-409`).

3. **`solver_completed` is not a candidate.** `require_hard_constraints` runs after it and a single
   failure downgrades the run to `solver_failed` / `hard_constraint_violated`. It passed on both
   fixtures at creation, so a violation means something changed — read Decision 5's rounding note
   before assuming a solver bug.

4. **`agent_completed` greens on a refusal and on a clarification.** `terminal_status`
   (`execute_turn.py:115-128`) accepts any of five outcome fields. Assert the activity kind too, or
   a double that politely declines will satisfy AC2's letter.

5. **Any numeral in the double's prose fails the turn.** `numeric_prose_violation` flags every
   character where `str.isnumeric()` is true — superscripts and vulgar fractions included — and the
   resulting `UncitedNumericProseError` is a `ValueError`, which `_classify` turns into
   `invalid_output`, the exact failure this story exists to remove.

6. **`SCOPE_CONTROLS` is asserted by nothing.** No test reads the tuple in `governed_adapter.py`,
   and it is not an `evidence/**/*.json` file, so a stale measured claim there ships green. That is
   the reason for *more* care, not less. Measure first, paste second.

7. **The reproducibility claim you are replacing was measured in a different configuration.** It
   used `max_deterministic_time=1.0` at 1 worker, where the deterministic ceiling binds first. The
   shipped 30/30 configuration is wall-bound, and was measured *non*-reproducible. Do not copy the
   old sentence's framing onto the new numbers.

8. **A dirty tree costs the one permitted skip.** `test_evidence_binding.py:570` skips on any
   uncommitted change; CI's ceiling is `--max-skipped 1` and the unconditional
   `test_scheduling_inspect.py:323` skip already spends it. Remove scratch files before measuring.

9. **The compose proof is opt-in and non-required.** Its CI job does not gate a PR, so a solver
   regression that only the composed stack shows will not redden anything. This is why Task 3's
   machine-dependence risk must be recorded, not assumed away.

10. **The two lexicographic implementations are not being unified.** That is explicitly out of scope
    (change proposal §6) — it turns a one-line behaviour change into a two-path refactor, the exact
    risk Decision 5 of Story 5.3 split this story out to avoid.

### Files being modified — read these before editing

| File | What it does today | What this story changes | What must be preserved |
|---|---|---|---|
| `backend/engine/governed_adapter.py` | Sole governed CP-SAT boundary. `_solve_lexicographic_governed` (`:195`) runs two rounds under one decreasing wall + deterministic budget; snapshots round 1 at `:245`; re-`Solve()`s at `:258` with no hint | Adds the round-2 hint at `:249-251` (Task 2); rewrites four `SCOPE_CONTROLS` entries (Task 4) | `apply_remaining_budget`'s `"wall"`/`"deterministic"` distinction — AD-7 requires wall exhaustion (`solver_timed_out`) stay distinguishable from any other ceiling (`budget_exhausted`); the `_GovernedLexResult.snapshot` fallback path and `value()`; the digest re-verification via `SolverInputSource`; the `use_deterministic_time` split; every `SCOPE_CONTROLS` entry this story does not name |
| `backend/engine/cpsat/objective.py` | Legacy lexicographic solve. Sets `max_time_in_seconds` **once** (`:47`), so OR-Tools grants each round a full budget | The same one-line hint at `:63-64`, with **no measured claim attached** | The `LexResult.snapshot` fallback and its docstring, which explains why the snapshot exists |
| `backend/settings.py` | `solver_num_search_workers` defaults to `1` at `:133` and `:384-388`; `minimum_lease_seconds = ceil(wall × 4)` at `:399` | Raises the worker-count default only (Task 3) | `solver_wall_time_limit_seconds`, `solver_max_deterministic_time`, `solver_seed`, `solver_engine_name`; the `LEASE_SECONDS` floor check at `:405-409`; `repr=False` on every credential-bearing field (Story 5.2, T-04-01) |
| `backend/agent/runtime.py` | `_configured_model` (`:525-547`) maps `"test"` → `infer_model("test")` and `<provider>:<model>` → a provider model; `ANSWER_OUTPUT_TOOL = "final_result"` (`:74`) | Adds one literal value returning the new double (Task 5) | The `provider:model` parse and its `ValueError`; `include_content=False` and `include_binary_content` handling (Story 5.2 AC1); `ANSWER_OUTPUT_TOOL`'s byte-identical name (`:72-74` explains why); the output-validator wiring for `numeric_prose_violation` |
| `backend/tests/compose_proof.py` | Opt-in `@pytest.mark.compose` bring-up: OIDC sign-in, session, CSRF, catalogue, agent turn, deterministic draft, enqueue, poll to terminal | Tightens two assertions, removes two deferral comments, adds Flow 1's tail (Task 7) | `_create_deterministic_draft` and its use of the real capability + repository boundary; `TERMINAL`'s full set and its docstring; the `check=False` teardown (a teardown that exits non-zero must not raise over the real assertion); the distinct `:compose-proof` image tags at `:128-129` and the reason recorded above them; the `snapshot_input_missing` / `snapshot_digest_mismatch` reason assertions, which are what catch an RLS mis-wiring |
| `backend/tests/test_governed_solver_adapter.py` | Two real-solve tests: reproducibility at det 1.0 / 1 worker (`:144`), and the 0.25s wall ceiling (`:215`) | Nothing expected; **both must be re-run and confirmed** (Task 6) | Both tests' explicit `num_search_workers` arguments — they insulate the tests from Task 3's default move and must not be replaced by settings lookups |
| `backend/tests/test_penalty_calibration.py` | Three real solves through `create_engine` → `objective.py` at `time_limit_s=10`; its module docstring documents non-convergent `UNKNOWN` | Prose only, and only if Task 2 changed the behaviour (Task 6) | The synthetic problem builders and the calibration assertions themselves |
| `docs/CONFIGURATION.md`, `docs/GETTING-STARTED.md` | Document `AGENT_RUNTIME_MODEL`'s default as `test` (`CONFIGURATION.md:29`; `GETTING-STARTED.md:28,31`) | The default's name moves (Task 5) | The live-provider override instructions and the "never required release evidence" framing — AC1 of Story 5.3 depends on both |
| `_bmad-output/implementation-artifacts/deferred-work.md` | The ledger | Closes `:719-806`'s three entries and corrects the first one's cause (Task 8) | Every other row, including `:50`, `:494`, `:521`, `:663`, `:669`, `:679`, `:684`, `:687`, `:689`, `:19-28` and the five other 5.3-review entries above `:719` |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | Records 5.3 `in-progress` with a bounded-exception note, 5.3a `ready-for-dev` | Both to `done`; the note removed (Task 8) | Every other key, the STATUS DEFINITIONS block, and all surrounding notes |

**New files:** the agent double under `backend/agent/`, its focused test under `backend/tests/`, and
the round-2 hint test under `backend/tests/`.

**Explicitly not touched:** `.github/workflows/ci.yml`; `backend/scripts/gate_a_checks.py`;
`backend/scripts/evidence_binding.py`'s `audit_evidence_file`; `docs/API.md`;
`application/use_cases/finalize_schedule_run.py`; `application/scheduling/hard_constraints.py`;
`engine/cpsat/builder.py`; any migration, route, or frontend file.

### The commit plan

| # | Commit | Contents | State after |
|---|---|---|---|
| 1 | `fix(story-5.3a): seed round 2 from the round-1 solution` | Tasks 2 and 3 — both halves of the fix and their tests. They ship together because neither is observable alone (Decision 1) | Tree clean, full suite green |
| 2 | `docs(story-5.3a): re-measure the governed solver scope controls` | Task 4, from commit 1's measurements | Tree clean, suite green |
| 3 | `feat(story-5.3a): complete the agent turn with a deterministic double` | Task 5 and its documentation corrections | Tree clean, suite green |
| 4 | `test(story-5.3a): prove Flow 1 end to end on the composed stack` | Task 7 | Tree clean, suite green, compose proof green |
| — | *(only if Task 8 found moved counts)* | Regenerate the readiness report on a clean tree at commit 4 | — |
| 5 | *(conditional)* `evidence(gate-a): refresh after story 5.3a` | The regenerated report alone | Tree clean |
| 6 | `docs(story-5.3a): close the ledger and the composition milestone` | Task 8's ledger closes and both status flips, together (Decision 10) | Tree clean |

Commit 2 is separate from commit 1 so a reviewer can check "were the recorded numbers measured from
the shipped code?" against a diff containing nothing but numbers. **Do not generate any evidence
file on a dirty tree.** Note the evidence convention's rule that a recorded commit must touch at
least one code file — Story 5.3 hit this at its final docs-only commit and had to amend
(`deferred-work.md`, "Story 5.3's commit 4 no longer matches its message"); plan for it here rather
than amending afterwards.

### Testing requirements

* Backend tests in `backend/tests/`; architecture guards in `backend/tests/architecture/`. Absolute
  imports from the backend root (`conftest.py` puts it on `sys.path`).
* Run with `uv run --frozen pytest -q` from `backend/`. `addopts = -m "not live"` stays. Docker
  PostgreSQL 18 must be up for the default suite to be comparable to the creation figures.
* **Every new guard needs a synthetic violating-source case**, matching
  `test_each_guard_detects_synthetic_violating_source`'s convention. The hint test satisfies this
  naturally: it must be red without the hint.
* The mutation table in the Dev Agent Record is required before review (Epic 4 retro A1). Rows worth
  planning for now: removing the `AddHint` loop (the round-2 hint test must redden); removing the
  snapshot/variable-count guard and feeding a mismatched snapshot; reverting
  `solver_num_search_workers` to 1 (the compose proof must redden, and no unit test should — which
  is itself the finding that the default move is only covered by an opt-in proof); making the
  double answer with a numeral in prose (the turn must reach `invalid_output`); making the double
  refuse instead of answer (`agent_run_status` stays `agent_completed`, so only the
  `activity_type` assertion reddens — this row proves Decision 8 was necessary).
* No new golden case, no change to `MVP_PRODUCT_CAPABILITIES`, no change to the four pinned
  injection case ids, no new frontend component or route, and **no edit to any CI count flag**.

### Project structure notes

`engine/` is the declared home for solver code and `engine/governed_adapter.py` is the sole governed
CP-SAT boundary — the hint belongs there, below the `SchedulerPort` seam, and is invisible to
`application/` and `domain/` (AD-1/AR1). `agent/` is the only layer permitted to construct a
framework model, which is why the double lives there and not in `application/` (guarded) or
`evals/` (a harness, not a runtime). `settings.py` is the single supplier of solver ceilings —
AD-7 is explicit that "application configuration, not the model" sets solver duration — so the
worker count moves there and nowhere else. `backend/tests/compose_proof.py` stays Story 5.3's
artifact; this story edits it rather than adding a parallel proof.

### Open questions — neither blocks this story

1. **Should `SCOPE_CONTROLS` blocks outside capability handlers be asserted by a test?** Nothing
   reads `governed_adapter.py`'s tuple, which is why it carried a wrong correction for a full story.
   Decision 6 deliberately does not add one here. **Revisit trigger:** the first story that finds a
   second stale `SCOPE_CONTROLS` block, or a convention pass over `docs/EVIDENCE-CONVENTION.md`.

2. **Should the compose proof become a required CI gate?** Story 5.3's Decision 14 said no on cost
   and marker-machinery grounds, and its open question 1 already carries this. This story sharpens
   the trigger: the solver default is now covered *only* by that opt-in proof. **Revisit trigger:**
   unchanged — the first time the one-command start is found broken by someone other than its
   author, or Epic 6, which needs a hosted equivalent anyway.

### References

* AC text, NFR21/NFR26, AR1 — `_bmad-output/planning-artifacts/epics.md:115,125,147,1445-1473`
* AD-7 (closed state machines, configuration owns solver duration, candidate only from feasible completion) — `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:84-90`
* The change proposal that inserted this story, its four corrections of record, and the approved task scope — `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-06.md` §2.1-2.5, §3.5, §3.6, §4.4, §6
* The three owned ledger entries, their measurements and the corrected cause line — `_bmad-output/implementation-artifacts/deferred-work.md:719-806`
* Story 5.3's Decision 5 (why this story exists), Decision 12 (now superseded), Decision 14 (the opt-in proof), Trap 1 (the RLS reason code), and its Review Findings D4 — `_bmad-output/implementation-artifacts/5-3-run-shiftmind-reproducibly-from-one-command.md:430-468,495-516,590-600,851-905`
* Flow 1, the primary journey and its ending — `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md:228-238`
* Evidence rules, the monotonicity principle, the `passed` contract — `docs/EVIDENCE-CONVENTION.md`
* Demand family/unit dimensional model (no metric is computed or added here; cited per the standing rule) — `docs/DOMAIN-MODEL.md` §1, §2, §3
* Demonstrated-red definition and the mutation-table requirement — `_bmad-output/implementation-artifacts/epic-4-retro-2026-09-02.md` §4, §6 A1
* CI count floors and the single permitted skip — `.github/workflows/ci.yml:168-179`

---

## Dev Agent Record

### Agent Model Used

### Implementation Plan

### Debug Log References

### Demonstrated-red mutation table (retro A1 — required before review)

| Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|

### Completion Notes List

### File List

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-06 | Story created at `167cd29`. Ten decisions recorded. **The change proposal's central premise was corrected by measurement at creation:** the round-2 hint is not the blocking fix at the shipped defaults, because at `num_search_workers=1` round 1 consumes the entire shared wall budget on both fixtures and round 2 is never entered — measured at 30s and again at 120s, and at 2 and 4 workers, all non-convergent. Both halves of the fix are therefore required and each was measured necessary in isolation (8 workers without the hint → `UNKNOWN`; 1 worker with the hint → round 2 unreachable), and the proposal's escalation step of raising the wall budget was measured insufficient rather than left as a contingency. Two further facts were measured rather than deferred to review: `require_hard_constraints` **passes** on the hinted round-2 solution for both fixtures, so `solver_completed` really does yield a candidate — the largest unnamed risk in the proposal; and the shipped 30/30 configuration is wall-bound, not deterministic-bound, so single-worker running is already non-reproducible there and the worker-count change sacrifices no reproducibility the running system has. The proposal's stated suite baseline (1614/2/7) was reproduced as a dirty-tree artefact and corrected to **1615/1/7**. Decision 8 was added beyond the proposal's scope after reading `terminal_status`: `agent_completed` is returned for a refusal or a clarification, so the compose proof must assert the activity kind or a politely declining double would satisfy AC2's letter. |
