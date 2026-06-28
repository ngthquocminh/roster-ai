# Architecture Research

**Domain:** LLM integration into layered FastAPI/CP-SAT scheduling backend
**Researched:** 2026-06-28
**Confidence:** HIGH (derived from direct codebase inspection: engine/base.py, services/run_service.py, store/db.py, api/deps.py, engine/cpsat/engine.py, design.md §4, PROJECT.md)

---

## Standard Architecture

### System Overview — Phase 3 Target State

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         HTTP API Layer                                        │
│  api/routers/scenarios.py   api/routers/runs.py   [new: runs insights route] │
│  POST /scenarios/{id}/parse-constraints    GET /runs/{id}/insights (NEW)     │
├────────────────────────────────────────────────────────────────────────────  ┤
│                         Service Layer                                         │
│  scenario_service.py   run_service.py   [new: parse_service.py]              │
│  - ScenarioService: set_overrides()            - NL text → OverrideCall[]    │
│  - RunService: pass overrides → SolverConfig   - Validate against fixture IDs│
├──────────────────┬────────────────────────────────────────────────────────── ┤
│  Engine Layer    │  LLM Layer (NEW)                                           │
│  engine/base.py  │  llm/base.py                                              │
│  SolverConfig ←──┘  LLMProvider Protocol                                     │
│  +overrides field    ClaudeLLMProvider / StubLLMProvider                     │
│  engine/cpsat/       (injected via api/deps.get_llm_provider)                │
│  builder.py                                                                   │
│  +apply overrides                                                             │
│  as soft constraints                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                  Domain Layer (pure Python — unchanged)                       │
│  domain/problem.py  domain/result.py  domain/types.py                        │
│  [new] domain/overrides.py  (OverrideCall union + 5 concrete types)          │
│  IMPORTS NOTHING outside stdlib                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                  Store Layer (SQLite WAL)                                     │
│  store/db.py — scenarios.overrides (JSON, already reserved)                  │
│  store/db.py — runs.insight_json TEXT (NEW column)                           │
│  store/repositories.py — ScenarioRepo.set_overrides() (NEW)                  │
│  store/repositories.py — RunRepo.set_insight() (NEW)                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Location | Decision tag |
|-----------|---------------|----------|--------------|
| `LLMProvider` Protocol | Abstract interface for all LLM vendor calls; `parse_constraints()` + `generate_insight()` + `name` property | `backend/llm/base.py` | confirm-baseline |
| `ClaudeLLMProvider` | Anthropic Claude implementation; reads `llm_model` from Settings | `backend/llm/claude.py` | confirm-baseline |
| `StubLLMProvider` | Deterministic fixed responses; no network; used in CI | `backend/llm/stub.py` | confirm-baseline |
| `create_llm_provider()` | Registry factory mirroring `create_engine()`; maps name → implementation | `backend/llm/base.py` | confirm-baseline |
| `OverrideCall` union types | 5 pure-Python dataclasses: lock\_worker\_shift, set\_min\_workers\_per\_task, exclude\_worker\_from\_task, scale\_demand, set\_max\_hours | `backend/domain/overrides.py` | propose-change (new file; not in llm/ — keeps engine/base.py importable without depending on llm/) |
| `SolverConfig.overrides` | Optional list of validated OverrideCall; passed to builder | `backend/engine/base.py` (extend existing SolverConfig dataclass) | propose-change (field addition; Protocol signature `solve(problem, config)` stays intact) |
| Override constraint builder | Reads `config.overrides`; adds soft-penalty CP-SAT constraints for each tool call | `backend/engine/cpsat/builder.py` (new method `apply_overrides()`) | propose-change (additive extension only; existing constraint logic untouched) |
| `parse_service.py` | Orchestrates NL → LLM call → tool-call validation → OverrideCall list | `backend/services/parse_service.py` | propose-change (new file; service layer is the correct home: validation needs fixture entity IDs, which service layer loads; not domain, not engine) |
| `get_llm_provider()` dep | FastAPI DI function mirroring `get_engine()` in `api/deps.py`; test-overridable | `backend/api/deps.py` (add alongside existing get\_engine) | confirm-baseline |
| Lazy insight endpoint | `GET /runs/{id}/insights` — fetches cached or calls LLM; LLM failure returns 503, leaves run intact | `backend/api/routers/runs.py` (new route) | propose-change (lazy on-demand preferred over eager post-run background task — simpler, more resilient; run COMPLETED is never blocked) |

