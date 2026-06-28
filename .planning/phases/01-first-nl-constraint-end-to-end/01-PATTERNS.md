# Phase 1: First NL Constraint End-to-End - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 11 (4 new, 5 modified, 2 new tests)
**Analogs found:** 11 / 11 (every new/modified file has a strong in-repo analog)

> No RESEARCH.md for this phase. All patterns below are extracted from the live
> codebase, which is the authoritative source. The planner should copy these
> conventions verbatim; this is an established codebase, not a greenfield build.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/domain/overrides.py` (NEW) | model | transform | `backend/domain/types.py` (frozen dataclasses) | exact |
| `backend/llm/base.py` (NEW) — `LLMProvider` Protocol + `create_provider` factory | provider/seam | transform | `backend/engine/base.py` (`SchedulerEngine` Protocol + `create_engine`) | exact |
| `backend/llm/stub.py` (NEW) — `StubLLMProvider` | provider | transform | `StubEngine` in `backend/tests/test_api.py:27-43` | exact |
| `backend/api/deps.py` (MOD) — add `get_llm_provider` | config/DI | request-response | `get_engine` in `backend/api/deps.py:30-31` | exact |
| `backend/api/routers/constraints.py` (NEW) — `POST /constraints` | route | request-response | `backend/api/routers/scenarios.py` + `runs.py` | exact |
| `backend/api/schemas.py` (MOD) — constraint req/resp models | model | request-response | `ScenarioCreate`/`ScenarioOut` in `schemas.py:9-20` | exact |
| `backend/services/constraint_service.py` (NEW) — parse→validate→persist | service | CRUD | `backend/services/scenario_service.py` | exact |
| `backend/engine/base.py` (MOD) — `SolverConfig.overrides` field | config | n/a | `SolverConfig` dataclass `engine/base.py:11-15` | self |
| `backend/engine/cpsat/builder.py` (MOD) — shortfall penalty | engine/builder | transform | headcount-unmet pattern `builder.py:285-305` | exact |
| `backend/store/repositories.py` (MOD) — `ScenarioRepo.update_overrides` | repository | CRUD | `RunRepo.set_running` `repositories.py:59-63` | exact |
| `backend/services/run_service.py` (MOD) — thread overrides into config | service | orchestration | `_execute` `run_service.py:74-94` | self |
| `backend/tests/test_constraints_api.py` (NEW) | test | request-response | `backend/tests/test_api.py` | exact |
| `backend/tests/test_engine_min_workers.py` (NEW) | test | transform | `backend/tests/test_engine_small.py` | exact |

> File paths above for NEW files are analog-driven suggestions (`llm/` mirrors
> `engine/`). The planner owns final placement; the conventions are mandatory.

---

## Universal Conventions (apply to EVERY new `.py` file)

Observed in every module read. Non-negotiable per `CLAUDE.md`:

```python
"""One-line module docstring explaining purpose / design decision."""
from __future__ import annotations          # ALWAYS first line after docstring

# absolute imports from backend root — NEVER relative (conftest adds backend to sys.path)
from domain.problem import SchedulingProblem
from store.repositories import ScenarioRepo
```

- snake_case modules/functions/vars; PascalCase classes/enums; UPPERCASE constants.
- Modern 3.10+ type hints: `float | None`, `list[dict]`, `Optional[...]` (both seen).
- Private helpers prefixed `_` (`_now`, `_dict`, `_overlap`).
- `@dataclass(frozen=True)` for immutable domain types; plain `@dataclass` for configs.
- `domain/` imports NOTHING from solver/web/llm (pure-domain rule, ENG-01). `OverrideCall` MUST honor this.

---

## Pattern Assignments

### `backend/domain/overrides.py` (NEW — model, transform)

**Analog:** `backend/domain/types.py` (frozen dataclasses), `backend/domain/problem.py`

**Pure-domain rule (D-08, ENG-01):** This file is the seam decoupling engine from
LLM. It imports only stdlib + `domain`. The engine references `OverrideCall`; the
LLM provider produces it — neither imports the other.

**Frozen-dataclass pattern** (copy from `domain/types.py:56-61`):
```python
@dataclass(frozen=True)
class Qualification:
    task_id: str
    rate: float
    preferred: bool = False
