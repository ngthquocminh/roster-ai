---
baseline_commit: 7eea305
---

# Story 5.0: Compare a Candidate Against the Real Promoted Baseline

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want the comparison to measure my candidate against the schedule that is actually running,
So that I can judge a repair before approving it — and, when no baseline exists yet, be told so rather than shown deltas against nothing.

**This is a corrective insert, not a member of Epic 5's portfolio sequence.** It was created by
`sprint-change-proposal-2026-09-03.md` from Epic 4 retrospective action **A3(i)**, and numbered `5.0`
so that Stories 5.1–5.4 keep their `sprint-status.yaml` keys. It **blocks Story 5.4's creation** and is
independent of 5.1, 5.2 and 5.3 in both directions.

**The defect, in one sentence:** `calculate_comparison` reads its baseline side from
`ScenarioProjectionReader.get_baseline_assignments`, whose PostgreSQL implementation applies its query to a
**hardcoded empty tuple** (`adapters/postgres/scenario_projection.py:643-645` — `_apply_query((), ...)`, a
literal, not an empty result set) — so before the first promotion the comparison renders fabricated deltas
against a schedule in which nobody works, and after the first promotion the EAD-8 guard fires and the
feature disappears permanently. **There is no state in which it works.**

**Scope summary:** one new repository port method, one call-site rewiring inside `calculate_comparison`, two
nullable fields on one published contract, `npm run codegen`, and the frontend rendering of the absent
state. **No migration, no new table, no new column, no new route, no new dependency, no new golden case, no
evidence file, and no Gate A registry change.**

**Depends on, and consumes:** Story 3.2's immutable `schedule_version` aggregate and its `payload` JSONB;
Story 3.8's `calculate_comparison` and `ComparisonSummary`; Story 4.1's `site_baseline` table and
`PostgresSiteBaselineReader`; Story 4.3's `promote_baseline` (the only writer of the pointer) and its
200-with-`comparison: null` degradation boundary.

