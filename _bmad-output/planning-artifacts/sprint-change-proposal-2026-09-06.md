# Sprint Change Proposal — 2026-09-06

**Trigger:** Story 5.3's code review built and ran the composed stack for the first time and
measured that no schedule run reaches `solver_completed`.
**Scope classification:** **Moderate** — one new story inserted into an in-flight epic, one
in-code measured-claim block corrected, no PRD/architecture/UX change.
**Routing:** Product Owner / Developer (backlog insertion, then story execution).
**Decided with:** Minh, 2026-09-06.

---

## 1. Issue Summary

### What happened

Story 5.3 assembled the first runnable composition of ShiftMind. Its code review did something no
prior story could: it **built the images and drove the running stack over HTTP**. Two assertions
that had been tightened by reading went red under measurement, and neither was a defect in the
patch being reviewed:

1. `status == "solver_completed"` → actual `solver_timed_out` / `budget_exhausted`
2. `agent_run_status == "agent_completed"` → actual `agent_failed` / `invalid_output`

### Why the first one blocks a downstream story

`finalize_schedule_run` (`backend/application/use_cases/finalize_schedule_run.py:41-58`) creates a
candidate **only** when the run reaches `solver_completed`. A timed-out run carries none, so
`POST /approvals` has nothing to act on. Flow 1's tail — request approval → approve as baseline →
read the provenance timeline — is therefore **unreachable from a real solve**.

Story 5.4's AC1 (`epics.md:1455-1456`) requires the walkthrough walk the Wednesday-coverage journey
"with real output" and that "every claim it makes about behavior is reproducible by the Story 5.3
command". Flow 1 ends at "approve as baseline → read the Provenance timeline". **5.4 has nothing to
describe until this is closed.**

### Corroborating evidence already on `main`

- `deferred-work.md:719-780` — three entries under *"Deferred from: code review of story-5.3
  (2026-09-06) — measured by running the composed stack"*, carrying measurements, cause, blast
  radius and owner.
- `5-3-run-shiftmind-reproducibly-from-one-command.md:915` — Decision 5, which reversed Decision 4
  after measurement and named Story 5.3a as owner.
- `backend/tests/compose_proof.py:262-292` — the loosened assertion, with the reason recorded inline.
- Commits `fd55130`, `aaa36d5`, `0bb90c8`, `b9c045e`.

### Categorization

**Technical limitation discovered during implementation.** Not a requirements misunderstanding and
not a strategic pivot: the requirement was correct, the mechanism was never exercised end to end
until composition existed, and composition is precisely what Story 5.3 delivered.

---

## 2. Correction of Record — read before implementing

The investigation was done at review and is not re-derived here. However, **three claims carried
forward from the review's write-up do not survive reading the code**, and each changes what 5.3a
must do. These were verified against `main` after PR #28 on 2026-09-06.

### 2.1 The blocking defect is in `governed_adapter.py`, not `objective.py`

There are **two** lexicographic solve implementations:

| | `engine/cpsat/objective.py:44`<br>`solve_lexicographic` | `engine/governed_adapter.py:195`<br>`_solve_lexicographic_governed` |
|---|---|---|
| **Reached by** | `api/deps.py:68` `create_engine("cpsat")` — legacy routes, `run.py` CLI, `scripts/calibrate_penalties.py` | `worker/composition.py:21` — **the worker, `finalize_schedule_run`, and the compose proof** |
| **Wall budget** | `max_time_in_seconds` set **once** (`:47`); OR-Tools applies it per `Solve()`, so each round receives a full budget | `apply_remaining_budget()` (`:209-227`) recomputes `wall_time_limit_seconds - elapsed` before each round — **one shared, decreasing budget** |
| **Round-1 snapshot** | taken `:58`, discarded as hint at `:64` | taken `:245`, discarded as hint at `:250-251` |

Both carry the same defect. Only the governed one is on the path that blocks Flow 1. **Patching
`objective.py:64` alone would leave the compose proof, the worker and Story 5.4 exactly as blocked
as they are today.**

### 2.2 The `CORRECTED` note in `SCOPE_CONTROLS` is wrong in the opposite direction

`governed_adapter.py:51-61` states that the *"one decreasing wall-time budget"* claim at `:47-48`
"does NOT match objective.py, which sets max_time_in_seconds ONCE on a shared CpSolver".

