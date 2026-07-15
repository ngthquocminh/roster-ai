# Phase 3: On-Demand Insight Reports - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a **decoupled, on-demand, metric-grounded, cached** natural-language insight
report for a completed run:

`GET insights for a COMPLETED run → (first call) generate a NL report off the
event loop, citing the run's REAL metric values verbatim → cache it in
runs.insight_json → (later calls) return the cache without re-calling the
provider.` Stub-driven, zero network calls in CI.

Insight generation is a **separate post-run step**: a provider failure must leave
the run COMPLETED and result_json untouched — it can never invalidate a
successfully computed schedule (INS-01…INS-04).

**Not in this phase** (later slices / deferred, do not pull in): auto-generate
insights after every run (INS-05, v2); the real Claude provider + penalty
calibration (Phase 4, LLM-02/ENG-04/TEST-04); what-if compare + delta explanation
(Phase 5); any frontend/UI (Phase 4+). Phase 3 is independent of Phase 2 but
consumes the `result.warnings[]` surface Phase 2 produced (D-13).
</domain>

<decisions>
## Implementation Decisions

### Endpoint & generation flow
- **D-01:** **GET lazy-generate + cache** on a single endpoint
  (`GET /runs/{run_id}/insights`, mirroring the existing
  `GET /runs/{run_id}/result`). The first GET on a COMPLETED run generates the
  report and writes `runs.insight_json`; subsequent GETs return the cached value
  (INS-04, criterion 4). No separate POST-to-generate step.
- **D-02:** Generation runs **off the event loop on a worker thread, but the GET
  blocks and returns the report in that same response** (criterion 1: "a GET
  returns a report" — satisfied in one call, no polling, no new insight-status
  field). The user explicitly chose this over an inline synchronous handler AND
  over a 202/poll async model.
  - **Pool caveat (research item):** the existing solve pool in
    `services/run_service.py` is a `ThreadPoolExecutor(max_workers=1)` that
    **serializes** work — running insight generation there would queue it behind
    CPU-bound solves. Researcher/planner must decide the thread path: a separate
    executor for insights, or simply rely on FastAPI running the sync `def` route
    in its own threadpool (which already keeps the event loop unblocked). Do NOT
    reuse the single-worker solve pool for insight generation.

### Report content & structure
- **D-03:** Structure = **short prose summary + structured metric highlights**
  (a 1-2 sentence narrative followed by labeled metric lines/bullets). Not
  free-form prose, not fully-sectioned headings.
- **D-04:** Length/tone = **concise operations-brief** — a few sentences plus a
  handful of metric highlights; quick to read, easy to ground.
