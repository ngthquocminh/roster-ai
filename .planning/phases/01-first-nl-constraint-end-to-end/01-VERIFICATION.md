---
phase: 01-first-nl-constraint-end-to-end
verified: 2026-06-28T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false
---

# Phase 1: First NL Constraint End-to-End — Verification Report

**Phase Goal:** A user submits one plain-English constraint and gets back a re-solved schedule that honors it — the stub provider parses the text into a soft override, the override is stored, CP-SAT applies it as a soft penalty, and the scenario re-solves to a schedule that reflects it.
**Verified:** 2026-06-28
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #  | Truth                                                                                                                                                                                                | Status     | Evidence                                                                                                                                                      |
|----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1  | A POST to the parse-constraints endpoint with plain-English text returns 200 and persists a soft override with a stable per-override id to the scenario `overrides` JSON.                           | VERIFIED   | `POST /constraints` route exists, wired in `main.py`; `constraint_service.parse_and_store` writes dict keyed by content-hash id; 15 API tests pass including idempotency and 404/400 error paths. |
| 2  | Re-solving a scenario that carries an override returns a schedule that visibly honors it; the override enters round-2 (cost) only — never round-1 (unmet), never a hard constraint.                | VERIFIED   | `_build_objectives` confirmed: `shortfall_terms` appears only in `round2_cost`, not `round1_unmet`. `test_min_workers_override_honored` (real CP-SAT) asserts >= 2 bodies vs 1-body baseline; `test_no_supply_override_stays_feasible` asserts FEASIBLE with no-supply override. |
| 3  | A scenario with no overrides re-solves identically to the pre-LLM baseline (no regression).                                                                                                         | VERIFIED   | `SolverConfig.overrides` defaults to `[]`. `test_no_regression_empty_overrides` asserts identical status/cost/schedule rows. `test_no_constraint_yields_empty_overrides_in_config` asserts empty list at API level. |
| 4  | `StubLLMProvider` is injected via `get_llm_provider` dependency (mirroring `get_engine`); it builds Claude-faithful `tool_use` blocks (`type`/`id`/`name`/`input`) internally; the full NL→override→re-solve round trip passes in CI with zero network calls. | VERIFIED   | `get_llm_provider` in `api/deps.py` confirmed. `stub.py` builds `tool_use_block` internally and translates via `_to_override_call`; no `anthropic` import on stub path (ast scan). `test_override_is_threaded_into_solver_config` passes: override id in `SolverConfig.overrides` matches posted id. 12 LLM provider tests pass. |

**Score: 4/4 ROADMAP success criteria verified.**

---

### Supporting Plan-Level Truths

These truths come from the plan frontmatter `must_haves` and provide finer-grained evidence for the ROADMAP SCs above. All are VERIFIED.