`SCOPE_CONTROLS` lives in and documents **`governed_adapter.py`**, whose budget *is* shared and
decreasing (`:222`, `:224-227`). The original `:47-48` claim was **accurate for the module it
describes**. The `120s → 133.8s` measurement that appeared to disprove it was taken through
`objective.py` — a module `SCOPE_CONTROLS` does not describe.

**Reconciling this means correcting the correction, not deleting the original line.**

### 2.3 The measured facts do not transfer to the governed path

The brief's measurements (`FEASIBLE` with a hint on both fixtures) were taken at **30s per
`Solve()`** — `objective.py` semantics. On the governed path, round 2 receives only
`30s − round-1 elapsed` (`settings.py:135`, `solver_wall_time_limit_seconds = 30.0`), sharing a
`max_deterministic_time = 30.0` ceiling (`settings.py:134`) as well.

**5.3a must re-measure on the governed path and must not assume the hint alone is sufficient
there.** A contingency is specified in §4, Task 2.

### 2.4 The blast radius is narrower than recorded

The ledger records "12+ test files read `round2`/`UNKNOWN`/`total_cost`". Of the files matching,
only these run a **real** solve:

| File | What it asserts | Expected impact |
|---|---|---|
| `test_governed_solver_adapter.py:235` | `solver_status == "UNKNOWN"` at a deliberate `wall_time_limit_seconds=0.25` ceiling, `wall_time_seconds <= 0.40` | **None expected** — the ceiling is too tight for round 1 to converge; a hint cannot exist. Must be re-run, not assumed. |
| `test_penalty_calibration.py` | documents non-convergent `UNKNOWN` on a large fixture | Re-run; may need its prose updated |
| `test_lease_next_job.py:164` | `labels["solver_status"] == "UNKNOWN"` | **None** — `_Scheduler()` is a stub, not a real solve |

Every other match feeds a synthetic `SolverOutcomeV1` (`test_finalize_schedule_run.py:150-153`,
`test_job_leasing_postgres.py:1091`, `test_run_snapshot_contracts.py:62`,
`test_schedule_runs_api.py:100`, `architecture/test_schedule_run_state_machine.py`) and is
indifferent to search behaviour. This narrows the risk but **does not remove the requirement to run
the full suite** — it changes the expectation from "expect breakage" to "investigate any breakage".

### 2.5 `SCOPE_CONTROLS` in `governed_adapter.py` is unasserted by any test

`test_capability_conformance.py:148` requires `SCOPE_CONTROLS` only of capability-handler modules;
`governed_adapter` is not one, and no test reads its tuple. It is also **not** an
`evidence/**/*.json` file, so `docs/EVIDENCE-CONVENTION.md`'s *measure → generate through
`evidence_binding.py`* rule does not literally bind it — only its spirit does.

This is a reason for **more** discipline, not less: nothing in the suite will catch a stale measured
claim there. §4, Task 3 specifies how it is updated.

---

## 3. Impact Analysis

### 3.1 Epic Impact