**Unblocks:** Story 5.4's walkthrough claim that the approve → promote → compare loop is reproducible by the
Story 5.3 command.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions. Every rule
below is recorded somewhere citable; none may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **EAD-8's premise about the pre-promotion state was false and has been amended.** The empty-baseline comparison was never honest; the "all assignments net-new" claim EAD-8 names existed *before* any promotion. The guard itself is sound and is **retained unchanged**. | `ARCHITECTURE-SPINE.md` — EAD-8, **AMENDED 2026-09-03** |
| **EAD-2: an absent `site_baseline` row is the valid "no baseline" state** — never a synthetic baseline row, never a silent rebase. | `ARCHITECTURE-SPINE.md` — EAD-2 |
| **The spine's Deferred row for this work is CLOSED by this story**, and records that the wage and selected-shift prerequisites are **not on this path**: they gate the `schedule_assignment` supply for the *projection* consumer. | `ARCHITECTURE-SPINE.md` — Deferred table, `CLOSED 2026-09-03 by Story 5.0` |
| **UX-DR11: "absent metrics say 'Not computed'."** UX-DR21 requires Results' comparison to be deterministic and model-independent. Story 3.8's own AC2 states the same rule and **has been unmet since it shipped**. | `epics.md:198` (UX-DR11), `epics.md:218` (UX-DR21), `epics.md:1047` (Story 3.8 AC2) |
| **EAD-1: only `site_baseline` holds the pointer, and no module may read or write it directly** other than through its reader/writer. | `ARCHITECTURE-SPINE.md` — EAD-1 |
| **AD-11: application calculators produce or verify every value; the model authors none.** | `ARCHITECTURE-SPINE.md` — AD-11; `epics.md:1042` (Story 3.8 AC1) |
| `outbound`/`inbound` demand is **volume**, `indirect` is **headcount**; assignments carry worker identity but **no `family`**; a metric that reads assignments must not accept a `family` argument; a dimension miss **raises** rather than returning zero. **This story adds no metric and passes no `family` anywhere** — it changes which assignment tuple an existing calculator receives. The rule still binds it: `calculate_candidate_metrics` converts volume rows through the *qualified-worker reference rate*, deliberately candidate-independent, so the **required** side is identical for both schedules by design and its delta is legitimately `0.00`. Do not "fix" that to make the number look interesting. | `docs/DOMAIN-MODEL.md` §1, §2, §3; `candidate_metrics.py:48-51` (the comment stating the rule) |
| **Evidence files: commit code, then measure, then generate through `evidence_binding.py`, then commit evidence separately.** Not exercised here — this story owes no evidence file (Decision 13). | `docs/EVIDENCE-CONVENTION.md`; `.claude/CLAUDE.md` |
| **Manual assistive-technology verification is descoped**; accessibility is proven by automated coverage alone. | `EXPERIENCE.md` — Accessibility Floor; `.claude/CLAUDE.md` |
| **Retro action A1 (`epic-4-retro-2026-09-02.md` §6): a red from incomplete code does not count.** The red must come from **mutating code that is already green**, and the Dev Agent Record must carry a mutation table (mutation, guard, before, after) before the story reaches review. This now loads automatically as a `bmad-dev-story` fact (commit `c4f5de1`), with a paired `bmad-code-review` fact requiring the reviewer to independently re-run at least one row. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml` |
| **A Task cites a Decision; it never re-argues one.** A Decision that states a mechanism must state, in one sentence, what that mechanism does **not** cover. | `_bmad/custom/bmad-create-story.toml`; the `epic-4` action item in `sprint-status.yaml` |

---

## Acceptance Criteria

Verbatim from `epics.md:1365-1385`.

**AC1.**
**Given** a completed candidate whose run snapshot froze a non-null `baseline_schedule_version`
**When** `ComparisonV1` is calculated
**Then** the baseline assignments are read from the `schedule_version` row that identifier names, through a site-scoped repository read
**And** every baseline-side metric, constraint result, and assignment-diff entry derives from those assignments, and `ComparisonV1.evidence_refs` carries a baseline locator for each. (FR15, AR11, AR20)

**AC2.**
**Given** a site with no promoted baseline
**When** Results renders the comparison
**Then** `baseline_metrics` is null, every delta reads "Not computed", and the baseline constraint list states that no baseline exists rather than listing satisfied constraints
**And** no assignment-diff entry claims a worker, shift, or task was added relative to a baseline that does not exist. (UX-DR11, UX-DR21)

**AC3.**
**Given** a non-null frozen `baseline_schedule_version`
**When** the `schedule_version` row it names cannot be read
**Then** the comparison fails closed exactly as it does today
**And** a readable version whose assignment set is legitimately empty produces a real comparison instead, with that emptiness visible rather than inferred.

**AC4.**
**Given** a real promoted baseline
**When** a later run completes and its result is read
**Then** the comparison is present and its deltas are measured against the promoted schedule, proven end to end against PostgreSQL
**And** each new guard is recorded in a demonstrated-red mutation table.

**Out of scope, deliberately** (frozen text, `epics.md:1387`): the hardcoded `baseline_assignment_count=0` in
the overview projection and `get_baseline_assignments` itself. They serve the Scenario Data workspace, a
different consumer whose need does genuinely depend on the Stories 3.8/3.10 prerequisites. This story changes
what *comparison* reads and leaves the projection group unchanged.

---

## Measured at creation — `7eea305`, clean tree

Do not re-derive these from code; re-verify them at Task 1 and record any drift.

| Fact | Measurement |
|---|---|
| Backend default suite, **PostgreSQL up** | **1511 passed, 2 skipped, 7 deselected** (137 s). This is the figure to expect. |
| Backend default suite, **PostgreSQL down** | **1357 passed, 156 skipped, 7 deselected** (300 s) — the postgres-marked tests skip silently. |
| Backend collection | **1513 / 1520 collected**, 7 deselected (`live` marker) |
| Backend `-m postgres` | **156 passed, 1364 deselected** (45 s, PostgreSQL 18 via `docker compose up -d postgres`). Matches Story 4.6's recorded figure exactly. |
| **The stable invariant** | **1513 collected either way** (1511+2 with the database up; 1357+156 with it down). Story 3.12's review established that the pass/skip split is environment-conditional and the TOTAL is what to compare. Record both. |
| Frontend Vitest | **85 files, 647 passed** (`npm test -- --run`, 86 s). The last figure recorded in a story file was 4.4's **575** — it was stale. |
| Playwright | **80 tests in 10 files** (`npx playwright test --list`, chromium + msedge). Story 4.6 recorded **66** — also stale. |
| Test ordering | **deterministic.** No `pytest-randomly`, no `pytest-xdist`; `addopts = -m "not live"` only (`backend/pyproject.toml:48-54`) |
| The baseline supply, literally | `_apply_query((), query, ASSIGNMENT_SORTS, ASSIGNMENT_FILTERS)` — a **hardcoded empty tuple**, `scenario_projection.py:643-645`. `get_locks` is the same shape at `:662-664`. `baseline_assignment_count=0` is a literal at `:567` |
| What `schedule_version` already persists | the **whole** `ScheduleVersionV1` as JSONB (`schedule_run.py:1082` — `TypeAdapter(ScheduleVersionV1).dump_python(candidate, mode="json")`), including `.assignments`, `.metrics`, `.constraint_results`, `.evidence_refs`, `.scenario_version_id`. `get_candidate` already hydrates it (`schedule_run.py:91-106`) |
| Who computed those persisted metrics | `finalize_schedule_run.py:65-95` — `require_hard_constraints(...)` then `calculate_candidate_metrics(...)`, both against `outcome.validation_facts`, which carries **real `wage_per_hour`** (`governed_adapter.py:318`) and **real `selected_shifts`** (`:334-346`). Never model-authored |
| The pointer's FK | `site_baseline.schedule_version_id` → `schedule_version.(id, site_id)`, `ondelete="RESTRICT"`, one row per site (`schema.py:516-518`) |
| What the snapshot froze | `snapshot.baseline_schedule_version = context.baseline_schedule_version` (`create_run_snapshot.py:110`), which is `str(baseline.schedule_version_id)` (`scenario_projection.py:557-560`) — **the exact UUID, not a label needing lookup** |
| `calculate_comparison`'s only production caller | `api/routers/schedule_runs.py:586`, inside `get_schedule_run_result`, which **already holds** `repository: ScheduleRunRepository` (`:556`) and already calls `get_candidate` (`:565`) and `load_snapshot` (`:575`) |
| `ScheduleRunRepository` conformance | a plain `typing.Protocol`, **not** `runtime_checkable` (`ports/schedule_run.py:115`). Structural typing means only the doubles in `tests/test_schedule_runs_api.py` (seven `_Repository` classes) need the new method |
| Existing baseline evidence locators | `comparison.py:232-244` — `producing_run_version=None`, `group="baseline-assignments"`. Zero are emitted today because `baseline` is always `()` |
| Frontend consumers of `baseline_metrics` | exactly one: `ComparisonSummary.tsx:34,37,40,82-86`. Plus the Playwright fixture `repairJourneyStubState.ts:142`, which supplies a **non-null** object and stays valid |

**A flake was observed once at creation, on this commit, with a clean tree — then did not recur.** The
first of three full runs gave **1350 passed / 7 failed**; the two after it were clean. Every failure was a
`tests/test_state_semantics_evidence.py::test_refused_report_writes_nothing` parametrization (three captured
by name: *a filtered run drops the count declaration*, *declared count disagrees with emitted states*, *the
matrix declares its size twice*), and the file passes **12/12 in isolation**. Test ordering is deterministic,
so the variable is state outside the test session — that suite asserts a report file is *not* written, which
a leftover artifact from an earlier run would falsify. **Treat green as the baseline and do not attribute a
red in that file to this story's changes.** If `deferred-work.md` has no entry, one is owed (Task 1); fixing
it is not this story's.

### Premises verified at creation — live PostgreSQL 18, not inferred

`sprint-change-proposal-2026-09-03.md:150-151` raised two risks as first-ten-minutes checks. Both were run
against a real migrated database at story creation, through `api/deps.py`'s `site_context` — the same
RLS-enforcing runtime path a request uses — seeding the chain with
`tests/test_approval_governance_postgres.py`'s own `_seed_candidate_run`. All three assertions passed.

| Premise | Result |
|---|---|
| **RLS on the new predicate.** `select(schedule_version.c.payload).where(id == ..., site_id == ...)` — the exact shape Decision 1's `get_version` proposes, keyed on `id` rather than `get_candidate`'s `schedule_run_id` | **PASS** — row returned, 3 assignments read back |
| **RLS is not vacuous.** The same read under a *different* site's context | **PASS** — returns `None`, so the isolation is real and the check above is not passing for the wrong reason |
| **Payload compatibility.** A `schedule_version.payload` row written by the existing writer, hydrated through `TypeAdapter(ScheduleVersionV1)` | **PASS** — round-tripped unchanged, `feasible_solver_status` and `scenario_version_id` both intact |

**Why this is safe to rely on:** the policy on every governed table is uniform —
`site_id = NULLIF(current_setting('app.site_id', true), '')::uuid` (`migrations/versions/d4e5f6a7b8c9_add_approval_governance.py:30`
and its siblings) — so it constrains `site_id` alone and is indifferent to which other column the predicate
names. The empirical check confirms the reasoning rather than replacing it.

**Decision 7's key is present on the hydrated object.** The probe read `scenario_version_id` straight off the
restored `ScheduleVersionV1`, so the equality guard needs no extra column and no second query.

**What this does NOT establish:** it used a seeded `schedule_version` written by the test helper in
`finalize_run`'s insert order, not a row produced by a real solve, and the site had no `site_baseline` row —
so it proves the *read* is possible, not that the promotion path produces a comparable baseline. That is
Task 9's job and is not discharged here.

---

## Thirteen decisions were made at story creation — do not re-litigate them

Each decision states its mechanism **and what that mechanism does not cover**. The second half is
load-bearing: Story 4.2's Decision 10 named a goal and a mechanism that blocked only one of two directions,
and the gap shipped.

### Decision 1 — The route loads the baseline version and passes it in; `calculate_comparison` gains a parameter, not a port

`ScheduleRunRepository` gains one method mirroring `get_candidate` exactly:

```python
def get_version(
    self, connection: Any, *, schedule_version_id: UUID, site_id: UUID
) -> ScheduleVersionV1 | None: ...
```

`get_schedule_run_result` resolves `snapshot.baseline_schedule_version` to a `UUID`, calls `get_version`, and
passes the result to `calculate_comparison` as `baseline_version: ScheduleVersionV1 | None`.
`calculate_comparison` takes **no second port**.

Precedent, verbatim from this repository three days ago: *"`promote_baseline` is called only from
`decide_approval.py:113` so it takes a parameter, not a port"* (`sprint-status.yaml`, Story 4.4a note).
`calculate_comparison` likewise has exactly one production caller.

**Does NOT cover:** the parameter carries no signal about *why* it is `None`. The route must distinguish "no
frozen baseline" (`snapshot.baseline_schedule_version is None`) from "frozen but unreadable" **before**
calling; the calculator cannot recover that distinction from the parameter alone, and the two states have
opposite outcomes under AC2 and AC3.

### Decision 2 — Readable-vs-empty is answered by the parameter's TYPE, never by tuple emptiness

`None` means the named row could not be read → `BaselineSupplyUnavailableError`, unchanged in shape. A
`ScheduleVersionV1` whose `.assignments` is `()` means a legitimately empty baseline → **a real comparison**,
with the emptiness visible.

This closes `deferred-work.md:574` on its own terms: *"A sound guard needs a readable/row-count signal from
the reader rather than the emptiness of the drained tuple."* The typed parameter **is** that signal. It also
retires the reachability the entry names — `ck_schedule_version_feasible_status` admits `OPTIMAL` and
`FEASIBLE` without requiring any assignment, so a fully-unmet-demand solve is a valid promotable candidate
with zero assignments, and today that truthful state raises.

**Does NOT cover:** a row that exists but whose JSONB payload fails `TypeAdapter(ScheduleVersionV1)`
validation. That raises inside the adapter and reaches the client as `versioned_unhandled_problem`
(`internal_error`), not as a fail-closed comparison. `get_candidate` has carried the identical exposure since
Story 3.2; this story keeps them symmetric rather than hardening one side alone.

### Decision 3 — `get_baseline_assignments` is not wired, and the comparison stops calling it

Delete the `reader.get_baseline_assignments` drain from `calculate_comparison` (`comparison.py:193`).
`PostgresScenarioProjectionReader.get_baseline_assignments` and `baseline_assignment_count=0` are
**untouched** — the frozen AC's out-of-scope clause names both.

**Consequence that must not be got wrong:** `deferred-work.md:531`'s trigger is *"the first story that wires a
real non-empty `get_locks`/`get_baseline_assignments` supply."* **This story is not that story.** Re-point it;
do not close it. Likewise `backend/evals/repair_correctness_report.py:173`'s honest-gap string *"production
get_locks/get_baseline_assignments remain empty by construction"* stays **literally true** and must not be
edited — it is bound into Story 3.10's committed evidence file.

**Does NOT cover:** the `scheduling_inspect` capability's `"assignments"` group, which still routes to
`get_baseline_assignments` (`use_cases/read_scenario_facts.py:36`) and still returns nothing in production.
That consumer keeps the gap; only the comparison leaves it.

### Decision 4 — The baseline side is made symmetric with the candidate side, which the code already gets right

Three sources, each matching what `calculate_comparison` already does for the candidate:

| Baseline field | Source | Candidate precedent |
|---|---|---|
| coverage, overtime, counts, objectives | **recomputed** by `calculate_candidate_metrics(baseline_version.assignments, tasks, demand, facts, constraints=())` | `comparison.py:200-202` |
| `total_cost` | **preserved** from `baseline_version.metrics.total_cost` via `replace(...)` | `comparison.py:206` — same call, same stated reason: *"wage was captured only inside the solver snapshot and is not readable through this projection"* |
| `baseline_hard_constraint_results` | the `constraint_class == "hard"` subset of **`baseline_version.constraint_results`** | `comparison.py:257` — `candidate_constraint_results=candidate.constraint_results`, already persisted, already not recomputed |

This closes **both halves** of `deferred-work.md:498` — not by adding wages and selected shifts to the
projection, but by reading the authoritative values `finalize_schedule_run` already persisted at the
baseline's own solve time.

**`metrics` is `MetricSetV1 | None` and `constraint_results` defaults to `()`**
(`contracts/schedule_version.py:126-127`). `finalize_schedule_run` always populates both, so a
production-built baseline has them — but the type does not, so reading `baseline_version.metrics.total_cost`
unguarded is an `AttributeError` → unhandled 500. A baseline whose `metrics` is `None` is an **unusable**
supply and must fail closed through the Decision 2 path with its own `reason`, never through
`ComparisonIntegrityError` (which is the candidate's 500 and would take the whole result down — the boundary
Story 4.3 deliberately moved). The candidate already has exactly this guard at `comparison.py:181-182`;
the baseline needs its own.

**Does NOT cover:** it does not give the projection the ability to express a wage or a solver-selected shift.
Any *future* consumer that needs baseline cost or hard constraints from the projection alone still faces
:498's original gap. Only the comparison is discharged, and the entry must say so rather than being struck.

### Decision 5 — `validate_hard_constraints` must NOT be called on the baseline; deleting that call is the point

This is the quietest trap in the story, and the obvious implementation walks straight into it.

`_facts()` builds the shared `ValidationFactsV1` with **`selected_shifts=()`** (`comparison.py:78`).
`validate_hard_constraints`'s first check is `a.shift_id not in shifts` where `shifts = {}`
(`hard_constraints.py:34,42-48`). Therefore, the moment real baseline assignments are supplied, **every one of
them is classified "outside its selected shift"** and `assignment_inside_selected_shift` flips to
`satisfied=False`.

So wiring the real supply while keeping `comparison.py:213` replaces seven fabricated `Satisfied` rows with a
fabricated **violation** — a different lie, in a code path that looks like it is now working. Per Decision 4
the line is deleted, not adjusted.

**Does NOT cover:** the candidate's own `validate_hard_constraints` usage elsewhere. `require_hard_constraints`
in `finalize_schedule_run` runs against the solver's real `validation_facts` and is correct; it is untouched.

### Decision 6 — A promoted baseline's hard constraints are all `Satisfied` by construction, and that is now true rather than fabricated

`finalize_schedule_run.py:65-78` calls `require_hard_constraints`, which raises `HardConstraintViolation`
(`hard_constraints.py:122-124`) — the run finalizes `solver_failed` with reason `hard_constraint_violated` and
**no `schedule_version` row is written at all**. A candidate with a failed hard constraint can never become a
`schedule_version`, and therefore can never become a baseline.

So an all-`Satisfied` baseline hard-constraint list is **correct**, and remains correct after this story. What
AC2 removes is that list appearing when there is *no baseline at all*.

**Does NOT cover:** it makes "a real baseline with an unsatisfied hard constraint" structurally unreachable. Do
not write a fixture for it — a hand-built `ScheduleVersionV1` carrying `satisfied=False` would prove rendering,
not behaviour, and would assert a state production cannot produce.

### Decision 7 — The baseline must share the candidate's `scenario_version_id`; a mismatch fails closed

**Why this is load-bearing and not defensive tidiness.** `calculate_candidate_metrics:80` does
`worker = workers[assignment.worker_id]` — an **unguarded dict lookup**. A baseline assignment naming a worker
absent from the current projection is a `KeyError`, which escapes as an unhandled 500. That crash path is
unreachable today *only* because `baseline` is always `()`; supplying a real tuple creates it.

Requiring `baseline_version.scenario_version_id == scenario_version_id` makes both the worker and the task
lookups **total**, because `comparison.py:177` already pins that same value to the projection's current
version — so both sides then normalize the identical `scenario_version.payload`.

**Reachability, measured:** a second `scenario_version` row for one scenario is creatable through the governed
import path — `adapters/postgres/fixture_history.py:155-168` inserts on `(site_id, fixture_id, version)`, so
the same fixture re-imported under a new `version` label produces one. This is a real condition, not a test
artifact.

Mechanism: `BaselineSupplyUnavailableError` gains a `reason` discriminator so the route's planner-facing
sentence names what actually happened. The degradation **shape** — `200` with `comparison: null`,
`comparison_unavailable_reason`, and `current_baseline_schedule_version` — is Story 4.3's and is unchanged
(`schedule_runs.py:595-615`).

**Does NOT cover:** it does not verify that the baseline's persisted `total_cost` was priced with the same wage
table in force today. A baseline promoted before a wage change contributes a cost from its own wage epoch, the
candidate contributes today's, and nothing detects the mix — see Decision 8.

### Decision 8 — No integrity recomputation is run against the baseline's persisted metrics

`_metrics_disagree` (`comparison.py:138-161`) stays **candidate-only**. The candidate is verified because its
row is being read and republished in this request; the baseline's recomputed fields are the values the
comparison publishes, so there is nothing more authoritative to check them against, and its `total_cost` cannot
be recomputed at all (no wages — Decision 4).

**Does NOT cover:** the cost-delta wage-epoch mix named in Decision 7. Record it in `SCOPE_CONTROLS` on
`comparison.py` as a stated non-coverage; do **not** invent a wage-version field to detect it.

### Decision 9 — "No baseline" is a nullable group of two fields, not one

`ComparisonV1` and `ComparisonOut` both change:

- `baseline_metrics: MetricSetV1 | None`
- `assignment_diff: AssignmentDiffV1 | None`

Both are `None` exactly when `expected_baseline_schedule_version is None`, and
`baseline_hard_constraint_results` is `()` exactly then.

**Why the diff must be `None` and not empty:** an empty diff reads as *"nothing changed"*. AC2 forbids the
claim that everything was added; substituting the claim that nothing was would be a second false statement,
not a fix.

`sprint-change-proposal-2026-09-03.md:146` anticipated only `baseline_metrics` becoming nullable. AC2's second
clause is what requires the diff to travel with it.

**Does NOT cover:** `baseline_hard_constraint_results` stays a **non-nullable** tuple. `()` is unreachable for
a real baseline (Decision 6 guarantees at least the seven `_result(...)` rows `validate_hard_constraints`
always emits), so it is unambiguous — but that is an invariant held by construction, not by the type. One test
must assert the three fields move together.

**And it is unreachable only in PRODUCTION.** Every seeded `schedule_version` in this repository's own
PostgreSQL tests has `constraint_results=()` and `metrics=None`, because
`tests/test_approval_governance_postgres.py`'s `_seed_candidate_run` sets neither (`:167-173`). A test that
asserts "`()` means no baseline" against a seeded baseline therefore **passes for the wrong reason**. See
Task 9.

### Decision 10 — The frontend's `sum()` becomes null-propagating; `delta()` is already correct and is not touched

Measured trap: `ComparisonSummary.tsx:9-14`'s `sum()` returns a `number` unconditionally, so
`delta(sum(candidate…), sum(baseline…))` at `:82-83` can **never** return "Not computed" no matter what the
backend sends. `delta()` at `:16-18` has always handled `null` and has never received one — the helper the
change proposal cites as evidence the frontend was "already built for it" is real, but two of the four rows
never reach it.

`objectiveNames` (`:35-38`) and `baselineObjectives` (`:40`) dereference `baseline` unguarded and throw on
`null`. `tsc -b` catches all of it once codegen runs — that is the intended detector.

**Does NOT cover:** `ComparisonSummary.test.tsx:121` — *"renders a real zero coverage delta for genuinely zero
demand, not 'Not computed'"* — **must keep passing**. A real baseline with zero demand still reads `0.00`; only
an absent baseline reads "Not computed". The two states are distinct and both are asserted.

### Decision 11 — Baseline evidence locators are emitted and pinned, but still do not resolve

`comparison.py:232-244` keeps `group="baseline-assignments"` and gains
`producing_run_version=expected_baseline_schedule_version`, matching `finalize_schedule_run.py:81-84`'s own
convention for naming the version that produced a record. Under Decision 7 the `scenario_version_id` and the
three `checksum_*` values taken from `overview` are the baseline's own, so the locator is correctly pinned.

**Does NOT cover: resolution.** Story 4.5 established that `resolve_assignment` searches `lambda: ()`, because
resolution reads `get_baseline_assignments` — which Decision 3 deliberately leaves hardcoded empty. Every
baseline locator therefore still resolves `not_found`. AC1 requires the locator to be **carried**, and it is.
Results renders evidence refs as plain text (`ScenarioResults.tsx:86`, Story 3.12 Decision 2), so there is no
user-visible regression. This is **declared, not fixed**, and `deferred-work.md:531` is the entry that keeps it.

### Decision 12 — Ledger disposition: two close, two re-point, one is untouched

| Entry | Disposition |
|---|---|
| `:498` baseline cost / hard constraints not authoritative | **CLOSES** (Decision 4), recording that it closed by reading persisted solve-time values, **not** by supplying wages or selected shifts to the projection |
| `:574` legitimately-empty vs unreadable baseline | **CLOSES** (Decision 2), on the entry's own stated terms |
| `:531` repair correctness proven against seeded supplies | **RE-POINTS.** Its trigger is a real `get_baseline_assignments` supply, which Decision 3 explicitly does not build. Owner stays open |
| `:73` comparison evidence trail names only `baseline-assignments` | **RE-POINTS at most.** Its trigger is a story needing task/demand/worker locators from the evidence list alone; this story needs none |
| `:568` write fault inside TX2 leaves no audit row | **UNTOUCHED** |

**Does NOT cover:** whether `:531`'s second sentence — *"must also discharge Story 3.8's wage/selected-shift
prerequisites before treating baseline cost or hard constraints as authoritative"* — is still accurate. It is
not, for the comparison: Decision 4 discharges it a different way. Amend that sentence when re-pointing.

### Decision 13 — No migration, no route, no golden case, no evidence file, no Gate A change

- **No migration.** No table, column, index, or grant changes. `alembic check` from the repository root must
  report zero operations and zero new migration files.
- **No new route.** `GET /api/v1/schedule-runs/{run_id}/result` keeps its path, method and status codes.
- **No new golden case.** This story has no model-facing surface and no LLM-scriptable turn — the Story
  3.10/3.11/3.12/4.5 precedent, all of which contributed zero. **Do not pad the dataset.**
- **No evidence file.** No AC carries a measured threshold (`docs/EVIDENCE-CONVENTION.md`).
- **No Gate A registry change.** `scripts/gate_a_checks.py` mentions "comparison" only inside Story 3.12's
  browser-journey description strings (`:93`, `:504`); no invariant gates this contract.
- **A published-contract change IS owed**, and it is the only one: `npm run codegen` regenerates
  `frontend/openapi.json` and `frontend/src/api/schema.d.ts`. Commit them.
- **`docs/API.md:586-596` becomes false** and must be corrected — it currently states the baseline assignment
  supply "is not wired yet, so from the first promotion onward the baseline half of the comparison cannot be
  computed."

---

## Tasks / Subtasks

- [ ] **Task 1 — Re-derive the baseline before touching anything** (AC: all)
  - [ ] Confirm a clean tree at `7eea305` or later; record the actual commit.
  - [ ] Run `uv run --frozen pytest -q` and record **totals alongside any pass/skip split** — Story 3.12's
        review established the split is environment-conditional and the total is the stable invariant.
  - [ ] Expect **1511 passed / 2 skipped / 7 deselected** with the database up. If
        `tests/test_state_semantics_evidence.py` is red, confirm it passes in isolation and treat it as the
        flake recorded above — not as this story's. Raise it to `deferred-work.md` if no entry exists.
  - [ ] Bring Docker PostgreSQL up (`docker compose up -d postgres`) and re-run
        `uv run --frozen pytest -m postgres -q`, expecting **156 passed / 1364 deselected**. A run that reports
        success with the service DOWN has proven nothing — those tests skip silently.
  - [ ] Record `npm test -- --run` and `npx playwright test --list` totals.
- [ ] **Task 2 — Re-confirm the two premises, already VERIFIED at creation** (AC: 1, 3) — named as
      first-ten-minutes checks by `sprint-change-proposal-2026-09-03.md:150-151`. Both were run against a live
      PostgreSQL 18 at story creation and **passed**; see *Premises verified at creation* below. This task is a
      cheap re-confirmation, not an open question — but do not take it on faith if the schema has moved.
  - [ ] Re-run the equivalent of the creation probe, or assert the same two facts inside the Task 9 test.
- [ ] **Task 3 — Add `get_version` to the port and the adapter** (AC: 1)
  - [ ] Add the method to `application/ports/schedule_run.py`'s Protocol, per Decision 1's signature.
  - [ ] Implement it in `adapters/postgres/schedule_run.py` beside `get_candidate` (`:91-106`), selecting on
        `schedule_version.c.id` and `schedule_version.c.site_id`.
  - [ ] Add the method to the seven `_Repository` doubles in `tests/test_schedule_runs_api.py` that the route
        now exercises.
- [ ] **Task 4 — Make the contract's baseline group nullable** (AC: 2)
  - [ ] `application/contracts/comparison.py`: `baseline_metrics` and `assignment_diff` become `| None`, per
        Decision 9.
  - [ ] `api/schemas.py:541-557`: the same two fields on `ComparisonOut`.
  - [ ] Extend `tests/test_comparison_contract.py` to round-trip **both** shapes — populated and absent.
- [ ] **Task 5 — Rewire `calculate_comparison`** (AC: 1, 2, 3)
  - [ ] Add the `baseline_version: ScheduleVersionV1 | None` parameter, per Decision 1.
  - [ ] Delete the `get_baseline_assignments` drain at `:193`, per Decision 3.
  - [ ] Replace the `not baseline` guard at `:194-197` with the typed check, per Decision 2, and add the
        `scenario_version_id` equality check with its `reason`, per Decision 7.
  - [ ] Recompute the baseline metrics and preserve `total_cost`; take the hard results from
        `baseline_version.constraint_results`; **delete the `validate_hard_constraints` call at `:213`** — per
        Decisions 4 and 5.
  - [ ] Guard `baseline_version.metrics is None` through the Decision 2 fail-closed path, not through
        `ComparisonIntegrityError` — per Decision 4.
  - [ ] Return the absent group as `None` when `expected_baseline_schedule_version is None`, per Decision 9.
  - [ ] Set `producing_run_version` on the baseline locators, per Decision 11.
  - [ ] Update `SCOPE_CONTROLS` (`:27-32`): the two lines naming the unwired supply and the wage/shift gap are
        now false. Add the wage-epoch non-coverage from Decision 8.
- [ ] **Task 6 — Rewire the route** (AC: 1, 2, 3)
  - [ ] In `get_schedule_run_result` (`schedule_runs.py:552-635`), resolve the frozen identifier, call
        `get_version`, and pass the result. Distinguish "no frozen baseline" from "frozen but unreadable"
        **before** calling, per Decision 1.
  - [ ] Carry the new `reason` into `comparison_unavailable_reason`; keep the response shape unchanged.
- [ ] **Task 7 — Rewrite the tests that currently encode the defect** (AC: 1, 2, 3)
  - [ ] `tests/test_schedule_comparison.py:121-133` —
        `test_empty_baseline_is_real_net_new_comparison_and_detects_staleness` **asserts the fabrication as
        correct behaviour in its own name.** It must be split: one test for the absent group (AC2), one for a
        legitimately empty but readable baseline (AC3). Do not preserve it by adjusting its assertions.
  - [ ] Add: a populated baseline produces real deltas; a `scenario_version_id` mismatch fails closed with its
        distinct reason; the three baseline fields move together.
- [ ] **Task 8 — Frontend** (AC: 2)
  - [ ] `npm run codegen`; commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts`.
  - [ ] `ComparisonSummary.tsx`: make `sum()` null-propagating and guard the objective-name union, per
        Decision 10. Render the explicit no-baseline statement in the baseline constraint panel (`:93`) and in
        place of the assignment diff (`:67-77`).
  - [ ] Verify `ComparisonSummary.test.tsx:121` still passes unchanged; add the absent-baseline cases beside it.
  - [ ] Run the existing axe assertion (`:149`) over the new state.
