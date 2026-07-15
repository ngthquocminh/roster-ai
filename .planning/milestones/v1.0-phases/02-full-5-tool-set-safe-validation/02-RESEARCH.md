# Phase 2: Full 5-Tool Set + Safe Validation — Research

**Researched:** 2026-06-29
**Domain:** Python backend — CP-SAT soft-override extension, NL constraint service rework, stub LLM multi-tool parsing
**Confidence:** HIGH (all claims grounded in live source with file:line refs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (response contract):** Endpoint uses partial-apply — 200 with structured body: `applied[]`, `rejected[]`, `clarification_needed`, `no_constraint_found`. A bad reference never discards valid constraints from the same sentence.
- **D-02:** `applied`, `rejected`, and `clarification_needed` can be non-null together. Clarification does not short-circuit the request.
- **D-03:** `no_constraint_found` returned only when text contains nothing constraint-like.
- **D-04:** `clarification_needed` returned when text matches a known constraint shape/keyword but is incomplete or ambiguous. Reroutes the current ambiguous-match 400 ValueError from `_resolve_task` to `clarification_needed`.
- **D-05:** `set_min_workers_per_task(task_id, n)` — unchanged from Phase 1.
- **D-06:** `scale_demand(task_id, factor)` — per-task factor; `factor > 0` required; down-scaling allowed.
- **D-07:** `lock_worker_shift(member_id, day)` — member+day granularity; soft round-2 penalty if member works zero shifts that day.
- **D-08:** `exclude_worker_from_task(member_id, task_id)` — soft round-2 penalty per assignment.
- **D-09:** `set_max_hours(member_id, max_hours)` — soft round-2 penalty per hour above `max_hours`; layered on top of existing HARD cap; `max_hours > 0` required.
- **D-10:** `scale_demand` reshapes problem input (not a round-2 penalty); applied pre-solve; confirmed insertion point must be researched.
- **D-11:** Add `_resolve_member` mirroring `_resolve_task`; zero-match → rejected; multi-match → `clarification_needed`.
- **D-12:** Per-tool argument bounds validated before persistence; failures go to `rejected[]` with plain-English error naming offending arg/reference and valid options.
- **D-13:** Degenerate-solve detection: task family with positive demand + zero assigned supply → warning in result; detection-only, never changes solver_status.

### Claude's Discretion

- Stub multi-tool extraction: conjunction handling, per-tool regex patterns, and how to signal `clarification_needed` vs `no_constraint_found` from a deterministic stub.
- Placeholder penalty weights for the four newly-wired tools; `MIN_WORKERS_PENALTY = 100_000` is the precedent.
- `parsed_constraint` wording per tool.
- `OverrideCall.args` typing: loose dict stays as-is.

### Deferred Ideas (OUT OF SCOPE)

- `remove_override` (NLC-07) and multi-turn auto-retry (NLC-08) — v2.
- Empirical penalty-weight calibration (ENG-04) — Phase 4.
- Insight reports (INS-*) — Phase 3.
- Forbidding `scale_demand` down-scaling (`factor < 1.0`) — not restricted in Phase 2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NLC-02 | Text parsed into zero or more solver-hook tool calls from the fixed five-tool set | Stub multi-tool extraction + service partial-apply loop |
| NLC-03 | No-match text returns "no constraint found" (not a spurious tool call) | `no_constraint_found` flag in service; stub returns `[]` for non-matching text |
| NLC-04 | Response echoes human-readable `parsed_constraint` summary | Per-tool `parsed_constraint` string in `applied[]` entries |
| NLC-05 | Ambiguous/unparseable input returns `clarification_needed` with a question (single-turn) | `_resolve_task`/`_resolve_member` multi-match rerouting; stub partial-match signals |
| VAL-01 | Tool-call argument bounds validated before reaching the solver | Per-tool validation in partial-apply loop: `factor > 0`, `max_hours > 0`, `n > 0`, `day` within horizon |
| VAL-02 | Member/task references validated against real scenario IDs | `_resolve_task` + new `_resolve_member` helper |
| VAL-03 | Validation failures return plain-English error naming offending reference/argument and valid options | `rejected[]` list with error strings |
| ENG-05 | Degenerate solves detected and flagged; zero-coverage task families surfaced in result | New `warnings: list[str]` field on `SolveResult`; check after computing `coverage_by_function` in `engine/cpsat/engine.py` |
| TEST-03 | Validation tests cover unknown IDs, out-of-bounds args, and mixed valid/invalid multi-tool calls | Extend `test_constraints_api.py`; reuse `StubEngine` + `dependency_overrides` pattern |
</phase_requirements>

---

## Summary

Phase 2 is a pure extension of Phase 1's established seam — no new libraries, no greenfield decisions. All seven source files identified in CONTEXT.md `<canonical_refs>` have been read end-to-end. The findings answer all seven open questions with exact file:line references and quoted code where the planner needs it.

The critical discovery is that `SolveResult` (domain/result.py) has no `warnings` field today — it must be added. All other insertion points (`_aggregate_demand`, `_build_objectives`, `parse_and_store`, stub regex table, router+schema) are clear extension points with no structural surprises. The partial-apply rework of `parse_and_store` is the largest single change (~100 lines net new), but the service already has all the primitives it needs.

**Primary recommendation:** Extend every existing seam in the order: domain types → builder → service → stub → schema → router → tests. Nothing needs to be added from outside the repo.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| NL text → OverrideCall list | LLM Provider (stub) | — | Protocol boundary isolates vendor parsing from the rest |
| Partial-apply + validation | Service (constraint_service) | — | Service layer owns business logic; router only translates exceptions |
| Ref resolution (task/member) | Service (constraint_service) | Domain (problem lookup) | Needs access to loaded SchedulingProblem; resolver helpers stay in the service |
| Override persistence | Service → Store | — | ScenarioRepo.update_overrides already exists (Phase 1) |
| Demand scaling (scale_demand) | Engine/Builder (_aggregate_demand) | — | Builder already owns demand → per-hour aggregation; insertion here keeps SchedulingProblem immutable |
| Soft round-2 penalties (3 new tools) | Engine/Builder (_build_objectives) | — | All soft overrides land in round2_cost only (locked project rule) |
| Degenerate-solve detection | Engine (CpSatEngine.solve) | Domain (SolveResult.warnings) | Detection occurs post-solve where coverage_by_function is already computed |
| API request/response shaping | Router (constraints.py) + Schema | — | Router translates LookupError → 404; service structured result → 200 body |
| Test isolation | Tests (dependency_overrides) | — | StubEngine + StubLLMProvider via FastAPI DI; no live API in CI |

---

## Standard Stack

This phase installs **no new packages**. All implementation uses the existing stack:

| Library | Version (from pyproject.toml) | Role in Phase 2 |
|---------|-------------------------------|-----------------|
| fastapi | current | Router + Pydantic schema changes |
| pydantic | (fastapi dep) | New `ConstraintParseResponse` shape |
| ortools | 9.11.4210 (pinned) | `_build_objectives` extension; no API changes |
| pytest | dev dep | TEST-03 validation tests |
| Python stdlib: re, json, hashlib | stdlib | Stub regexes; override store |

**No `npm view`, `pip index versions`, or legitimacy checks required — no new packages.**

---

## Package Legitimacy Audit

Not applicable — this phase installs no external packages.

---

## Architecture Patterns

### System Architecture Diagram (Phase 2 data flow)

```
POST /constraints
     │
     ▼
constraints.py router
     │  LookupError → 404
     ▼
constraint_service.parse_and_store()
     │
     ├─ ScenarioRepo.get(scenario_id)
     │    └─ LookupError if not found ─────────────────────────────► 404
     │
     ├─ provider.parse_constraints(text)          ◄─── StubLLMProvider
     │    └─ returns list[OverrideCall]
     │         (can include _clarification signals)
     │
     ├─ load_problem(fixture_path)
     │
     ├─ for each call:
     │     ├─ _resolve_task / _resolve_member
     │     │    ├─ zero match  → rejected[]
     │     │    ├─ multi-match → clarification_needed
     │     │    └─ one match   → resolved_args
     │     ├─ validate arg bounds (VAL-01)
     │     │    └─ out-of-bounds → rejected[]
     │     └─ apply → applied[]
     │
     ├─ ScenarioRepo.update_overrides(applied only)
     │
     └─ return {applied, rejected, clarification_needed, no_constraint_found}
                    │
                    ▼
         router returns 200 structured body


POST /scenarios/{id}/runs → run_service._execute (worker thread)
     │
     ├─ load_problem(fixture_path)
     ├─ parse scenario["overrides"] → list[OverrideCall]
     ├─ SolverConfig(overrides=...)
     ├─ CpSatBuilder(problem, overrides).build()
     │     ├─ _aggregate_demand()
     │     │    └─ applies scale_demand factor per task_id (D-10)
     │     ├─ _build_objectives()
     │     │    └─ per override tool:
     │     │         set_min_workers_per_task → shortfall slack (existing)
     │     │         lock_worker_shift        → absent_day bool (new)
     │     │         exclude_worker_from_task → assignment vars (new)
     │     │         set_max_hours            → hours_over var (new)
     │     └─ scale_demand applied in _aggregate_demand (not here)
     ├─ solve_lexicographic(builder, ...)
     ├─ CpSatEngine._extract_result()
     │    └─ check coverage_by_function → warnings[] (ENG-05)
     └─ SolveResult(status, schedule, metrics, stats, warnings=[...])
```

### Recommended Project Structure (additions only)

```
backend/
├── domain/
│   └── result.py           # add warnings: list[str] field to SolveResult
├── engine/cpsat/
│   ├── builder.py          # _aggregate_demand + _build_objectives extension
│   └── engine.py           # degeneracy detection after coverage_by_function
├── llm/
│   └── stub.py             # 5 tool regexes + conjunction splitting + _clarification signal
├── services/
│   └── constraint_service.py  # full partial-apply rework
├── api/
│   ├── routers/constraints.py  # remove ValueError → 400; pass structured body
│   └── schemas.py              # new ConstraintParseResponse + supporting models
├── config/
│   └── constants.py        # 4 new penalty constants
└── tests/
    └── test_constraints_api.py  # TEST-03 cases appended
```

---

## Open Question Answers (Code Archaeology)

### OQ-1: scale_demand application point (D-10)

**Finding:** The correct insertion point is `builder._aggregate_demand()` in `backend/engine/cpsat/builder.py` (lines 111–129). [VERIFIED: live source read]

**Evidence — current `_aggregate_demand` loop (builder.py L111–129):**

```python
def _aggregate_demand(self):
    vol: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    hc: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    is_ind: Dict[str, bool] = {}
    for b in self.p.demand:
        h0, h1 = int(math.floor(b.start_h)), int(math.ceil(b.end_h))
        if b.family == DemandFamily.INDIRECT:
            is_ind[b.task_id] = True
            for h in range(h0, h1):
                if _overlap((b.start_h, b.end_h), (h, h + 1)) > 0:
                    hc[b.task_id][h] += b.amount
        else:
            is_ind.setdefault(b.task_id, False)
            dur = max(b.duration_h, 1e-9)
            for h in range(h0, h1):
                ov = _overlap((b.start_h, b.end_h), (h, h + 1))
                if ov > 0:
                    vol[b.task_id][h] += b.amount * ov / dur
    return vol, hc, is_ind
```

**Why this is the right seam:**
- The builder already holds `self.overrides` (set in `__init__`, builder.py L93–95).
- `SchedulingProblem` is an immutable snapshot — mutating `.demand` on it would violate domain purity and surprise the no-override path.
- The `unmet_vol`/`unmet_hc` slack vars are bounded by the aggregated demand value (`NewIntVar(0, rhs, ...)` at `_add_coverage_constraints` L281–302). Scaling `vol[task_id][h]` by `factor` scales `rhs` proportionally, so `unmet` still absorbs the full shortfall — infeasibility is structurally impossible regardless of `factor`.
- This keeps `scale_demand` isolated from `_build_objectives`, honouring the "deliberate, documented exception to overrides = round-2 penalty" (D-10).

**Implementation pattern — read scale factors before the loop:**

```python
def _aggregate_demand(self):
    # Build per-task demand scale map from scale_demand overrides (D-10).
    # Applied here so SchedulingProblem stays immutable; unmet slack absorbs
    # any resulting shortfall, so factor can never cause infeasibility.
    scale: dict[str, float] = {}
    for ov in self.overrides:
        if ov.tool == "scale_demand":
            scale[ov.args["task_id"]] = float(ov.args["factor"])

    vol: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    hc: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    is_ind: Dict[str, bool] = {}
    for b in self.p.demand:
        f = scale.get(b.task_id, 1.0)          # <-- scaling applied here
        h0, h1 = int(math.floor(b.start_h)), int(math.ceil(b.end_h))
        if b.family == DemandFamily.INDIRECT:
            is_ind[b.task_id] = True
            for h in range(h0, h1):
                if _overlap((b.start_h, b.end_h), (h, h + 1)) > 0:
                    hc[b.task_id][h] += b.amount * f
        else:
            is_ind.setdefault(b.task_id, False)
            dur = max(b.duration_h, 1e-9)
            for h in range(h0, h1):
                ov = _overlap((b.start_h, b.end_h), (h, h + 1))
                if ov > 0:
                    vol[b.task_id][h] += b.amount * f * ov / dur
    return vol, hc, is_ind
```

**Safety guarantee confirmed:** `_add_coverage_constraints` (L280–302) creates `unmet = NewIntVar(0, rhs, ...)` where `rhs = int(round(dvol * C.VOL_SCALE))`. When `factor` scales `dvol` up or down, `rhs` scales correspondingly and `unmet` always absorbs the full shortfall — the constraint `sum(supply) + unmet >= rhs` is always satisfiable.

---

### OQ-2: Override loop in `builder._build_objectives` — exact current code + extension plan

**Exact current code (builder.py L325–351):** [VERIFIED: live source read]

```python
# --- soft shortfall penalty for NL-derived overrides (D-02/D-03) ---
# Added to round2_cost ONLY — never to round1_unmet, never as a hard
# constraint.  Because round 1 is locked before round 2 is minimised
# (objective.py), this term can never affect round-1 feasibility; an
# override can therefore never make the solve infeasible (T-01-E1).
shortfall_terms = []
for ov in self.overrides:
    if ov.tool != "set_min_workers_per_task":
        continue  # only tool supported in Phase 1 (D-01)
    tid = ov.args["task_id"]
    n = int(ov.args["n"])
    # hours with demand for this task (union of vol and hc demand)
    hours = set(self.vol_demand.get(tid, {})) | set(self.hc_demand.get(tid, {}))
    for h in hours:
        # body count: bare vars (coeff ignored) — headcount form (D-02)
        bodies = [var for var, _ in self.coverage_terms.get((tid, h), [])]
        # slack bounded by n so an empty supply degrades to a constant
        # penalty rather than causing infeasibility (T-01-E1)
        short = self.m.NewIntVar(0, n, f"minw_short_{tid[:6]}_{h}")
        self.m.Add(sum(bodies) + short >= n)
        shortfall_terms.append(short)

self.round2_cost = (
    sum(cost_terms) + C.MIN_WORKERS_PENALTY * sum(shortfall_terms)
    if (cost_terms or shortfall_terms)
    else 0
)
```

**Builder attributes available for the three new tools:**

| Attribute | Type | Populated at | Content |
|-----------|------|-------------|---------|
| `self.shift_vars` | `List[ShiftVar]` | `build()` inner loop | All generated shift candidates; each has `.member` (Member), `.window`, `.start_h`, `.end_h`, `.eff_h` |
| `self.task_vars` | `List[TaskVar]` | `build()` inner loop | All task assignment vars; each has `.var` (BoolVar), `.shift` (ShiftVar), `.task_id`, `.hour_overlap` |
| `self.coverage_terms` | `Dict[(task_id, h), List[(var, coeff)]]` | L233 | Per-(task,hour) (var, coeff) supply terms — used for min-workers; bare vars give headcount |
| `self.vol_demand` / `self.hc_demand` | `Dict[task_id, Dict[h, float]]` | `_aggregate_demand` → stored at L176 | Demanded hours per task per hour bucket |
| `C.VOL_SCALE` | `int = 100` | constants.py L29 | Scaling factor for volumes and rates |
| `C.HOUR_SCALE` | `int = 100_000` | constants.py L30 | Scaling factor for labour-hours in objectives |
| `C.COST_SCALE` | `int = 100` | constants.py L31 | Scaling factor for dollars |

**Extension plan for three new tools:**

**`lock_worker_shift(member_id, day)`** (D-07):
- Filter `self.shift_vars` by `sv.member.contact_id == member_id AND int(sv.start_h // 24) == day`.
- Create `absent = self.m.NewBoolVar(f"lock_absent_{member_id[:6]}_{day}")`.
- Add: `self.m.Add(sum(sv.var for sv in day_shifts) + absent >= 1)`. When `day_shifts` is empty (no candidates for that day), `absent = 1` unconditionally — the penalty fires but the model stays feasible because `absent` is not upper-bounded to zero.
- Accumulate: `lock_terms.append(absent)`.
- Note: `present + absent >= 1` means if no shift selected, `absent` must be 1 (penalty incurred). If any shift selected, `absent` can be 0 (optimizer clears the penalty). This is the bounded-slack pattern consistent with existing shortfall terms.

**`exclude_worker_from_task(member_id, task_id)`** (D-08):
- Filter `self.task_vars` by `tv.shift.member.contact_id == member_id AND tv.task_id == task_id`.
- No new slack variable needed — the assignment vars `tv.var` are themselves boolean; when 1, they incur the penalty.
- Accumulate: `excl_terms.extend(tv.var for tv in matching_tvs)`.
- Penalty: `C.EXCLUDE_WORKER_PENALTY * sum(excl_terms)` added to `round2_cost`.

**`set_max_hours(member_id, max_hours)`** (D-09):
- Filter `self.shift_vars` by `sv.member.contact_id == member_id`.
- `scaled_max = int(round(max_hours * C.VOL_SCALE))`.
- `total_scaled = sum(int(round(sv.eff_h * C.VOL_SCALE)) * sv.var for sv in member_svs)` (mirrors the existing hard-cap expression at builder.py L269–270).
- The existing HARD weekly cap ensures `total_scaled` never exceeds `cap * VOL_SCALE`. The soft max_hours override is layered below that cap, so the overflow var is bounded by `int(round((hard_cap - max_hours) * VOL_SCALE))`.
- `hard_cap_scaled = int(round(self.p.max_hours_per_week.get(member.emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK) * C.VOL_SCALE))`.
- `over = self.m.NewIntVar(0, max(0, hard_cap_scaled - scaled_max), f"maxh_over_{member_id[:6]}")`.
- Add: `self.m.Add(total_scaled <= scaled_max + over)`.
- Accumulate: `maxh_terms.append(over)`.
- Penalty: `C.MAX_HOURS_PENALTY * sum(maxh_terms)` where `over` is in VOL_SCALE units (per-100th-of-an-hour), so the penalty per actual hour over limit = `MAX_HOURS_PENALTY / VOL_SCALE`.

**Suggested `_build_objectives` extension structure:**

```python
shortfall_terms = []   # set_min_workers_per_task (existing)
lock_terms = []        # lock_worker_shift (new)
excl_terms = []        # exclude_worker_from_task (new)
maxh_terms = []        # set_max_hours (new)

for ov in self.overrides:
    if ov.tool == "set_min_workers_per_task":
        # ... existing code unchanged ...
    elif ov.tool == "lock_worker_shift":
        # ... new code ...
    elif ov.tool == "exclude_worker_from_task":
        # ... new code ...
    elif ov.tool == "set_max_hours":
        # ... new code ...
    # scale_demand is handled in _aggregate_demand, not here

self.round2_cost = (
    sum(cost_terms)
    + C.MIN_WORKERS_PENALTY * sum(shortfall_terms)
    + C.LOCK_SHIFT_PENALTY * sum(lock_terms)
    + C.EXCLUDE_WORKER_PENALTY * sum(excl_terms)
    + C.MAX_HOURS_PENALTY * sum(maxh_terms)
    if (cost_terms or shortfall_terms or lock_terms or excl_terms or maxh_terms)
    else 0
)
```

**New constants to add to `backend/config/constants.py`:**

```python
# Penalty for lock_worker_shift: soft penalty if member has zero shifts on the locked day.
# Same order of magnitude as MIN_WORKERS_PENALTY to be "visibly honored".
# Empirical calibration deferred to Phase 4 (ENG-04).
LOCK_SHIFT_PENALTY: int = 100_000

# Penalty per task-var assignment where excluded member produces excluded task.
# Assignment vars are booleans; penalty fires once per assigned slot, not per hour.
# Set large enough to discourage but not overwhelm round-2 cost.
EXCLUDE_WORKER_PENALTY: int = 50_000

# Penalty per VOL_SCALE unit of hours-over-max_hours.
# Actual penalty per hour over limit = MAX_HOURS_PENALTY / VOL_SCALE = 1000.
# Layered atop the existing hard cap, which the optimizer cannot exceed.
MAX_HOURS_PENALTY: int = 100_000
```

---

### OQ-3: Degeneracy detection seam (D-13 / ENG-05)

**Finding:** `SolveResult` at `backend/domain/result.py` has **no `warnings` field** today. A `warnings: list[str]` field must be added. [VERIFIED: live source read]

**Current `SolveResult` (domain/result.py L48–52):**

```python
@dataclass
class SolveResult:
    status: str
    schedule: List[ScheduleRow]
    metrics: SummaryMetrics
    stats: SolverStats
```

**Required change — add `warnings` field:**

```python
@dataclass
class SolveResult:
    status: str
    schedule: List[ScheduleRow]
    metrics: SummaryMetrics
    stats: SolverStats
    warnings: List[str] = field(default_factory=list)
```

**Detection logic — where to compute:** In `engine/cpsat/engine.py`, after `coverage_by_function` is assembled (engine.py L90–93). At that point, `req_func[fn]` (required labour-hours) and `unmet_func[fn]` (unmet hours) are both available:

```python
# After: coverage_by_function = { fn: CoverageStat(...) for fn, req in ... }
warnings: list[str] = []
for fn, stat in coverage_by_function.items():
    if stat.required_h > 1e-9 and stat.served_h <= 1e-9:
        warnings.append(
            f"Degenerate solve: task family '{fn}' has demand "
            f"({stat.required_h:.1f}h required) but zero assigned supply."
        )
```

**Key constraints:**
- Detection only — never sets `status` or alters `solver_status`. The `SolveResult.status` is set from `lex.status` at engine.py L115 and is not touched.
- Works at the function/family level because `coverage_by_function` aggregates by `Task.function` (engine.py L38, L69, L75).
- The `StubEngine` in tests (test_constraints_api.py L38–43) currently returns `warnings=[]` implicitly because `SolveResult` will have the default. Test assertions only check the fields they care about, so adding `warnings` is backward-compatible.

**Serialization path — update `services/serialize.py`:**

Current `serialize_result` (serialize.py L21–44) does not emit `warnings`. Add to the return dict:

```python
return {
    "status": r.status,
    "warnings": r.warnings,          # new — survives to runs.result_json
    "metrics": { ... },
    "stats": { ... },
    "schedule": [ ... ],
}
```

The `runs.result_json` column stores this dict via `json.dumps` in `run_service._execute` (run_service.py L94–95). The `GET /runs/{run_id}/result` endpoint returns it as-is — no schema change needed there unless an explicit response model is added (currently it returns raw JSON).

---

### OQ-4: Service partial-apply rework — exact current code + concrete change plan

**Exact current `parse_and_store` flow (constraint_service.py L67–146):** [VERIFIED: live source read]

```
parse_and_store(conn, provider, scenario_id, text, data_dir):
1. ScenarioRepo.get(scenario_id) → LookupError if not found
2. provider.parse_constraints(text) → calls: list[OverrideCall]
3. if not calls: raise ValueError("No constraint found...")       ← becomes no_constraint_found
4. load_problem(fixture_path)
5. for call in calls:
     if tool == "set_min_workers_per_task":
         resolved_task_id = _resolve_task(problem, args["task_id"])    ← raises on unknown/ambiguous
         n = int(args["n"])
         if n <= 0: raise ValueError(...)                              ← becomes rejected[]
     else:
         raise ValueError(f"Unsupported tool {tool!r}...")             ← becomes rejected[]
     new_id = override_id(tool, args)
     resolved_calls.append(OverrideCall(new_id, tool, args))
6. merge resolved_calls into existing[id] = {tool, args}
7. repo.update_overrides(scenario_id, json.dumps(existing))
8. conn.commit()
9. return {id, tool, args, parsed_constraint}  ← first call only
```

**Exact current `_resolve_task` (constraint_service.py L31–64):**

```python
def _resolve_task(problem, token: str) -> str:
    if problem.task(token) is not None:   # exact GUID match
        return token
    token_lower = token.lower()
    matches = [
        t for t in problem.tasks
        if token_lower in t.task_id.lower() or token_lower in t.name.lower()
    ]
    if len(matches) == 1:
        return matches[0].task_id
    valid_names = ", ".join(f"{t.task_id!r} ({t.name!r})" for t in problem.tasks)
    if len(matches) == 0:
        raise ValueError(
            f"Unknown task reference {token!r}. Valid tasks: {valid_names}"
        )
    # Multiple matches
    matched_names = ", ".join(f"{t.task_id!r} ({t.name!r})" for t in matches)
    raise ValueError(
        f"Ambiguous task reference {token!r} matches {len(matches)} tasks: "
        f"{matched_names}. Use a more specific token."
    )
```

**Concrete rework plan — new `parse_and_store` return shape and logic:**

Step 1: Introduce a resolution result type (internal, not a domain type):

```python
# Internal result of _resolve_task / _resolve_member — not exported
from typing import NamedTuple
class _ResolveResult(NamedTuple):
    resolved_id: str | None     # set on single match
    error: str | None           # set on zero match (VAL-02 / VAL-03)
    clarification: str | None   # set on multi-match (NLC-05)
```

Step 2: Rewrite `_resolve_task` to return `_ResolveResult` instead of raising:

```python
def _resolve_task(problem, token: str) -> _ResolveResult:
    if problem.task(token) is not None:
        return _ResolveResult(resolved_id=token, error=None, clarification=None)
    token_lower = token.lower()
    matches = [t for t in problem.tasks
               if token_lower in t.task_id.lower() or token_lower in t.name.lower()]
    valid_names = ", ".join(f"'{t.name}' (id: {t.task_id})" for t in problem.tasks)
    if len(matches) == 0:
        return _ResolveResult(
            resolved_id=None,
            error=f"Unknown task '{token}'. Valid tasks: {valid_names}",
            clarification=None,
        )
    if len(matches) == 1:
        return _ResolveResult(resolved_id=matches[0].task_id, error=None, clarification=None)
    matched = ", ".join(f"'{t.name}'" for t in matches)
    return _ResolveResult(
        resolved_id=None, error=None,
        clarification=f"'{token}' matches multiple tasks: {matched}. Which did you mean?",
    )
```

Step 3: Add `_resolve_member` mirroring `_resolve_task` (D-11):

```python
def _resolve_member(problem, token: str) -> _ResolveResult:
    token_lower = token.lower()
    matches = [
        m for m in problem.members
        if token_lower in m.contact_id.lower() or token_lower in m.name.lower()
    ]
    valid_names = ", ".join(f"'{m.name}'" for m in problem.members)
    if len(matches) == 0:
        return _ResolveResult(
            resolved_id=None,
            error=f"Unknown member '{token}'. Valid members: {valid_names}",
            clarification=None,
        )
    if len(matches) == 1:
        return _ResolveResult(resolved_id=matches[0].contact_id, error=None, clarification=None)
    matched = ", ".join(f"'{m.name}'" for m in matches)
    return _ResolveResult(
        resolved_id=None, error=None,
        clarification=f"'{token}' matches multiple members: {matched}. Which did you mean?",
    )
```

Step 4: New `parse_and_store` signature and return contract:

```python
def parse_and_store(...) -> dict:
    """Returns:
        {
          "applied": [{"id": ..., "tool": ..., "args": ..., "parsed_constraint": ...}, ...],
          "rejected": [{"tool": ..., "error": ...}, ...],
          "clarification_needed": "...question..." | None,
          "no_constraint_found": bool,
        }
    Raises:
        LookupError: scenario_id not found (router maps to 404).
        # No longer raises ValueError for per-call failures — those go to rejected[].
    """
```

Step 5: Per-tool validation in the partial-apply loop — validation rules per tool:

| Tool | Resolution needed | Arg bounds (VAL-01) |
|------|------------------|---------------------|
| `set_min_workers_per_task` | `_resolve_task(args["task_id"])` | `n > 0` |
| `scale_demand` | `_resolve_task(args["task_id"])` | `factor > 0` |
| `lock_worker_shift` | `_resolve_member(args["member_id"])`, `day` within `0..int(problem.horizon_h // 24) - 1` | day integer |
| `exclude_worker_from_task` | `_resolve_member(args["member_id"])` + `_resolve_task(args["task_id"])` | — |
| `set_max_hours` | `_resolve_member(args["member_id"])` | `max_hours > 0` |
| `_clarification` (stub signal) | — | — |

Step 6: Clarification aggregation — use the first clarification question encountered (or concatenate multiple); Phase 2 is single-turn so one question suffices.

Step 7: `no_constraint_found = True` when provider returns `[]` AND no `_clarification` signals were generated. If provider returns `[]` but the stub also produced no `_clarification` signal, set `no_constraint_found = True`.

Step 8: Persist only `applied[]` entries to `scenario.overrides`; `rejected[]` and `clarification_needed` are response-only.

---

### OQ-5: Stub multi-tool extraction

**Current stub (llm/stub.py L30–77):** Single `_MIN_WORKERS_RE` regex; returns at most one OverrideCall; no conjunction handling; unsupported tool returns `[]`. [VERIFIED: live source read]

**Recommended approach for Phase 2 (Claude's Discretion area):**

**Architecture:** Conjunction splitting → per-fragment regex matching → per-tool tool_use block → OverrideCall list. Keeps all wire-format construction inside `llm/stub.py`, protocol boundary unchanged.

**Step 1 — Split text on conjunctions:**

```python
import re
_SPLIT_RE = re.compile(r"\s+and\s+|\s+but\s+|\s*,\s*", re.IGNORECASE)

def _split_fragments(text: str) -> list[str]:
    return [f.strip() for f in _SPLIT_RE.split(text) if f.strip()]
```

**Step 2 — Per-tool regex table (all `re.IGNORECASE`):**

```python
# set_min_workers_per_task (existing, slightly generalized)
_MIN_WORKERS_RE = re.compile(
    r"(?:at\s+least|minimum|min|need\s+at\s+least|require\s+at\s+least)"
    r"\s+(\d+)\s+(?:workers?\s+)?on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)

# scale_demand: "plan for 20% more Pick volume" / "increase Pick demand by 1.5x"
_SCALE_DEMAND_RE = re.compile(
    r"(?:plan\s+for\s+|increase\s+|scale\s+|boost\s+)?(\d+(?:\.\d+)?)\s*x?\s*"
    r"(?:more\s+)?(\w+(?:\s+\w+){0,2})\s+(?:volume|demand|workload)",
    re.IGNORECASE,
)

# lock_worker_shift: "keep Alice on Tuesday" / "lock Alice on Monday"
_LOCK_SHIFT_RE = re.compile(
    r"(?:keep|lock|assign)\s+(\w+(?:\s+\w+)?)\s+on\s+"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d+)",
    re.IGNORECASE,
)

# exclude_worker_from_task: "exclude Alice from Pick" / "don't assign Bob to Receiving"
_EXCLUDE_RE = re.compile(
    r"(?:exclude|remove|don'?t\s+assign|no)\s+(\w+(?:\s+\w+)?)"
    r"\s+(?:from|to|on)\s+(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)

# set_max_hours: "Alice maximum 40 hours" / "cap Bob at 35 hours"
_MAX_HOURS_RE = re.compile(
    r"(?:cap|limit|max(?:imum)?)\s+(\w+(?:\s+\w+)?)\s+(?:at|to)?\s*(\d+(?:\.\d+)?)\s+hours?",
    re.IGNORECASE,
)

# Partial match — constraint-shaped but missing required arg:
# "more people on Pick" / "fewer workers on Receiving"
_PARTIAL_WORKERS_RE = re.compile(
    r"(?:more|fewer|less|extra)\s+(?:workers?|people|staff)\s+on\s+(?:the\s+)?(\w+(?:\s+\w+){0,2})",
    re.IGNORECASE,
)
```

**Step 3 — Signalling `clarification_needed` from the stub:**

The service layer is responsible for computing `clarification_needed` (see CONTEXT.md canonical_refs: "parse-UX signals... computed in the service, not the Protocol"). However, the stub must communicate "I recognized a constraint shape but it was incomplete" through the `list[OverrideCall]` Protocol boundary.

**Recommended approach:** emit a reserved `OverrideCall(tool="_clarification", args={"question": "..."})`. The service filters these before processing, extracts the question, and routes to `clarification_needed`. This keeps the Protocol return type (`list[OverrideCall]`) unchanged while allowing the stub to signal partial matches.

```python
# In stub._match_fragment(fragment):
m = _PARTIAL_WORKERS_RE.search(fragment)
if m:
    task_token = m.group(1)
    return OverrideCall(
        id=f"clr_{uuid.uuid4().hex[:8]}",
        tool="_clarification",
        args={"question": f"How many workers minimum on '{task_token}'?"},
    )
```

The service `parse_and_store` checks: `if call.tool == "_clarification": set clarification_needed = call.args["question"]; continue`.

**Step 4 — Day-name → day-number mapping for `lock_worker_shift`:**

The stub must convert "Monday"/"Tuesday"/... to a 0-indexed integer matching `int(sv.start_h // 24)` in the builder. Include a `_DAY_MAP = {"monday": 0, "tuesday": 1, ..., "sunday": 6}` lookup in the stub.

**Multi-tool test case (from CONTEXT.md D-02 example):**
- Input: `"at least 2 on Pick and more people on packing"`
- Fragment 1: `"at least 2 on Pick"` → `_MIN_WORKERS_RE` matches → `set_min_workers_per_task(task_id="Pick", n=2)`
- Fragment 2: `"more people on packing"` → `_PARTIAL_WORKERS_RE` matches → `_clarification` OverrideCall
- Service result: `applied=[{set_min_workers_per_task...}]`, `clarification_needed="How many workers minimum on 'packing'?"`

---

### OQ-6: API/schema changes

**Current router (api/routers/constraints.py L22–48):** [VERIFIED: live source read]

```python
@router.post("", response_model=ConstraintParseResponse, ...)
def parse_constraint(body, conn, provider, settings):
    try:
        return constraint_service.parse_and_store(...)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

**Current schema (api/schemas.py L34–43):** [VERIFIED: live source read]

```python
class ConstraintParseRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)

class ConstraintParseResponse(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str
```

**Required schema changes — replace `ConstraintParseResponse` and add support models:**

```python
class AppliedConstraint(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str

class RejectedConstraint(BaseModel):
    tool: str
    error: str

class ConstraintParseResponse(BaseModel):
    applied: list[AppliedConstraint]
    rejected: list[RejectedConstraint]
    clarification_needed: str | None
    no_constraint_found: bool
```

**Required router changes:**
- Remove the `except ValueError` catch-and-400 block (per-call errors no longer raise from the service).
- The `except LookupError` block (404 for unknown scenario) stays unchanged — D-01 says "404 is still returned only for an unknown scenario_id".
- The service now returns the structured body dict directly; router passes it through as-is.

```python
@router.post("", response_model=ConstraintParseResponse,
             responses={404: {"description": "Scenario not found"}})
def parse_constraint(body, conn, provider, settings):
    try:
        return constraint_service.parse_and_store(...)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # No longer catches ValueError — per-call errors are in rejected[]
```

**Backward-compatibility note:** Existing tests in `test_constraints_api.py` assert the old response shape (`id`, `tool`, `args`, `parsed_constraint` as top-level fields). These tests will need to be updated to use the new shape (`applied[0].id`, etc.) or replaced by the new TEST-03 suite. The Phase-1 happy-path tests should be updated, not deleted — they still exercise valid end-to-end behaviour.

---

### OQ-7: Validation Architecture (Nyquist)

See dedicated section below.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bounded slack var for infeasibility prevention | Custom "guard" hard constraints | `m.NewIntVar(0, upper_bound, name)` + `m.Add(supply + slack >= threshold)` pattern | Already proven in Phase 1; bounded IntVar is the canonical CP-SAT soft-penalty pattern |
| Demand scaling at the problem level | Mutating SchedulingProblem.demand | Scale in `_aggregate_demand()` before per-hour accumulation | Keeps domain object immutable; unmet slack absorbs shortfall |
| Override ID stability across re-submissions | Random UUID | `override_id(tool, args)` from `domain/overrides.py` | Content-hash already stable (D-05); used in Phase 1 |
| Test isolation from live CP-SAT | Real engine in unit tests | `StubEngine` + `app.dependency_overrides[get_engine]` | Established pattern in `test_api.py` and `test_constraints_api.py` |
| Test isolation from live LLM | Real provider in CI | `app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()` | Established pattern in `test_constraints_api.py` L77–79 |

**Key insight:** Every new builder pattern (bounded slack, supply sum, bool var for presence) is already in the codebase. Phase 2 does not need to invent a new CP-SAT idiom; it generalises the existing `set_min_workers_per_task` pattern to three new variable shapes.

---

## Common Pitfalls

### Pitfall 1: Mutating SchedulingProblem.demand for scale_demand

**What goes wrong:** Code modifies `b.amount` in `problem.demand` in-place or creates a new `SchedulingProblem` copy, breaking the immutable-domain rule and potentially re-using a scaled problem in subsequent solve calls.
**Why it happens:** The natural impulse is to scale at the input layer (adapter or problem object).
**How to avoid:** Apply the scale factor exclusively inside `_aggregate_demand()` via the `scale` dict, multiplying `b.amount * f` during accumulation without touching `self.p.demand`.
**Warning signs:** Any reference to `self.p.demand` being modified, or a new `SchedulingProblem` being constructed in the builder.

### Pitfall 2: lock_worker_shift when no shift candidates exist for that (member, day)

**What goes wrong:** If no shift is generated for a member on the locked day (e.g. member has no availability window on that day), `day_shifts` is empty and `sum([]) + absent >= 1` forces `absent = 1` always. The penalty fires but the model is still feasible. This is correct behaviour, but it can confuse debugging.
**Why it happens:** Shift candidates are generated only for windows that exist; a day without a window produces no candidates.
**How to avoid:** The bounded-slack pattern handles this correctly by design. Document in a comment that `absent = 1` when no candidates exist is expected (the day is uncoverable).
**Warning signs:** Treating an empty `day_shifts` list as a no-op (skipping the penalty term entirely), which would mean the override is silently ignored.

### Pitfall 3: set_max_hours overflow var bounded too large

**What goes wrong:** `over = NewIntVar(0, MAX_INT, ...)` is unbounded, giving the solver room to assign unlimited hours and absorb it into the penalty rather than respecting the soft cap.
**Why it happens:** Forgetting to bound the overflow var by `(hard_cap - max_hours) * VOL_SCALE`.
**How to avoid:** Compute `hard_cap_scaled` from `self.p.max_hours_per_week` (or the default) and set `upper = max(0, hard_cap_scaled - scaled_max)`. The hard cap constraint at L269–270 already prevents hours exceeding `hard_cap`, so the actual overflow is bounded.
**Warning signs:** `NewIntVar(0, 999999, ...)` without deriving the bound from the actual caps.

### Pitfall 4: Partial-apply persisting rejected entries

**What goes wrong:** The service writes all `resolved_calls` to the override store, including ones that should be rejected, if the validation step is not properly gated.
**Why it happens:** The Phase-1 logic validates-then-appends in a single block; the Phase-2 rework must explicitly gate persistence to `applied[]` only.
**How to avoid:** Only pass `applied` OverrideCalls to `repo.update_overrides`. Rejected and clarification entries are response-only, never persisted.
**Warning signs:** Any code that builds the `existing[id]` dict before the per-call validation result is checked.

### Pitfall 5: Breaking existing test_constraints_api.py assertions

**What goes wrong:** Phase-1 tests assert `r.json()["id"]`, `r.json()["tool"]` etc. as top-level fields. The new response shape nests these under `applied[0]`.
**Why it happens:** The response model change is breaking.
**How to avoid:** Update the Phase-1 happy-path assertions to use `r.json()["applied"][0]["id"]` etc. alongside adding the new TEST-03 cases. Do not delete the Phase-1 tests.
**Warning signs:** Leaving Phase-1 assertions as-is while changing the response model — they will fail with `KeyError`.

### Pitfall 6: `no_constraint_found` vs `clarification_needed` collision

**What goes wrong:** Both set to `True` / non-null simultaneously when provider returns `[]` and a `_clarification` signal was also emitted (impossible by design but easy to code carelessly).
**Why it happens:** Checking `len(calls) == 0` for `no_constraint_found` without accounting for `_clarification` signals already extracted.
**How to avoid:** `no_constraint_found = True` only when provider returns `[]` AND after filtering, no `_clarification` signals were in the list. Set it at the end, not the start of processing.

---

## Code Examples

### scale_demand — application in `_aggregate_demand` (before per-hour accumulation)

```python
# Source: builder.py _aggregate_demand pattern; scale applied at point-of-use
def _aggregate_demand(self):
    scale = {ov.args["task_id"]: float(ov.args["factor"])
             for ov in self.overrides if ov.tool == "scale_demand"}
    vol = defaultdict(lambda: defaultdict(float))
    hc = defaultdict(lambda: defaultdict(float))
    is_ind = {}
    for b in self.p.demand:
        f = scale.get(b.task_id, 1.0)
        # ... existing accumulation with b.amount * f ...
```

### lock_worker_shift — bounded absence bool pattern

```python
# Source: generalisation of minw_short pattern (builder.py L343-345)
mid = ov.args["member_id"]
day = int(ov.args["day"])
day_shifts = [sv for sv in self.shift_vars
              if sv.member.contact_id == mid and int(sv.start_h // 24) == day]
absent = self.m.NewBoolVar(f"lock_absent_{mid[:6]}_{day}")
self.m.Add(sum(sv.var for sv in day_shifts) + absent >= 1)
lock_terms.append(absent)
```

### exclude_worker_from_task — direct penalty on assignment vars

```python
# Source: coverage_terms / task_vars pattern (builder.py L211-213)
mid = ov.args["member_id"]
tid = ov.args["task_id"]
excl_vars = [tv.var for tv in self.task_vars
             if tv.shift.member.contact_id == mid and tv.task_id == tid]
excl_terms.extend(excl_vars)
# penalty: C.EXCLUDE_WORKER_PENALTY * sum(excl_terms) added to round2_cost
```

### set_max_hours — bounded overflow above soft cap

```python
# Source: hard-cap expression at builder.py L269-270; soft version below
mid = ov.args["member_id"]
max_h = float(ov.args["max_hours"])
member_svs = [sv for sv in self.shift_vars if sv.member.contact_id == mid]
if not member_svs:
    continue
emp_type = member_svs[0].member.emp_type
hard_cap = self.p.max_hours_per_week.get(emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK)
scaled_max = int(round(max_h * C.VOL_SCALE))
hard_cap_scaled = int(round(hard_cap * C.VOL_SCALE))
over = self.m.NewIntVar(0, max(0, hard_cap_scaled - scaled_max), f"maxh_over_{mid[:6]}")
total = sum(int(round(sv.eff_h * C.VOL_SCALE)) * sv.var for sv in member_svs)
self.m.Add(total <= scaled_max + over)
maxh_terms.append(over)
```

### Degeneracy detection — post-solve in engine.py

```python
# Source: engine.py L90-93 (after coverage_by_function is built)
warnings: list[str] = []
for fn, stat in coverage_by_function.items():
    if stat.required_h > 1e-9 and stat.served_h <= 1e-9:
        warnings.append(
            f"Degenerate solve: task family '{fn}' has {stat.required_h:.1f}h "
            f"required but zero assigned supply."
        )
return SolveResult(
    status=lex.status, schedule=schedule,
    metrics=metrics, stats=stats, warnings=warnings,
)
```

### Partial-apply loop skeleton in `parse_and_store`

```python
# Source: constraint_service.py parse_and_store rework (new structure)
applied: list[dict] = []
rejected: list[dict] = []
clarification_needed: str | None = None

# Extract _clarification signals from provider output before processing
tool_calls = []
for call in calls:
    if call.tool == "_clarification":
        if clarification_needed is None:
            clarification_needed = call.args["question"]
    else:
        tool_calls.append(call)

no_constraint_found = (not tool_calls and clarification_needed is None)

for call in tool_calls:
    try:
        resolved_args, parsed_constraint = _validate_and_resolve(call, problem)
        new_id = override_id(call.tool, resolved_args)
        applied.append({"id": new_id, "tool": call.tool,
                        "args": resolved_args, "parsed_constraint": parsed_constraint})
    except _ClarificationNeeded as exc:
        if clarification_needed is None:
            clarification_needed = str(exc)
    except _ValidationError as exc:
        rejected.append({"tool": call.tool, "error": str(exc)})

# Persist ONLY applied entries
if applied:
    existing = json.loads(scenario["overrides"] or "{}")
    for entry in applied:
        existing[entry["id"]] = {"tool": entry["tool"], "args": entry["args"]}
    repo.update_overrides(scenario_id, json.dumps(existing))
    conn.commit()

return {
    "applied": applied,
    "rejected": rejected,
    "clarification_needed": clarification_needed,
    "no_constraint_found": no_constraint_found,
}
```

---

## State of the Art

| Old Approach | Current Approach (Phase 2) | Why Changed |
|--------------|---------------------------|-------------|
| Single tool, raise on first error → 400 | Partial-apply → 200 structured body | D-01: bad reference must not discard valid constraints in same sentence |
| `ConstraintParseResponse` with top-level `id/tool/args/parsed_constraint` | Nested `applied[]`, `rejected[]`, `clarification_needed`, `no_constraint_found` | Response must carry multi-tool outcomes simultaneously |
| `no_constraint_found` → 400 ValueError | `no_constraint_found: true` in 200 body | UX signal, not an error |
| Ambiguous match → 400 ValueError | `clarification_needed` in 200 body | User needs to rephrase, not get an error |
| Only `set_min_workers_per_task` in builder | All five tools | Phase 2 scope |
| No `warnings` on `SolveResult` | `warnings: list[str]` field | Degenerate-solve detection (ENG-05) |

---

## Validation Architecture

`workflow.nyquist_validation = true` (config.json L25). This section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (dev dependency in `backend/pyproject.toml`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && pytest tests/test_constraints_api.py -x -q` |
| Full suite command | `cd backend && pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NLC-02 | Multi-tool text yields multiple applied[] entries | API-level | `pytest tests/test_constraints_api.py::test_multi_tool_applied -x` | ❌ Wave 0 |
| NLC-03 | Non-constraint text → `no_constraint_found: true`, 200 | API-level | `pytest tests/test_constraints_api.py::test_no_constraint_found -x` | ❌ Wave 0 (replaces existing 400 test) |
| NLC-04 | Each applied entry has non-empty `parsed_constraint` string | API-level | `pytest tests/test_constraints_api.py::test_parsed_constraint_echoed -x` | ❌ Wave 0 |
| NLC-05 | Ambiguous task token → `clarification_needed` non-null, 200 | API-level | `pytest tests/test_constraints_api.py::test_ambiguous_task_clarification -x` | ❌ Wave 0 (replaces existing 400 test) |
| NLC-05 | Partial phrasing (no number) → `clarification_needed` non-null | API-level | `pytest tests/test_constraints_api.py::test_partial_phrasing_clarification -x` | ❌ Wave 0 |
| VAL-01 | scale_demand factor ≤ 0 → rejected[], 200 | API-level | `pytest tests/test_constraints_api.py::test_scale_demand_bad_factor -x` | ❌ Wave 0 |
| VAL-01 | set_max_hours = 0 → rejected[], 200 | API-level | `pytest tests/test_constraints_api.py::test_max_hours_zero_rejected -x` | ❌ Wave 0 |
| VAL-02 | Unknown task ref → `rejected[]` entry naming it, 200 | API-level | `pytest tests/test_constraints_api.py::test_unknown_task_rejected -x` | ❌ Wave 0 |
| VAL-02 | Unknown member ref → `rejected[]` entry naming it, 200 | API-level | `pytest tests/test_constraints_api.py::test_unknown_member_rejected -x` | ❌ Wave 0 |
| VAL-03 | Rejection error names the offending reference and lists valid options | Unit | `pytest tests/test_constraints_api.py::test_rejection_error_names_ref -x` | ❌ Wave 0 |
| ENG-05 | solve where coverage collapses → `warnings[]` in result JSON | Unit (engine-level) | `pytest tests/test_engine_degenerate.py -x` | ❌ Wave 0 |
| TEST-03 (criterion 5) | Mixed multi-tool: one valid task + one unknown member → applied[]+rejected[] in same 200 | API-level | `pytest tests/test_constraints_api.py::test_mixed_valid_invalid_multi_tool -x` | ❌ Wave 0 |
| TEST-03 (criterion 5) | Mixed multi-tool: one valid + one out-of-bounds → applied[]+rejected[] | API-level | `pytest tests/test_constraints_api.py::test_mixed_valid_oob_multi_tool -x` | ❌ Wave 0 |

### Template: StubEngine + dependency_overrides (from test_constraints_api.py)

The existing `client` fixture (test_constraints_api.py L67–82) is the canonical template for Phase-2 tests:

```python
# Source: backend/tests/test_constraints_api.py L67-82 — exact pattern to reuse

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)
    from api.deps import get_engine, get_llm_provider
    from api.main import app
    from llm.stub import StubLLMProvider

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

For ENG-05 (degeneracy detection), the test should use a `SolveResult` with `coverage_by_function` showing 100% unmet for one function, which the `warnings` field should reflect.

### Sampling Rate

- **Per task commit:** `cd backend && pytest tests/test_constraints_api.py -x -q`
- **Per wave merge:** `cd backend && pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_constraints_api.py` — update Phase-1 happy-path assertions for new `applied[0]` shape; add all TEST-03 cases listed in the table above
- [ ] `tests/test_engine_degenerate.py` — new file; unit-test degeneracy detection via `SolveResult.warnings` (does not need a full CP-SAT solve — can call `CpSatEngine` with a tiny fixture or check the detection logic directly in a unit test)

*(Phase-1 test infrastructure covers the rest: `conftest.py` sets sys.path, `_DATA_DIR` resolves the real fixture, `StubEngine` + `StubLLMProvider` injection is proven.)*

---

## Security Domain

`security_enforcement = true` (config.json L46). ASVS level 1 (config.json L47).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth paths added |
| V3 Session Management | No | No session state |
| V4 Access Control | No | No new access control paths |
| V5 Input Validation | Yes | Pydantic `Field(min_length=1, max_length=2000)` on `text`; per-tool arg bounds validation in service |
| V6 Cryptography | No | No new crypto; `override_id` uses SHA-256 for content-hash (stdlib) |

### Known Threat Patterns for Python/FastAPI backend

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via NL constraint text | Tampering | Stub is regex-only; real Claude (Phase 4) needs system-prompt hardening. Phase 2 is stub-only — no live LLM call, no injection surface. |
| Reference injection (hallucinated task/member IDs) | Tampering | `_resolve_task`/`_resolve_member` validate against real scenario IDs loaded from the fixture; unknown IDs go to `rejected[]`, never reach the solver. |
| Integer overflow in penalty vars | Tampering | `NewIntVar(0, upper_bound, ...)` strictly bounded; `upper_bound` derived from hard-cap constants, not user input. |
| SQLite injection via override JSON | Tampering | `repo.update_overrides` uses parameterised query (existing pattern in `store/repositories.py`); override content is validated before reaching the store. |
| Out-of-bounds day index | Tampering | `day` arg for `lock_worker_shift` validated against `0..int(problem.horizon_h // 24) - 1` in service before reaching the builder. |

---

## Environment Availability

No new external tools required. All tools confirmed present from Phase 1:

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Python 3.10–3.12 | All backend | ✓ | Phase 1 ran successfully |
| uv | Dependency management | ✓ | `uv.lock` present |
| ortools 9.11.4210 | CP-SAT builder | ✓ | Pinned; Phase 1 ran CP-SAT solves |
| pytest | TEST-03 | ✓ | Phase 1 test suite passes |
| SQLite (stdlib) | Override persistence | ✓ | In use since Phase 0 |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Day-of-week numbering in `lock_worker_shift` matches `int(sv.start_h // 24)` 0-indexed scheme | OQ-2 builder extension | If the fixture uses a different day numbering, the penalty targets the wrong day. The stub's day-name→int mapping must be verified against a real fixture solve. |
| A2 | `problem.members` is accessible from within `parse_and_store` via the loaded SchedulingProblem (same as `problem.tasks`) | OQ-4 `_resolve_member` | `SchedulingProblem.members: List[Member]` at domain/problem.py L14 — verified from source. Risk: LOW. |
| A3 | Existing tests in `test_constraints_api.py` that assert `r.json()["id"]` (top-level) will fail after the schema change — they must be updated | OQ-6 backward compat | If tests are not updated before the router/schema change, CI will report failures that look like regressions. |
| A4 | The `_clarification` sentinel tool name (for stub-to-service signalling) does not conflict with any future real Claude tool name | OQ-5 stub signals | Use a leading underscore (`_clarification`) as a private sentinel; the real Claude provider (Phase 4) will never emit this name. |

**Verified claims:** All code quotations in this document are from live source files read in this session. No claim about existing code relies on training data.

---

## Sources

### Primary (HIGH confidence — verified from live source)

- `backend/engine/cpsat/builder.py` — `_aggregate_demand` (L111–129), `build` (L173–237), `_add_coverage_constraints` (L280–302), `_build_objectives` (L305–351) — exact current code quoted
- `backend/services/constraint_service.py` — `_resolve_task` (L31–64), `parse_and_store` (L67–146) — exact current code quoted
- `backend/llm/stub.py` — `StubLLMProvider.parse_constraints` (L58–77), `_MIN_WORKERS_RE` (L30–34) — full stub read
- `backend/api/routers/constraints.py` — full router read
- `backend/api/schemas.py` — full schema read
- `backend/domain/result.py` — `SolveResult` (L48–52) — confirmed no `warnings` field
- `backend/engine/cpsat/engine.py` — coverage computation (L60–98), result construction (L101–115)
- `backend/config/constants.py` — `MIN_WORKERS_PENALTY = 100_000` (L41), scaling constants (L29–32)
- `backend/tests/test_constraints_api.py` — `StubEngine`, `client` fixture, all Phase-1 test cases
- `backend/domain/types.py` — `Member`, `Task`, `DemandBand`, `Window` field shapes
- `backend/domain/problem.py` — `SchedulingProblem.members`, `tasks`, `demand`, `task()` method
- `backend/services/run_service.py` — `_execute` override-threading path (L85–95)
- `backend/services/serialize.py` — `serialize_result` (L21–44) — confirmed `warnings` not yet serialized

### Secondary (MEDIUM confidence)

- Phase 2 CONTEXT.md decisions D-01…D-13 — authoritative user decisions from `/gsd-discuss-phase`
- Phase 1 CONTEXT.md decisions D-01…D-10 — locked prior-phase decisions this phase extends

---

## Metadata

**Confidence breakdown:**
- Code archaeology (all OQ answers): HIGH — all findings from direct source reads with line references
- Architecture patterns: HIGH — extend-not-replace; all insertion points identified in live code
- Penalty constant recommendations: MEDIUM — pragmatic placeholders consistent with `MIN_WORKERS_PENALTY = 100_000` precedent; empirical calibration deferred to Phase 4 (ENG-04)
- Stub regex patterns: MEDIUM — deterministic and test-friendly by design; exact phrases tuned during test writing

**Research date:** 2026-06-29
**Valid until:** 2026-07-29 (stable codebase; no external dependencies)
