# Phase 2: Full 5-Tool Set + Safe Validation — Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 9 (modified) + 1 (new test file)
**Analogs found:** 9 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/llm/stub.py` | provider | transform | `backend/llm/stub.py` (Phase-1 version) | exact — extend in place |
| `backend/services/constraint_service.py` | service | request-response | `backend/services/constraint_service.py` (Phase-1 version) | exact — rework in place |
| `backend/api/routers/constraints.py` | router | request-response | `backend/api/routers/constraints.py` (Phase-1 version) | exact — minor edit |
| `backend/api/schemas.py` | schema | request-response | `backend/api/schemas.py` (Phase-1 `ConstraintParseResponse`) | exact — replace schema class |
| `backend/engine/cpsat/builder.py` | engine | CRUD/transform | `backend/engine/cpsat/builder.py` `_build_objectives` L325–351 | exact — extend loop |
| `backend/domain/result.py` | model | — | `backend/domain/result.py` `SolveResult` L48–52 | exact — add field |
| `backend/config/constants.py` | config | — | `backend/config/constants.py` `MIN_WORKERS_PENALTY` L41 | exact — add constants |
| `backend/engine/cpsat/engine.py` | engine | request-response | `backend/engine/cpsat/engine.py` L90–115 (metrics loop) | exact — extend result construction |
| `backend/services/serialize.py` | service | transform | `backend/services/serialize.py` (existing `serialize_result`) | role-match |
| `backend/tests/test_constraints_api.py` | test | request-response | `backend/tests/test_constraints_api.py` (Phase-1 tests) | exact — extend + update |
| `backend/tests/test_engine_degenerate.py` | test | request-response | `backend/tests/test_constraints_api.py` `StubEngine` pattern | role-match (new file) |

---

## Pattern Assignments

### `backend/llm/stub.py` (provider, transform)

**Analog:** `backend/llm/stub.py` lines 1–78 (Phase-1 full file, read above)

**Imports pattern** (lines 17–23):
```python
from __future__ import annotations
import re
import uuid
from domain.overrides import OverrideCall, override_id
```

**Core pattern — single regex + `_to_override_call` + `StubLLMProvider.parse_constraints`** (lines 37–77):

The Phase-1 stub has one regex, one `_to_override_call` translator, and a single-return `parse_constraints`. Phase 2 extends with:

1. Add `_SPLIT_RE` conjunction splitter and `_split_fragments(text)` helper.
2. Replace the single `_MIN_WORKERS_RE` check with a regex dispatch table. Add four new compiled regexes and one partial-match regex (for `_clarification` signalling). All use `re.IGNORECASE`.
3. Replace `parse_constraints` body: split → iterate fragments → match against each regex in order → build `tool_use` block per match → collect `OverrideCall` list.
4. Partial match (e.g. "more people on Pick") → emit `OverrideCall(id=f"clr_{uuid.uuid4().hex[:8]}", tool="_clarification", args={"question": "..."})` — sentinel that the service filters before processing.
5. Day-name → int mapping `_DAY_MAP = {"monday": 0, ..., "sunday": 6}` for `lock_worker_shift`.

**Existing `_to_override_call` helper** (lines 37–50) — copy unchanged; new tool_use blocks follow the same `{type, id, name, input}` dict shape.

**Method signature** — unchanged:
```python
def parse_constraints(self, text: str) -> list[OverrideCall]:
```

---

### `backend/services/constraint_service.py` (service, request-response)

**Analog:** `backend/services/constraint_service.py` lines 1–146 (full file, read above)

**Imports pattern** (lines 17–28) — add `from typing import NamedTuple`:
```python
from __future__ import annotations
import json, os, sqlite3
from typing import NamedTuple
from domain.overrides import OverrideCall, override_id
from ingest.input_adapter import load_problem
from llm.base import LLMProvider
from settings import default_settings
from store.repositories import ScenarioRepo
```

**`_resolve_task` pattern** (lines 31–64) — the template for `_resolve_member`:

Current signature raises `ValueError` on zero/multi-match. Phase 2 reworks it to return `_ResolveResult` (a `NamedTuple`) instead of raising:

```python
class _ResolveResult(NamedTuple):
    resolved_id: str | None
    error: str | None           # zero-match → rejected[]
    clarification: str | None   # multi-match → clarification_needed