| Epic | Assessment |
|---|---|
| **Epic 5** | Completable as planned. Requires **one inserted story (5.3a)**, no scope change to 5.0–5.4. |
| **Epic 6** | No impact. Nothing in 5.3a touches hosted composition; `Dockerfile`/registry deferrals stay Epic 6's. |
| **Epics 1–4** | Complete. No change. The solver contract (`SolverOutcomeV1`, the state machine, `finalize_schedule_run`'s candidate rule) is unchanged by 5.3a — only which status a real solve reaches. |

No epic is obsolete, none is newly needed, and no resequencing is required. **Epic 5's internal
order changes only by insertion:** 5.3 → **5.3a** → 5.4.

### 3.2 Story Impact

| Story | Impact |
|---|---|
| **5.3** | Stays `in-progress`. Its `compose_proof.py` assertions are restored by 5.3a; it flips to `done` in that same pass. Its AC1 wording is **not** amended. |
| **5.3a** | **New.** Owns the solver hint fix, the deterministic agent double, the restored compose-proof assertions, and the `SCOPE_CONTROLS` reconciliation. |
| **5.4** | Unblocked by 5.3a. Retains AC1 unchanged. Inherits only the *illustrative* half of the agent-output question (§3.5). |

### 3.3 Artifact Conflicts

| Artifact | Conflict | Action |
|---|---|---|
| **PRD** | None. NFR21/NFR26 (keyless demonstrability) are what 5.3a *restores*, not what it changes. | No edit |
| **Architecture** | None. No component, boundary, contract, schema or API changes. A search hint is an internal solver-strategy detail below the `SchedulerPort` seam. | No edit |
| **UX / `EXPERIENCE.md`** | None. | No edit |
| **`epics.md`** | Needs Story 5.3a inserted between 5.3 and 5.4. | **Edit — §4.1** |
| **`sprint-status.yaml`** | Needs the 5.3a key and a note. | **Edit — §4.2** |
| **`deferred-work.md`** | Three entries name Story 5.3a as owner; they close when 5.3a lands. Additionally, the first entry's cause line names the wrong module (§2.1) and must be corrected now so 5.3a is not implemented against it. | **Edit — §4.3** |
| **`governed_adapter.py` `SCOPE_CONTROLS`** | Records measured claims that become false, plus a `CORRECTED` note that is itself wrong. | **Edit inside 5.3a — §4.4, Task 3** |
| **CI (`.github/workflows/ci.yml`)** | `--min-passed` / `--max-skipped` are floors and ceilings. **Explicitly not edited.** | No edit |
| **`docs/EVIDENCE-CONVENTION.md`** | No change. §2.5 clarifies its scope; it does not alter the convention. | No edit |
| **`docs/TESTING.md` / `DEVELOPMENT.md`** | Only if the compose-proof runtime changes materially. Assess during 5.3a. | Conditional |

### 3.4 Technical Impact

- **Behaviour change on a hot path.** Supplying a hint changes CP-SAT's search. Solutions may
  differ from today's for the same seed. `SCOPE_CONTROLS`' reproducibility claim
  (`round1=247.44352`, `round2=1118241`, "identical … in 3/3 runs") must be **re-measured**, not
  edited to taste.
- **Runtime.** A round 2 that now *finds* a solution may return sooner (it can prove optimality) or
  consume its full remaining budget. The compose proof's 120s poll deadline
  (`compose_proof.py:248`) and the current 60.54s proof runtime should be re-checked.
- **No contract change.** `SolverOutcomeV1`, the run state machine, telemetry labels and the
  candidate-creation rule are untouched.

### 3.5 Decision — the `TestModel` agent turn

**Measured 2026-09-06 through the composed stack's public HTTP route:**
`POST /conversations/{id}/agent-runs/{id}/execute` returns `agent_run_status: "agent_failed"`,
`reason: "invalid_output"`. Cause: `TestModel`'s generated tool arguments cannot name governed
fixture record IDs, so the tool call fails validation.

Story 5.3's Decision 12 asserted that `TestModel` "synthesises schema-conformant values" and that
"the journey completes". The first is wrong and the second follows from it.

**Decision: split it.**

- **5.3a owns the deterministic double.** Story 5.3's AC1 requires the journey complete "against
  deterministic model doubles with no provider credential required". That clause is 5.3's, and
  `TestModel` cannot satisfy it. 5.3a adds a runtime-selectable double (a `FunctionModel` returning
  fixture-valid arguments) and tightens the assertion to `agent_completed`.
- **5.4 owns the illustration.** Whether the walkthrough *displays* live-provider output for the
  agent step is a presentation decision, and Decision 12's recommended split applies there.

**Rationale:** routing all of it to 5.4 would hand 5.4 an unowned collision — its AC1 requires every
behavioural claim be "reproducible by the Story 5.3 command", which a live-provider-only agent step
cannot satisfy alongside 5.3's keyless requirement.

### 3.6 Decision — Story 5.3's status

**Decision: Story 5.3 stays `in-progress` until 5.3a lands, then flips to `done` in the same pass.**

**Mechanism:** 5.3a restores the assertions to `backend/tests/compose_proof.py` — Story 5.3's own
artifact. When those assertions are green, 5.3's AC1 is satisfied as originally written.

**Why not close it `done` now:** the ledger's owner-and-trigger pattern is for work knowingly
deferred, not for recording an AC as met when its "completable end to end" clause is measurably
false.

**Why not amend AC1:** it is a defensible reading that `epics.md:1434-1435` over-reached by
conflating composition with behaviour in a story its own file frames as "a COMPOSITION story, not a
feature story". But editing a frozen AC after measurement reads as goalpost-moving even when it is
not, and the cost of not editing it is bounded: exactly one story.

**Accepted cost:** `in-progress` is defined in `sprint-status.yaml:23` as "Developer actively
working on implementation", and nobody is working on 5.3. This is recorded in the status file as an
explicit, bounded exception (§4.2) rather than left to be rediscovered.

**Nothing is blocked by this choice.** 5.4 waits on 5.3a regardless of what 5.3's key says.

---

## 4. Detailed Change Proposals

### 4.1 `_bmad-output/planning-artifacts/epics.md`

**Insert a new section between Story 5.3 and Story 5.4 (before line 1445, `### Story 5.4`).**
Story 5.3's own section, including its AC1 at `:1434-1435`, is **unchanged**.

```markdown
### Story 5.3a: Make a Real Solve Reach a Candidate [Technical Enabler]

**Inserted 2026-09-06** by `sprint-change-proposal-2026-09-06.md`, from Story 5.3's code review —
the first review able to build and run the composed stack. Numbered `5.3a` rather than renumbering
5.4 because it is a corrective prerequisite discovered inside 5.3, not a member of the portfolio
sequence. It exists because Story 5.3's Decision 5 measured that changing solver search behaviour
did not belong in a composition story.

As a reviewer of this portfolio,
I want a real schedule run to produce a candidate I can approve,
So that the approval, baseline-promotion and provenance features are demonstrable rather than
merely unit-tested.

Blocks: Story 5.4's walkthrough, whose AC1 requires the Wednesday-coverage journey be walked "with
real output" and every behavioural claim be "reproducible by the Story 5.3 command".
Closes: `deferred-work.md`'s three entries under "Deferred from: code review of story-5.3
(2026-09-06) — measured by running the composed stack".

**Acceptance Criteria:**

**Given** a governed schedule run on either shipped fixture at the default solver budget
**When** the worker executes it through `GovernedSchedulerAdapter`
**Then** the run reaches `solver_completed` and `finalize_schedule_run` creates a candidate
**And** the round-2 search is seeded from the round-1 solution rather than restarted from zero,
and the resulting reproducibility characteristics are re-measured and recorded in
`engine/governed_adapter.py`'s `SCOPE_CONTROLS` from that measurement, never hand-edited. (NFR21)

**Given** the composed stack started by the Story 5.3 command
**When** `backend/tests/compose_proof.py` runs
**Then** it asserts `solver_completed` for the schedule run and `agent_completed` for the agent
turn, driven by a deterministic model double that requires no provider credential
**And** it exercises Flow 1's tail end to end — request approval, approve as baseline, read the
provenance timeline — against the candidate that real solve produced. (NFR21, NFR26, AR1)
```

**Rationale:** AC1 pins the behaviour and the evidence discipline; AC2 pins the restored proof. The
"Blocks/Closes" lines make the ledger relationship discoverable from the epic, matching the
convention Story 5.0's insertion note established at `epics.md:1353`.

---

### 4.2 `_bmad-output/implementation-artifacts/sprint-status.yaml`

**At `:2436-2437`:**

```yaml
# OLD
  5-3-run-shiftmind-reproducibly-from-one-command: in-progress
  5-4-publish-the-portfolio-walkthrough: backlog

# NEW
  # 5.3 stays `in-progress` deliberately, though it is merged on `main` (PR #28) with its code
  # review closed. Its AC1 clause "the primary journey is completable end to end against
  # deterministic model doubles" is measurably unsatisfied: no real solve reaches
  # `solver_completed`, so no candidate exists and Flow 1's approval leg is unreachable. Story
  # 5.3a restores the assertions to 5.3's OWN `compose_proof.py`; 5.3 flips to `done` in that same
  # pass. This is a bounded, single-story exception to the "developer actively working" definition
  # above, chosen over closing `done` on an unmet AC and over amending a frozen AC after
  # measurement. See `sprint-change-proposal-2026-09-06.md` §3.6.
  5-3-run-shiftmind-reproducibly-from-one-command: in-progress
  # Inserted 2026-09-06 by `sprint-change-proposal-2026-09-06.md`. Corrective prerequisite from
  # 5.3's code review, not a portfolio-sequence member -- hence `5-3a`, with 5.4's key unchanged.
  # Owns the three ledger entries at `deferred-work.md:719-780`.
  5-3a-make-a-real-solve-reach-a-candidate: backlog
  5-4-publish-the-portfolio-walkthrough: backlog
```

---

### 4.3 `_bmad-output/implementation-artifacts/deferred-work.md`

**Correct the first entry's cause line now** (before 5.3a is implemented against it), and append the
governed-path correction. The measurements are kept and labelled with the module they were taken
through, rather than deleted.

```markdown
# OLD (within the first entry, :~722-730)
  `engine/cpsat/objective.py:64` re-`Solve()`s the same model with a new objective and **no
  hint**, discarding the round-1 solution it snapshotted four lines earlier at `:58`

# NEW
  **CORRECTED 2026-09-06 while drafting `sprint-change-proposal-2026-09-06.md`:** the entry below
  named `engine/cpsat/objective.py:64`. That module carries the same defect but is NOT on the
  blocked path. The worker composes `GovernedSchedulerAdapter`
  (`worker/composition.py:21`), so the run that fails to reach `solver_completed` goes through
  `governed_adapter.py:195` `_solve_lexicographic_governed`, which snapshots at `:245` and
  re-`Solve()`s with no hint at `:250-251`. `objective.py` is reached only by
  `api/deps.py:68 create_engine("cpsat")` -- the legacy routes, the `run.py` CLI and
  `scripts/calibrate_penalties.py`.

  The two also differ in budget, which invalidates the transfer of the measurements below:
  `objective.py:47` sets `max_time_in_seconds` ONCE, so OR-Tools grants each round a full budget
  (this is what the 120s -> 133.8s measurement observed). `_solve_lexicographic_governed`'s
  `apply_remaining_budget()` (`:209-227`) recomputes `wall_time_limit_seconds - elapsed` before
  each round, so round 2 receives only what round 1 left of a shared 30s
  (`settings.py:135`) under a shared 30s deterministic ceiling (`settings.py:134`).
  **The table below was measured through `objective.py` at 30s PER `Solve()` and does not
  transfer. Story 5.3a must re-measure on the governed path.**

  `objective.py:64` re-`Solve()`s the same model with a new objective and **no hint**, discarding
  the round-1 solution it snapshotted four lines earlier at `:58`
```

The three entries otherwise keep their owner (`Story 5.3a`) and trigger. They close when 5.3a lands.

---

### 4.4 Story 5.3a — task breakdown for the story file

`bmad-create-story` will author `_bmad-output/implementation-artifacts/5-3a-make-a-real-solve-reach-a-candidate.md`.
The following is the scope this proposal approves, for that story to carry.

#### Task 1 — Seed round 2 from the round-1 snapshot

- `backend/engine/governed_adapter.py:250-251` — **the blocking fix.** Before the second
  `solver.Solve(model)`, clear any existing hints and add the round-1 snapshot as a solution hint
  over the model's variables.
- `backend/engine/cpsat/objective.py:64` — the same one-line fix, for consistency. **No new measured
  claim is attached to this path**; it is not what `SCOPE_CONTROLS` documents and not what the
  compose proof drives.
- Guard the hint against a snapshot/variable-count mismatch rather than assuming index alignment.

#### Task 2 — Re-measure on the governed path, with a stated contingency

Measure through `GovernedSchedulerAdapter` at the shipped defaults (`wall_time_limit_seconds=30.0`,
`max_deterministic_time=30.0`, seed 42), on **both** shipped fixtures, ≥3 runs each. Record status,
`round1_value`, `round2_value`, assignment count, distinct-member count, wall time.

**If the hint alone does not reach `OPTIMAL`/`FEASIBLE` on the governed path** — plausible, because
round 2 there receives less budget than the `objective.py` measurements assumed — escalate in this
order, taking the first that works and recording why:

1. Set `solver.parameters.fix_variables_to_their_hinted_value` or repair the hint, so round 2 starts
   from a known-feasible point rather than merely a suggested one.
2. Raise `solver_wall_time_limit_seconds` for the composed stack **via configuration**
   (`settings.py:135`), not by editing the shared ceiling — and note that `minimum_lease_seconds`
   derives from it at `settings.py:399`.
3. If neither suffices, **stop and report** rather than widening scope. That outcome is a genuine
   finding about the fixture, and the compose proof's approval leg would need a different route.

#### Task 3 — Reconcile `SCOPE_CONTROLS`

`backend/engine/governed_adapter.py:38-68`:

- **Restore** the `solver:wall_total` claim at `:47-48`. Per §2.2 it was accurate for this module;
  the `CORRECTED` note that disputed it was measured through the wrong one.
- **Rewrite** `:51-61`'s `NOT COVERED: any terminal status other than UNKNOWN` — after Task 2 this
  is false, and it is the entry naming Story 5.3a as owner.
- **Re-measure and rewrite** `solver:reproducibility` (`:40-43`) and `solver:multi_worker_trade`
  (`:44-46`) from Task 2's runs. **Every number is replaced by a measured one. No value is carried
  forward, adjusted, or estimated.** `EVIDENCE-CONVENTION.md`'s generator does not cover this block
  (§2.5) and no test asserts it, so the discipline is procedural: measure first, paste second.
- Record the module distinction from §2.1 in the block, so the next reader does not repeat the
  conflation.

#### Task 4 — A deterministic agent double that completes the turn

- Replace `TestModel` in the composed stack's keyless path with a runtime-selectable double
  (a `pydantic_ai` `FunctionModel`, or equivalent) that emits tool arguments naming **real governed
  fixture record IDs** — the failure `TestModel` cannot avoid, since it synthesises values without
  knowledge of seeded records.
- Selectable at runtime by configuration; the keyless default. No provider credential required.
- Correct Story 5.3's Decision 12 in place: `TestModel` does **not** synthesise usable values here.

#### Task 5 — Restore the compose proof

`backend/tests/compose_proof.py`:

- `:286-291` — tighten the run assertion from `{solver_completed, solver_timed_out,
  solver_infeasible}` to **`solver_completed`**, and remove the inline deferral comment at `:262-284`.
- `:205-208` — tighten the agent assertion from `{agent_completed, agent_failed}` to
  **`agent_completed`**, and remove the deferral comment at `:198-204`.
- `:293-300` — **re-add the approval leg**: request approval → approve as baseline → read the
  provenance timeline, against the candidate the real solve produced. Decision 5 records that this
  was written and removed; recover it from that work.
- Leave `TERMINAL` (`:36-42`) as the full terminal set — it ends the poll loop; the assertion below
  it is what discriminates. Its docstring already says so.
- Re-check the 120s poll deadline (`:248`) and the proof's 60.54s runtime against Task 2's timings.

#### Task 6 — Verify the blast radius empirically

Run the full backend suite. Baseline after PR #28: **1614 passed, 2 skipped, 7 deselected**.

Expected to need attention (§2.4): `test_governed_solver_adapter.py:235` (expected unaffected — its
0.25s ceiling precedes any hint; **verify, do not assume**), `test_penalty_calibration.py` (prose
may need updating). Every other `UNKNOWN`/`round2` match feeds a synthetic outcome and should be
indifferent.

**CI `--min-passed` and `--max-skipped` are floors and ceilings and are not edited.** If the suite
cannot meet them, the fix is wrong.

#### Task 7 — Close out

- Close the three `deferred-work.md` entries at `:719-780` with the closing convention already used
  at `:721`.
- Flip `5-3-run-shiftmind-reproducibly-from-one-command` to `done` **in this same commit**, and
  remove the bounded-exception note added in §4.2.
- Flip `5-3a-make-a-real-solve-reach-a-candidate` to `done`.
- If any `evidence/**/*.json` is regenerated, follow `docs/EVIDENCE-CONVENTION.md`: commit code,
  measure, generate through `backend/scripts/evidence_binding.py`, commit evidence separately.

---

## 5. Path Forward Evaluation

| Option | Verdict |
|---|---|
| **1. Direct Adjustment** — insert one story into Epic 5 | **✅ Selected.** Effort: Medium. Risk: Medium (hot-path search behaviour). Timeline impact: one story before 5.4. |
| **2. Rollback** — revert Story 5.3 | **❌ Not viable.** 5.3 is correct and merged; it *found* this defect. Reverting the composition would destroy the only mechanism that can prove the fix. |
| **3. PRD MVP Review** — reduce scope | **❌ Not warranted.** The MVP is achievable. NFR21/NFR26 are unchanged and a one-line search hint plus a test double is not an MVP-scope question. Invoking it would descope a demonstrable capability over a bug. |

**Justification.** The defect is narrow (two call sites), the blocked value is high (Flow 1's entire
approval → baseline → provenance leg, and Story 5.4 with it), and the risk is real but bounded and
measurable — which is exactly the situation a separate story exists to hold. Decision 5 already
reached this conclusion under measurement; this proposal ratifies it, corrects the module it names,
and specifies the contingency if the fix proves insufficient.

**MVP impact: none.** No requirement is dropped, deferred or reworded.

---

## 6. Implementation Handoff

**Scope: Moderate** — backlog insertion plus story execution.

| Step | Owner | Deliverable |
|---|---|---|
| 1. Apply §4.1–§4.3 (`epics.md`, `sprint-status.yaml`, `deferred-work.md`) | Product Owner / Developer | Backlog reflects 5.3a; the ledger's cause line no longer misdirects |
| 2. Author the story file | `bmad-create-story` | `5-3a-make-a-real-solve-reach-a-candidate.md`, carrying §4.4's tasks and §2's corrections as context |
| 3. Implement | `bmad-dev-story` | Tasks 1–7 |
| 4. Review | `bmad-code-review` | **Must build and run the composed stack**, as 5.3's review did — the only way this class of defect surfaces |
| 5. Unblock | — | 5.3 → `done`, 5.3a → `done`, Story 5.4 proceeds |

### Success criteria

1. A real governed solve on both shipped fixtures reaches `solver_completed` and produces a candidate.
2. `compose_proof.py` asserts `solver_completed` **and** `agent_completed`, and walks Flow 1's tail
   against that real candidate.
3. `SCOPE_CONTROLS` carries only freshly measured numbers, with the `objective.py` /
   `governed_adapter.py` distinction recorded.
4. Full backend suite green against CI's unmodified floors and ceilings.
5. All three `deferred-work.md:719-780` entries closed.
6. Story 5.4 can walk the Wednesday-coverage journey with real output.

### Explicitly out of scope

- Unifying the two lexicographic implementations (considered and rejected — turns a one-line
  behaviour change into a two-path refactor, the exact risk Decision 5 split 5.3a out to avoid).
- Editing CI `--min-passed` / `--max-skipped`.
- Amending Story 5.3's AC1, or any PRD, architecture or UX artifact.
- The walkthrough's presentation of live-provider agent output (Story 5.4, per §3.5).
- Every other open ledger entry, including the postgres healthcheck race, base-image digest pinning
  and the undeclared `httpx` import — all carry different owners and triggers.

---

## Appendix — Change Navigation Checklist

| § | Item | Status |
|---|---|---|
| 1.1 | Triggering story identified — Story 5.3, code review 2026-09-06, PR #28 | [x] Done |
| 1.2 | Core problem defined — technical limitation found during implementation | [x] Done |
| 1.3 | Evidence gathered — ledger, Decision 5, compose proof, four commits, source read on `main` | [x] Done |
| 2.1 | Epic 5 completable as planned | [x] Done |
| 2.2 | Epic change: insert Story 5.3a; no scope change to 5.0–5.4 | [x] Done |
| 2.3 | Remaining epics reviewed — Epic 6 unaffected | [x] Done |
| 2.4 | No epic invalidated; no new epic needed | [x] Done |
| 2.5 | Order changes by insertion only: 5.3 → 5.3a → 5.4 | [x] Done |
| 3.1 | PRD — no conflict; NFR21/NFR26 restored, not changed | [N/A] |
| 3.2 | Architecture — no conflict; change is below the `SchedulerPort` seam | [N/A] |
| 3.3 | UI/UX — no conflict | [N/A] |
| 3.4 | Other artifacts — `SCOPE_CONTROLS`, compose proof, ledger, sprint status | [!] Action-needed → §4 |
| 4.1 | Option 1 Direct Adjustment — Medium effort, Medium risk | [x] Viable |
| 4.2 | Option 2 Rollback — would destroy the proving mechanism | [ ] Not viable |
| 4.3 | Option 3 MVP Review — MVP unaffected | [ ] Not viable |
| 4.4 | Selected: **Option 1** | [x] Done |
| 5.1–5.5 | Proposal sections 1–6 | [x] Done |
| 6.1–6.2 | Checklist and proposal reviewed | [x] Done |
| 6.3 | Explicit user approval | [!] Pending |
| 6.4 | `sprint-status.yaml` updated | [!] Pending approval → §4.2 |
| 6.5 | Handoff confirmed | [!] Pending approval → §6 |