**Import graph must stay acyclic:**
```
api → services → engine, llm, domain, store
engine → domain          (engine/base.py imports domain/overrides.py)
llm → domain             (llm/base.py imports domain/overrides.py for return types)
domain → (nothing)
store → (nothing, stdlib sqlite3 only)
services → engine, llm, domain, store (no cross-dependency between engine and llm layers)
```

**Critical: engine and llm layers must NOT import each other.** `OverrideCall` types live in `domain/` so both layers can import them without creating a cycle.

---

## Recommended Project Structure Changes

```
backend/
├── domain/
│   ├── overrides.py        # NEW: OverrideCall union + 5 concrete dataclasses
│   ├── problem.py          # unchanged
│   ├── result.py           # unchanged
│   └── types.py            # unchanged
│
├── engine/
│   ├── base.py             # EXTEND: SolverConfig += overrides: list[OverrideCall]
│   └── cpsat/
│       ├── builder.py      # EXTEND: apply_overrides(config.overrides) in build()
│       ├── engine.py       # unchanged (passes config through; builder handles it)
│       └── objective.py    # unchanged
│
├── llm/                    # NEW package (mirrors engine/ structure)
│   ├── __init__.py
│   ├── base.py             # LLMProvider Protocol + create_llm_provider() factory
│   ├── claude.py           # ClaudeLLMProvider (Anthropic SDK)
│   └── stub.py             # StubLLMProvider (deterministic, no network)
│
├── services/
│   ├── parse_service.py    # NEW: parse_and_validate(nl_text, scenario, llm) → list[OverrideCall]
│   ├── run_service.py      # EXTEND: load overrides from scenario JSON → SolverConfig
│   ├── scenario_service.py # EXTEND: set_overrides() call path
│   └── serialize.py        # unchanged
│
├── store/
│   ├── db.py               # EXTEND: add insight_json TEXT column to runs table
│   └── repositories.py     # EXTEND: ScenarioRepo.set_overrides(), RunRepo.set_insight()
│
├── api/
│   ├── deps.py             # EXTEND: add get_llm_provider() dependency
│   ├── schemas.py          # EXTEND: NLParseRequest, NLParseResponse, InsightResponse
│   └── routers/
│       ├── scenarios.py    # EXTEND: POST /{id}/parse-constraints route
│       └── runs.py         # EXTEND: GET /{id}/insights route
│
└── settings.py             # EXTEND: add llm_model: str, llm_api_key: str fields
```

---

## Data Flows

### Flow 1: NL Constraint Parsing → Override Storage

```
POST /scenarios/{id}/parse-constraints  {"nl_text": "Give Alice at least 2 breaks..."}
    │
    ▼ api/routers/scenarios.py
    Fetch scenario row → ScenarioRepo.get(scenario_id)
    Resolve LLM provider → get_llm_provider() dep (ClaudeLLMProvider or StubLLMProvider)
    │
    ▼ services/parse_service.parse_and_validate(nl_text, scenario, llm_provider)
    Load fixture → load_problem(scenario["fixture"])  [same as run_service does]
    Build entity context → {"member_ids": [...], "task_ids": [...], "horizon_h": 168}
    │
    ▼ llm_provider.parse_constraints(nl_text, context)
    LLM returns raw tool calls (list of dicts)
    │
    ▼ parse_service (validation step)
    For each tool call:
      - Check tool name is one of the 5 known tools
      - Validate member_id in context["member_ids"] (if applicable)
      - Validate task_id in context["task_ids"] (if applicable)
      - Check numeric bounds (min_count ≥ 0, factor > 0, etc.)
    Unknown refs → discard with warning; never raise (partial success OK)
    │
    ▼ ScenarioRepo.set_overrides(scenario_id, json.dumps([...]))
    Persist validated OverrideCall list as JSON to scenarios.overrides
    │
    ▼ HTTP 200: {"parsed": [...], "rejected": [...]}
```

### Flow 2: Solve with Overrides (Worker Thread)

