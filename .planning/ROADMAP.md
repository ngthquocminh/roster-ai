# Roadmap: ShiftMind

## Milestones

- ✅ **v0.3 LLM Layer** — 4 phases (shipped 2026-07-15)
- 🔨 **v0.4 Frontend (React UI)** — Phases 1-4 (in progress)

> **Phase numbering restarts at each milestone.** v0.4's Phase 1 is not v0.3's
> Phase 1 — each milestone owns its own 1..N sequence. Shipped milestones keep
> their numbering in their archived roadmaps
> (`.planning/milestones/v0.3-ROADMAP.md`). The Progress table below tracks the
> **current milestone only**; prior milestones are summarised under Phases.

## Phases

<details>
<summary>✅ v0.3 LLM Layer — SHIPPED 2026-07-15 (its own Phases 1-4)</summary>

- [x] Phase 1: First NL Constraint End-to-End (3/3 plans) — completed 2026-06-28
- [x] Phase 2: Full 5-Tool Set + Safe Validation (4/4 plans) — completed 2026-06-29
- [x] Phase 3: On-Demand Insight Reports (2/2 plans) — completed 2026-06-30
- [x] Phase 4: Real LLM Provider (free-tier first) + Penalty Calibration (3/3 plans) — completed 2026-07-15

Full detail: `.planning/milestones/v0.3-ROADMAP.md`

</details>

### 🔨 v0.4 Frontend (React UI) — Phases 1-4

- [x] **Phase 1: Browser-Callable API + App Shell + Scenario List** - CORS, Vite/React/TS scaffold, typed client, and a Home view that lists and creates scenarios (completed 2026-07-16)
- [ ] **Phase 2: Scenario Detail + Plain-English Constraints** - ScenarioEditor: applied-overrides list, NL constraint box, partial-apply and provider-down handling
- [ ] **Phase 3: Run Execution & History** - Trigger a run, poll to terminal, honest waiting, prior-run list with failures shown
- [ ] **Phase 4: Results & Insights** - Coverage cards, demand-vs-served chart, schedule table, on-demand insight report

## Phase Details

### Phase 1: Browser-Callable API + App Shell + Scenario List

**Goal**: A user can open ShiftMind in a browser and see and create scenarios against the live backend.
**Depends on**: Nothing (first phase of v0.4; the backend shipped in v0.3)
**Requirements**: BE-01, SHELL-01, SHELL-02, SHELL-03, SHELL-04, SCEN-01, SCEN-02
**Success Criteria** (what must be TRUE):

  1. User can start the dev server, open the app in a browser, and see the list of existing scenarios fetched from the running backend — with no CORS error in the console.
  2. User can create a scenario by naming it and choosing one of the fixtures the backend offers (`GET /fixtures`), and see it appear in the list.
  3. User can move between the app's routes through a persistent nav and deep-link straight to a route by URL. Views built in later phases are reachable placeholders, not dead links.
  4. When the backend is unreachable or returns an error, the user sees a readable message naming what failed — never a blank screen and never a silent failure.
  5. Allowed origins are configurable rather than hardcoded, and the app builds to static assets with one command.

**Notes**:

  - BE-01 is the milestone's only backend change and a hard gate: no browser origin can call the API without it. It lands here, first, not late.
  - SHELL-03 is the routing/nav capability; each later phase mounts its view into the shell established here. Criterion 3 is what is verifiable at this phase — the full four-view surface completes as Phases 2-4 land.
  - The typed client (SHELL-02) mirrors `docs/API.md`, which is the accurate contract as of commit 93ca4e0. Notably `POST /constraints` is top-level with `scenario_id` in the body, and `/runs/{id}/insights` is not shaped like `/runs/{id}/result`.

