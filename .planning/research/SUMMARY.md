# Project Research Summary

**Project:** ShiftMind — Phase 3 LLM Layer
**Domain:** LLM constraint-editing + insight layer over a CP-SAT workforce scheduler
**Researched:** 2026-06-28
**Confidence:** MEDIUM-HIGH

> Design-anchored research: `design.md`/`PLAN.md` are the baseline. Each finding is
> tagged **confirm-baseline** (the existing plan holds) or **propose-change** (a
> refinement to fold into Phase 3). Detailed docs: [STACK.md](STACK.md),
> [FEATURES.md](FEATURES.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PITFALLS.md](PITFALLS.md).

## Executive Summary

Phase 3 adds a natural-language constraint-editing layer on top of the existing
CP-SAT scheduler, using a vendor-swap seam that mirrors the existing
`SchedulerEngine` Protocol. A user submits English ("lock Alice to Outbound
Tuesday"); Claude translates it into one of 5 well-defined solver tools; the tool
calls are validated against real scenario IDs, stored as scenario overrides,
applied as **soft** constraints, and the scenario re-solves. Separately, a
post-run step turns run metrics into a structured natural-language insight report.
Production uses a `ClaudeLLMProvider`; CI uses a `StubLLMProvider` with no network
calls.

The research **confirms the baseline design is sound and production-ready**. No
phase-ordering change is needed. The recommended default model is
`claude-sonnet-4-6` (Opus is over-resourced for a closed 5-tool schema; Haiku is an
acceptable override). No new heavy frameworks are required — the `anthropic` SDK
for tool use, `typing.Protocol` for the seam, and `pydantic` (already present) for
argument validation are sufficient.

The main risks are solver-specific and known: penalty miscalibration (overrides
silently ignored or distorting the cost objective), degenerate solves from
unbounded args (`scale_demand=0`), hallucinated member/task IDs, Claude tool-schema
mistakes (missing `required` array), and stub-vs-real wire-format divergence. All
have concrete prevention strategies and map cleanly to Phase 3 build steps.

## Key Findings

### Recommended Stack

The existing Python/FastAPI/CP-SAT/SQLite stack is unchanged. The LLM layer adds
only the official Anthropic SDK plus stdlib/pydantic patterns. [confirm-baseline]

**Core technologies:**
- `anthropic` (Python SDK): Claude tool-use calls for NL→tool-call parsing and insight generation — official, well-supported. Default model `claude-sonnet-4-6`.
- `typing.Protocol` (stdlib): the `LLMProvider` seam (sync interface — calls run in the worker thread, not the event loop), mirroring `SchedulerEngine`. No inheritance, no framework.
- `pydantic` v2 (already installed via FastAPI): validate tool-call arguments and scenario-ID references before anything reaches the solver.
- Stub via structural subtyping (`StubLLMProvider`) — no `MagicMock`/`respx`; must match Claude's `tool_use` wire format (`type`, `id`, `name`, `input`) exactly.

### Expected Features

**Must have (table stakes) — confirm-baseline:**
- 5 solver-hook tools: `lock_worker_shift`, `set_min_workers_per_task`, `exclude_worker_from_task`, `scale_demand`, `set_max_hours`
- Validation of tool calls against real scenario IDs (reject unknown member/task refs)
- Overrides applied as **soft** constraints + re-solve (never infeasible)
- Insight generator: metrics → NL report, as a **separate** post-run step (LLM failure can't fail a schedule)
- Stubbed provider for CI

**Should have (low-cost refinements to absorb into Phase 3) — propose-change:**
- Plain-English validation errors ("Unknown worker 'Alice'. Available: Bob, Carol") — table stakes for trust
- `parsed_constraint` human-readable echo in the API response (enables a future Phase-4 confirmation UI without frontend work now)
- `clarification_needed` / question field for ambiguous/unparseable input
- Insight prompt must cite **specific metric values** (no generic "coverage was adequate")

**Defer (out of Phase 3):**
- `remove_override` (6th tool) — low complexity, high UX value; safe to defer, but store overrides with stable IDs now to keep the door open
- Multi-turn auto-retry on ID rejection — single-turn (user rephrases) is fine for this milestone
- Frontend (Phase 4), what-if/delta + deploy (Phase 5)

### Architecture Approach

Layered integration that respects existing seams: API → Service (orchestration +
entity validation) → `LLMProvider` Protocol and `SchedulerEngine` Protocol
(decoupled, neither imports the other) → Domain → Store. [confirm-baseline for
structure]

**Major components:**
1. `domain/overrides.py` — `OverrideCall` types live in **domain**, not `llm/`, so the engine can reference them without an engine→llm import cycle. [propose-change]
2. `llm/base.py` (`LLMProvider` Protocol) + `llm/stub.py` + later `llm/claude.py`; injected via a new `get_llm_provider()` dependency mirroring `get_engine`. [confirm-baseline]
3. `services/parse_service.py` — NL → validated tool calls (ID + arg-bounds validation), persisted to the scenario `overrides` JSON. [confirm-baseline]
4. Engine extension — `SolverConfig.overrides`; the CP-SAT builder applies each override as a soft-penalty term (extends the existing `unfilled_roster`/`unmet_*` penalty pattern). Protocol signature unchanged. [propose-change to SolverConfig]
5. Insight endpoint — `GET /runs/{id}/insights`, lazy/on-demand, cached in a new `runs.insight_json` column; LLM failure returns an error without touching the COMPLETED run. [confirm-baseline mandate, lazy is the proposed mechanism]

### Critical Pitfalls

1. **Penalty miscalibration / wrong lex round** — overrides added to the round-1 (unmet) objective instead of round-2 (cost) silently distort results while the solver still reports OPTIMAL. *Decide which round overrides enter; calibrate weights against the committed full-week fixture.*
2. **Degenerate solves from unbounded args** — `scale_demand(0)` → empty schedule, trivially "optimal". "Soft never infeasible" does NOT protect against this. *Add explicit argument-bounds validation as a separate layer.*
3. **Hallucinated member/task IDs** — *strict ID validation against scenario entities before the solver; return a plain-English error.*
4. **Claude tool-schema mistakes** — missing `required` array makes Claude send `{"input": {}}`; `additionalProperties:false` needed. *Define schemas carefully; golden test cases.*
5. **Stub wire-format divergence** — stub passes, live fails. *Stub must mirror real `ToolUseBlock` structure exactly; one real-Claude integration test.*
6. **Nondeterminism / latency** — multi-worker CP-SAT can break reproducibility; LLM calls on the request path add latency. *Keep the solve seed fixed; keep parse off the event loop appropriately.*

## Implications for Roadmap

Research confirms the baseline; the natural build order (stub-first, real Claude
last) means only the final step needs a live API key — everything before it is CI-testable.

### Phase 3.1: Domain overrides + soft-penalty engine
**Rationale:** Foundation; no LLM needed, fully testable with existing fixtures.
**Delivers:** `domain/overrides.py`, `SolverConfig.overrides`, CP-SAT soft-penalty application + degenerate-solve/arg-bounds guards.
**Avoids:** penalty miscalibration, degenerate solves.

### Phase 3.2: LLMProvider seam + stub
**Rationale:** Enables all later test coverage with zero API calls.
**Delivers:** `llm/base.py` Protocol, `llm/stub.py`, `get_llm_provider()` DI, tool JSON schemas.
**Avoids:** stub wire-format divergence, Claude schema mistakes.

### Phase 3.3: NL parse service + validation + API
**Rationale:** Full NL→override→re-solve round-trip, driven by the stub.
**Delivers:** `services/parse_service.py`, ID + arg-bounds validation, plain-English errors, `parsed_constraint`/`clarification_needed` fields, parse endpoint, `overrides` storage with stable IDs.
**Avoids:** hallucinated IDs, prompt-injection of unsafe args.

### Phase 3.4: Insight endpoint
**Rationale:** Independent, decoupled from run success.
**Delivers:** `GET /runs/{id}/insights`, `runs.insight_json`, metric-citation-grounded prompt.
**Avoids:** insights that invent numbers; LLM failure failing a schedule.

### Phase 3.5: Real Claude provider + calibration
**Rationale:** Drops in behind the Protocol; CI stays stub-only.
**Delivers:** `llm/claude.py`, `ANTHROPIC_MODEL` setting, penalty-weight calibration, one live integration test.

### Phase Ordering Rationale
- Domain + engine first so override application is correct and testable before any LLM exists.
- Stub before real provider so the entire pipeline is CI-testable without an API key.
- Insight endpoint is independent and can be built in parallel with the parse pipeline.

### Research Flags
- **Phase 3.5:** needs empirical penalty-weight calibration (a small matrix of solver runs against the full-week fixture) and one real-Claude integration test — flag for a focused research/validation pass at plan time.
- **Phases 3.1–3.4:** standard patterns (Protocol seam, pydantic validation, CP-SAT soft penalties) — can skip deep per-phase research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | SDK syntax + model ids verified via Context7 against `anthropic-sdk-python`; unversioned pin |
| Features | MEDIUM | 5-tool baseline well-supported by analogy (MeetMate/SMILO/ConstraintLLM); proposed additions are judgment calls |
| Architecture | HIGH | Derived from direct inspection of `engine/base.py`, `api/deps.py`, `run_service.py`, `builder.py` |
| Pitfalls | MEDIUM-HIGH | OR-Tools docs + published literature; penalty calibration is project-specific |

**Overall confidence:** MEDIUM-HIGH. Design is sound and ready for planning; execution risks are known and manageable.

### Gaps to Address
- **Penalty weight scale:** integer-unit weights relative to the cost objective — resolve empirically in Phase 3.5 against the committed fixture.
- **`overrides` JSON shape:** store `{id, tool, input}` with stable IDs from the start (prepares for `remove_override`); confirm Phase-2 column is a list, not a blob.
- **Insight trigger:** on-demand/lazy recommended (user controls cost) vs. auto after every run — decide at plan time.
- **`runs.insight_json` migration:** no migration framework exists; add a guarded `ALTER TABLE`/conditional DDL in `init_db()`.

## Sources

### Primary (HIGH confidence)
- Context7: `anthropic-sdk-python` — tool-use syntax, `ModelParam` literals (`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`)
- Context7: Google OR-Tools — CP-SAT soft-constraint / enforcement-literal patterns
- Direct codebase inspection: `engine/base.py`, `api/deps.py`, `services/run_service.py`, `engine/cpsat/builder.py`, `store/db.py`, `design.md` §4

### Secondary (MEDIUM confidence)
- Published NL-to-constraint systems (MeetMate, SMILO, ConstraintLLM, SAGE-Agent) — architecture + clarification-value evidence
- OWASP LLM01:2025 (prompt injection); OR-Tools issue tracker (multi-worker nondeterminism)

---
*Research completed: 2026-06-28*
*Ready for roadmap: yes*