```
POST /scenarios/{id}/runs
    │
    ▼ run_service.submit_run(run_id, scenario, engine, db_path, data_dir)
    Returns 201 immediately (same as today — NO CHANGE to HTTP contract)
    │
    [worker thread: run_service._execute()]
    │
    ▼ Read scenario["overrides"] from DB  (JSON string)
    Parse → list[OverrideCall] via domain/overrides.py deserializer
    │
    ▼ load_problem(path) → SchedulingProblem  [unchanged]
    │
    ▼ SolverConfig(time_limit_s=..., overrides=parsed_overrides)  [new overrides field]
    │
    ▼ engine.solve(problem, config)   [Protocol signature unchanged]
    │
    ▼ CpSatEngine.solve() → CpSatBuilder(problem).build()
    builder.apply_overrides(config.overrides):
      lock_worker_shift    → add BoolVar penalty if shift not at locked time
      set_min_workers_per_task → add IntVar + penalize shortage
      exclude_worker_from_task → sum of task[member, task_id] == 0 as hard gate
                                  OR soft penalty (choose soft to never infeasible)
      scale_demand         → multiply vol_demand[task_id][h] by factor before building coverage
      set_max_hours        → tighten per-member hour cap
    │
    ▼ solve_lexicographic(builder, ...)  [unchanged]
    │
    ▼ repo.set_completed(...)  [unchanged]
    run.status = COMPLETED, result_json stored
```

**Override application safety rule:** Every override must be applied as a soft penalty, never a hard constraint. Violation is penalized (adds to objective), never makes the model infeasible. This is consistent with the existing `unfilled_roster` soft pattern in builder.py.

### Flow 3: Insight Generation (Lazy, Decoupled)

```
GET /runs/{id}/insights
    │
    ▼ RunRepo.get(run_id) → run row
    If run.status != COMPLETED → 409 (run not finished)
    If run.insight_json is not None → return cached insight (200)
    │
    ▼ Extract metrics subset from run.result_json
    metrics = {"total_unmet_hours": ..., "coverage_by_function": ...,
               "coverage_by_day": ..., "total_cost": ..., "scheduled_members": ...}
    │
    ▼ llm_provider.generate_insight(metrics)
    LLM failure → raise → caught at route level → HTTP 503
    Schedule result unaffected (stored independently)
    │
    ▼ RunRepo.set_insight(run_id, insight_text)
    Cache in runs.insight_json
    │
    ▼ HTTP 200: {"insight": "...", "run_id": "..."}
```

**Decoupling guarantee:** Insight generation is never called in `run_service._execute()`. The worker thread only marks COMPLETED and stores `result_json`. Insights are produced only when explicitly requested by the client, after the run is COMPLETED. An LLM outage cannot propagate to the solve lifecycle.

---

## Architectural Patterns

### Pattern 1: Protocol Seam with Factory (confirm-baseline)

The existing `SchedulerEngine` Protocol in `engine/base.py` is the template to mirror exactly.

```python
# llm/base.py
from __future__ import annotations
from typing import Protocol
from domain.overrides import OverrideCall

class LLMProvider(Protocol):
    async def parse_constraints(
        self, nl_text: str, context: dict
    ) -> list[OverrideCall]: ...

    async def generate_insight(self, metrics: dict) -> str: ...

    @property
    def name(self) -> str: ...


def create_llm_provider(name: str) -> LLMProvider:
    """Registry mirroring create_engine(). Add a vendor here to make it swappable."""
    if name == "claude":
        from llm.claude import ClaudeLLMProvider
        return ClaudeLLMProvider()
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['claude', 'stub']")
```

```python
# api/deps.py (extend existing file)
from llm.base import LLMProvider, create_llm_provider

def get_llm_provider() -> LLMProvider:
    return create_llm_provider(get_settings().llm_provider)
```

Tests override `get_llm_provider` exactly as they already override `get_engine`:
```python
# conftest.py (extend existing pattern)
app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
```

### Pattern 2: OverrideCall as Pure Domain Type (propose-change)

Override types go in `domain/`, not `llm/`, because `engine/base.py` must reference them in `SolverConfig` and `engine/base.py` cannot import from `llm/` (that would create an engine→llm dependency, violating the independence of the two Protocol seams).

```python
# domain/overrides.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union

@dataclass(frozen=True)
class LockWorkerShift:
    tool: Literal["lock_worker_shift"]
    member_id: str
    day: int          # 0-indexed from scenario start
    start_h: float    # hours from scenario start

@dataclass(frozen=True)
class SetMinWorkersPerTask:
    tool: Literal["set_min_workers_per_task"]
    task_id: str
    min_count: int

@dataclass(frozen=True)
class ExcludeWorkerFromTask:
    tool: Literal["exclude_worker_from_task"]
    member_id: str
    task_id: str

@dataclass(frozen=True)
class ScaleDemand:
    tool: Literal["scale_demand"]
    task_id: str
    factor: float     # 1.0 = no change; 1.2 = 20% more demand

@dataclass(frozen=True)
class SetMaxHours:
    tool: Literal["set_max_hours"]
    member_id: str
    max_hours: float

OverrideCall = Union[
    LockWorkerShift, SetMinWorkersPerTask,
    ExcludeWorkerFromTask, ScaleDemand, SetMaxHours
]
```