```

Rewrite `_resolve_task` to return `_ResolveResult`. Copy the substring-match logic from lines 44–63 exactly; replace the two `raise ValueError(...)` calls with `return _ResolveResult(resolved_id=None, error=..., clarification=None)` and `return _ResolveResult(resolved_id=None, error=None, clarification=...)`.

**`_resolve_member` pattern** — mirrors `_resolve_task` with `problem.members`, matching on `m.contact_id` and `m.name` instead of `t.task_id` and `t.name`. Return type is the same `_ResolveResult`.

**`parse_and_store` core pattern** (lines 67–146) — rework:

- Keep the LookupError guard (lines 84–87) and `load_problem` call (lines 94–98) unchanged.
- Replace the monolithic `for call in calls` loop (lines 101–123) with a partial-apply loop:

```python
# Partition _clarification signals before processing real tool calls
applied: list[dict] = []
rejected: list[dict] = []
clarification_needed: str | None = None

tool_calls = []
for call in calls:
    if call.tool == "_clarification":
        if clarification_needed is None:
            clarification_needed = call.args["question"]
    else:
        tool_calls.append(call)

no_constraint_found = (not tool_calls and clarification_needed is None)

for call in tool_calls:
    # per-tool resolve + validate → bucket into applied / rejected / clarification
    ...

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

**Per-tool `parsed_constraint` wording** — copy the Phase-1 pattern (line 138) and extend naturally:
- `set_min_workers_per_task`: `f"At least {n} workers on {task_label} (every demanded hour)"`
- `scale_demand`: `f"Scale demand for {task_label} by {factor}x"`
- `lock_worker_shift`: `f"Keep {member_name} scheduled on day {day}"`
- `exclude_worker_from_task`: `f"Exclude {member_name} from {task_label}"`
- `set_max_hours`: `f"Cap {member_name} at {max_hours} hours per week (soft)"`

**Return type** (lines 140–146) — replace the flat dict with the structured body. The service no longer raises `ValueError` for per-call failures.

---

### `backend/api/routers/constraints.py` (router, request-response)

**Analog:** `backend/api/routers/constraints.py` lines 1–49 (full file, read above)

**Imports** (lines 1–18) — unchanged.

**Router decorator** — update `responses` annotation; remove `400` entry (per-call errors go to `rejected[]`):
```python
@router.post(
    "",
    response_model=ConstraintParseResponse,
    responses={404: {"description": "Scenario not found"}},
)
```

**Handler body** — remove the `except ValueError` block; keep only `except LookupError`:
```python
def parse_constraint(body, conn, provider, settings) -> dict:
    try:
        return constraint_service.parse_and_store(...)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # ValueError no longer raised by service — per-call failures go to rejected[]
```

---

### `backend/api/schemas.py` (schema, request-response)

**Analog:** `backend/api/schemas.py` lines 34–43 (existing `ConstraintParseResponse` and `ConstraintParseRequest`)

**Imports** (lines 1–6) — unchanged.

**`ConstraintParseRequest`** (lines 34–36) — unchanged.

**Replace `ConstraintParseResponse`** and add two supporting models:
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

Copy the existing `BaseModel` + `Field` import pattern from `ScenarioCreate` (lines 9–12); the new models need no `Field` constraints.

---

### `backend/engine/cpsat/builder.py` — `_aggregate_demand` + `_build_objectives` (engine, transform)

**Analog:** `backend/engine/cpsat/builder.py`
- `_aggregate_demand`: lines 111–129 (read above)
- `_build_objectives`: lines 305–351 (read above)