- [ ] **Task 9 — Prove the loop end to end against PostgreSQL** (AC: 4)
  - [ ] Extend the real-PostgreSQL suite: promote a baseline through the shipped Story 4.3 path, complete a
        later run, read its result, and assert the comparison is present with deltas measured against the
        promoted schedule — **not** against a hand-built `ScheduleVersionV1`.
  - [ ] Reuse `tests/test_approval_governance_postgres.py`'s promotion scaffold rather than writing a second
        one — **but not unmodified.** Its `_seed_candidate_run` (`:167-173`) sets neither `metrics` nor
        `constraint_results`, which are the two fields Decision 4 reads. Used as-is the baseline would carry
        `metrics=None` and `constraint_results=()`, and the whole proof would be vacuous. Either extend the
        helper to populate both, or build the baseline through the real `finalize_schedule_run` path.
  - [ ] Assert the baseline's `total_cost` is **non-zero and equal to its persisted value** — the single
        assertion that distinguishes Decision 4 from trap 2. A proof that omits it cannot tell the fix from
        the defect.
- [ ] **Task 10 — Documentation and ledger** (AC: 1, 3)
  - [ ] Correct `docs/API.md:586-596`, per Decision 13.
  - [ ] Apply Decision 12's ledger dispositions in `deferred-work.md`, including amending `:531`'s second
        sentence.
  - [ ] Update `ARCHITECTURE-SPINE.md`'s EAD-9 supplier table row *"Baseline assignment supply | **none** —
        guarded by EAD-8"* (`:118`) to name the real supplier. EAD-8's Rule and the amended premise stay as
        they are.