```python
# engine/base.py (extend SolverConfig — propose-change)
from domain.overrides import OverrideCall

@dataclass
class SolverConfig:
    time_limit_s: float = 30.0
    num_workers: int = 8
    seed: int = 42
    overrides: list[OverrideCall] = field(default_factory=list)  # NEW
```

### Pattern 3: Soft-Penalty Override Application (propose-change)

Each override is applied as an additive penalty term, never a hard gate. This extends the existing pattern in `builder.py` where `unfilled_roster` uses a soft `== 1` with a penalty weight.

```python
# engine/cpsat/builder.py — skeleton (propose-change: additive method)
def apply_overrides(self, overrides: list[OverrideCall]) -> None:
    """Apply NL-derived overrides as soft penalties. Never raises — bad refs skipped."""
    for ov in overrides:
        if ov.tool == "scale_demand":
            # Multiply pre-built vol_demand entries for task_id by factor.
            # Must be called before coverage constraints are built.
            self._scale_demand(ov.task_id, ov.factor)
        elif ov.tool == "exclude_worker_from_task":
            # Penalize any task var where member_id matches task_id.
            self._penalize_assignment(ov.member_id, ov.task_id)
        # ... other tools
```

`apply_overrides()` is called between variable creation and constraint creation in `build()`, or as a post-constraint penalty pass. `scale_demand` must happen before coverage constraints reference `vol_demand`; others can be appended as penalty terms after.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: LLM call in the worker thread / solve path

**What happens:** NL parsing or insight generation is called inside `run_service._execute()`, which runs in the single-worker `ThreadPoolExecutor`.

**Why it's wrong:** The worker thread is serialized; a slow LLM call (2–10s) blocks all subsequent solve submissions. An LLM API error during insight generation marks the run FAILED even though the schedule was valid. The event loop (async) cannot be driven from the worker thread without special `asyncio.run()` wrapping.

**Do this instead:** NL parse runs on the request thread (FastAPI async handler calls `await llm_provider.parse_constraints(...)` before run submission). Insights are produced lazily via a dedicated endpoint after the run completes.

### Anti-Pattern 2: OverrideCall types defined in llm/ package

**What happens:** `domain/overrides.py` does not exist; instead `OverrideCall` is defined in `llm/base.py`. Then `engine/base.py` must import from `llm/` to add `overrides` to `SolverConfig`.

**Why it's wrong:** Creates an engine→llm import dependency. Breaks the independence guarantee of the two Protocol seams. Any test that imports only the engine layer now pulls in the LLM package.

**Do this instead:** `OverrideCall` and its concrete subtypes live in `domain/overrides.py` (pure Python, zero external imports). Both `engine/` and `llm/` import from `domain/`.

### Anti-Pattern 3: Applying overrides as hard constraints

**What happens:** `ExcludeWorkerFromTask` becomes `model.Add(sum_task_vars == 0)` as a hard equality. `SetMinWorkersPerTask` becomes `model.Add(sum >= min_count)` as a hard lower bound.

**Why it's wrong:** An erroneous or conflicting NL instruction (e.g., exclude the only qualified worker from a task) makes the model infeasible. CP-SAT returns INFEASIBLE, empty schedule, no metrics. The user gets a failed run with no explanation.

**Do this instead:** All overrides add penalty IntVars/BoolVars. Violation is penalized at a weight higher than coverage unmet (so the solver prefers honoring overrides when possible) but the model never becomes infeasible.

### Anti-Pattern 4: Eager post-run insight generation in the worker thread

**What happens:** After `repo.set_completed()`, the worker thread immediately calls `llm_provider.generate_insight(result)` and stores the result before returning.

**Why it's wrong:** A network timeout or LLM outage causes the worker to mark the run FAILED even though the solve succeeded. The single-worker pool is occupied during the LLM call (seconds), blocking the next queued solve.

**Do this instead:** `_execute()` only writes `result_json` and status COMPLETED. Insights are a separate, client-driven fetch via `GET /runs/{id}/insights`. The run status lifecycle is decoupled from LLM availability.

### Anti-Pattern 5: Putting business validation (entity ID checks) in the LLM layer

**What happens:** `ClaudeLLMProvider.parse_constraints()` loads the scenario fixture and validates member/task IDs internally.

**Why it's wrong:** The LLM provider becomes coupled to the data layer. The stub provider must also replicate this fixture-loading logic. Swapping providers becomes more complex.