**`_aggregate_demand` extension** — add scale-factor dict before the demand loop:
```python
def _aggregate_demand(self):
    # scale_demand overrides: per-task factor applied here (D-10).
    # SchedulingProblem stays immutable; unmet slack absorbs resulting shortfall.
    scale: dict[str, float] = {
        ov.args["task_id"]: float(ov.args["factor"])
        for ov in self.overrides if ov.tool == "scale_demand"
    }
    vol: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    hc: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    is_ind: Dict[str, bool] = {}
    for b in self.p.demand:
        f = scale.get(b.task_id, 1.0)          # factor=1.0 when no override
        h0, h1 = int(math.floor(b.start_h)), int(math.ceil(b.end_h))
        if b.family == DemandFamily.INDIRECT:
            ...
                hc[b.task_id][h] += b.amount * f   # scaled
        else:
            ...
                vol[b.task_id][h] += b.amount * f * ov / dur  # scaled
    return vol, hc, is_ind
```

**`_build_objectives` extension** — replace the single `if ov.tool != "set_min_workers_per_task": continue` guard with a full elif chain. Copy the existing shortfall-slack pattern (lines 330–345) as the template for three new shapes:

```python
shortfall_terms = []   # set_min_workers_per_task (existing — lines 330-345, copy unchanged)
lock_terms = []        # lock_worker_shift (new)
excl_terms = []        # exclude_worker_from_task (new)
maxh_terms = []        # set_max_hours (new)

for ov in self.overrides:
    if ov.tool == "set_min_workers_per_task":
        # ... existing lines 334–345 unchanged ...
    elif ov.tool == "lock_worker_shift":
        mid = ov.args["member_id"]
        day = int(ov.args["day"])
        day_shifts = [sv for sv in self.shift_vars
                      if sv.member.contact_id == mid and int(sv.start_h // 24) == day]
        absent = self.m.NewBoolVar(f"lock_absent_{mid[:6]}_{day}")
        self.m.Add(sum(sv.var for sv in day_shifts) + absent >= 1)
        # absent=1 when no shift candidates for that day — penalty fires but
        # model stays feasible (same bounded-slack guarantee as shortfall terms)
        lock_terms.append(absent)
    elif ov.tool == "exclude_worker_from_task":
        mid = ov.args["member_id"]
        tid = ov.args["task_id"]
        excl_vars = [tv.var for tv in self.task_vars
                     if tv.shift.member.contact_id == mid and tv.task_id == tid]
        excl_terms.extend(excl_vars)
    elif ov.tool == "set_max_hours":
        mid = ov.args["member_id"]
        max_h = float(ov.args["max_hours"])
        member_svs = [sv for sv in self.shift_vars if sv.member.contact_id == mid]
        if not member_svs:
            continue
        emp_type = member_svs[0].member.emp_type
        hard_cap = self.p.max_hours_per_week.get(emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK)
        scaled_max = int(round(max_h * C.VOL_SCALE))
        hard_cap_scaled = int(round(hard_cap * C.VOL_SCALE))
        over = self.m.NewIntVar(
            0, max(0, hard_cap_scaled - scaled_max), f"maxh_over_{mid[:6]}"
        )
        total = sum(int(round(sv.eff_h * C.VOL_SCALE)) * sv.var for sv in member_svs)
        self.m.Add(total <= scaled_max + over)
        maxh_terms.append(over)
    # scale_demand handled in _aggregate_demand, not here

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

**Builder attributes confirmed available** (from `__init__` and `build()`):
- `self.shift_vars: List[ShiftVar]` — each has `.member`, `.start_h`, `.end_h`, `.eff_h`, `.var`
- `self.task_vars: List[TaskVar]` — each has `.var`, `.shift` (ShiftVar), `.task_id`
- `self.coverage_terms: Dict[(task_id, h), List[(var, coeff)]]`
- `self.vol_demand`, `self.hc_demand` — set at `build()` line 176
- `self.overrides: list[OverrideCall]` — set at `__init__` line 95
- `self.p.max_hours_per_week` — `SchedulingProblem` field for hard caps

---

### `backend/domain/result.py` (model)

**Analog:** `backend/domain/result.py` lines 1–52 (full file, read above)

**Import pattern** (lines 1–6):
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
```

**`SolveResult` extension** — add `warnings` field with `field(default_factory=list)` so existing call sites that do not pass `warnings` continue to work:

Current (lines 48–52):
```python
@dataclass
class SolveResult:
    status: str
    schedule: List[ScheduleRow]
    metrics: SummaryMetrics
    stats: SolverStats
```