- [ ] **Task 11 — Demonstrated-red mutation table** (AC: 4)
  - [ ] For each new guard, mutate the **finished, green** code and record mutation / guard / before / after in
        the Dev Agent Record. A red from incomplete code does not count.
  - [ ] The table must include the `validate_hard_constraints` deletion (Decision 5) and the
        `scenario_version_id` equality check (Decision 7) — both are guards whose absence looks like working
        code. The mutation for a *deletion* is to reinstate the deleted call on finished code and confirm the
        test that asserts the persisted source goes red.
- [ ] **Task 12 — Full gates** (AC: 4)
  - [ ] Backend default and `-m postgres`; `tests/test_evidence_convention.py`; Vitest; `tsc -b`; lint; build;
        Playwright; `alembic check` from the repository root (expect zero operations, zero new files); Gate A
        re-run per AR28.

---

## Dev Notes

### Traps — the quietest first

1. **The one-line fix that produces a different lie.** Supplying real baseline assignments while leaving
   `validate_hard_constraints` in place flips the baseline constraint list from seven fabricated `Satisfied`
   rows to a fabricated violation, because `_facts()` supplies `selected_shifts=()`. Decision 5. Nothing in the
   AC text warns about this; only the code does.

2. **The fix that leaves the headline number exactly as wrong as it is today.** `_facts()` sets
   `wage_per_hour=0.0` (`comparison.py:72`), and `calculate_candidate_metrics:81` prices every minute through
   it. Recompute the baseline naively and `baseline.total_cost` is `0.00` — so **"Cost delta" still reads the
   candidate's entire cost**, which is the single number the change proposal opens with. AC1 would be satisfied
   to the letter and the defect would ship. Decision 4.