**Do this instead:** The `LLMProvider` contract only transforms NL text + a plain `context` dict into raw tool calls. The `parse_service.py` in the service layer owns entity validation — it loads the fixture, builds the context dict, calls the provider, then validates returned IDs against real entities. The provider is stateless regarding data.

---

## Suggested Build Order

Build order respects dependencies: each step only requires what was built in prior steps.

| Step | What to build | Depends on | Unblocks |
|------|--------------|-----------|---------|
| 1 | `domain/overrides.py` (OverrideCall types) | nothing | engine ext, llm/ |
| 2 | Extend `engine/base.py` SolverConfig + `engine/cpsat/builder.py` override application | Step 1 | integration tests against engine |
| 3 | `llm/base.py` Protocol + `llm/stub.py` | Step 1 | all test coverage; parse_service |
| 4 | `services/parse_service.py` + `store/` extensions (set_overrides, insight_json column, set_insight) + `settings.py` LLM fields | Steps 1, 3 | API layer |
| 5 | `api/deps.get_llm_provider()` + API schemas + routes (parse-constraints, insights) | Steps 3, 4 | end-to-end tests |
| 6 | Extend `services/run_service._execute()` to deserialize overrides → SolverConfig | Steps 1, 2, 4 | override round-trip test |
| 7 | `llm/claude.py` real implementation | Step 3 Protocol | manual smoke test; CI uses stub |

**Stub-first strategy:** Steps 1–6 can be built and fully tested against the `StubLLMProvider` with zero LLM API calls. Step 7 (real Claude integration) only requires integration of an already-stable interface.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic Claude API | `async` HTTP via `anthropic` Python SDK (or `httpx`); called from `llm/claude.py` | Model id from `Settings.llm_model`; API key from `Settings.llm_api_key` / env `ANTHROPIC_API_KEY`; Claude API supports function/tool calling natively — use that for NL→tool call |
| SQLite | Existing WAL pattern; insight_json added as nullable TEXT column on runs | No migration framework; `init_db()` re-runs `CREATE TABLE IF NOT EXISTS` — add new column via `ALTER TABLE` run on startup (or add to schema string with `DEFAULT NULL`) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API ↔ Services | Direct function call (same process); FastAPI DI for LLMProvider + DB | NL parse endpoint is sync from caller's perspective (awaits LLM call); no background task needed |
| Services ↔ LLM layer | `await llm_provider.parse_constraints(...)` and `await llm_provider.generate_insight(...)` | Provider must be async-compatible; stub implements same async interface |
| Services ↔ Engine layer | `SolverConfig` dataclass carries overrides; no direct call from engine to services | Decoupled via config object; engine has no knowledge of LLM |
| Worker thread ↔ Domain | `domain/overrides.py` deserialization from `scenario["overrides"]` JSON happens in worker | Pure Python, no async needed in worker thread for this step |

---

## Scaling Considerations

| Concern | Current (Phase 3) | Future |
|---------|-------------------|--------|
| LLM latency (parse) | Acceptable on request thread; Claude typically 1–3s for tool calls | If latency grows, move parse to background + poll, same PENDING→COMPLETED pattern as solves |
| LLM latency (insights) | Lazy fetch; client controls when to request | Cache in `runs.insight_json` means second request is instant |
| Concurrent NL parses | No serialization needed (LLM calls are I/O-bound, not CPU-bound); FastAPI handles naturally | Rate-limit if API quota is a concern |
| Solver queue contention | LLM call on request thread never enters the single-worker solve pool | No change to solver concurrency model |

---

## Sources

All findings are derived directly from codebase inspection (HIGH confidence, no external sources required):

- `backend/engine/base.py` — SchedulerEngine Protocol, SolverConfig shape, factory pattern
- `backend/api/deps.py` — existing DI seam for engine injection (get_engine pattern)
- `backend/services/run_service.py` — worker thread lifecycle, _execute() structure, SolverConfig instantiation
- `backend/store/db.py` — scenarios.overrides column (TEXT NOT NULL DEFAULT '{}') confirmed reserved
- `backend/store/repositories.py` — ScenarioRepo/RunRepo DAO patterns
- `backend/engine/cpsat/builder.py` / `engine.py` — soft penalty patterns (unfilled_roster), how SolverConfig flows to builder
- `docs/design.md` §4 — LLMProvider Protocol intent, insight-decoupling mandate, tool call list, soft constraint mandate
- `.planning/PROJECT.md` — milestone constraints, stub provider requirement, overrides-as-soft mandate

---

*Architecture research: ShiftMind Phase 3 LLM layer integration*
*Researched: 2026-06-28*
