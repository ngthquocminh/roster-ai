# Phase 1: First NL Constraint End-to-End - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the LLM→solver seam by driving **one** plain-English constraint all the way
through, stub-driven, with zero network calls in CI:

`POST text → StubLLMProvider parses → validated OverrideCall stored in scenario
overrides JSON → re-solve via the run lifecycle → CP-SAT applies it as a SOFT
round-2 penalty → returned schedule visibly honors it.`

The one tool for this slice is **`set_min_workers_per_task`**. A scenario with no
overrides must re-solve identically to the pre-LLM baseline (no regression).

**Not in this phase** (later slices, do not pull in): the other four tools and
parse-UX fields like `no constraint found` / `clarification_needed` (Phase 2),
arg/ID validation breadth (Phase 2), insight reports (Phase 3), real Claude
provider + penalty-weight calibration (Phase 4).
</domain>

<decisions>
## Implementation Decisions

### Tool to prove the seam
- **D-01:** Phase 1 implements exactly one tool: **`set_min_workers_per_task`**.
  Chosen because it is purely **additive** (a new soft shortfall-penalty term),
  cannot make the model infeasible, and its effect is visually obvious in the
  schedule (more bodies on the task). Rejected: `lock_worker_shift` (brittle —
  must pin an exact generated shift var) and `set_max_hours` (overlaps the
  existing hard weekly-hours cap, less visible).
- **D-02:** The floor applies **per demanded hour**, matching the model's hourly
  coverage granularity. For each `(task, hour)` with demand:
  `shortfall_h = max(0, N - assigned_h)` where `assigned_h` reuses the existing
  per-`(task,hour)` `coverage_terms`; `round2_cost += W * sum(shortfall_h)`.
  Rejected: "N distinct members over the week" (coarse, guarantees nothing at any
  given hour, needs new per-member-per-task indicator vars).
- **D-03:** The penalty enters **round 2 (cost) only** as a soft term — never
  round 1 (unmet), never a hard constraint. (Locked project decision; restated
  because the per-hour shortfall term must be added in `builder._build_objectives`
  to `round2_cost`, not to `round1_unmet`.)

### Override persistence
- **D-04:** The scenario `overrides` column holds a JSON **object keyed by
  override id** (not a list): `{ "<id>": {"tool": ..., "args": {...}}, ... }`.
  O(1) lookup/removal by id (helps the v2 `remove_override` tool) and natural
  dedup.
- **D-05:** The per-override id (NLC-06 "stable id") is a **content hash**:
  `"ov_" + sha256(tool + canonical(args))[:8]`. `canonical(args)` MUST sort keys
  so the hash is stable regardless of arg ordering. Consequence: re-submitting the
  same constraint maps to the same key and overwrites in place — **idempotent**, no
  duplicate overrides. Rejected: random uuid (no dedup) and sequential index
  (read-modify-write race under WAL).

### Parse endpoint contract
- **D-06:** The endpoint **parses + validates + stores only** — it does NOT
  trigger a solve. Re-solving stays the existing run-trigger path, which now reads
  the scenario's overrides into `SolverConfig`. Keeps the long CP-SAT solve off the
  request thread and preserves the existing async-run model.
- **D-07:** Route is **top-level `POST /constraints`** with `scenario_id` in the
  request body (not nested under `/scenarios/{id}/...`). Response echoes the stored
  override: id, tool, args, and a human-readable `parsed_constraint` summary,
  returning 200. (User preferred the flat route over the nested resource style.)

### LLM provider seam (stub fidelity — layered design)
- **D-08:** `LLMProvider.parse_constraints(text)` returns a **provider-neutral
  `list[OverrideCall]`** — the public Protocol contract carries NO vendor-specific
  shape. This is the extensibility seam: a future Gemini (or other) provider
  implements the same Protocol, parses its own vendor function-call format
  internally, and returns the same `OverrideCall` domain objects. Nothing
  downstream (service, engine) ever sees an Anthropic-shaped payload.
- **D-09:** **Inside** the Claude/Stub provider, the model emits **Claude-faithful
  `tool_use` blocks** `{type, id, name, input}`, which the provider translates →
  `OverrideCall`. This satisfies TEST-01 and Success Criterion 4 (Claude-faithful
  wire format) and proves the exact parse path Phase 4's real Claude reuses
  **unchanged**. Do NOT leak a minimal `{tool, args}` dict across the Protocol
  boundary — that would force a rewrite when real Claude lands.
- **D-10:** The `StubLLMProvider` is **keyword-routed**: it does light
  keyword/regex extraction (e.g. a task name + a number from "at least 2 on Pick")
  to build a real `tool_use` for `set_min_workers_per_task`; text with no match
  yields no tool_use (empty). Tests therefore exercise real text→args extraction,
  not just plumbing. Injected via a `get_llm_provider` FastAPI dependency mirroring
  `get_engine` (locked).

### Claude's Discretion
- Phase-1 **placeholder penalty weight `W`** — pick a fixed, reasonable value that
  makes the override "visibly honored" without dominating the round-2 cost
  objective. Empirical calibration is explicitly Phase 4 (ENG-04); a sensible
  constant is fine here. Document the chosen value.
- The exact field shape of the `OverrideCall` domain type (dataclass fields, how
  `tool` + `args` are typed) — open to standard approaches, kept in `domain/` to
  avoid an engine→llm import cycle (locked).
- How `run_service._execute` threads `scenario["overrides"]` into `SolverConfig`
  (parse JSON → `list[OverrideCall]` → attach to config) — standard wiring,
  planner's call.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project design source-of-truth
- `docs/design.md` — the engineering design of record for the scheduling model and
  the planned LLM layer (provider seam, soft-override mechanism).