3. **`workers[assignment.worker_id]` is an unguarded dict lookup** (`candidate_metrics.py:80`). It cannot raise
   today because the baseline is always empty. Decision 7's version equality is what keeps it total — it is not
   defensive tidiness, and removing it re-opens a 500.

4. **A test whose name asserts the defect is correct.**
   `test_empty_baseline_is_real_net_new_comparison_and_detects_staleness` (`test_schedule_comparison.py:121`)
   passes today and must not be kept passing. Task 7.

5. **`sum()` makes two of the four "Not computed" rows unreachable from the backend.**
   `ComparisonSummary.tsx:9-14` returns a `number` unconditionally. Sending `null` from the server is necessary
   and not sufficient. Decision 10.

6. **An empty `assignment_diff` is a second false claim, not a fix.** Decision 9.

7. **`repair_correctness_report.py:173` and `deferred-work.md:531` are still true after this story.** Both
   describe `get_baseline_assignments`, which stays hardcoded empty. Closing them opportunistically would
   record work that was not done, and the first is bound into Story 3.10's committed evidence.

8. **`request_approval.py:117-128` and `decide_approval.py:79` must keep a zero-line diff.** The
   `consequence_summary` string is hashed into every persisted `consequence_hash`, and `revalidate_binding`
   re-derives it on every decision. It reads candidate assignment counts only and needs nothing from the
   comparison — editing it would stale every pending binding in existence.