| Plan  | Truth                                                                                                        | Status   | Evidence                                                                                  |
|-------|--------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------------------------------------------------------|
| 01-01 | CP-SAT places >= N bodies on the overridden task at every demanded hour.                                     | VERIFIED | `test_min_workers_override_honored` — per-hour body count asserted for hours 0..7.        |
| 01-01 | overrides=[] is byte-identical to the pre-override baseline.                                                 | VERIFIED | `test_no_regression_empty_overrides` — status, total_cost, sorted schedule rows matched.  |
| 01-01 | An override can never make a solve infeasible — bounded soft slack in round-2 only.                          | VERIFIED | `test_no_supply_override_stays_feasible` asserts FEASIBLE. Code: slack `NewIntVar(0, n)` summed into `round2_cost` only. |
| 01-02 | POST /constraints returns 200 echoing stored override (id, tool, args, parsed_constraint).                   | VERIFIED | `test_post_constraints_response_has_required_fields`, `test_post_constraints_echoes_correct_tool`. |
| 01-02 | Override persisted as JSON keyed by stable content-hash id; re-submitting is idempotent.                     | VERIFIED | `test_post_constraints_idempotent_same_id` — same id on second submit.                    |
| 01-02 | StubLLMProvider builds Claude-faithful `tool_use` blocks internally; non-matching text returns `[]`.         | VERIFIED | Code inspection of `stub.py` lines 70-75 (`tool_use_block` dict); `test_parse_constraints_no_match_returns_empty_list`. |
| 01-02 | Unknown/ambiguous task reference or n <= 0 rejected with plain-English error before persistence.              | VERIFIED | `test_post_constraints_ambiguous_task_token_returns_400`, `test_post_constraints_unknown_task_token_returns_400`. |
| 01-03 | `run_service._execute` reads scenario's overrides JSON into `SolverConfig.overrides` before solving.         | VERIFIED | Code at `run_service.py` lines 89-91: `json.loads(...) → list[OverrideCall]` confirmed.   |
| 01-03 | Full NL → override → re-solve round trip passes in CI with zero network calls.                               | VERIFIED | `test_override_is_threaded_into_solver_config` passes; `stub.py` imports only `re`, `uuid`, `domain.overrides`. |
| 01-03 | Re-solved scenario with override yields schedule visibly honoring it; baseline unchanged.                     | VERIFIED | Proved by composition: engine test (plan 01-01) proves honoring; threading test (plan 01-03) proves override flows end-to-end. Both pass. Plan explicitly anticipated this composition. |

---

### Required Artifacts

| Artifact                                           | Expected                                           | Status   | Details                                                              |
|----------------------------------------------------|----------------------------------------------------|----------|----------------------------------------------------------------------|
| `backend/domain/overrides.py`                      | OverrideCall frozen dataclass + override_id helper | VERIFIED | Substantive: 54 lines. Pure stdlib only (hashlib, json, dataclasses). |
| `backend/engine/base.py`                           | SolverConfig.overrides field (defaulted)           | VERIFIED | `overrides: list[OverrideCall] = field(default_factory=list)` confirmed. |
| `backend/config/constants.py`                      | MIN_WORKERS_PENALTY scaled-int constant            | VERIFIED | `MIN_WORKERS_PENALTY: int = 100_000` in integer-scaling block.       |
| `backend/engine/cpsat/builder.py`                  | Per-(task,hour) shortfall penalty in round2_cost   | VERIFIED | `_build_objectives` lines 331-351: shortfall_terms only in round2_cost. |
| `backend/engine/cpsat/engine.py`                   | Threads config.overrides into CpSatBuilder         | VERIFIED | Line 26: `CpSatBuilder(problem, overrides=config.overrides).build()`. |
| `backend/tests/test_engine_min_workers.py`         | Honors-override + no-regression + no-supply tests  | VERIFIED | 3 substantive tests; all pass.                                       |
| `backend/llm/__init__.py`                          | LLM package init                                   | VERIFIED | Exists.                                                              |
| `backend/llm/base.py`                              | LLMProvider Protocol + create_provider factory     | VERIFIED | 28 lines; mirrors engine/base.py pattern exactly.                    |
| `backend/llm/stub.py`                              | StubLLMProvider (keyword-routed, Claude-faithful)  | VERIFIED | 78 lines; builds tool_use internally; returns list[OverrideCall].    |
| `backend/api/deps.py`                              | get_llm_provider dependency                        | VERIFIED | `get_llm_provider() -> LLMProvider: return create_provider("stub")`. |
| `backend/api/schemas.py`                           | ConstraintParseRequest / ConstraintParseResponse   | VERIFIED | Both Pydantic models present; text field capped at max_length=2000.  |
| `backend/api/routers/constraints.py`               | POST /constraints route                            | VERIFIED | Router at prefix="/constraints"; returns 200, maps LookupError→404, ValueError→400. |
| `backend/services/constraint_service.py`           | parse_and_store (resolve/validate/merge/persist)   | VERIFIED | 147 lines; 5-step flow confirmed in code.                            |
| `backend/store/repositories.py`                    | ScenarioRepo.update_overrides                      | VERIFIED | Parameterized UPDATE; does not commit (caller commits).              |
| `backend/api/main.py`                              | constraints router mounted                         | VERIFIED | `app.include_router(constraints.router)` confirmed at line 31.       |
| `backend/services/run_service.py`                  | Overrides threaded from scenario JSON into config  | VERIFIED | Lines 89-91: raw JSON → list[OverrideCall] → SolverConfig.overrides. |
| `backend/tests/test_constraints_api.py`            | End-to-end stub-driven round-trip test             | VERIFIED | 17 substantive tests: 15 API tests + 2 threading/baseline tests.     |
| `backend/tests/test_llm_provider.py`               | LLM provider unit tests                            | VERIFIED | 12 substantive tests; all pass.                                      |