- `docs/PLAN.md` — the hand-written phase tracker this GSD milestone formalizes.

### Requirements / roadmap (this phase)
- `.planning/REQUIREMENTS.md` — Phase-1 requirement IDs: ENG-01, ENG-02, ENG-03,
  ENG-06, LLM-01, LLM-03, NLC-01, NLC-06, TEST-01, TEST-02.
- `.planning/ROADMAP.md` §"Phase 1: First NL Constraint End-to-End" — goal +
  4 success criteria the build is judged against.

### Live code seams this phase touches
- `backend/engine/base.py` — `SchedulerEngine` Protocol + `SolverConfig` dataclass.
  `SolverConfig` must carry the overrides; `solve(problem, config)` signature stays
  unchanged (ENG-02).
- `backend/api/deps.py` — `get_engine` dependency; the new `get_llm_provider`
  dependency mirrors it (LLM-03).
- `backend/engine/cpsat/builder.py` — `_build_objectives` builds `round2_cost`;
  the per-hour shortfall penalty is added here. `_add_coverage_constraints` /
  `coverage_terms` are the per-`(task,hour)` supply expressions to reuse (D-02).
- `backend/engine/cpsat/objective.py` — `solve_lexicographic`: round 1 = unmet,
  round 2 = cost (lock-and-minimize). Confirms the override must land in round 2.
- `backend/store/db.py` — `scenarios.overrides TEXT DEFAULT '{}'` column (reserved
  in Phase 2) is where overrides persist (D-04/D-05).
- `backend/store/repositories.py` — `ScenarioRepo`; needs an update path to write
  the overrides JSON.
- `backend/services/run_service.py` — `_execute` builds `SolverConfig` from the
  scenario; extend to thread overrides through (Claude's discretion item).
- `backend/api/routers/scenarios.py` — existing CRUD router; pattern for the new
  constraints route (though D-07 makes it a top-level `/constraints` route).
- `backend/tests/test_api.py` — `StubEngine` + `dependency_overrides` pattern;
  the template for stubbing `get_llm_provider` and the NL→override→re-solve test.
- `backend/domain/types.py`, `backend/domain/problem.py`, `backend/domain/result.py`
  — pure domain layer where `OverrideCall` types live (ENG-01).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coverage_terms` (`builder.build` / `_add_coverage_constraints`): per-`(task,hour)`
  list of `(var, coeff)` supply terms — directly reusable to compute `assigned_h`
  for the shortfall penalty (D-02).
- `StubEngine` + `app.dependency_overrides` in `tests/test_api.py`: exact pattern
  to follow for `StubLLMProvider` + `get_llm_provider` override (no live API).
- `SolverConfig` dataclass already plumbed end-to-end (run_service → engine →
  objective); add an `overrides` field rather than changing the solve signature.
- `uuid4().hex` id style already used for run ids — content-hash ids (D-05) sit
  alongside it as a deliberate variant (for dedup).

### Established Patterns
- **Pure domain rule:** `domain/` imports nothing from solver/web/llm. `OverrideCall`
  lives here so the engine references it without an engine→llm cycle (ENG-01).
- **Soft-penalty precedent:** `unfilled_roster`, `unmet_vol`, `unmet_hc` are existing
  soft terms summed into objectives — the shortfall penalty extends this pattern.
- **Integer/scaled model:** times in hours, volumes/rates scaled via
  `config.constants` (`VOL_SCALE`, `HOUR_SCALE`, `COST_SCALE`). The penalty term must
  be a scaled integer expression like the existing cost terms.
- **Lexicographic solve:** round 1 (unmet) is locked, then round 2 (cost) minimized.
  Overrides go into `round2_cost` only.
- **Per-request fresh settings + dependency injection** for swappable seams.

### Integration Points
- New `POST /constraints` router mounted in `api/main.py` alongside health/fixtures/
  scenarios/runs.
- `get_llm_provider` added to `api/deps.py`; `ANTHROPIC_MODEL`/provider selection is
  config-driven but the real Claude impl is Phase 4 — Phase 1 wires the stub.
- `ScenarioRepo` gains an overrides-update method; service layer validates the
  `OverrideCall` (task id exists, `n` positive) before persisting.
- `run_service._execute` reads `scenario["overrides"]` → `list[OverrideCall]` →
  `SolverConfig.overrides`.
</code_context>

<specifics>
## Specific Ideas

- Example NL the stub should handle for the demo/test: "at least 2 on Pick" →
  `set_min_workers_per_task(task_id="Pick", n=2)` → `tool_use` block → `OverrideCall`.
- User explicitly values the provider seam being **vendor-agnostic** (Gemini or
  other LLMs pluggable behind `LLMProvider` returning `list[OverrideCall]`) — this
  drove D-08/D-09 and should be honored in the Protocol design.
- User preferred a flat `POST /constraints` route and a dict-keyed-by-id override
  store over the more conventional nested-resource / list alternatives.
</specifics>

<deferred>
## Deferred Ideas

- **v2 `remove_override` tool** (NLC-07) — the dict-keyed-by-id store (D-04) is
  chosen partly to make this easy later, but it is not built in Phase 1.
- **Full Anthropic wire-format fidelity surfaced across the boundary** — not
  needed; the layered design (D-08/D-09) keeps wire format internal. Real Claude
  provider is Phase 4.
- Other four tools, parse-UX (`no constraint found`, `clarification_needed`),
  broad arg/ID validation, insight reports — all later phases (kept out per scope).

None of these were scope-creep redirects; discussion stayed within phase scope.
</deferred>

---

*Phase: 1-First NL Constraint End-to-End*
*Context gathered: 2026-06-28*