Add after `stats`:
```python
    warnings: List[str] = field(default_factory=list)
```

Copy `field(default_factory=list)` usage pattern from `SummaryMetrics` (lines 30–36) — same module, same idiom.

---

### `backend/config/constants.py` (config)

**Analog:** `backend/config/constants.py` lines 34–41 (existing `MIN_WORKERS_PENALTY` block, read above)

**Pattern** — copy the three-line block (constant + docstring comment) for each new penalty:

```python
# Penalty for lock_worker_shift: soft round-2 penalty if member has zero shifts
# on the locked day. Same order of magnitude as MIN_WORKERS_PENALTY.
# Empirical calibration deferred to Phase 4 (ENG-04).
LOCK_SHIFT_PENALTY: int = 100_000

# Penalty per task-var assignment where excluded member produces excluded task.
# Assignment vars are booleans; penalty fires once per assigned slot (not per hour).
EXCLUDE_WORKER_PENALTY: int = 50_000

# Penalty per VOL_SCALE unit of hours over soft max_hours cap.
# Actual penalty per hour over limit = MAX_HOURS_PENALTY / VOL_SCALE = 1_000.
# Layered atop the existing HARD weekly cap (cannot exceed it).
MAX_HOURS_PENALTY: int = 100_000
```

---

### `backend/engine/cpsat/engine.py` (engine, request-response) — degeneracy detection

**Analog:** `backend/engine/cpsat/engine.py` lines 60–115 (read above) — the metrics computation block and `SolveResult` construction at line 115

**Pattern** — after `coverage_by_function` is assembled (after line 93) and before `SolveResult(...)` construction (line 115), insert:

```python
# ENG-05: Degenerate-solve detection. Detection-only — never alters status.
warnings: list[str] = []
for fn, stat in coverage_by_function.items():
    if stat.required_h > 1e-9 and stat.served_h <= 1e-9:
        warnings.append(
            f"Degenerate solve: task family '{fn}' has {stat.required_h:.1f}h "
            f"required but zero assigned supply."
        )
```

Update the `return SolveResult(...)` at line 115 to pass `warnings=warnings`.

**Available references** at that point in the engine: `coverage_by_function` (dict built lines 90–93), `CoverageStat.required_h` and `CoverageStat.served_h` attributes (from `domain/result.py`).

---

### `backend/services/serialize.py` (service, transform)

**Analog:** `backend/services/serialize.py` `serialize_result` — existing dict return

**Pattern** — add `"warnings": r.warnings` to the top-level return dict, parallel to `"status"`, `"metrics"`, `"schedule"`, `"stats"`. The `runs.result_json` column stores this via `json.dumps` in `run_service._execute`. No schema change needed on `GET /runs/{id}/result` (it returns raw JSON).

---

### `backend/tests/test_constraints_api.py` (test, request-response)

**Analog:** `backend/tests/test_constraints_api.py` lines 1–398 (full file, read above)

