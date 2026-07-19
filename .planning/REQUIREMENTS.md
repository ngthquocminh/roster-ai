# Requirements: ShiftMind — v0.4 Frontend (React UI)

**Defined:** 2026-07-15
**Core Value:** A user can express a scheduling constraint change in plain English and get back a re-solved schedule that honors it (as a soft constraint) plus a readable explanation of what changed.

## v1 Requirements

Requirements for milestone v0.4. Each maps to exactly one roadmap phase.

### App Shell & API Client

- [x] **SHELL-01**: A Vite + React + TypeScript app lives under `frontend/`, runs against a local backend in dev, and builds to static assets
- [x] **SHELL-02**: A typed API client wraps every endpoint the UI uses; request/response types mirror the contracts in `docs/API.md`
- [x] **SHELL-03**: User can navigate between the four views (Home, ScenarioEditor, RunHistory, ResultsView)
- [x] **SHELL-04**: Network and API failures surface as a readable message; the UI never shows a silent blank state on error

### Backend Enablement

- [x] **BE-01**: The FastAPI app accepts cross-origin requests from the frontend's dev-server and built origins, with allowed origins configurable rather than hardcoded

### Scenario Management

- [x] **SCEN-01**: User can see a list of existing scenarios
- [x] **SCEN-02**: User can create a scenario by picking from the fixtures the backend offers (`GET /fixtures`) — no file upload in v0.4
- [x] **SCEN-03**: User can open a scenario and see its details, including the overrides currently applied to it

### Constraint Editing

- [x] **CONS-01**: User can type a plain-English constraint for a scenario and submit it
- [x] **CONS-02**: The UI shows a readable echo of what was understood (`parsed_constraint`) rather than raw tool-call JSON
- [x] **CONS-03**: When a submission partially applies, the UI shows both what was applied and what was rejected — with the rejection reason and valid options
- [x] **CONS-04**: When the parser needs clarification, the UI shows the question and lets the user rephrase
- [x] **CONS-05**: When the LLM provider is unavailable (`503`), the UI says so honestly — distinct from "your constraint was invalid"

### Run Execution & History

- [x] **RUN-01**: User can trigger a run for a scenario
- [x] **RUN-02**: The UI polls run status until terminal and reflects `PENDING → RUNNING → COMPLETED/FAILED`
- [x] **RUN-03**: While a run is in flight the UI communicates the wait honestly — it can take minutes, and it cannot be cancelled
- [x] **RUN-04**: User can see prior runs for a scenario with their status and timing
- [x] **RUN-05**: A `FAILED` run shows its recorded error rather than appearing merely absent

### Results & Insights

- [ ] **RES-01**: User can see coverage summary cards for a completed run
- [x] **RES-02**: User can see a demand-vs-served chart for a completed run
- [x] **RES-03**: User can see the schedule as a readable table
- [ ] **RES-04**: User can fetch a plain-language insight report on demand; the UI branches on the response's `ready` field, not on the status code
- [ ] **RES-05**: An insight failure (`502`) leaves the rest of the results view intact — a completed schedule is never invalidated by a failed report
- [ ] **RES-06**: Degenerate-solve warnings recorded on the run (`SolveResult.warnings`) are surfaced rather than silently dropped

## v2 Requirements

Deferred. Tracked, not in the v0.4 roadmap.

### Input Ingestion

- **UP-01**: User can upload their own workforce/demand data instead of picking a committed fixture. Needs size limits + multipart/streaming (real weekly input is ~16MB JSON). **Hard prerequisite: WR-04 must land first** — an upload endpoint writing attacker-named files into `data/` makes that existing traversal hole materially worse.

### What-If

- **WHAT-01**: User can clone a scenario, tweak it, and re-run
- **WHAT-02**: An LLM-generated delta explanation describes what changed between two runs
- **WHAT-03**: User can compare two runs side by side

### Known-Issue Carry-Overs

- **WR-04**: Fixture path traversal hardening in `constraint_service.py`
- **D-06-FIX**: `_grounding_guard` admits `coverage_by_day` dict keys (day-index integers), closing the false-positive class

### Operability

- **OPS-01**: User can cancel an in-flight run
- **OPS-02**: Round-2 relative-gap stop bounds the cost-optimality tail

## Out of Scope

Explicitly excluded from v0.4. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Auth / sessions | Never built; vision.md's localStorage session UUID never happened. Not needed for local/demo use. Becomes a real gate before any public deploy. |
| Input upload | Deferred to v0.5 — v0.4 demos against committed fixtures. Depends on WR-04. |
| What-if compare + delta | Unblocked but held back: a second large feature on top of a from-scratch React app is how scope slips. |
| Run cancellation | No cancel path exists in the engine (single-worker pool, CP-SAT needs a stop callback — a Protocol change). v0.4 shows an honest wait instead. |
| AWS deploy | Out of scope until the feature set for a public-facing release is complete (carried from v0.3). |
| Mobile / responsive polish | Desktop-first; this is a portfolio POC, not a shipped product. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SHELL-01 | Phase 1 | Complete |
| SHELL-02 | Phase 1 | Complete |
| SHELL-03 | Phase 1 | Complete |
| SHELL-04 | Phase 1 | Complete |
| BE-01 | Phase 1 | Complete |
| SCEN-01 | Phase 1 | Complete |
| SCEN-02 | Phase 1 | Complete |
| SCEN-03 | Phase 2 | Complete |
| CONS-01 | Phase 2 | Complete |
| CONS-02 | Phase 2 | Complete |
| CONS-03 | Phase 2 | Complete |
| CONS-04 | Phase 2 | Complete |
| CONS-05 | Phase 2 | Complete |
| RUN-01 | Phase 3 | Complete |
| RUN-02 | Phase 3 | Complete |
| RUN-03 | Phase 3 | Complete |
| RUN-04 | Phase 3 | Complete |
| RUN-05 | Phase 3 | Complete |
| RES-01 | Phase 4 | Pending |
| RES-02 | Phase 4 | Complete |
| RES-03 | Phase 4 | Complete |
| RES-04 | Phase 4 | Pending |
| RES-05 | Phase 4 | Pending |
| RES-06 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 24 total
- Mapped to phases: 24 ✓
- Unmapped: 0
- Duplicates: 0

**By phase:**

| Phase | Requirements | Count |
|-------|--------------|-------|
| Phase 1 — Browser-Callable API + App Shell + Scenario List | BE-01, SHELL-01, SHELL-02, SHELL-03, SHELL-04, SCEN-01, SCEN-02 | 7 |
| Phase 2 — Scenario Detail + Plain-English Constraints | SCEN-03, CONS-01, CONS-02, CONS-03, CONS-04, CONS-05 | 6 |
| Phase 3 — Run Execution & History | RUN-01, RUN-02, RUN-03, RUN-04, RUN-05 | 5 |
| Phase 4 — Results & Insights | RES-01, RES-02, RES-03, RES-04, RES-05, RES-06 | 6 |

---
*Requirements defined: 2026-07-15*
*Last updated: 2026-07-15 — traceability populated at v0.4 roadmap creation (Phases 1-4; numbering restarts per milestone)*
</content>
