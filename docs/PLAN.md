# ShiftMind — Build Plan & Status

Living tracker for the build. **[`design.md`](design.md) is the source of truth
for *how*; this file tracks *what's done* and *what's next*.** Update the
checkboxes as work lands; keep phase status in sync with the table below.

Status legend: ✅ done · 🟡 in progress · ⬜ not started · ⏸ deferred/optional

### How we document a phase

1. **Before coding** — write a per-phase plan doc `phase-<n>-<name>.md` (here in
   `docs/`): goal & measurable targets, design sketch, step-by-step tasks, open
   questions. Expand this file's phase checklist to match.
2. **While building** — tick the checklist here; keep the phase doc current;
   update [`API.md`](API.md) when endpoints change.
3. **When it ships** — fold the durable design into [`design.md`](design.md),
   mark the phase ✅ here. The phase doc stays as a record (or is deleted).

## Status at a glance

| Phase | Scope | Status |
|---|---|---|
| 1 | Scheduling Engine + data spine | ✅ complete |
| 2 | Backend skeleton (FastAPI + SQLite + runs) | ✅ complete |
| 3 | LLM layer (NL constraints + insights) | ⬜ next |
| 4 | Frontend (React UI) | ⬜ |
| 5 | What-if + delta explanation, polish, deploy | ⬜ |

**Current focus:** Phases 1–2 complete and committed; Phase 3 (LLM layer) is the
next build target (not yet started).

---

## Phase 1 — Scheduling Engine + data spine ✅

Plan doc: [`phase-1-engine.md`](phase-1-engine.md).

The distilled CP-SAT engine that turns a real-schema weekly input into a
schedule + coverage/cost metrics. CLI only — no web, no LLM.

- [x] Fixture tool (`fixtures/build_short_input.py`) — vertical shrink, full
      week, coherent supply, demand scaled to real roster-window capacity
- [x] Input adapter (`ingest/`) — real-schema JSON → `SchedulingProblem`,
      consumes materialized Workload tables; all 3 demand families
- [x] Pure domain types (`domain/`) — no solver/web deps
- [x] CP-SAT model (`engine/cpsat/builder.py`) — shift gen, shift↔task link,
      hourly coverage + unmet, qualification gate, hours/shift/gap caps
- [x] Lexicographic objective (`engine/cpsat/objective.py`) — unmet → cost via
      solve-and-lock, with round-1 snapshot so a round-2 timeout degrades
      gracefully (no crash)
- [x] Engine seam (`engine/base.py`) — `SchedulerEngine` Protocol + registry
      (swap CP-SAT for PuLP/CPLEX later without touching domain/adapter)
- [x] CLI `run.py` — load → solve → print per-function/per-day coverage, cost,
      schedule sample; optional time-limit arg
- [x] Tests — `test_engine_small.py` (known-optimum), `test_adapter.py` (fixture
      parses without loss); 5 passing
- [x] Dependency management via uv (`pyproject.toml` + `uv.lock`)
- [x] Repo hygiene — no proprietary names / external paths; 16 MB weekly input
      git-ignored; committed tiny fixture

**Done criteria (met):** deterministic solve of the fixture; unmet-optimal in
~20s; tests green. See `design.md` §3.6.

### Phase 1 follow-ups (optional, not blocking)
- [ ] ⏸ Tune `DEMAND_LOAD` / task mix so low-coverage functions (Receiving ~10%,
      Pick ~35%) land in a more even band, if a prettier demo matters
- [ ] ⏸ Round-2 relative-gap stop so cost-optimality doesn't take ~2 min on the
      full week (see Open decisions)

---

## Phase 2 — Backend skeleton ✅

Plan doc: [`phase-2-backend.md`](phase-2-backend.md).

FastAPI app exposing the engine: manage scenarios, trigger runs off the event
loop, serve results. SQLite (WAL) persistence. No LLM yet.