---

### Key Link Verification

| From                         | To                               | Via                                                             | Status   | Details                                                        |
|------------------------------|----------------------------------|-----------------------------------------------------------------|----------|----------------------------------------------------------------|
| `config.overrides`           | `CpSatBuilder._build_objectives` | `CpSatBuilder(problem, overrides=config.overrides)` → `self.overrides` | VERIFIED | engine.py line 26; builder stores in `self.overrides`.         |
| `_build_objectives`          | `round2_cost` only               | `shortfall_terms` summed with `MIN_WORKERS_PENALTY` into `round2_cost` | VERIFIED | `round1_unmet` assignment precedes shortfall block; no shortfall in round1. |
| `get_llm_provider` DI seam   | `StubLLMProvider`                | `create_provider("stub")` lazy import                          | VERIFIED | `api/deps.py` line 35-36; `dependency_overrides` used in tests. |
| `provider.parse_constraints` | `list[OverrideCall]`             | `_to_override_call(tool_use_block)` inside `stub.py`           | VERIFIED | `tool_use` dict consumed internally; OverrideCall returned.    |
| `constraint_service.parse_and_store` | `scenarios.overrides` column | `ScenarioRepo.update_overrides(id, json.dumps(store))` + `conn.commit()` | VERIFIED | Service reads existing dict, merges by id, writes, commits.    |
| `scenario['overrides']` JSON | `SolverConfig.overrides`         | `run_service._execute` lines 89-91                             | VERIFIED | `json.loads(... or "{}") → list[OverrideCall]` confirmed.     |

---

### Data-Flow Trace (Level 4)

| Artifact                       | Data Variable    | Source                                 | Produces Real Data | Status    |
|--------------------------------|------------------|----------------------------------------|--------------------|-----------|
| `constraint_service.py`        | overrides dict   | `ScenarioRepo.get` + problem fixture   | Yes — real task GUIDs from loaded SchedulingProblem | FLOWING |
| `run_service._execute`         | overrides list   | `scenario["overrides"]` SQLite column  | Yes — real OverrideCall from persisted JSON          | FLOWING |
| `builder._build_objectives`    | shortfall_terms  | `self.coverage_terms` per-(task,hour)  | Yes — real CP-SAT IntVars from model construction    | FLOWING |

---

### Behavioral Spot-Checks

