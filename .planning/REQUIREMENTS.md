# Requirements: ShiftMind — Phase 3 LLM Layer

**Defined:** 2026-06-28
**Core Value:** A user can express a scheduling constraint change in plain English and get back a re-solved schedule that honors it (as a soft constraint) plus a readable explanation of what changed.

## v1 Requirements

Requirements for this milestone (Phase 3). Each maps to a roadmap phase.

### LLM Provider Seam

- [x] **LLM-01**: An `LLMProvider` Protocol defines a synchronous interface with two operations — parse constraints, and generate insights
- [ ] **LLM-02**: A Claude implementation sits behind the Protocol with a config-driven model id (default `claude-sonnet-4-6` via an `ANTHROPIC_MODEL` setting)
- [x] **LLM-03**: The provider is injected via a FastAPI dependency seam (mirroring `get_engine`), so a stub can be substituted in tests

### NL Constraint Parsing

- [x] **NLC-01**: User can submit plain-English constraint text for a scenario via an API endpoint
- [x] **NLC-02**: Text is parsed into zero or more solver-hook tool calls from the fixed set: `lock_worker_shift`, `set_min_workers_per_task`, `exclude_worker_from_task`, `scale_demand`, `set_max_hours`
- [x] **NLC-03**: When the text maps to no tool, the system returns "no constraint found" rather than forcing a spurious tool call
- [x] **NLC-04**: The response echoes a human-readable `parsed_constraint` summary of what was understood
- [x] **NLC-05**: Ambiguous or unparseable input returns a `clarification_needed` signal with a question (single-turn — the user rephrases)
- [x] **NLC-06**: Validated tool calls are persisted to the scenario `overrides` JSON with stable per-override IDs

### Constraint Validation

- [x] **VAL-01**: Tool-call arguments are validated for type and bounds before reaching the solver (reject `scale_demand` factor ≤ 0, `set_max_hours` = 0, negatives, and other degenerate values)
- [x] **VAL-02**: Member/task references are validated against real scenario IDs; unknown references are rejected (no hallucinated IDs reach the engine)
- [x] **VAL-03**: Validation failures return a plain-English error naming the offending reference/argument and the available options

### Engine Override Application

- [x] **ENG-01**: `OverrideCall` domain types live in `domain/` so the engine references them without an engine→llm import cycle
- [x] **ENG-02**: `SolverConfig` carries the overrides; the `SchedulerEngine.solve(problem, config)` signature is unchanged
- [x] **ENG-03**: The CP-SAT builder applies each override as a **soft** penalty term — never a hard constraint that can make the model infeasible
- [ ] **ENG-04**: Overrides enter the correct lexicographic round with calibrated penalty weights (respected, but not dominating the cost objective)
- [ ] **ENG-05**: Re-solving a scenario with overrides yields a schedule reflecting them; degenerate solves (e.g. coverage collapsing to zero) are detected and flagged
- [x] **ENG-06**: A scenario with no overrides solves identically to today (no regression)

### Insights

- [ ] **INS-01**: An endpoint generates a natural-language insight report from a completed run's metrics
- [ ] **INS-02**: Insights are generated as a separate, on-demand step; an LLM failure never changes run status or invalidates the schedule result
- [ ] **INS-03**: The insight report cites specific metric values from the run (no generic "coverage was adequate" language)
- [ ] **INS-04**: The insight result is cached (`runs.insight_json`) so repeat fetches don't re-call the LLM

### Testing

- [x] **TEST-01**: A `StubLLMProvider` implements the Protocol with Claude-faithful tool-use wire format; no live LLM API runs in CI
- [x] **TEST-02**: Tests cover the full NL → override → re-solve round trip driven by the stub
- [ ] **TEST-03**: Validation tests cover unknown IDs and out-of-bounds arguments
- [ ] **TEST-04**: One live-Claude integration test exists but is excluded from the default CI run

## v2 Requirements

Deferred to a future milestone. Tracked but not in this roadmap.

### Constraint Management

- **NLC-07**: `remove_override` tool so a user can undo a previously applied constraint by id
- **NLC-08**: Multi-turn auto-retry — the system lets Claude self-correct a hallucinated id instead of surfacing the error for manual rephrase

### Insights

- **INS-05**: Auto-generate insights after every completed run (rather than on demand)

## Out of Scope

Explicitly excluded for this milestone. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| React / frontend UI | Phase 4 — this milestone is API + engine only |
| What-if compare + delta explanation | Phase 5 — depends on the LLM layer landing first |
| Deploy / AWS infra | Phase 5 — out until the feature set is complete |
| Live LLM calls in default CI | Determinism + cost — CI uses the stub provider |
| Hard/infeasible-making NL constraints | All overrides apply as soft penalties by design |
| OT1/OT2 cost split, two-layer coverage, task flow, capacity/load mgmt | Production-model fidelity deferrals from design.md — not part of the LLM layer |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENG-01 | Phase 1 | Complete |
| ENG-02 | Phase 1 | Complete |
| ENG-03 | Phase 1 | Complete |
| ENG-06 | Phase 1 | Complete |
| LLM-01 | Phase 1 | Complete |
| LLM-03 | Phase 1 | Complete |
| NLC-01 | Phase 1 | Complete |
| NLC-06 | Phase 1 | Complete |
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 1 | Complete |
| NLC-02 | Phase 2 | Complete |
| NLC-03 | Phase 2 | Complete |
| NLC-04 | Phase 2 | Complete |
| NLC-05 | Phase 2 | Complete |
| VAL-01 | Phase 2 | Complete |
| VAL-02 | Phase 2 | Complete |
| VAL-03 | Phase 2 | Complete |
| ENG-05 | Phase 2 | Pending |
| TEST-03 | Phase 2 | Pending |
| INS-01 | Phase 3 | Pending |
| INS-02 | Phase 3 | Pending |
| INS-03 | Phase 3 | Pending |
| INS-04 | Phase 3 | Pending |
| LLM-02 | Phase 4 | Pending |
| ENG-04 | Phase 4 | Pending |
| TEST-04 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 26 total (source count of "24" was a miscount; 26 distinct IDs enumerated above)
- Mapped to phases: 26 ✓
- Unmapped: 0

---
*Requirements defined: 2026-06-28*
*Last updated: 2026-06-28 after roadmap creation (traceability populated)*