**Plans**: 7/7 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — BE-01: configurable CORS origins on the FastAPI app (Wave 1)
- [x] 01-02-PLAN.md — Blocking human legitimacy gate for the 10 [SUS]-flagged npm packages (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-03-PLAN.md — SHELL-01: Vite + React + TS scaffold, shadcn/Tailwind v4, Vitest harness (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — SHELL-02: typed client generated from the backend's OpenAPI schema (Wave 3)
- [x] 01-05-PLAN.md — SHELL-03/04: four-route shell with persistent nav, honest placeholders, error surfaces (Wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-06-PLAN.md — SCEN-01: scenario list on Home across all five states (Wave 4)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-07-PLAN.md — SCEN-02: create a scenario from a backend-offered fixture (Wave 5)

**UI hint**: yes

### Phase 2: Scenario Detail + Plain-English Constraints

**Goal**: A user can open a scenario and shape its constraints by typing plain English.
**Depends on**: Phase 1
**Requirements**: SCEN-03, CONS-01, CONS-02, CONS-03, CONS-04, CONS-05
**Success Criteria** (what must be TRUE):

  1. User can open a scenario from Home and see its details along with every override currently applied to it.
  2. User can type a constraint in plain English, submit it, and see a readable echo of what was understood (`parsed_constraint`) rather than raw tool-call JSON — with newly applied overrides appearing in the scenario's list.
  3. When a submission partially applies, the user sees both what was applied and what was rejected, each rejection carrying its plain-English reason and valid options.
  4. When the parser needs clarification, the user sees the question and can rephrase without losing their place.
  5. When the LLM provider is unavailable (`503`), the user sees a message saying the provider is down — visibly distinct from "your constraint was invalid".

**Notes**:

  - `POST /constraints` does **not** trigger a solve. This phase ends with overrides persisted and legible; seeing their effect is Phase 3's job.
  - Works against the default `LLM_PROVIDER=stub` (keyless, deterministic, regex-routed). Nothing here may require a live key; default CI stays keyless. Only a demo of genuine NL understanding needs `gemini`/`openrouter`.
  - The response is a partial-apply shape (`applied[]` + `rejected[]`) — criterion 3 is about rendering both halves of one `200`, not an error path.

**Plans**: 4/7 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — D-01/D-02 backend: `GET /scenarios/{id}/overrides` + `OverrideOut` + persist `parsed_constraint` + docs (Wave 1)

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — Frontend API layer: codegen regen + typed wrappers (getScenario/getScenarioOverrides/applyConstraint) + Textarea (Wave 2)

**Wave 3** *(blocked on Wave 2)*

- [x] 02-03-PLAN.md — TanStack Query hooks: useScenario, useOverrides (dependent), useApplyConstraint (overrides invalidation) (Wave 3)

**Wave 4** *(blocked on Wave 3 — two parallel plans)*

- [x] 02-04-PLAN.md — Read surface: ScenarioHeader (404 terminal) + OverridesList (legacy fallback) (Wave 4)
- [ ] 02-05-PLAN.md — Write surface: TranscriptEntry/ConstraintTranscript + ConstraintInput + ProviderDownBanner (Wave 4)

**Wave 5** *(blocked on Wave 4)*

- [ ] 02-06-PLAN.md — Editor route composition + App.tsx wiring + session transcript state (Wave 5)

**Wave 6** *(blocked on Wave 5)*

- [ ] 02-07-PLAN.md — Blocking human-verify checkpoint: five outcome treatments, layout, reload durability, backstops (Wave 6)

**UI hint**: yes

### Phase 3: Run Execution & History

**Goal**: A user can trigger a solve and follow it to a terminal state without leaving the browser.
**Depends on**: Phase 2
**Requirements**: RUN-01, RUN-02, RUN-03, RUN-04, RUN-05
**Success Criteria** (what must be TRUE):

  1. User can trigger a run for a scenario and see it appear immediately as `PENDING`.
  2. User can watch a run advance through `PENDING → RUNNING → COMPLETED/FAILED` without manually refreshing.
  3. While a run is in flight the user is told honestly that it can take minutes and cannot be cancelled — no progress affordance implying imminent completion, and no abort control that does not exist.
  4. User can see prior runs for a scenario with their status and timing (created/started/finished).
  5. A `FAILED` run shows its recorded `error` text in the UI rather than appearing merely absent or permanently stuck.

**Notes**:

  - Runs are async and genuinely slow: round-2 cost-optimality is a ~2min tail against ~20s for round 1, on a single-worker pool. Poll `GET /runs/{id}` until terminal.
  - No cancellation path exists in the engine (see `todos/pending/`, OPS-01). Criterion 3 requires an honest wait, not a spinner that lies. Do not build a cancel button.
  - A time-limited solve still ends `COMPLETED` with `solver_status = UNKNOWN` — that is success, not failure. `FAILED` is reserved for unexpected errors.

**Plans**: TBD
**UI hint**: yes

### Phase 4: Results & Insights

**Goal**: A user can read a completed run's schedule, coverage, and plain-language insight report.
**Depends on**: Phase 3
**Requirements**: RES-01, RES-02, RES-03, RES-04, RES-05, RES-06
**Success Criteria** (what must be TRUE):

  1. User can open a completed run and see coverage summary cards (cost, unmet hours, coverage by function and by day), with any degenerate-solve warnings recorded on the run surfaced alongside them rather than silently dropped.
  2. User can see a demand-vs-served chart comparing required against served hours.
  3. User can read the schedule as a readable table (member, task, function, shift window).
  4. User can request an insight report on demand and get either the report or an honest "not ready yet" — the UI branching on the response's `ready` field, never on the status code.
  5. When insight generation fails (`502`), the rest of the results view stays intact and usable — a completed schedule is never invalidated by a failed report.

**Notes**:

  - `GET /runs/{id}/insights` returns `200` with `ready:false` when the run is not `COMPLETED` — deliberately **not** `409` — and `502` on generation failure. `GET /runs/{id}/result` by contrast **does** `409` before completion. These two endpoints must not be treated alike; criterion 4 is the guard against that.
  - Numeric fields in `metrics` may be `null` (a non-finite solver cost serializes as `null`, not `NaN`). Cards and chart must render that without breaking.
  - Criterion 1 folds RES-01 and RES-06 together: the warnings are a coverage-honesty signal and belong next to the coverage they qualify.

**Plans**: TBD
**UI hint**: yes

## Progress

Current milestone (**v0.4**) only. v0.3's phases are summarised above and
detailed in `.planning/milestones/v0.3-ROADMAP.md`.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|-----------------|--------|-----------|
| 1. Browser-Callable API + App Shell + Scenario List | v0.4 | 7/7 | Complete    | 2026-07-16 |
| 2. Scenario Detail + Plain-English Constraints | v0.4 | 4/7 | In Progress|  |
| 3. Run Execution & History | v0.4 | 0/TBD | Not started | - |
| 4. Results & Insights | v0.4 | 0/TBD | Not started | - |
