# Phase 2: Full 5-Tool Set + Safe Validation - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Broaden the Phase-1 seam from one tool to the **full five-tool set**, add the
**parse-UX signals** and **safe validation** layer, and detect **degenerate
re-solves** — all still stub-driven with zero network calls in CI.

A user can express any of the five supported constraints in plain English, see a
readable echo of what was understood (`parsed_constraint`), and have unsafe,
degenerate, or unknown inputs rejected with clear guidance **before** anything
reaches the solver.

The five tools: `set_min_workers_per_task` (already wired in Phase 1),
`scale_demand`, `lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours`.

**Not in this phase** (later slices, do not pull in): insight reports (Phase 3);
the real Claude provider + empirical penalty-weight calibration (Phase 4,
ENG-04); `remove_override` / multi-turn auto-retry (v2, NLC-07/08); any
hard/infeasible-making constraint (all overrides stay soft by project rule).
</domain>

<decisions>
## Implementation Decisions

### Response contract (multi-tool, partial-apply)
- **D-01:** One text can yield **0, 1, or many** tool calls (NLC-02). The endpoint
  uses **partial-apply**: persist every valid tool call and return **200** with a
  structured body carrying all outcomes simultaneously:
  ```
  {
    "applied":  [ {id, tool, args, parsed_constraint}, ... ],
    "rejected": [ {tool, error}, ... ],            // plain-English error + valid options (VAL-03)
    "clarification_needed": {question} | null,     // NLC-05
    "no_constraint_found": bool                    // NLC-03 (true only when nothing recognized)
  }
  ```
  A single bad reference never discards the good constraints in the same sentence
  (criterion 5's mixed valid/invalid case). This **replaces** Phase 1's
  single-call, raise-on-first-error → 400 shape. 404 is still returned only for an
  unknown `scenario_id` (the whole request can't proceed).
- **D-02:** `applied`, `rejected`, and `clarification_needed` can be **non-null
  together** in one response — apply the clear constraints AND ask about the
  ambiguous fragment in the same turn. Clarification does **not** short-circuit the
  request. The user answers the question in a follow-up `POST /constraints`.

### Parse signals (deterministic stub)
- **D-03:** **`no_constraint_found`** (NLC-03) is returned only when the text
  contains **nothing constraint-like** (no recognized tool keyword/shape).
- **D-04:** **`clarification_needed`** (NLC-05) is returned when the text matches a
  known constraint **shape/keyword but is incomplete or ambiguous** — e.g. a
  min-workers phrasing with no number ("more people on Pick"), or a reference token
  that matches **2+ tasks/members**. This **reroutes** Phase 1's ambiguous-match
  case (currently a 400 ValueError in `_resolve_task`) into a `clarification_needed`
  question instead of a hard error. Single-turn: the question names the ambiguity
  and the valid options; the user rephrases and resubmits.

### The five tools — semantics + soft application
All overrides remain **soft round-2 penalties** and can **never** make the solve
infeasible (project rule; D-03 of Phase 1). Tools land in
`builder._build_objectives` alongside the existing `set_min_workers_per_task`
shortfall term, **except `scale_demand`** (see D-09).

- **D-05:** `set_min_workers_per_task(task_id, n)` — unchanged from Phase 1
  (per-demanded-hour shortfall penalty, `n > 0`).
- **D-06:** `scale_demand(task_id, factor)` — **per-task** factor. Multiplies that
  one task's demand amounts by `factor` (e.g. "plan for 20% more Pick volume" →
  `factor = 1.2`). Resolves a single task via the existing task-resolution path.
  `factor > 0` required (VAL-01 rejects `≤ 0`). Down-scaling below `1.0` is allowed
  (not asked to forbid it).
- **D-07:** `lock_worker_shift(member_id, day)` — **member + day** granularity (NOT
  exact-shift-var pinning, which Phase 1 D-01 flagged brittle). Soft round-2
  penalty if the named member works **zero shifts on that day**. Validates
  `member_id` + that `day` is within the horizon. Robust against the
  per-(member×template×window) shift-var generation while staying visibly honored.
- **D-08:** `exclude_worker_from_task(member_id, task_id)` — soft round-2 penalty on
  **any assignment where that member produces that task**. Validates both refs.
- **D-09:** `set_max_hours(member_id, max_hours)` — soft round-2 penalty **per hour
  the member is scheduled above `max_hours`**, layered **on top of** the existing
  HARD weekly-hours cap (does not replace it). `max_hours > 0` (0/negative rejected
  by VAL-01).
- **D-10:** `scale_demand` is the **one override that reshapes problem input**
  rather than adding a round-2 penalty term — it scales the demand bands pre-solve.
  It is still **safe** (cannot make the model infeasible) because the existing
  `unmet` slack absorbs any resulting shortfall. **Researcher must confirm** where
  this scaling is applied (adapter/builder input vs. a config-time problem
  transform) so round-1 unmet behaviour stays the deliberate, documented exception
  to "overrides = round-2 penalty."

### Validation (VAL-01 / VAL-02 / VAL-03)
- **D-11:** Add a **`_resolve_member`** helper mirroring the existing
  `_resolve_task` — case-insensitive substring on `contact_id` / `Member.name`,
  **exactly-one match** required. Zero matches → rejected (VAL-02). Multiple matches
  → `clarification_needed` (D-04), not a hard error.
- **D-12:** Per-tool **argument bounds** validated before persistence (VAL-01):
  `n > 0`, `factor > 0`, `max_hours > 0`, `day` within horizon. Each failure
  produces a plain-English error naming the **offending arg/reference and the valid
  options** (VAL-03), collected into the `rejected[]` list (D-01).

### Degenerate-solve detection (ENG-05 / criterion 4)
- **D-13:** Flag a re-solve as degenerate when a **task family that has positive
  demand ends up with literally zero assigned supply** across the horizon (coverage
  collapsed to zero). Surface it as a **structured warning in the run result /
  metrics JSON** (e.g. `result.warnings[]` naming the affected family/task) so a
  downstream insight step (Phase 3) narrates it honestly instead of reporting
  success. This is detection-and-flag only — it never changes solver status or
  fails the run.

### Claude's Discretion
- **Stub multi-tool extraction** — how the keyword-routed `StubLLMProvider` splits
  a sentence (e.g. conjunctions "… and …") to emit **multiple** Claude-faithful
  `tool_use` blocks, and the per-tool keyword/regex patterns. Must stay
  deterministic and test-friendly; the real-Claude path (Phase 4) inherits the
  multi-tool contract for free. Exact phrasings/synonyms are the planner's call.
- **Placeholder penalty weights** for the four newly-wired tools — pick reasonable
  fixed constants alongside `MIN_WORKERS_PENALTY` (in `config/constants.py`) that
  make each override "visibly honored" without dominating round-2 cost. Empirical
  calibration is explicitly Phase 4 (ENG-04). Document chosen values.
- **`parsed_constraint` wording** per tool — human-readable echo strings (the
  Phase-1 pattern: "At least N workers on <task> (every demanded hour)"); extend
  naturally per tool.
- **`OverrideCall.args` typing** — loose dict per tool stays as-is (Phase 1 ENG-01);
  per-tool arg shapes added without changing the dataclass.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project design source-of-truth
- `docs/design.md` — engineering design of record for the scheduling model and the
  LLM layer (provider seam, soft-override mechanism).
- `docs/PLAN.md` — hand-written phase tracker this GSD milestone formalizes.

### Requirements / roadmap (this phase)
- `.planning/REQUIREMENTS.md` — Phase-2 requirement IDs: **NLC-02, NLC-03, NLC-04,
  NLC-05, VAL-01, VAL-02, VAL-03, ENG-05, TEST-03**.
- `.planning/ROADMAP.md` §"Phase 2: Full 5-Tool Set + Safe Validation" — goal +
  5 success criteria the build is judged against.
- `.planning/phases/01-first-nl-constraint-end-to-end/01-CONTEXT.md` — Phase-1
  locked decisions (D-01…D-10) this phase extends; especially the provider seam
  (D-08/D-09), override store (D-04/D-05), and soft-round-2 rule (D-03).

### Live code seams this phase touches
- `backend/llm/stub.py` — `StubLLMProvider`; extend from single min-workers regex
  to **all five tools + multi-tool extraction**; keep tool_use wire format internal.
- `backend/llm/base.py` — `LLMProvider` Protocol; `parse_constraints` contract is
  unchanged (returns `list[OverrideCall]`); parse-UX signals (no-constraint /
  clarification) are computed in the **service**, not the Protocol.
- `backend/services/constraint_service.py` — `parse_and_store` +
  `_resolve_task`; rework to **partial-apply** (applied/rejected/clarification),
  add `_resolve_member`, per-tool validation, and the new response shape.
- `backend/api/routers/constraints.py` — `POST /constraints`; update to return the
  new structured body (200) instead of raise→400 for per-call failures.
- `backend/api/schemas.py` — `ConstraintParseRequest` / `ConstraintParseResponse`;
  add `applied[]`, `rejected[]`, `clarification_needed`, `no_constraint_found`.
- `backend/engine/cpsat/builder.py` §`_build_objectives` (the override loop at
  ~L325–351) — extend to apply `lock_worker_shift`, `exclude_worker_from_task`,
  `set_max_hours` as soft round-2 terms; reuse `coverage_terms`, `shift_vars`,
  `vol_demand`/`hc_demand`.
- `backend/engine/cpsat/objective.py` — `solve_lexicographic`; confirms round-1
  (unmet) is locked before round-2 (cost) — the safety guarantee for soft overrides.
- `backend/domain/result.py` — where the degenerate-solve `warnings[]` surface
  lives (D-13); confirm/extend the result shape.
- `backend/domain/types.py` / `backend/domain/problem.py` — `Member`, `Task`,
  `DemandBand`, `DemandFamily`, `SchedulingProblem.task()`; basis for member/family
  resolution and the zero-supply degeneracy check.
- `backend/config/constants.py` — `MIN_WORKERS_PENALTY` and friends; add penalty
  constants for the new tools.
- `backend/tests/test_api.py` — `StubEngine` + `dependency_overrides` pattern; the
  template for TEST-03 (unknown IDs, out-of-bounds args, mixed valid/invalid call).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_resolve_task` (`services/constraint_service.py`): exact → case-insensitive
  substring, exactly-one-or-raise. Directly the template for `_resolve_member`
  (D-11); the multi-match branch becomes a `clarification_needed` source (D-04).
- Override loop in `builder._build_objectives` (~L325–351): the established
  per-(task,hour) shortfall pattern (`coverage_terms`, bounded slack var → round-2
  term) generalizes to the other tools (D-07/08/09).
- `coverage_terms`, `shift_vars`, `vol_demand`/`hc_demand` on the builder: supply
  expressions reusable for exclusion, day-lock, max-hours, and the zero-supply
  degeneracy check.
- `OverrideCall` + `override_id` content-hash (`domain/overrides.py`): unchanged;
  new tools just produce new `(tool, args)` shapes — idempotent store still holds.
- `StubEngine` + `app.dependency_overrides` (`tests/test_api.py`): no-live-API test
  pattern; extend for TEST-03 validation cases.

### Established Patterns
- **Pure domain rule:** `domain/` imports nothing from solver/web/llm. Override
  types and any new degeneracy-warning type stay framework-agnostic (ENG-01).
- **Soft-penalty precedent:** `unfilled_roster`, `unmet_vol`, `unmet_hc`,
  `set_min_workers` shortfall — all soft terms summed into objectives. New tools
  extend this; **bounded slack vars** keep every term from ever causing
  infeasibility.
- **Lexicographic solve:** round 1 (unmet) locked, then round 2 (cost) minimized.
  All penalty-style overrides go into `round2_cost` only.
- **Service raises / router translates:** preserved for the 404 (unknown scenario)
  path; per-call validation now returns structured `rejected[]` instead of raising.
- **Integer/scaled model:** penalty terms must be scaled integer expressions
  (`VOL_SCALE`/`HOUR_SCALE`/`COST_SCALE`), like the existing cost terms.

### Integration Points
- `constraint_service.parse_and_store` becomes the orchestrator of partial-apply:
  parse → per-call resolve/validate → bucket into applied/rejected/clarification →
  merge applied into overrides JSON → return structured body.
- Degeneracy detection (D-13) runs **post-solve** — likely in the run/result
  serialization path (`services/run_service.py` / `services/serialize.py` /
  `domain/result.py`), reading metrics, not in the request thread.
- `scale_demand` (D-10) needs a confirmed application point (input transform) —
  the one override that is not a round-2 penalty.
</code_context>

<specifics>
## Specific Ideas

- Example mixed sentence the stub/service should handle:
  "at least 2 on Pick and more people on packing" → `applied`:
  `set_min_workers_per_task(Pick, 2)`; `clarification_needed`: a question about the
  "more people on packing" fragment (no number) — both in one 200 response (D-02).
- Example rejection (criterion 5): a multi-tool call with one valid task ref and one
  unknown member ref → valid one in `applied[]`, unknown one in `rejected[]` naming
  the bad reference and listing valid members (VAL-02/VAL-03).
- `lock_worker_shift` phrased at day level ("keep Alice on Tuesday") rather than
  pinning a generated shift — deliberate robustness choice (D-07).
- `scale_demand` phrased per task ("plan for 20% more Pick volume") with `factor`,
  down-scaling allowed (D-06).
</specifics>

<deferred>
## Deferred Ideas

- **`remove_override` (NLC-07)** and **multi-turn auto-retry (NLC-08)** — v2; the
  dict-keyed store makes removal easy later, but not built here.
- **Empirical penalty-weight calibration (ENG-04)** — Phase 4; Phase 2 uses
  reasonable placeholder constants.
- **Insight reports (INS-*)** — Phase 3 consumes the `warnings[]` surface this phase
  produces, but generation is out of scope here.
- **Forbidding `scale_demand` down-scaling (`factor < 1.0`)** — considered; allowed
  for now (not restricted). Revisit if it proves confusing.

None of these were scope-creep redirects; discussion stayed within phase scope.
</deferred>

---

*Phase: 2-Full 5-Tool Set + Safe Validation*
*Context gathered: 2026-06-28*