**`client` fixture pattern** (lines 67–82) — copy unchanged for all Phase-2 tests:
```python
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

**`StubEngine.solve` return pattern** (lines 37–53) — copy for new test file; add `warnings=[]` once `SolveResult` has the field (backward-compatible with `default_factory=list`).

**Phase-1 assertion updates** — existing assertions like `r.json()["id"]`, `r.json()["tool"]` (lines 109–158) become `r.json()["applied"][0]["id"]`, `r.json()["applied"][0]["tool"]`. The `400` assertions for no-constraint, ambiguous task, unknown task, n<=0 (lines 204–225) become 200-with-structured-body assertions.

**New TEST-03 test structure** — follow the same `def test_xxx(client, scenario_id):` pattern:
```python
def test_multi_tool_applied(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick and cap Alice at 40 hours",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 2
    assert body["no_constraint_found"] is False

def test_mixed_valid_invalid_multi_tool(client, scenario_id):
    r = client.post("/constraints", json={
        "scenario_id": scenario_id,
        "text": "at least 2 on C Pick and exclude XYZ_NONEXISTENT from C Pick",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) == 1
    assert len(body["rejected"]) == 1
    assert "XYZ_NONEXISTENT" in body["rejected"][0]["error"]
```

---

### `backend/tests/test_engine_degenerate.py` (test — new file)

**Analog:** `backend/tests/test_constraints_api.py` `StubEngine` pattern (lines 37–53); no live CP-SAT needed

**Pattern** — unit-test the degeneracy detection logic directly. Two approaches:
1. Instantiate `CoverageStat` with `required_h > 0` and `served_h = 0`, then assert the warning string.
2. Use a minimal fixture where all supply is excluded, run through `CpSatEngine`, assert `result.warnings` is non-empty.

For Phase 2, approach (1) is simpler and avoids CP-SAT setup in a new test file:

```python
# test_engine_degenerate.py
from domain.result import CoverageStat, SolveResult, SummaryMetrics, SolverStats

def test_warnings_field_present_on_solve_result():
    r = SolveResult(
        status="OPTIMAL", schedule=[],
        metrics=SummaryMetrics(), stats=SolverStats(...),
    )
    assert r.warnings == []

def test_degeneracy_detection_warns_on_zero_supply():
    # The detection logic (engine.py post-solve) produces warnings when
    # stat.required_h > 0 and stat.served_h == 0.
    # Test the warning condition directly — no CP-SAT needed.
    coverage = {"Pick": CoverageStat(required_h=10.0, served_h=0.0)}
    warnings = []
    for fn, stat in coverage.items():
        if stat.required_h > 1e-9 and stat.served_h <= 1e-9:
            warnings.append(
                f"Degenerate solve: task family '{fn}' has {stat.required_h:.1f}h "
                f"required but zero assigned supply."
            )
    assert len(warnings) == 1
    assert "Pick" in warnings[0]
```

---

## Shared Patterns

### Bounded slack variable (infeasibility prevention)
**Source:** `backend/engine/cpsat/builder.py` lines 342–345
**Apply to:** All three new `_build_objectives` override terms
```python
short = self.m.NewIntVar(0, n, f"minw_short_{tid[:6]}_{h}")
self.m.Add(sum(bodies) + short >= n)
```
The upper bound on the `NewIntVar` is the key: it caps the slack so the optimizer cannot use an infinite penalty to satisfy the constraint without real assignments.

### Soft round-2 only
**Source:** `backend/engine/cpsat/builder.py` lines 325–329 (comment block)
**Apply to:** All four tools' penalty terms in `_build_objectives`

All override penalty terms go into `self.round2_cost` only — never `round1_unmet`, never a hard `Add` constraint with no slack. This is enforced by the comment and the structure of `_build_objectives`.

### LookupError → 404 (router error translation)
**Source:** `backend/api/routers/constraints.py` lines 45–46
**Apply to:** `constraints.py` router — unchanged, always keep
```python
except LookupError as exc:
    raise HTTPException(status_code=404, detail=str(exc))
```
Per-call validation failures go to `rejected[]`, not this handler.

### `dependency_overrides` test isolation
**Source:** `backend/tests/test_constraints_api.py` lines 67–82
**Apply to:** All Phase-2 test fixtures (`test_constraints_api.py` and `test_engine_degenerate.py`)

### `override_id` content hash
**Source:** `backend/domain/overrides.py` (imported in `constraint_service.py` line 24 and `stub.py` line 22)
**Apply to:** `parse_and_store` — call `override_id(tool, resolved_args)` with the resolved (not raw) args; idempotent re-submission guaranteed by D-05.

### `from __future__ import annotations`
**Source:** Every backend module
**Apply to:** All modified/new files

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All files have direct analogs in the existing Phase-1 codebase |

---

## Metadata

**Analog search scope:** `backend/llm/`, `backend/services/`, `backend/api/`, `backend/engine/cpsat/`, `backend/domain/`, `backend/config/`, `backend/tests/`
**Files read end-to-end:** `stub.py`, `constraint_service.py`, `constraints.py` (router), `schemas.py`, `result.py`, `constants.py`, `test_constraints_api.py`, `builder.py` (partial: L88–207, L305–351), `engine.py` (partial: L60–115)
**Pattern extraction date:** 2026-06-29