9. **The seven `_Repository` doubles in `tests/test_schedule_runs_api.py`** are structural, not
   `runtime_checkable`. Missing `get_version` fails at call time inside a route test, not at import — read the
   failure as a missing double method, not as a route bug.

10. **The repo's own seeded baselines have `metrics=None` and `constraint_results=()`.**
    `_seed_candidate_run` sets neither, so the two fields Decision 4 reads are absent in every existing
    PostgreSQL fixture. Two consequences: reading `.metrics.total_cost` unguarded is an `AttributeError`, and
    a test asserting Decision 9's `()`-means-no-baseline invariant passes for the wrong reason. Decisions 4
    and 9, Task 9.

11. **Do not re-verify the baseline's persisted metrics.** Decision 8. Adding `_metrics_disagree` to the
    baseline side creates a guard that raises on legitimate float noise between the solver's ingest facts and
    the projection's re-normalization — the exact ~1e-9 disagreement `comparison.py:106-114` documents.

### Files being modified — read these before editing

| File | Current state | What changes | What must be preserved |
|---|---|---|---|
| `application/scheduling/comparison.py` | drains `get_baseline_assignments`, recomputes baseline metrics with zero wages, recomputes baseline hard constraints against empty selected shifts | Decisions 2–5, 7, 9, 11 + `SCOPE_CONTROLS` | `_metrics_disagree` on the candidate; `_sorted_values`' record-id-namespace reasoning; the float tolerances; `stale` derivation; `unresolved_gap_record_ids` (candidate-only) |
| `api/routers/schedule_runs.py` | `get_schedule_run_result` calls `get_candidate`, `load_snapshot`, `calculate_comparison`; degrades on `BaselineSupplyUnavailableError` | Decision 6 (task) — resolve and pass the baseline version | the 200-not-409 boundary and its comment; the `ComparisonIntegrityError` arm's distinction from `versioned_unhandled_problem`; `current_baseline_schedule_version` mirrored onto the result |
| `application/contracts/comparison.py` | both baseline fields non-optional | two become `\| None` | `SCHEMA_VERSION` stays `"1"` — this is an additive nullability change, not a new schema version |
| `api/schemas.py` | `ComparisonOut` mirrors the contract | the same two fields | `ScheduleRunResultOut`'s docstring, which states the EAD-8 scoping rule |
| `adapters/postgres/schedule_run.py` | `get_candidate` reads by `schedule_run_id` | add `get_version` beside it | `get_candidate` itself — do not generalize the two into one method |
| `frontend/src/components/run-results/ComparisonSummary.tsx` | `sum()` non-null; `baseline` dereferenced in four places | Decision 10 | the stale banner; the fail-closed `pendingApproval` logic; the "real zero is not Not computed" behaviour |
| `frontend/src/routes/ScenarioResults.tsx` | renders `ComparisonSummary` only when `comparison` is truthy | nothing structural — the absent group lives *inside* a present comparison | the candidate-only branch (`:93-115`) that keeps a refused comparison from hiding the schedule |