- **D-05:** The report MUST always cover all four of:
  1. **Coverage** — per-function/family served-vs-required hours + pct
     (`metrics.coverage_by_function`).
  2. **Unmet hours + total cost** — `metrics.total_unmet_hours`,
     `metrics.total_cost` (the top-line objective outcomes).
  3. **Degenerate-family warnings** — narrate `result.warnings[]` (zero-coverage
     families, Phase-2 D-13) HONESTLY rather than reporting success. This is the
     concrete mechanism behind INS-03's "no generic 'coverage was adequate'" rule.
  4. **Applied overrides in effect** — which NL constraints/overrides shaped this
     run (sourced from the scenario's `overrides` JSON at solve time).

### Grounding enforcement (INS-03 / criterion 2)
- **D-06:** **Post-hoc number-verification guard**, provider-agnostic. After
  generation, extract the numerics from the report text and assert each appears in
  the run's metrics JSON; reject/flag the report if any number is not found. This:
  - makes criterion 2 ("every number appears verbatim") **directly testable**;
  - guards the **real Claude provider in Phase 4** too (the guard lives at the
    seam, not in the stub);
  - is stronger than template-slots-only (guarantee would live only in the stub)
    or trust-the-prompt (weakest, hard to test).
  - **Planner note:** decide the failure mode when the guard catches an
    ungrounded number — treat as a generation failure (→ D-08 5xx path, nothing
    cached) so a fabricated report is never persisted or returned.

### Failure & not-ready responses
- **D-07:** **Not-ready** (run not COMPLETED yet) → **200 with a not-ready body**
  (e.g. `ready=false` + reason/current-status). **Deliberate divergence** from the
  existing `GET /runs/{id}/result`, which returns **409**. The user chose the
  friendlier 200 polling-style shape on purpose — downstream agents must NOT
  "correct" this to 409 for consistency.
- **D-08:** **Provider failure during generation** → **5xx (502/503) with error
  detail**; the run stays **COMPLETED**, `result_json` is untouched, and **nothing
  is cached** (so a later retry can succeed). Insights are eligible for
  **COMPLETED runs only** (a FAILED run has no metrics to ground against).

### LLM provider seam (structural, locked by LLM-01)
- **D-09:** The `LLMProvider` Protocol gains a **second operation,
  `generate_insights`**, alongside `parse_constraints` (LLM-01: "two operations").
  `StubLLMProvider` must implement it **deterministically** with no external I/O
  (TEST-01) so CI stays stub-only and criterion-2 verification is reproducible.
  Reuse the existing `get_llm_provider` dependency seam (LLM-03) — no new injection
  mechanism.
  - **Planner discretion:** the input contract for `generate_insights` (raw
    metrics dict vs a prepared summary vs the domain `SolveResult`) and its return
    shape (plain string vs small structured object). Keep it provider-neutral
    (mirror D-08/D-09 of Phase 1: no vendor payload crosses the Protocol).

### Caching semantics
- **D-10:** A new `runs.insight_json TEXT` column holds the cached report
  (INS-04). No migrations framework exists (DDL is embedded in `store/db.py` as
  `CREATE TABLE IF NOT EXISTS`), so the planner must handle adding the column for
  **existing** DBs (an `ALTER TABLE … ADD COLUMN` guard) as well as the schema
  string for fresh DBs. Runs are immutable once COMPLETED (a re-solve creates a new
  run), so **no cache invalidation** is needed.

### Claude's Discretion
- Exact prose wording / phrasing of the report (within D-03 structure + D-04
  conciseness).
- `generate_insights` input/return contract shape (see D-09 planner discretion).
- Insight-generation thread path (separate executor vs FastAPI `def`-route
  threadpool) — see D-02 pool caveat; just NOT the single-worker solve pool.
- Numeric-extraction strategy for the D-06 guard (regex over the report text,
  tolerance for formatting like `%`, commas, decimals) — planner's call, but it
  must catch fabricated figures.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project design source-of-truth
- `docs/design.md` — engineering design of record: scheduling model + the LLM
  layer (provider seam, soft-override mechanism, insight step).
- `docs/PLAN.md` — hand-written phase tracker this GSD milestone formalizes.

### Requirements / roadmap (this phase)
- `.planning/REQUIREMENTS.md` — Phase-3 requirement IDs: **INS-01, INS-02, INS-03,
  INS-04** (and the locked LLM-01/LLM-03, TEST-01 seam constraints this phase
  relies on).
- `.planning/ROADMAP.md` §"Phase 3: On-Demand Insight Reports" — goal + 4 success
  criteria the build is judged against.
- `.planning/phases/02-full-5-tool-set-safe-validation/02-CONTEXT.md` — Phase-2
  decisions, esp. **D-13** (the `result.warnings[]` degenerate-family surface this
  report narrates) and the partial-apply / stub patterns.
- `.planning/phases/01-first-nl-constraint-end-to-end/01-CONTEXT.md` — provider
  seam design (D-08/D-09: provider-neutral Protocol, no vendor payload crosses the
  boundary) the new `generate_insights` op must follow.

### Live code seams this phase touches
- `backend/llm/base.py` — `LLMProvider` Protocol + `create_provider` factory;
  **add `generate_insights`** here (D-09); currently only `parse_constraints`.
- `backend/llm/stub.py` — `StubLLMProvider`; add a deterministic
  `generate_insights` implementation (no external I/O) (TEST-01).
- `backend/api/deps.py` — `get_llm_provider` dependency (reuse, do not replace).
- `backend/api/routers/runs.py` — existing `GET /runs/{id}/result` (the 409
  not-ready pattern, which D-07 deliberately diverges from); add
  `GET /runs/{id}/insights` alongside it.
- `backend/api/schemas.py` — add an insight response schema (`RunOut` is the
  current run shape).
- `backend/services/run_service.py` — `_execute`, the single-worker
  `ThreadPoolExecutor` (D-02 pool caveat); pattern for off-event-loop work and
  RunRepo status writes. Likely home (or a sibling service) for an
  `insight_service`.
- `backend/services/serialize.py` — `serialize_result` defines the exact metrics
  JSON the report cites and the D-06 guard verifies against
  (`total_cost`, `total_unmet_hours`, `coverage_by_function`, `coverage_by_day`,
  `warnings`).
- `backend/store/db.py` — `runs` table DDL; add `insight_json TEXT` (D-10) for
  fresh DBs + an `ALTER TABLE` guard for existing ones.
- `backend/store/repositories.py` — `RunRepo`; add read/write for `insight_json`.
- `backend/domain/result.py` — `SolveResult` / metrics / `warnings[]` shape the
  report draws from.
- `backend/tests/test_api.py` — `StubEngine` + `app.dependency_overrides` pattern;
  template for stubbing `get_llm_provider.generate_insights` and the
  generate→cache→provider-failure→not-ready tests.
</code_context>

<code_context>
## Existing Code Insights

### Reusable Assets
- `serialize_result` (`services/serialize.py`): the canonical metrics dict the
  report cites and the D-06 grounding guard verifies against. Already coerces
  NaN/inf → None (lex round-2 timeout case) — the report/guard must handle null
  metric values gracefully.
- `RunRepo` + `runs.result_json` pattern (`store/repositories.py`): the exact
  read/write template for the new `insight_json` cache column.
- `GET /runs/{id}/result` (`api/routers/runs.py`): not-ready / status-gate
  pattern to mirror structurally (D-07 changes its status code to 200, not the
  shape of the gate logic).
- `StubEngine` + `app.dependency_overrides` (`tests/test_api.py`): no-live-API
  test seam; extend for a stub `generate_insights` and the failure-injection test
  (criterion 3).
- Single-worker `ThreadPoolExecutor` + RunRepo status writes
  (`services/run_service.py`): the off-event-loop precedent — but see D-02, do NOT
  reuse the serialized solve pool for insights.

### Established Patterns
- **Provider-neutral Protocol seam:** nothing vendor-specific crosses
  `LLMProvider` (Phase 1 D-08/D-09); `generate_insights` follows the same rule so
  Phase 4's real Claude drops in unchanged.
- **Service raises / router translates:** services raise for caller-level errors
  (e.g. unknown run), routers map to HTTP; partial/expected outcomes go in the
  response body. Applies to the not-ready (D-07) and failure (D-08) paths.
- **Per-request fresh settings + dependency injection** for swappable seams
  (`get_llm_provider`).
- **No migrations framework:** schema is embedded `CREATE TABLE IF NOT EXISTS` in
  `store/db.py`; column additions need explicit handling for existing DBs (D-10).

### Integration Points
- New `GET /runs/{id}/insights` route mounted in `api/main.py` alongside
  health/fixtures/scenarios/runs/constraints.
- An `insight_service` orchestrates: load run → gate on status (COMPLETED) →
  return cache if present → else generate off the event loop → run the D-06
  grounding guard → persist `insight_json` → return. Provider failure / guard
  failure → 5xx, nothing cached (D-08).
- Applied-overrides content (D-05 item 4) is read from the scenario's `overrides`
  JSON associated with the run.

</code_context>

<specifics>
## Specific Ideas

- The not-ready response (D-07) is intentionally **200 + `ready=false`**, NOT the
  409 the result endpoint uses — a conscious, friendlier polling-style choice.
- The degenerate-family `warnings[]` narration (D-05 item 3) is the concrete way
  the report avoids generic "coverage was adequate" language (INS-03): when a
  family has real demand but zero served hours, the report must say so.
- The D-06 grounding guard is deliberately **provider-agnostic** so it also
  protects the Phase-4 real-Claude path, not just the stub.
- A fabricated/ungrounded number must never be cached or returned — guard failure
  routes to the D-08 5xx path.
</specifics>

<deferred>
## Deferred Ideas

- **Auto-generate insights after every completed run (INS-05)** — v2; Phase 3 is
  on-demand only.
- **Real Claude `generate_insights` implementation + model config (LLM-02)** —
  Phase 4; Phase 3 wires only the stub behind the seam.
- **Async 202 / polling insight model with an insight-status field** — considered
  and rejected in favor of the blocking-GET-on-worker-thread model (D-02). Could
  revisit if generation latency grows.
- **What-if compare + delta explanation** — Phase 5.

### Reviewed Todos (not folded)
- **WR-05 — Add real-engine test for ENG-05 degeneracy detection** (testing):
  reviewed; not folded. It hardens the Phase-2 `warnings[]` surface this report
  consumes, but the test itself is a Phase-2 testing gap, not insight-report work.
- **WR-04 — Harden scenario fixture path against traversal** (api): reviewed; not
  folded. A Phase-4/security item in `constraint_service.py`, unrelated to the
  insight endpoint.

</deferred>

---

*Phase: 3-On-Demand Insight Reports*
*Context gathered: 2026-06-30*