| Behavior                                                     | Command                                                                                             | Result     | Status |
|--------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|------------|--------|
| Engine tests: override honored + no regression + no-supply   | `uv run python -m pytest tests/test_engine_min_workers.py tests/test_engine_small.py -q`           | 5 passed   | PASS   |
| API + LLM provider tests                                     | `uv run python -m pytest tests/test_constraints_api.py tests/test_llm_provider.py -q`              | 29 passed  | PASS   |
| Full suite (42 tests)                                        | `uv run python -m pytest -q`                                                                        | 42 passed, 1 warning | PASS   |
| Domain seam: OverrideCall, override_id stability, MIN_WORKERS_PENALTY | `python -c "from domain.overrides import OverrideCall, override_id; ..."` | ok         | PASS   |
| Stub has no network/anthropic imports                        | AST scan of `llm/stub.py`                                                                           | No anthropic/network imports | PASS   |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                            | Status    | Evidence                                                                 |
|-------------|-------------|------------------------------------------------------------------------|-----------|--------------------------------------------------------------------------|
| ENG-01      | 01-01       | OverrideCall domain types in domain/ — no engine→llm import cycle      | SATISFIED | `domain/overrides.py` imports only stdlib; engine/cpsat/builder.py imports from domain.overrides, not llm. |
| ENG-02      | 01-01       | SolverConfig carries overrides; solve() signature unchanged            | SATISFIED | `SolverConfig.overrides: list[OverrideCall] = field(default_factory=list)` added; `solve(problem, config)` unchanged. |
| ENG-03      | 01-01       | CP-SAT applies override as soft penalty only                           | SATISFIED | `shortfall_terms` summed into `round2_cost` only; `round1_unmet` unmodified. `test_min_workers_override_honored` passes. |
| ENG-06      | 01-01       | No-override scenario re-solves identically to baseline                 | SATISFIED | `overrides=[]` default; `test_no_regression_empty_overrides` asserts byte-identical. |
| LLM-01      | 01-02       | LLMProvider Protocol with parse_constraints + name property             | SATISFIED | `llm/base.py` defines `LLMProvider(Protocol)` with correct signature; no vendor types in return. |
| LLM-03      | 01-02       | Provider injected via FastAPI dependency seam                          | SATISFIED | `get_llm_provider` in `api/deps.py`; tests override via `app.dependency_overrides`. |
| NLC-01      | 01-02       | User can submit plain-English constraint text via API endpoint         | SATISFIED | `POST /constraints` accepts `{scenario_id, text}`; returns 200 with echoed override. |
| NLC-06      | 01-02       | Validated tool calls persisted with stable per-override IDs            | SATISFIED | `constraint_service` writes dict keyed by `override_id(tool, resolved_args)`; idempotency test passes. |
| TEST-01     | 01-02       | StubLLMProvider with Claude-faithful wire format; no live LLM in CI   | SATISFIED | `stub.py` builds `tool_use_block` dict internally; `dependency_overrides[get_llm_provider]` swaps it in tests; no network egress. |
| TEST-02     | 01-03       | Tests cover full NL → override → re-solve round trip driven by stub   | SATISFIED | `test_override_is_threaded_into_solver_config`: NL text → POST /constraints → run → CapturingEngine.captured_config.overrides verified. |

**No orphaned requirements.** All 10 Phase 1 requirement IDs in REQUIREMENTS.md are marked `[x] Complete` and are fully accounted for above.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | — |

No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or `PLACEHOLDER` markers found in any file modified by this phase. No stub implementations masquerading as production code (the `StubLLMProvider` is the intentional Phase-1 production default provider — not a placeholder).

---

### Human Verification Required

None. All phase must-haves are verified programmatically:
- Behavioral evidence exists for every truth in the form of passing named tests.
- No visual/UX/real-time behaviors requiring human observation.
- No external service integrations in scope (CI uses stub only).

---

## Gaps Summary

None. All 4 ROADMAP success criteria are verified, all 10 phase requirements are satisfied, all 42 tests pass, and no anti-patterns were found.

**Key composition note for Truth 4 / Plan 01-03 truth #3** (documented for auditors): the API-level round-trip test uses a `CapturingEngine` rather than the real CP-SAT engine to avoid coupling the integration test to fixture-specific body-count assertions. The plan explicitly anticipated this and documents the fallback: "rely on plan 01-01's engine test for the strict honoring proof". `test_min_workers_override_honored` provides that proof with the real engine. The two tests together constitute complete behavioral coverage of the end-to-end goal.

---

_Verified: 2026-06-28_
_Verifier: Claude (gsd-verifier)_