```

**Suggested shape** (Claude's discretion per D-09/CONTEXT line 93-95). `args` typed
loosely since only one tool exists in Phase 1; keep it provider-neutral (no
Anthropic `tool_use` shape leaks here — that stays inside the provider, D-08/D-09):
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class OverrideCall:
    id: str                       # content hash "ov_<sha256(tool+canonical(args))[:8]>" (D-05)
    tool: str                     # "set_min_workers_per_task" (only tool this phase, D-01)
    args: dict[str, Any] = field(default_factory=dict)   # {"task_id": "Pick", "n": 2}
```
> `frozen=True` + a `dict` field: use `field(default_factory=dict)`. Note a frozen
> dataclass with a dict field is not hashable by default — fine, we key the JSON
> store by `id` (D-04), not by hashing the object.

---

### `backend/llm/base.py` (NEW — provider seam, transform)

**Analog:** `backend/engine/base.py` (THE template — Protocol + factory).

This is a near-line-for-line mirror of the engine seam. Copy its structure:

**Full analog** (`engine/base.py:1-30`):
```python
"""SchedulerEngine seam — the swap point for solver backends."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from domain.problem import SchedulingProblem
from domain.result import SolveResult

class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...
    @property
    def name(self) -> str: ...

def create_engine(name: str) -> SchedulerEngine:
    """Registry of available engines. Add a backend here to make it swappable."""
    if name == "cpsat":
        from engine.cpsat.engine import CpSatEngine
        return CpSatEngine()
    raise ValueError(f"Unknown solver engine: {name!r}. Available: ['cpsat']")
```

**Apply to `LLMProvider`** (D-08: returns provider-neutral `list[OverrideCall]`):
```python
class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    @property
    def name(self) -> str: ...

def create_provider(name: str) -> LLMProvider:
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub']")
```
> Lazy import inside the factory branch (matches `engine/base.py:28`) keeps optional
> deps from loading at import time. `name` property mirrors `SchedulerEngine.name`.

---

### `backend/llm/stub.py` (NEW — provider, transform)

**Analog:** `StubEngine` in `tests/test_api.py:27-43` (the stub idiom), but this is
PRODUCTION code (not a test fixture) — it ships as the Phase-1 default provider.

**D-09/D-10 mechanics:** keyword/regex-extract from `text` → build a Claude-faithful
`tool_use` dict `{type, id, name, input}` INTERNALLY → translate to `OverrideCall`.
The `tool_use` shape never crosses the Protocol boundary (D-08/D-09). Text with no
match returns `[]` (D-10). Demo input to support (CONTEXT line 182):
`"at least 2 on Pick"` → `set_min_workers_per_task(task_id="Pick", n=2)`.

**id construction (D-05)** — content hash with sorted-key canonical args:
```python
import hashlib, json
def _override_id(tool: str, args: dict) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return "ov_" + hashlib.sha256((tool + canonical).encode()).hexdigest()[:8]
```

---

### `backend/api/deps.py` (MODIFIED — add `get_llm_provider`)

**Analog:** `get_engine` in the same file (`deps.py:30-31`) — exact mirror.

**Existing pattern** (`deps.py:30-31`):
```python
def get_engine() -> SchedulerEngine:
    return create_engine("cpsat")
```

**Add** (mirror exactly; provider name is config-driven, real Claude is Phase 4 —
Phase 1 wires the stub, CONTEXT line 171-172):
```python
from llm.base import LLMProvider, create_provider

def get_llm_provider() -> LLMProvider:
    return create_provider("stub")
```
> This is the override seam: tests swap it via `app.dependency_overrides`
> (see test analog below), exactly as `get_engine` is swapped in `test_api.py:55`.