### Testing requirements

- Backend: `pytest` under `backend/`, absolute imports, doubles over mocks. The real-PostgreSQL proof is
  `-m postgres` and **skips silently when the service is down** — a run that reports success with the database
  off has proven nothing (Story 4.5's generator finding).
- Frontend: Vitest + Testing Library, co-located `*.test.tsx`. Keep the existing axe assertion green over the
  new state.
- Every new guard owes a demonstrated red produced by mutating finished code (Task 11).

### Project structure notes

No new directory, module, or package. `get_version` lands in the existing port and adapter; every other change
is an edit to a file that already exists. The zero-line-diff fences that have held since Epic 2 —
`backend/domain/**`, `backend/engine/**`, `backend/llm/**`, `backend/ingest/**`, `backend/store/**`,
`backend/services/**`, `backend/migrations/**`, `backend/evals/golden/**` — all hold here too.

### Open questions — neither blocks this story

1. **Does the `test_state_semantics_evidence` flake have an owner?** Task 1 records it; if `deferred-work.md`
   has no entry, one is owed. It is not this story's to fix.
2. **Should `baseline_hard_constraint_results` become nullable for symmetry?** Decision 9 says no, on the
   grounds that `()` is unreachable for a real baseline. If a later story finds a reachable empty case, that
   story owns the third nullable field.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.0` — lines 1351-1387]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-03.md` — the whole document]