- [x] FastAPI app scaffold (`api/`: main, deps, schemas, routers) + uvicorn
- [x] SQLite schema + repos (`store/`): scenarios, runs (WAL, per-connection)
- [x] Scenario CRUD (create from a fixture; `overrides` JSON column reserved for
      Phase 3 NL constraints)
- [x] Run execution **in a worker thread** (`services/run_service.py`, single
      pool); status lifecycle `PENDING → RUNNING → COMPLETED/FAILED`
- [x] Results endpoints: run status, metrics, schedule rows, coverage
      (`GET /runs/{id}`, `/runs/{id}/result`); NaN cost coerced to null
- [x] Existing `SchedulerEngine` wired behind a service layer (no domain leak);
      engine is a `get_engine` dependency seam (tests inject a stub)
- [x] API tests (TestClient + stub engine): scenario → run → result lifecycle
- [x] Local run docs in README (uv + uvicorn + curl walkthrough)

**Done criteria (met):** POST a scenario, trigger a run, poll to `COMPLETED`,
GET schedule + metrics — all via HTTP, solve off the event loop. Verified
end-to-end with the real CP-SAT engine (run finished `COMPLETED`/`UNKNOWN` in
~11s at an 8s limit; API stayed responsive during the solve).

### Phase 2 follow-ups (optional, not blocking)
- [ ] ⏸ Run cancellation + concurrency limits (currently one solve at a time)
- [ ] ⏸ Input upload endpoint (currently fixtures must exist in `data/`)
- [ ] ⏸ Per-scenario engine selection (currently always `cpsat`)

---

## Phase 3 — LLM layer ⬜

Natural-language constraint editing + insight generation, behind an
`LLMProvider` Protocol (Claude default).

- [ ] `LLMProvider` Protocol + Claude implementation (config-driven model id)
- [ ] NL → solver-hook tools: `lock_worker_shift`, `set_min_workers_per_task`,
      `exclude_worker_from_task`, `scale_demand`, `set_max_hours`
- [ ] Tool-call validation against real scenario IDs (reject unknown refs)
- [ ] Apply overrides as **soft** constraints (a bad tweak penalizes, never
      makes the model infeasible)
- [ ] Insight generator: run metrics → structured natural-language report
- [ ] Insights as a **separate step** after the run (LLM failure can't fail a
      valid schedule)
- [ ] Tests with a stubbed provider (no live API in CI)

---

## Phase 4 — Frontend ⬜

React UI over the Phase 2/3 API.

- [ ] App scaffold under `frontend/` (Vite + React)
- [ ] Home → scenario list/create
- [ ] ScenarioEditor (input select, constraint overrides, NL constraint box)
- [ ] RunHistory (trigger, status, list)
- [ ] ResultsView (coverage cards, demand-vs-served chart, insights, schedule)
- [ ] API client + types shared with backend contracts

---

## Phase 5 — What-if, polish, deploy ⬜

- [ ] What-if: clone a scenario, tweak, re-run, **delta explanation** (LLM)
- [ ] WhatIfView (side-by-side compare)
- [ ] Polish: error states, loading, empty states
- [ ] Deploy: containerize backend; **AWS** target — frontend → S3 + CloudFront,
      backend container → ECR + App Runner/ECS/EC2 (container compute, not
      Lambda — CP-SAT solves are CPU-heavy/long). Docker Compose for local.

---

## Open decisions (carried from `design.md` §5)

Revisit before the phase they gate; don't silently resolve.

- **OT/cost fidelity** — flat $/hr now vs. ordinary/OT1/OT2 split (gates cost realism)
- **Coverage formulation** — single per-hour `supply ≥ demand − unmet` vs. the
  real two-layer (order-volume balance + per-hour supply≥produced)
- **Fixture realism** — full-week / 11-member default; scale up once proven
- **Solve-time vs. optimality** — cap the time limit + report unmet-optimal, or
  add a round-2 relative-gap stop, before the API/UI drive runs interactively
- **Deploy target detail** — AWS preferred but not yet specced (ECS vs App
  Runner vs EC2; SQLite on EFS vs move to RDS)