---

### `backend/api/routers/constraints.py` (NEW — route, request-response)

**Analog:** `backend/api/routers/scenarios.py` (router skeleton) +
`backend/api/routers/runs.py` (404 + DI of a seam dependency).

**D-06/D-07:** top-level `POST /constraints` (NOT nested), `scenario_id` in body,
parses+validates+stores only (NO solve trigger), returns 200 echoing the override.

**Router + DI + 404 pattern** (from `scenarios.py:14-27` and `runs.py:19-34`):
```python
"""Constraint parsing: NL text -> validated override stored on a scenario."""
from __future__ import annotations
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_db, get_llm_provider
from api.schemas import ConstraintParseRequest, ConstraintParseResponse
from llm.base import LLMProvider
from services import constraint_service

router = APIRouter(prefix="/constraints", tags=["constraints"])

@router.post("", response_model=ConstraintParseResponse,
             responses={404: {"description": "Scenario not found"}})
def parse_constraint(
    body: ConstraintParseRequest,
    conn: sqlite3.Connection = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> dict:
    ...  # delegate to constraint_service; raise HTTPException(404) if scenario missing
```
> `prefix="/constraints"` makes the route top-level (D-07). Status defaults to 200
> (don't set `status_code=201` here — unlike create_scenario, this is not a create).
> Validation failures (unknown `task_id`, non-positive `n`) → `HTTPException(400/422)`,
> following the `scenarios.py:25` style (`status_code=400, detail=...`).

**Mount in `api/main.py`** (analog `main.py:13,27-30`):
```python
from api.routers import constraints, fixtures, health, runs, scenarios
...
app.include_router(constraints.router)
```

---

### `backend/api/schemas.py` (MODIFIED — request/response models)

**Analog:** `ScenarioCreate` / `ScenarioOut` (`schemas.py:9-20`).

**Pattern** (`schemas.py:9-20`):
```python
class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    time_limit_s: float = Field(default=60.0, gt=0)
```

**Add** (request carries `scenario_id` + `text`; response echoes stored override +
human-readable `parsed_constraint`, D-07):
```python
class ConstraintParseRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    text: str = Field(min_length=1)

class ConstraintParseResponse(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str        # e.g. "At least 2 workers on Pick (every demanded hour)"
```

---

### `backend/services/constraint_service.py` (NEW — service, CRUD)

**Analog:** `backend/services/scenario_service.py` (orchestration over a repo).

**Orchestration + JSON-overrides pattern** (`scenario_service.py:17-31` shows the
`json.dumps(overrides or {})` convention and `_now()` helper):
```python
def create_scenario(conn, name, fixture, time_limit_s=60.0, overrides=None) -> dict:
    sid = uuid.uuid4().hex
    repo = ScenarioRepo(conn)
    repo.insert({..., "overrides": json.dumps(overrides or {}), ...})
    conn.commit()
    return repo.get(sid)
```

**This service** does: `provider.parse_constraints(text)` → validate each
`OverrideCall` against the loaded problem (task_id exists, `n > 0`, CONTEXT line
173-174) → read scenario, `json.loads(scenario["overrides"])` → merge by `id`
(D-04 dict-keyed, idempotent overwrite, D-05) → `json.dumps` → persist via the new
`ScenarioRepo.update_overrides` → `conn.commit()`.
> Validation: load the problem to check `task_id` exists. `SchedulingProblem.task(task_id)`
> (`domain/problem.py:22-26`) returns `None` for unknown ids — use it. Service raises
> a plain exception/ValueError; the router converts to `HTTPException` (CLAUDE.md
> error-handling convention: services raise, routers translate).

---

### `backend/engine/base.py` (MODIFIED — `SolverConfig.overrides`)

**Analog:** the `SolverConfig` dataclass itself (`engine/base.py:11-15`).

**Current** (`engine/base.py:11-15`):
```python
@dataclass
class SolverConfig:
    time_limit_s: float = 30.0
    num_workers: int = 8
    seed: int = 42
```

**Add a defaulted field** (so the `solve()` signature stays unchanged — ENG-02;
default keeps the no-override path identical to baseline — CONTEXT line 16-17):
```python
from domain.overrides import OverrideCall
...
    overrides: list[OverrideCall] = field(default_factory=list)   # needs: from dataclasses import field
```
> A scenario with no overrides yields `[]` → builder adds zero penalty terms →
> byte-identical baseline solve (no-regression requirement). Test this explicitly.

---

### `backend/engine/cpsat/builder.py` (MODIFIED — soft shortfall penalty)

**Analog:** the headcount-unmet soft term — THE closest pattern (a per-`(task,hour)`
slack var added into an objective). Copy it almost verbatim.

**(A) Threading overrides into the builder.** The builder currently takes only
`problem` (`builder.py:92`) and `_build_objectives(self, is_ind)` is called at
`builder.py:228` while `coverage_terms` is a local in `build()` (`builder.py:175`).
Two wiring changes the planner MUST make:
1. Pass overrides into the builder. `CpSatEngine.solve` constructs
   `CpSatBuilder(problem).build()` (`engine/cpsat/engine.py:26`) — thread
   `config.overrides` in (e.g. `CpSatBuilder(problem, overrides=config.overrides)`).
2. Pass `coverage_terms` (and overrides) into `_build_objectives` so the penalty can
   reuse the per-`(task,hour)` supply expressions (D-02).

**(B) The supply expression to reuse.** For a worker *count* per hour, use the bare
vars (coeff ignored) exactly as the headcount-coverage path does (`builder.py:290-291`):
```python
terms = coverage_terms.get((tid, h), [])
supply = [var for var, _ in terms]          # number of bodies on (task, hour)
```
> Do NOT use the volume coeffs (`rate*ov`) for a *worker-count* floor — those encode
> output volume, not headcount. The `[var for var, _ in terms]` form (line 291) is
> the right body-count expression. Build penalty for every `(tid, h)` that has demand
> for the overridden task (iterate the same hour keys used in coverage).

**(C) The slack + objective pattern.** Headcount unmet constraint
(`builder.py:285-294`) + its objective term (`builder.py:304-305`):
```python
# constraint (lines 285-294)
unmet = self.m.NewIntVar(0, req, f"unmet_hc_{tid[:6]}_{h}")
self.unmet_hc[(tid, h)] = unmet
self.m.Add(sum(supply) + unmet >= req)
# objective term (lines 304-305) — into round1 here; YOURS goes into round2
unmet_terms.append(C.HOUR_SCALE * var)
```

**Apply (D-02/D-03)** — same slack idiom, summed into `round2_cost` (NOT round1):
```python
# in _build_objectives, after existing cost_terms (builder.py:312-316)
shortfall_terms = []
for ov in self.overrides:                     # only set_min_workers_per_task in Phase 1
    tid, n = ov.args["task_id"], int(ov.args["n"])
    for h in hours_with_demand_for(tid):
        bodies = [var for var, _ in coverage_terms.get((tid, h), [])]
        short = self.m.NewIntVar(0, n, f"minw_short_{tid[:6]}_{h}")
        self.m.Add(sum(bodies) + short >= n)
        shortfall_terms.append(short)
W = C.MIN_WORKERS_PENALTY          # NEW scaled-int constant (Claude's discretion, see below)
self.round2_cost = (sum(cost_terms) + W * sum(shortfall_terms)) if (cost_terms or shortfall_terms) else 0
```

**Penalty weight `W` (Claude's discretion, CONTEXT lines 89-92).** Pick a fixed
scaled-integer constant in `config/constants.py` alongside `VOL_SCALE`/`HOUR_SCALE`/
`COST_SCALE`/`ROSTER_UNFILL_WEIGHT` (`constants.py:29-32`). It must be large enough
that adding a body beats the wage cost of that body (round-2 cost is in scaled cents,
`COST_SCALE=100`; a shift's cost term is `eff_h * wage * COST_SCALE`, `builder.py:313`)
yet not so large it distorts everything. A sensible starting value: roughly one
expensive shift's scaled cost per unit shortfall (e.g. `MIN_WORKERS_PENALTY = 1_000_00`
≈ a few hundred dollars), documented in the constant's comment. Calibration is Phase 4.

> Round-2-only placement (D-03) is enforced by the lexicographic solver: round 1
> minimizes `round1_unmet` then locks it (`objective.py:52,62`); round 2 minimizes
> `round2_cost` (`objective.py:63`). Adding to `round2_cost` cannot affect round-1
> feasibility, so the override can never make the solve infeasible (safety constraint).

---

### `backend/store/repositories.py` (MODIFIED — `ScenarioRepo.update_overrides`)

**Analog:** `RunRepo.set_running` / `set_completed` — the UPDATE-by-id idiom
(`repositories.py:59-71`); `ScenarioRepo` (`repositories.py:16-34`) holds the home.

**UPDATE pattern** (`repositories.py:59-63`):
```python
def set_running(self, run_id: str, started_at: str) -> None:
    self.conn.execute(
        "UPDATE runs SET status='RUNNING', started_at=? WHERE id=?",
        (started_at, run_id),
    )
```

**Add to `ScenarioRepo`** (writes the `overrides` JSON column; column already exists
in schema `store/db.py:15` as `overrides TEXT NOT NULL DEFAULT '{}'`):
```python
def update_overrides(self, scenario_id: str, overrides_json: str) -> None:
    self.conn.execute(
        "UPDATE scenarios SET overrides=? WHERE id=?",
        (overrides_json, scenario_id),
    )
```
> Repo takes already-serialized JSON `str` (callers own `json.dumps`, matching
> `scenario_service.create_scenario` `scenario_service.py:27`). Caller commits
> (repos never commit — `repositories.py:1` docstring). Note: `ScenarioOut`
> (`schemas.py:15-20`) does NOT expose `overrides`; leave it that way unless the
> response model needs it.

---

### `backend/services/run_service.py` (MODIFIED — thread overrides into config)

**Analog:** `_execute` itself (`run_service.py:74-94`) — the `SolverConfig`
construction site.

**Current** (`run_service.py:84`):
```python
config = SolverConfig(time_limit_s=float(scenario["time_limit_s"]))
```

**Change to** (CONTEXT lines 96-98, 175-176 — parse JSON dict-keyed store → list):
```python
import json   # already imported at run_service.py:11
from domain.overrides import OverrideCall
...
raw = json.loads(scenario["overrides"] or "{}")        # {id: {tool, args}}  (D-04)
overrides = [OverrideCall(id=k, tool=v["tool"], args=v["args"]) for k, v in raw.items()]
config = SolverConfig(time_limit_s=float(scenario["time_limit_s"]), overrides=overrides)
```
> `scenario["overrides"]` is the raw DB column value (`ScenarioRepo.get` returns the
> row dict, `repositories.py:27-29`). Empty store → `[]` → identical baseline solve.
> `json` is already imported (`run_service.py:11`).

---

### `backend/tests/test_constraints_api.py` (NEW — test, request-response)

**Analog:** `backend/tests/test_api.py` — copy the fixture + override idiom whole.

**StubEngine + dependency_overrides fixture** (`test_api.py:27-58`) — replicate for
the LLM seam (TEST-01/TEST-02, no live API in CI — CLAUDE.md):
```python
class StubEngine: ...                      # test_api.py:27-43 (keep, run still solves via stub)

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)
    from api.deps import get_engine, get_llm_provider
    from api.main import app
    app.dependency_overrides[get_engine] = lambda: StubEngine()
    app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()   # NEW seam
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```
> Key idioms to keep: env set BEFORE importing `api.deps`/`api.main` (so default
> settings aren't cached — `test_api.py:51` comment); `_DATA_DIR` constant
> (`test_api.py:24`); `_wait_terminal` poll helper (`test_api.py:61-68`) for the
> async run. The end-to-end test: create scenario → `POST /constraints`
> `{"scenario_id", "text": "at least 2 on Pick"}` → assert 200 + echoed override →
> trigger run → poll terminal. The StubLLMProvider can be the production one from
> `llm.stub` (it's already deterministic) or a local test stub mirroring it.

---

### `backend/tests/test_engine_min_workers.py` (NEW — test, transform)

**Analog:** `backend/tests/test_engine_small.py` — hand-built instance with a known
optimum, solved through the REAL engine (no stub — this validates the penalty).

**Pattern** (`test_engine_small.py:18-44`): build a tiny `SchedulingProblem`, solve
via `create_engine("cpsat").solve(problem, SolverConfig(...))`, assert on
`res.metrics`. For the override test, pass `SolverConfig(overrides=[OverrideCall(...)])`
and assert the schedule places >= N bodies on the task at demanded hours vs. the
no-override baseline (the "visibly honored" success criterion). Also add a
no-override regression assert: same problem with `overrides=[]` matches baseline
(CONTEXT line 16-17).

---

## Shared Patterns

### Protocol + factory seam (THE recurring architecture pattern)
**Source:** `backend/engine/base.py:18-30`
**Apply to:** `llm/base.py` (`LLMProvider` + `create_provider`)
Protocol with method(s) + a `name` property; module-level factory with lazy imports
inside each branch; `ValueError` listing available names for unknown input.

### Dependency-injection seam swapped in tests
**Source:** `get_engine` (`deps.py:30-31`) + `app.dependency_overrides[get_engine]` (`test_api.py:55`)
**Apply to:** `get_llm_provider` and its test override. Zero-arg dependency returning
the real implementation; tests substitute a stub via `dependency_overrides`.

### JSON-column persistence (dict-keyed-by-id, D-04)
**Source:** `scenario_service.py:27` (`json.dumps(overrides or {})`), `db.py:15` (column), `repositories.py:27-29` (read)
**Apply to:** constraint_service merge logic + `ScenarioRepo.update_overrides`.
Service owns (de)serialization; repo stores/returns the raw `TEXT` column.

### Soft-penalty slack term (NEVER hard, NEVER round 1)
**Source:** headcount unmet — constraint `builder.py:285-294`, objective `builder.py:304-305`; lex enforcement `objective.py:52-63`
**Apply to:** the min-workers shortfall penalty. `NewIntVar(0, N, ...)`,
`Add(sum(supply) + slack >= N)`, sum `W * slack` into `round2_cost`. Guarantees the
override can never cause infeasibility (project safety constraint).

### Scaled-integer objective terms
**Source:** `config/constants.py:28-32`; usage `builder.py:261,279,302,313`
**Apply to:** the penalty weight `W` — declare a new scaled-int constant in
`constants.py`; multiply integer slack vars by it. CP-SAT is integer-only.

### Error handling: services raise, routers translate
**Source:** CLAUDE.md; `scenarios.py:24-25` (router raises `HTTPException`), `run_service.py:90-92` (background catches+persists)
**Apply to:** constraint_service raises `ValueError` on bad task_id / non-positive n;
`constraints.py` router converts to `HTTPException(400/404/422)`.

---

## No Analog Found

None. Every file in scope maps to a concrete in-repo analog. The repository already
contains the exact two seams this phase extends (engine Protocol+factory+DI, and the
soft-penalty slack idiom), so the planner should treat this as pattern replication,
not invention.

---

## Metadata

**Analog search scope:** `backend/{api,domain,engine,services,store,config,tests}`, `backend/settings.py`
**Files scanned:** 16 (deps, base, builder, objective, engine, constants, test_api,
test_engine_small, scenarios router, runs router, repositories, db, run_service,
scenario_service, schemas, main, types, problem, settings, CONTEXT)
**Pattern extraction date:** 2026-06-28