- [Source: `ARCHITECTURE-SPINE.md` (architecture-epic-4-2026-08-27) — EAD-1, EAD-2, EAD-8 (amended), EAD-9, Deferred table]
- [Source: `docs/DOMAIN-MODEL.md` §1, §2, §3]
- [Source: `docs/EVIDENCE-CONVENTION.md`; `docs/API.md` lines 586-596]
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` — :73, :498, :531, :568, :574]
- [Source: `_bmad-output/implementation-artifacts/epic-4-retro-2026-09-02.md` §4, §6 A1, §6 A3(i)]

---

## Dev Agent Record

### Agent Model Used

### Implementation Plan

### Debug Log References

### Demonstrated-red mutation table (retro A1 — required before review)

| Mutation | Guard | Before | After |
|---|---|---|---|

### Completion Notes List

### File List

## Change Log

| Date | Change |
|---|---|
| 2026-09-03 | Story created from `sprint-change-proposal-2026-09-03.md` (Epic 4 retrospective A3(i)). Baseline `7eea305`. |
| 2026-09-03 | PostgreSQL brought up. `-m postgres` measured (**156 passed**) and the default suite re-measured with the database up (**1511 passed / 2 skipped**); total 1513 either way. Task 2's two premises **verified against a live database** rather than left as open risks — see *Premises verified at creation* — and Task 2 reduced to a re-confirmation. |
| 2026-09-03 | Decision 4 corrected: `ScheduleVersionV1.metrics` is Optional and the repo's own seeded baselines set neither `metrics` nor `constraint_results`, so the unguarded read is an `AttributeError` and Task 9's scaffold would have proven nothing unmodified. Added the fail-closed guard, trap 10, and the Task 9 non-vacuity assertion. |
