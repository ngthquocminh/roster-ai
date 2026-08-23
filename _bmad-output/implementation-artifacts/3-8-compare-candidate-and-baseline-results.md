---
baseline_commit: a77df3579c79933e6a5cfdd0d8ad2c17e1a8d51f
---

# Story 3.8: Compare Candidate and Baseline Results

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want to inspect exactly what a candidate changes,
So that I can judge coverage repair and trade-offs before any approval decision.

**Planner-visible outcome: the third one since Story 3.1.** This is the story that builds the **Results**
view — the fourth and last of the four peer scenario surfaces (Chat, Scenario Data, Runs, Results;
`EXPERIENCE.md:40`). Story 3.7 already links every Runs row to `/scenarios/{scenarioId}/runs/{runId}`;
that route (`ScenarioResults.tsx`) is today a bare `WorkspaceTabPlaceholder` and every click on "View
Progress"/"View Results" dead-ends there (`deferred-work.md`, "story-3.7 code review", entry naming this
story as owner). This story replaces the placeholder with a real page: the run's literal terminal state,
its immutable evidence, and — for a feasible completed run — a `ComparisonV1` against the scenario's
baseline.

**Depends on, and consumes:** Story 3.2's `ScheduleVersionV1`/`schedule_version`/`schedule_assignment`
tables (created, never yet read back by any route); Story 3.5's `ScheduleRunStatusV1` closed graph and
`GET /schedule-runs/{run_id}` view; Story 3.7's Runs workspace, `RunStatusBadge`, and the "View
Results" link it already renders; Story 1.6's shared primitives (`InlineAlert`, `EmptyState`,
`StatusBadge`, `IdentifierCopyButton`); the grounding calculator idioms from Epic 2
(`application/grounding/calculators.py`'s `_drain` paging helper); `application/scheduling/candidate_metrics.py`
and `application/scheduling/hard_constraints.py` from Story 3.2 (reused, not reimplemented — see Decision B).

**Unblocks:** Story 4.1 (approval needs a rendered comparison to bind); Story 3.10–3.12 (proof stories
exercise the full repair loop, which is not "full" until Results exists).

**Scope summary:** One new backend contract module (`application/contracts/comparison.py` —
`ComparisonV1`). One new application calculator (`application/scheduling/comparison.py`) that reuses
Story 3.2's `calculate_candidate_metrics`/`validate_hard_constraints` against the baseline assignment
set instead of duplicating their logic. One new repository read method
(`ScheduleRunRepository.get_candidate`) and one new route
(`GET /api/v1/schedule-runs/{run_id}/result`). One rewritten frontend route (`ScenarioResults.tsx`,
today a placeholder) plus new components (`ComparisonSummary.tsx`, `TerminalOutcomeCard.tsx`) and one
new hook (`useScheduleRunResult`). **No new migration** — `schedule_version`/`schedule_assignment`
already exist from Story 3.2 with everything this story reads.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. `docs/DOMAIN-MODEL.md` is cited, not
re-derived — see the note at the end of this section for exactly how it applies (or does not) here.

| Fact | Where it is written |
|---|---|
| `ComparisonV1`'s required shape: candidate/baseline versions; affected worker, shift, task diffs; interval coverage, overtime, cost/objective deltas; constraint status; unresolved infeasibility | AD-20 *Normative contract minimums* (`ARCHITECTURE-SPINE.md:326`) |
| `ScheduleVersionV1`'s required shape: schedule/run/scenario/proposal IDs and versions, feasible solver status, immutable `AssignmentV1[]`, `MetricSetV1`, `ConstraintResultV1[]`, warnings, evidence refs | AD-20 (`ARCHITECTURE-SPINE.md:325`); implemented `backend/application/contracts/schedule_version.py:117` |
| Application calculators — not the model, not the client — must produce or verify every numerical claim and candidate/baseline delta against immutable evidence; missing/unauthorized/version-mismatched evidence are distinct failures with no fallback to another version or row | AD-11 (`ARCHITECTURE-SPINE.md:150-154`) |
| Only feasible `solver_completed` can reference a candidate `ScheduleVersion`; `solver_infeasible`/`solver_timed_out`/`solver_cancelled`/`solver_failed` never have one | AD-7 (`ARCHITECTURE-SPINE.md:84-131`); enforced in the database by `ck_schedule_run_candidate_completed` (`schema.py:449`) |
| `schedule_version` stores `payload` (the full `ScheduleVersionV1`, JSONB) plus `canonical_hash`/`checksum_algorithm`/`checksum_schema_version`; `schedule_assignment` stores one denormalized row per candidate assignment for direct querying | `adapters/postgres/schema.py:452-503`; write side in `adapters/postgres/schedule_run.py:1041-1058` (`finalize_run`) — **no read-back method exists yet for either table; this story adds the first one** |
| **There is no baseline schedule version anywhere in the real system, and Story 3.2 explicitly declined to invent one.** `baseline_schedule_version` (on `RunSnapshotV1`, `EvidenceRefV1`, `ScenarioOverviewV1`) is always `None` — `adapters/postgres/scenario_projection.py:556`, `adapters/postgres/scenario_catalogue.py:117-118`. The pointer and its move belong to **Story 4.3** (Epic 4), not this story | Story 3.1 Decision 7 / Gap 1 (`3-1-...md:242-326`); Story 3.2 Decision 7 (`3-2-...md:230-240`: *"a candidate produced by this story has no baseline to be a candidate against... that is 3.8's problem to raise, not this story's to pre-solve. Do not create a synthetic baseline row."*) |
| `PostgresScenarioProjectionReader.get_baseline_assignments` returns `()` unconditionally — the only populated source anywhere is the eval double `evals/fixture_projection.py`'s `ASSIGNMENTS` | `docs/DOMAIN-MODEL.md` §2; measured directly in `adapters/postgres/scenario_projection.py:632-646` |
| `application/scheduling/candidate_metrics.calculate_candidate_metrics(assignments, tasks, demand, facts, *, constraints)` and `application/scheduling/hard_constraints.validate_hard_constraints(assignments, facts, *, preserved_locks)` are **general-purpose over any `AssignmentV1` tuple** — neither is solver-specific. Story 3.2's `finalize_schedule_run.py` calls them on the candidate's own solved assignments; nothing prevents calling them on the baseline's assignment set the same way | Read directly: `candidate_metrics.py:31-102`, `hard_constraints.py:27` |
| **Two distinct safety properties, not one.** `validate_hard_constraints` only dereferences `facts.selected_shifts`/`by_shift` inside its per-assignment loop — safe against an empty baseline regardless of what `selected_shifts` contains (Decision B's placeholder `()` is fine). `calculate_candidate_metrics` is **not** gated the same way: its `demand`-row loop runs unconditionally (not gated on `assignments`), and raises `ValueError` for any `volume`-family task with zero qualified workers among `facts.workers` — a worker-coverage requirement, not an assignments-emptiness one (see the row above) | `hard_constraints.py:27-40`; `candidate_metrics.py:57-64` |
| The read-model `WorkerV1` (`application/contracts/scenario_projection.py:73-82`, what `ScenarioProjectionReader.get_workers` returns) has **no `wage_per_hour` field**. Only the solver-internal `WorkerSchedulingFactV1` (`schedule_version.py:35-42`, built only inside `engine/governed_adapter.py` from the domain `Member`) carries wage. `calculate_candidate_metrics` needs `worker.wage_per_hour` to compute `total_cost` | Confirmed by grep: `wage_per_hour` exists only in `domain/types.py`, `ingest/input_adapter.py`, `schedule_version.py`, and `candidate_metrics.py` — never in `scenario_projection.py` or any adapter reading it |
| Grounding calculators already page a `ScenarioProjectionReader` group to exhaustion under an explicit row bound (`_drain` in `calculators.py:146-223`), verifying `scenario_version_id`/`site_id` pin on every page. It is private (`_`-prefixed) to that module | `application/grounding/calculators.py:146` |
| The fixture's real row counts: demand 1547, tasks 6, workers 10 (or 22 on the larger fixture) — `calculate_metric`'s default `max_rows=400` is scoped to one task/window and **under-bounds a whole-scenario drain** | `3-1-...md:305` (the scenario-wide totals; `docs/DOMAIN-MODEL.md` §2 states only one task's per-family breakdown, 197/53/6 rows, not these totals) |
| `calculate_candidate_metrics` raises a bare `ValueError` for **any** `volume`-family demand row (`outbound`/`inbound`) whose task has zero qualified workers among `facts.workers` — independent of whether `assignments` is empty. This is a *worker-coverage* failure mode, distinct from Decision B/Trap 3's *empty-assignments* safety argument | `candidate_metrics.py:57-64` (`row.unit != "headcount"` branch, `if not rates: raise ValueError(...)`) |
| `EvidenceGroupV1` already includes `"baseline-assignments"` as a first-class evidence group | `application/contracts/evidence_ref.py:19-26` |
| The Results route already exists and is linked from Runs (`/scenarios/{scenarioId}/runs/{runId}` → `ScenarioResults.tsx`, `App.tsx:66`); only its content is a placeholder | `frontend/src/routes/ScenarioResults.tsx` (read directly) |
| UX: "Comparison summary... Missing metrics say 'Not computed'." "Terminal outcome... A non-promotable result never exposes an enabled Approve as baseline control." "A newer baseline marks comparison stale and blocks approval until refresh/revise/rerun." | `EXPERIENCE.md:89,91,126` |
| Literal terminal-state rendering (no percentage, ETA, invented state), reused from Story 3.7's `RunStatusBadge` | UX-DR10/UX-DR13 (`epics.md:193,...`); `3-7-...md` |

**`docs/DOMAIN-MODEL.md` applies narrowly here and must not be over-applied.** This story computes
`ComparisonV1` by diffing two `AssignmentV1` sets (candidate vs. baseline) and their derived
`MetricSetV1`s — it does **not** compute `shortfall_minutes` (required-minus-staffed against demand),
which DOMAIN-MODEL.md §4 still forbids for the reasons given there (assignments carry no `family`,
so a demand-vs-assignment subtraction cannot be scoped to match). Do not read this story as the trigger
DOMAIN-MODEL.md §4 names ("Story 3.8 at the earliest") as authorization to build `shortfall_minutes` —
conditions 2–4 of that section (family-complete required minutes, matching-dimension staffed side, a
mixed-family test) remain unmet regardless of what this story ships. `interval_coverage_*_minutes` here
comes straight from `MetricSetV1`, already computed the DOMAIN-MODEL-compliant way by
`calculate_candidate_metrics` (§1's volume→minutes conversion, §3's fail-closed-not-zero). No demand row
is read with a `family` argument by this story's own new code.

---

## Acceptance Criteria

Verbatim from `epics.md:1037-1057`.

1. **Given** a completed feasible candidate and its frozen baseline **When** `ComparisonV1` is
   calculated **Then** it names both versions and includes affected workers, shifts, tasks/roles,
   interval coverage, overtime, total cost, objective components, constraint status, warnings, and
   unresolved gaps **And** every value/delta is produced or verified by application calculators against
   immutable evidence. (FR15, AR11, AR20)

2. **Given** a selected completed run **When** Results renders **Then** deterministic status, warnings,
   metrics, comparison, schedule, and evidence remain available independently of model-generated
   summaries **And** missing metrics say "Not computed" rather than zero or an invented value.
   (UX-DR11, UX-DR21)

3. **Given** a failed, infeasible, timed-out, or cancelled run **When** Results renders **Then** the
   literal non-promotable outcome and available evidence are distinct from fetch failure and completed
   result **And** no enabled approval action is displayed. (UX-DR13, UX-DR25)

4. **Given** the current baseline changes after comparison **When** the result is revisited **Then**
   the comparison is marked stale with expected/current versions and remains historical evidence **And**
   it is not silently recalculated or represented as current. (AR9)

---

## Decisions — resolved so the dev agent does not have to guess

Following the pattern Stories 3.1/3.2 established (Decision N, Gap N): resolve ambiguity here, in
writing, rather than let it surface as a decision-grade code-review finding after implementation.

### Decision A — "Baseline" is the scenario's baseline assignment supply, not the (nonexistent) pointer

AC1 says "candidate and its frozen baseline." AD-9 calls the site baseline "a versioned pointer," but
that pointer (`baseline_schedule_version`) is `None` everywhere today and stays that way until Story
4.3. Story 3.2 named this gap and explicitly refused to invent a synthetic baseline row to make
comparison "demonstrable" (`3-2-...md:239-240`).

**Resolution:** the baseline side of `ComparisonV1` is the scenario's `get_baseline_assignments()` read
— real, immutable, version-pinned, and **empty in the real Postgres reader today**. This is not a
placeholder: it is the true current state ("the schedule as it operationally exists"), and comparing a
non-empty candidate against a genuinely empty baseline is a correct, honest comparison (100% of the
candidate's assignments are net-new), not a fabricated one. **Do not** build a `schedule_version` row,
a baseline pointer, or any other synthetic baseline. The mechanism (the calculator and its tests) must
be proven against a **seeded non-empty baseline** too — via `evals/fixture_projection.py`'s `ASSIGNMENTS`
double or an equivalent seeded reader — so this is not "a guard that cannot go red" (the dominant Epic 2
retro failure mode, `docs/DOMAIN-MODEL.md`'s own framing).

### Decision B — Reuse Story 3.2's calculators for the baseline side; do not write a second metrics engine

`calculate_candidate_metrics` and `validate_hard_constraints` are general over any `AssignmentV1` tuple
(Facts table, row 7). Call them a second time — once for `candidate.assignments` (already done at run
finalize time, but **recomputed here too**, per AD-11's "produced or verified... against immutable
evidence," rather than trusted from the persisted payload verbatim) and once for `baseline_assignments`
— with the **same** `tasks`/`demand` read fresh from the current scenario projection (Decision C covers
sourcing). Diff the two `MetricSetV1`s field-by-field for the deltas AC1 asks for. **Do not** write a
parallel "baseline metrics" formula — that is exactly the trap DOMAIN-MODEL.md exists to prevent (a rule
re-derived instead of cited/reused).

**Known, explicitly scoped-out consequence:** `calculate_candidate_metrics` needs `worker.wage_per_hour`
for `total_cost`, and the read-model `WorkerV1` this story sources baseline facts from does not carry
it (Facts table, row 8). Build the baseline's `ValidationFactsV1.workers` with
`wage_per_hour=0.0` for every worker, and **say so** in a comment naming this exact gap. This is safe
and non-fabricating **today** only because `baseline_assignments` is always empty (Decision A), so the
`total_cost` sum's `for assignment in assignments: ... * worker.wage_per_hour` loop never actually
executes against a placeholder wage. **The moment any future story populates a real, non-empty baseline
assignment supply, `total_cost`/`overtime_minutes` computed this way become wrong for the baseline
side** — record this as a `deferred-work.md` entry (Task 10) naming the story that adds real baseline
assignments as owner, so it is not silently inherited as a passing test that goes wrong the day the
precondition changes. Candidate-side `total_cost` is unaffected — it is read from the persisted
`ScheduleVersionV1.metrics`, whose wage data came from the solver's own `WorkerSchedulingFactV1` at
solve time.

`validate_hard_constraints` also needs `facts.selected_shifts` (shift-window boundaries), which this
story's baseline `ValidationFactsV1` cannot populate from the projection alone (shift slicing is
solver-adapter-internal, `engine/governed_adapter.py`). Supply `selected_shifts=()`. This is safe today
because the function only dereferences `shifts[...]` inside its per-assignment loop, and the baseline
assignment set is empty (Decision A) — so the loop body never runs. Record the same future-gap note.

Populate every other unused `ValidationFactsV1` field for the baseline call with a trivial, honestly-
labelled placeholder (`max_hours_per_week=()`, `max_shifts_per_day=()`, `minimum_gap_minutes=0`,
`horizon_minutes=<from ScenarioOverviewV1>`) — neither calculator reads them.

**Worker identity mapping:** `WorkerV1` (projection) has no `worker_id` field, only `record_id`/
`contact_id`; map `WorkerV1.record_id` → `WorkerSchedulingFactV1.worker_id` when building the baseline
facts. The real Postgres reader always sets `record_id == contact_id` (`scenario_projection.py:229-231`),
so either source field resolves correctly today — use `record_id` for consistency with every other
`*V1 → *SchedulingFactV1`-shaped mapping in this codebase, which keys off `record_id`.

### Decision C — Source `tasks`/`demand`/`workers` for the baseline calculation via a shared, promoted drain helper

`_drain` (`calculators.py:145`) already pages a `ScenarioProjectionReader` group to exhaustion under a
row bound, pinning `scenario_version_id`/`site_id` on every page — exactly what's needed to read all
tasks/demand/workers/baseline-assignments for one scenario. It is private to `calculators.py` today,
and this story is the second consumer. **Promote it**: move `_drain` (unchanged logic) into a new
shared module `application/grounding/pagination.py`, export it, and have `calculators.py` import it
back — do not duplicate the loop, and do not reach into another module's `_`-prefixed name. Use
`page_size=200, max_rows=2000` for `tasks`/`demand`/`workers`/baseline-`assignments` reads (the fixture
has 1547 demand rows; `calculate_metric`'s single-task default of 400 under-bounds a whole-scenario
read — Facts table, row 9). Record `NOT COVERED: comparisons over a scenario exceeding 2000 rows in any
one group` in this module's `SCOPE_CONTROLS`, matching the `candidate_metrics.py` convention.

### Decision D — Constraint status: hard constraints both sides, soft constraints candidate-only

Candidate's `ConstraintResultV1[]` already exists on the persisted `ScheduleVersionV1` (hard + the five
proposal-derived soft kinds, Story 3.2 Decision 6). For the baseline, compute **only** hard constraints
via `validate_hard_constraints(baseline_assignments, facts, preserved_locks=())` — the proposal's five
soft constraint kinds (`avoid_worker`, `set_max_hours`, etc.) are evaluations of *this proposal's*
request and have no meaning against a pre-proposal baseline state; do not invent a baseline reading for
them. `ComparisonV1.constraint_status` therefore carries the candidate's full `ConstraintResultV1[]`
(hard + soft) plus the baseline's hard-only `ConstraintResultV1[]`, kept in two clearly-labelled fields
— never merged into one list that would look like a single apples-to-apples set.

### Decision E — Objective components ARE computable for both sides; they are not solver-internal

`MetricSetV1.objective_components` (both call sites) is `(("unmet_minutes", ...), ("overtime_minutes",
...))` — an application-level recomputation from assignments, **not** CP-SAT's internal weighted
objective terms (`candidate_metrics.py`'s own `SCOPE_CONTROLS`: "the engine prices all hours at base
rate"). This is exactly what `calculate_candidate_metrics` already returns for whichever assignment set
it's given — no "Not computed" fallback is needed for this field on either side. Reserve AC2's "Not
computed" wording for a genuinely unavailable value (see Decision B's wage gap does *not* trigger this —
placeholder wage still yields a real `0.0` for an empty baseline, which is a true number, not a missing
one; if a future story's non-empty-baseline patch cannot yet source wage, *that* is where "Not computed"
belongs, on `total_cost`/`overtime_minutes` specifically).

### Decision F — `ComparisonV1` is computed on read, not persisted; no new table, no new migration

AD-11 requires calculators to "produce or verify" claims against immutable evidence — recomputation
satisfies this without a cache. Gate staleness (AC4) on `expected_baseline_schedule_version` (frozen
onto `RunSnapshotV1` at run-accept time, already a field — `run_snapshot.py:67`) vs. the scenario's
*current* `ScenarioOverviewV1.baseline_schedule_version`, read fresh on every `GET`. **Both are `None`
today** (Decision A / Facts table row 6), so `None == None` is truthfully "not stale" — AC4's mechanism
is real and tested (seed a case where they differ, e.g. via a direct-write test fixture, and assert the
`stale: true` flag + expected/current values render) but **vacuously non-stale in production until
Story 4.3 ships baseline promotion** — the same honest-gap shape as Story 3.1's Gap 2 ("fail before
solver execution" was vacuously satisfied until Story 3.2 gave it a solver to fail before). State this
plainly in the story's own record; do not claim AC4 is "fully proven end-to-end" when its trigger cannot
occur yet.

---

## Architecture compliance guardrails

**New contract — `application/contracts/comparison.py`:**

```python
SCHEMA_VERSION = "1"

@dataclass(frozen=True)
class AssignmentDiffV1:
    added_worker_ids: tuple[str, ...]
    removed_worker_ids: tuple[str, ...]
    added_shift_ids: tuple[str, ...]
    removed_shift_ids: tuple[str, ...]
    added_task_ids: tuple[str, ...]
    removed_task_ids: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class ComparisonV1:
    candidate_schedule_version_id: UUID
    candidate_schedule_run_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    expected_baseline_schedule_version: str | None
    current_baseline_schedule_version: str | None
    stale: bool
    assignment_diff: AssignmentDiffV1
    candidate_metrics: MetricSetV1
    baseline_metrics: MetricSetV1
    candidate_constraint_results: tuple[ConstraintResultV1, ...]
    baseline_hard_constraint_results: tuple[ConstraintResultV1, ...]
    warnings: tuple[str, ...]
    unresolved_gap_record_ids: tuple[str, ...]  # candidate interval rows where served < required
    evidence_refs: tuple[EvidenceRefV1, ...]
    schema_version: str = SCHEMA_VERSION
```

Field names are free (AD-20 only fixes the *conceptual* shape: "candidate/baseline versions; affected
worker, shift and task diffs; interval coverage, overtime, cost/objective deltas; constraint status;
unresolved infeasibility") — do not rename `MetricSetV1`/`ConstraintResultV1`, which are already
canonical. Deltas (interval coverage, overtime, cost, objective components) are **derived client-side**
by subtracting `candidate_metrics` from `baseline_metrics` field-by-field, not precomputed into the
contract — both full `MetricSetV1`s are already immutable evidence-backed values, and shipping both
lets the UI show "candidate: X, baseline: Y, delta: X−Y" without losing either absolute number (AC2's
"Not computed" affordance needs the raw values, not a pre-collapsed delta, to distinguish "delta is
zero" from "delta is unknown").

**New calculator — `application/scheduling/comparison.py`:**

```python
def calculate_comparison(
    reader: ScenarioProjectionReader,
    connection: Any,
    *,
    candidate: ScheduleVersionV1,
    scenario_id: UUID,
    scenario_version_id: UUID,
    site_id: UUID,
    expected_baseline_schedule_version: str | None,
) -> ComparisonV1:
    ...
```

Reads tasks/demand/workers via the promoted `_drain` (Decision C), reads `baseline_assignments` the
same way, builds the placeholder `ValidationFactsV1` (Decision B), calls
`calculate_candidate_metrics`/`validate_hard_constraints` for both sides, diffs worker/shift/task ID
sets for `AssignmentDiffV1`, reads `ScenarioOverviewV1.baseline_schedule_version` for the staleness
check (Decision F), and returns `ComparisonV1`. **Recomputes candidate metrics too** (Decision B) rather
than trusting `candidate.metrics` blindly — if the recomputation disagrees with the persisted value,
that is itself evidence of drift and should raise, mirroring Story 3.2's own recomputation-equality test
pattern (`3-2-...md:143-147`).

**New repository method — `ScheduleRunRepository.get_candidate`:**

```python
def get_candidate(
    self, connection: Connection, *, schedule_run_id: UUID, site_id: UUID
) -> ScheduleVersionV1 | None:
```

Reads the `schedule_version` row by `schedule_run_id`+`site_id` (unique per `uq_schedule_version_run`),
deserializes `payload` via `TypeAdapter(ScheduleVersionV1).validate_python(row.payload)` — the exact
inverse of `finalize_run`'s `TypeAdapter(ScheduleVersionV1).dump_python(candidate, mode="json")`
(`schedule_run.py:1058`). Returns `None` when no candidate row exists (every non-`solver_completed`
terminal state, or a `solver_completed` row somehow missing its candidate — should not happen given the
`ck_schedule_run_candidate_completed` CHECK, but the port stays `| None` rather than asserting).

**New route — `GET /api/v1/schedule-runs/{run_id}/result`:**

Response envelope (new `ScheduleRunResultOut` in `api/schemas.py`):

```python
class ScheduleRunResultOut(BaseModel):
    run: ScheduleRunOut
    candidate: ScheduleVersionOut | None
    comparison: ComparisonOut | None
```

- `run` is always populated (reuses `_view_out`/`ScheduleRunOut` from Story 3.5/3.7 — do not fork a
  second run-summary shape).
- `candidate`/`comparison` are `None` together for any non-`solver_completed` status (AC3) — the route
  does not attempt a comparison against a candidate that doesn't exist.
- For `solver_completed`: `candidate` is always present (DB guarantees it); `comparison` is computed via
  `calculate_comparison`. A comparison calculation failure (e.g., a drained group exceeds its row bound)
  is a distinct 5xx problem, not a silently-omitted `comparison: null` — AC2's "Not computed" is a
  per-field affordance inside a successful comparison, not a way to paper over a failed one.
- Site isolation follows the **closest sibling route's actual pattern, not a catalogue-reader detour**:
  `GET /{run_id}` (`get_schedule_run`, `schedule_runs.py:527-538`) calls
  `repository.get_run(connection, run_id=run_id, site_id=session.site_id)` on an RLS-scoped connection
  from `get_site_context` (`api/deps.py`) and returns `_not_found()` (code `schedule_run_not_found`) on
  `None` — no `ScenarioCatalogueReader`/`scenario_not_found` involved anywhere on this route today. This
  new route does the same: `get_candidate`/the run lookup are scoped by `site_id` alone, and a missing
  or cross-site run returns `_not_found()` with `schedule_run_not_found`, matching the sibling route's
  code, not `get_projection`'s `scenario_not_found`. `ScheduleVersionV1` already carries `scenario_id`/
  `scenario_version_id` (`schedule_version.py:117-120`), so `calculate_comparison` takes them straight
  off the fetched candidate — no separate scenario resolution or catalogue-reader lookup needed at all.
- Declare `_PROBLEMS` (401/404) exactly like every other route in this router (Story 3.7's patch pass
  fixed this same omission once already — do not reintroduce it).

**Frontend — `ScenarioResults.tsx` (full rewrite, not incremental patch):**

- Loading → `Skeleton` (Story 1.6 primitive).
- Fetch failure → `InlineAlert` with retry, same pattern as `ScenarioRuns.tsx`'s error-with-data
  handling (Story 3.7 patch pass) — but Results has no "stale rows to keep visible" case since it's a
  single-resource fetch, not a list; a failure here is a full `InlineAlert`, not a partial render.
  Do **not** hide the Runs/Chat/Scenario Data tab links on failure (AC2's "remain available" spirit,
  same as Story 3.7 AC2 — reuse `ScenarioRunsWorkspace.test.tsx`'s "shell survives" testing pattern for
  Results too, this story's Task 9 names it explicitly).
- Non-terminal run (`solver_queued`/`solver_running`/`cancellation_requested`) → reuse
  `runs/ProgressCard.tsx` verbatim (already renders exactly this literal-state case; do not build a
  second progress card).
- Terminal, non-promotable (`solver_infeasible`/`solver_timed_out`/`solver_cancelled`/`solver_failed`)
  → new `TerminalOutcomeCard.tsx`: literal status (reuse `RunStatusBadge`), `reason`, and any
  `run.warnings`/evidence that exist even without a candidate. **No enabled control resembling
  "Approve as baseline" anywhere on this branch** (AC3) — not even disabled; there is nothing to
  disable when there is no candidate to approve.
- Terminal, feasible (`solver_completed`) → new `ComparisonSummary.tsx`: candidate/baseline version
  identifiers (with `IdentifierCopyButton`), `AssignmentDiffV1` (added/removed workers/shifts/tasks as
  labelled lists, not a raw diff blob), interval coverage/overtime/cost/objective **deltas** (computed
  in the component from the two `MetricSetV1`s the API already returned — AC2's "Not computed" applies
  per-field only when a value is genuinely absent, e.g. an empty `interval_coverage_*_minutes` tuple,
  never when it's a real zero), constraint status (candidate hard+soft, baseline hard-only, two
  visually separate lists — Decision D), warnings, unresolved gaps. `stale: true` renders a distinct
  banner naming expected/current baseline versions (AC4) — still shows the (frozen, historical) numbers
  underneath, never hides them.
- "Approve as baseline" on the completed branch: uniformly disabled, identical posture to Story 3.7's
  `RunsTable` `ApproveButton` (no working command exists — Epic 4/Story 4.1) — reuse that component or
  its exact pattern rather than inventing a second disabled-button convention.

---

## Previous story learnings to apply

**From Story 3.2 (candidate creation):** `calculate_candidate_metrics`/`validate_hard_constraints` are
the two functions this story's whole backend surface is built on top of — read them fully before writing
anything, do not re-derive their formulas. The recomputation-equality test pattern
(`test_candidate_validation.py`'s "rebuild `MetricSetV1` from the persisted candidate + snapshot and
assert equality") is the template for this story's own candidate-side recomputation check (Decision B).

**From Story 3.7 (Runs workspace):** Cancel/Retry taught the "server decides, don't speculatively guess
client-side" lesson (Trap 5) — apply the same here: don't pre-compute "is this run completed" client-side
before deciding whether to render `ComparisonSummary`; branch on the literal `run.status` the API
returns, exactly as `RunsTable` does. Reuse `RunStatusBadge`/`ProgressCard`/`IdentifierCopyButton`
verbatim — do not fork parallel components. The "shell survives a data-fetch failure" test pattern
(`ScenarioRunsWorkspace.test.tsx`, mounting the real route+shell against only a mocked network boundary)
is exactly what this story's Task 9 should do for Results, because Story 3.7's own code review found
that mocking the child component wholesale is what let two real defects ship with a fully green suite.

**From Story 3.1 (Gap 1, locks/baseline assignments):** "Do not write a test that asserts 'X was
preserved' against a supply of zero" — the dominant Epic 2 retro failure mode. Every test asserting
comparison behavior against an empty baseline must be paired with at least one seeded-non-empty-baseline
test proving the mechanism itself (Decision A).

**From Story 1.6 (shared primitives):** `Skeleton`, `EmptyState`, `InlineAlert`, `StatusBadge`,
`IdentifierCopyButton` are the fixture-catalogue vocabulary — reused, never reimplemented. Accessibility
is proven by automated Vitest/Testing-Library checks only (no manual AT verification scope, per
`EXPERIENCE.md`'s Accessibility Floor).

---

## Traps and guards

### Trap 1: Building a synthetic baseline schedule version to make comparison "look real"
Story 3.2 explicitly forbade this. The baseline is `get_baseline_assignments()`, full stop — empty
today, real always. **Guard:** grep the diff for any new row inserted into `schedule_version` outside
`finalize_run`'s existing candidate-creation path; there should be none.

### Trap 2: Trusting `candidate.metrics` from the persisted payload without recomputing
AD-11 requires calculators to *verify*, not just relay — a silent mismatch between what's stored and
what recomputes must never surface as an ordinary 200. **Guard:** a test that corrupts the persisted
`schedule_version.payload`'s metrics (direct DB write) and asserts `calculate_comparison` **raises**
(not: returns 200 with the recomputed value silently substituted) — the route then maps that to a
distinct 5xx problem, per Task 5's "a comparison calculation failure is a distinct 5xx problem, not a
silently-omitted `comparison: null`." This mirrors Story 3.2's own recomputation-equality test in
*intent* (both prove recomputation happens and disagreement is detectable) but differs in outcome: 3.2's
test is a same-process equality assertion inside candidate creation itself, not an API-level 200 with
swapped numbers.

### Trap 3: Computing baseline `total_cost`/`overtime_minutes` as if wage data were real
It works today only because baseline assignments are empty (Decision B). **Guard:** a unit test on the
comparison calculator directly (not through the API) that seeds a **non-empty** baseline assignment set
via a fake reader and asserts the wage-placeholder gap is either explicitly flagged in the result or
covered by a `deferred-work.md` entry — do not let a green suite imply this is production-correct for a
non-empty baseline. **This seeded fixture must give every demand task at least one qualified worker** —
`calculate_candidate_metrics` raises `ValueError` for any `volume`-family task with zero qualified
workers regardless of assignment emptiness (Facts table), an unrelated failure mode that would otherwise
make this test red for the wrong reason.

### Trap 4: Rendering an enabled "Approve as baseline" anywhere on the Results page
No approval command exists (Epic 4 / Story 4.1). AC3 is explicit: "no enabled approval action is
displayed" — not "displayed but disabled elsewhere," `displayed` at all for a non-promotable outcome.
**Guard:** a test asserting zero elements with an "Approve" accessible name exist in the DOM for every
non-`solver_completed` status; for `solver_completed`, assert the one that exists is `disabled`.

### Trap 5: Silently recomputing a "current" comparison when the baseline has moved
AC4: "not silently recalculated or represented as current." Once `stale: true`, still render the frozen
numbers with a stale banner — do not fetch a fresh comparison against the new baseline and swap the
numbers without the banner. **Guard:** a test seeding a baseline change between two fetches asserts the
second fetch's `stale: true` and that the returned `candidate_metrics`/`baseline_metrics` still describe
the **original** comparison inputs, not a silently-rebased one.

### Trap 6: Treating "Not computed" as a shortcut for "I didn't implement this field"
AC2 reserves "Not computed" for genuine absence (Decision E). Every `MetricSetV1` field this story's
calculator can honestly produce (which is nearly all of them, per Decision E) must be a real number, not
a lazy "Not computed" placeholder. **Guard:** a test asserting `objective_components` and
`interval_coverage_*_minutes` are non-empty tuples for a scenario with real demand, not "Not computed"
text.

### Trap 7: Reaching into `calculators.py`'s private `_drain`
Decision C requires promoting it to a shared module first. **Guard:** lint/grep for any cross-module
import of an underscore-prefixed name; the comparison calculator's own file should import the promoted,
public name only.

### Trap 8: Forgetting the row-bound headroom for a whole-scenario drain
`calculate_metric`'s single-task default (`max_rows=400`) is not this story's default (Decision C:
`max_rows=2000`). **Guard:** a test against the larger fixture (1547 demand rows) asserting the drain
completes without raising `CalculationLimitError`.

---

## Tasks / Subtasks

- [ ] **Task 1 — `ComparisonV1` contract** (AC: 1)
  - [ ] `application/contracts/comparison.py`: `AssignmentDiffV1`, `ComparisonV1` per the Architecture
        guardrails' shape. `schema_version` on both, `SCHEMA_VERSION = "1"`.
  - [ ] Contract-shape test mirroring `schedule_version.py`'s own (round-trip via `TypeAdapter`, every
        AD-20-required concept present).

- [ ] **Task 2 — Promote `_drain` to a shared module** (Decision C, Trap 7)
  - [ ] Move `_drain` from `calculators.py` into `application/grounding/pagination.py`, export it
        publicly (rename without the leading underscore), update `calculators.py`'s three call sites to
        import it back. No behavior change — same signature, same `MAX_PAGES` guard.
  - [ ] Full Epic 2 grounding test suite still green (proves the move was mechanical).

- [ ] **Task 3 — Baseline comparison calculator** (AC: 1, 2, 4; Decisions B–F; Traps 2, 3, 6, 8)
  - [ ] `application/scheduling/comparison.py`: `calculate_comparison(...)` per the Architecture
        guardrails. Drains tasks/demand/workers/baseline-assignments via the promoted helper
        (`page_size=200, max_rows=2000`), builds the wage/shift-placeholder `ValidationFactsV1` for the
        baseline side (Decision B, with the inline comment naming the gap), calls
        `calculate_candidate_metrics`/`validate_hard_constraints` for **both** candidate and baseline
        assignment sets, diffs worker/shift/task ID sets into `AssignmentDiffV1`, computes
        `unresolved_gap_record_ids` from the candidate's own `interval_coverage_*_minutes` (served <
        required), reads `ScenarioOverviewV1.baseline_schedule_version` and compares it against the
        `expected_baseline_schedule_version` argument to set `stale`/`expected_baseline_schedule_version`/
        `current_baseline_schedule_version` on `ComparisonV1` (Decision F, AC4).
  - [ ] `SCOPE_CONTROLS` tuple recording the `max_rows=2000` bound and the wage/shift-placeholder gap
        (Story 2.5's convention).
  - [ ] Tests: empty baseline (today's real case) produces a real, non-"Not computed" comparison
        showing 100% net-new; a **seeded non-empty** baseline (fake reader, every demand task given at
        least one qualified worker per Trap 3's note) proves the diff/delta mechanism goes red on a
        mutation (Trap 3's guard); candidate-metrics recomputation disagreement with a corrupted
        persisted payload raises, not silently substitutes (Trap 2's guard); a 1547-row demand drain
        completes under the raised bound (Trap 8's guard); `objective_components`/
        `interval_coverage_*` are real tuples, never "Not computed" (Trap 6's guard); **AC4/Decision F:**
        a fake `ScenarioOverviewV1` reader returning a `baseline_schedule_version` different from the
        `expected_baseline_schedule_version` argument asserts `stale: true` with both values populated
        on the result; equal (including both `None`, today's real case) asserts `stale: false` — this is
        the one test that actually exercises AC4's mechanism; Task 5/9 only carry it through the API/UI.

- [ ] **Task 4 — Repository: `get_candidate` read** (AC: 1, 2, 3)
  - [ ] `application/ports/schedule_run.py`: add `get_candidate` to `ScheduleRunRepository` Protocol.
  - [ ] `adapters/postgres/schedule_run.py`: implement — SELECT `schedule_version` by
        `schedule_run_id`+`site_id`, deserialize `payload` via
        `TypeAdapter(ScheduleVersionV1).validate_python`. Return `None` if no row.
  - [ ] Unit test: a `solver_completed` run's candidate reads back byte-identical (via canonical hash)
        to what `finalize_run` wrote; a non-`solver_completed` run returns `None`; cross-site read
        returns `None` (site isolation).

- [ ] **Task 5 — Route: `GET /api/v1/schedule-runs/{run_id}/result`** (AC: 1, 2, 3)
  - [ ] `api/schemas.py`: `ScheduleVersionOut`, `ComparisonOut`/`AssignmentDiffOut`,
        `ScheduleRunResultOut { run, candidate, comparison }`.
  - [ ] `api/routers/schedule_runs.py`: new route, `site_id`-scoped exactly like `get_schedule_run`
        (`schedule_runs.py:527-538`) — no `ScenarioCatalogueReader` detour, no separate scenario
        resolution. `scenario_id`/`scenario_version_id` for `calculate_comparison` come straight off the
        fetched candidate's `ScheduleVersionV1`. Unknown/cross-site run id → `_not_found()`, code
        `schedule_run_not_found` (matching the sibling route, not `get_projection`'s
        `scenario_not_found`). `_PROBLEMS` (401/404) declared like every sibling route (Trap from Story
        3.7's own patch pass — don't reintroduce the gap).
  - [ ] Router tests: `solver_completed` → full envelope with `comparison` populated;
        `solver_infeasible`/`solver_timed_out`/`solver_cancelled`/`solver_failed` → `candidate`/
        `comparison` both `None`, `run` populated with literal status/reason; non-terminal
        (`solver_queued`/`solver_running`/`cancellation_requested`) → same null shape; unknown run id →
        `schedule_run_not_found`; cross-site run id → same code, not 403 (matches the repo's
        non-disclosing pattern, AD-3).

- [ ] **Task 6 — Regenerate the OpenAPI contract** (AC: 1, 2, 3)
  - [ ] `npm run codegen` (backend must import cleanly) so `frontend/openapi.json`/`schema.d.ts` carry
        the new route/schemas. No hand-authored frontend types.

- [ ] **Task 7 — Frontend API client + hook**
  - [ ] `api/scheduleRuns.ts`: add `getScheduleRunResult(runId)` (GET, schema-derived types).
  - [ ] `hooks/useScheduleRunResult.ts`: TanStack Query wrapper (`queryKey: scheduleRunResultKey(runId)`
        following the `scheduleRunsKey`/`proposalKey` exported-factory convention Story 3.7's patch pass
        established), `enabled` on non-empty `runId`, `useRedirectOnUnauthorized`/`getErrorStatus` wired
        like the sibling hooks.
  - [ ] Tests for both (success/failure shape; disabled-until-runId).

- [ ] **Task 8 — `TerminalOutcomeCard.tsx`** (AC: 3; Trap 4)
  - [ ] Renders literal status (`RunStatusBadge`), reason, available warnings/evidence for a
        non-promotable or non-terminal run. Zero elements with an "Approve" accessible name.
  - [ ] Test: renders for all 4 non-promotable terminal statuses + all 3 non-terminal statuses, no
        forbidden token (%, ETA, remaining, likely, probably — same list Story 3.7 used), zero "Approve"
        controls.

- [ ] **Task 9 — `ComparisonSummary.tsx`** (AC: 1, 2, 4; Traps 4, 5, 6)
  - [ ] Renders candidate/baseline version identifiers (`IdentifierCopyButton`), `AssignmentDiffV1` as
        labelled added/removed lists, coverage/overtime/cost/objective **deltas** derived from the two
        `MetricSetV1`s, constraint status (candidate full, baseline hard-only, visually separate,
        Decision D), warnings, unresolved gaps. `stale` banner with expected/current versions when
        `comparison.stale`. "Approve as baseline" uniformly disabled (Story 3.7's `ApproveButton`
        pattern, reused).
  - [ ] Tests: real (non-"Not computed") values render for every AC1-named field on a populated
        comparison; a field with a genuinely empty source tuple renders "Not computed" (not zero); a
        `stale: true` comparison shows the banner **and** still renders the historical numbers
        underneath (Trap 5); zero enabled "Approve" controls (Trap 4).

- [ ] **Task 10 — `ScenarioResults.tsx` route wiring + `deferred-work.md` entries**
  - [ ] Replace the `WorkspaceTabPlaceholder` outright: loading (`Skeleton`) → error (`InlineAlert` +
        retry) → non-terminal (`ProgressCard`, reused from `components/runs/`) → non-promotable
        terminal (`TerminalOutcomeCard`) → completed (`ComparisonSummary`).
  - [ ] New `ScenarioResultsWorkspace.test.tsx` mounting the real shell/route/hooks against only a
        mocked network boundary (Story 3.7's `ScenarioRunsWorkspace.test.tsx` pattern) — asserts the
        Chat/Scenario Data/Runs tabs survive a Results fetch failure.
  - [ ] Record in `deferred-work.md`: (a) the wage-placeholder/shift-placeholder gap from Decision B,
        naming "the first story that populates a real non-empty baseline assignment supply" as owner;
        (b) AC4's staleness mechanism being real-but-vacuously-non-stale until Story 4.3 (Decision F),
        naming Story 4.3 as the trigger; (c) any other conscious scope trim discovered during
        implementation, not left as a silent gap.
  - [ ] Full regression: backend `pytest` (postgres included), frontend `vitest run`, `tsc --noEmit`,
        `oxlint`, `npm run build`. Walk every Done checklist item below against the shipped code.

---

## Done checklist

- [ ] `application/contracts/comparison.py` — `ComparisonV1`/`AssignmentDiffV1` implemented and tested
- [ ] `_drain` promoted to a shared, exported module; Epic 2 grounding suite unaffected
- [ ] `application/scheduling/comparison.py` — `calculate_comparison` reuses Story 3.2's calculators,
      does not duplicate their formulas
- [ ] `ScheduleRunRepository.get_candidate` implemented and tested (byte-identical read-back, site
      isolation, `None` for non-completed runs)
- [ ] `GET /api/v1/schedule-runs/{run_id}/result` implemented, `_PROBLEMS` declared, tested for every
      terminal/non-terminal status
- [ ] Frontend: `TerminalOutcomeCard.tsx`, `ComparisonSummary.tsx`, `useScheduleRunResult` hook,
      `getScheduleRunResult` client function
- [ ] `ScenarioResults.tsx` replaces the placeholder end-to-end; every "View Results"/"View Progress"
      link from Story 3.7's Runs workspace now lands on real content
- [ ] AC1: `ComparisonV1` names both versions, includes worker/shift/task diffs, coverage/overtime/cost/
      objective deltas, constraint status (both sides, correctly scoped per Decision D), warnings,
      unresolved gaps — every value produced by an application calculator, none by the model
- [ ] AC2: deterministic status/warnings/metrics/comparison/schedule/evidence render independent of any
      model summary; "Not computed" reserved for genuine absence only (Decision E, Trap 6)
- [ ] AC3: non-promotable terminal outcomes are visually/textually distinct from fetch failure and from
      a completed result; zero enabled (or displayed) approval controls (Trap 4)
- [ ] AC4: staleness mechanism is real and tested against a seeded case; recorded as vacuously
      non-stale in production until Story 4.3 (Decision F) — not overclaimed as fully proven end-to-end
- [ ] Baseline-empty-today comparisons show real, non-fabricated numbers (100% net-new), not
      placeholders (Decision A)
- [ ] Wage/shift-placeholder gap and AC4's vacuous-today status both recorded in `deferred-work.md`
      with explicit owners (Task 10)
- [ ] Keyboard navigation and WCAG AA accessibility pass automated checks only (Story 1.6/3.7 posture,
      no new manual-AT scope)
- [ ] Test: `ScenarioResultsWorkspace.test.tsx` proves the workspace shell survives a Results fetch
      failure
- [ ] Full backend + frontend regression, typecheck, lint, and production build all pass

---

## Summary

Story 3.8 builds the fourth and last peer scenario surface — Results — closing the loop Story 3.7 opened
by linking every run row to a page that, until now, was a placeholder. The backend adds one contract
(`ComparisonV1`), one calculator that deliberately reuses Story 3.2's `calculate_candidate_metrics`/
`validate_hard_constraints` against the scenario's real (today: empty) baseline assignment supply rather
than inventing a parallel formula or a synthetic baseline row, one repository read method, and one route.
The frontend adds two new components and a hook, and rewrites `ScenarioResults.tsx` end-to-end.

**Key architectural decisions:**
1. Baseline = `get_baseline_assignments()` (real, empty today) — never a synthetic/pointer-based row
   (Story 3.2 explicitly forbade the latter)
2. Reuse, don't reinvent: the same two calculators produce both candidate and baseline `MetricSetV1`/
   hard `ConstraintResultV1[]`
3. Constraint status is two clearly-separated lists (candidate hard+soft, baseline hard-only) — the
   proposal's soft constraints have no baseline reading
4. `ComparisonV1` is computed on read, not cached — no new migration
5. AC4's staleness check is a real, tested mechanism that is honestly vacuous in production until Story
   4.3 ships baseline promotion — recorded as such, not overclaimed

**This story unblocks** Story 4.1 (needs a rendered comparison to bind an approval to) and completes the
planner-visible surface Stories 3.10–3.12's proof stories exercise end-to-end.

---

## Dev Agent Record

### Agent Model Used

_To be filled by the dev agent._

### Debug Log References

### Completion Notes List

### File List
