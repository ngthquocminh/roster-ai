<!-- refreshed: 2026-06-26 -->
# Architecture

**Analysis Date:** 2026-06-26

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        HTTP API Layer / CLI                                  │
│         `api/main.py` (FastAPI), `run.py` (CLI)                             │
├──────────────────────────┬─────────────────────────────┬────────────────────┤
│   Health Endpoints       │   Scenario Management       │   Run Lifecycle    │
│  `api/routers/health.py` │ `api/routers/scenarios.py`  │ `api/routers/runs` │
│                          │ `api/routers/fixtures.py`   │                    │
└──────────────────────────┴──────────────┬──────────────┴────────────────────┘
                                          │
                          Service Layer (Request Processing)
                 ┌────────────────────────┴────────────────────────┐
                 │                                                  │
        ┌────────▼──────────────┐              ┌──────────────────▼────┐
        │  ScenarioService      │              │  RunService           │
        │ `services/scenario_*` │              │ `services/run_service`│
        │                       │              │                       │
        │  - Get scenario       │              │  - Create run row     │
        │  - Save fixture ref   │              │  - Submit to thread   │
        │  - List scenarios     │              │  - Poll status        │
        └───────────┬───────────┘              └──────────────┬────────┘
                    │                                         │
                    │           ┌─────────────────────────────┘
                    │           │
        ┌───────────▼───────────▼────────────────────────┐
        │         Domain Layer (Pure Models)             │
        │  `domain/problem.py` - SchedulingProblem       │
        │  `domain/result.py` - SolveResult              │
        │  `domain/types.py` - Member, Task, etc.        │
        │  `ingest/input_adapter.py` - Transformation    │
        │  `ingest/scenario_time.py` - Time utilities     │
        └───────────┬────────────────────────────────────┘
                    │
        ┌───────────▼────────────────────────────────────┐
        │    Engine Layer (Pluggable Solvers)            │
        │      `engine/base.py` - SchedulerEngine        │
        │      Factory Pattern: create_engine("cpsat")   │
        │                                                 │
        │      `engine/cpsat/engine.py`                  │
        │      `engine/cpsat/builder.py` - Model build   │
        │      `engine/cpsat/objective.py` - Solve       │
        └───────────┬────────────────────────────────────┘
                    │
        ┌───────────▼────────────────────────────────────┐
        │  Solver Backend (Google OR-Tools CP-SAT)       │
        │  Lexicographic multi-round optimization        │
        └───────────┬────────────────────────────────────┘
                    │
        ┌───────────▼────────────────────────────────────┐
        │     Data Layer (SQLite Storage)                │
        │   `store/db.py` - Connections + Schema         │
        │   `store/repositories.py` - Data access        │
        │                                                 │
        │   Tables: scenarios, runs                       │
        │   Mode: WAL (concurrent reads/writes)          │
        └────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI App | HTTP server, route mounting, lifespan management | `api/main.py` |
| API Routers | Request handling, validation, HTTP responses | `api/routers/` |
| Scenario Service | Fetch scenario metadata, manage test fixtures | `services/scenario_service.py` |
| Run Service | Create run rows, orchestrate async solves, status persistence | `services/run_service.py` |
| Input Adapter | Transform JSON fixture into SchedulingProblem domain model | `ingest/input_adapter.py` |
| Domain Models | Immutable representations (SchedulingProblem, SolveResult) | `domain/` |
| Scheduler Engine | Abstract solver interface (pluggable backend) | `engine/base.py` |
| CP-SAT Engine | Google OR-Tools constraint solver, lexicographic optimization | `engine/cpsat/` |
| SQLite Store | Persistent scenarios and run records | `store/db.py`, `store/repositories.py` |
| CLI | Direct solve execution, metrics printing | `run.py` |

## Pattern Overview

**Overall:** Layered architecture with clean separation of concerns.

**Key Characteristics:**
- **Domain-Driven Design:** Pure domain types (`domain/`) import nothing from framework or solver. Enables framework-agnostic reuse.
- **Engine Abstraction:** Solver swappable via factory pattern (`engine/base.py`). Current implementation: CP-SAT (Google OR-Tools).
- **Threading Model:** FastAPI event loop (async request handling) + single-worker `ThreadPoolExecutor` for CPU-bound solves. Prevents event loop blocking.
- **Async-First API:** FastAPI dependencies handle DB connections, engine injection. Dependencies yielded per request.
- **Database Concurrency:** SQLite WAL mode allows worker thread to write run status while request threads read scenario metadata.

## Layers

**HTTP API Layer:**
- Purpose: Expose solve capabilities via REST, manage scenario lifecycle, poll run status
- Location: `api/`
- Contains: FastAPI app, route handlers, Pydantic schemas
- Depends on: Services, Domain, Engine, Store
- Used by: HTTP clients, tests

**Service Layer:**
- Purpose: Orchestrate use cases (scenario CRUD, run submission, async execution coordination)
- Location: `services/`
- Contains: `scenario_service.py`, `run_service.py`, serialization utilities
- Depends on: Domain, Engine, Store, Ingest
- Used by: API, CLI

**Domain Layer:**
- Purpose: Immutable representations of problems, solutions, and intermediate types. Framework-agnostic.
- Location: `domain/`
- Contains: `SchedulingProblem`, `SolveResult`, `Member`, `Task`, `Window`, `Qualification`, etc.
- Depends on: Nothing (no framework imports)
- Used by: Engine, Services, Ingest, Serialization

**Ingest Layer:**
- Purpose: Adapt external fixture format (JSON) into domain SchedulingProblem
- Location: `ingest/`
- Contains: `input_adapter.py` (main transformer), `scenario_time.py` (time utilities)
- Depends on: Domain
- Used by: Services (run executor), CLI

**Engine Layer:**
- Purpose: Abstract solver backend. Pluggable via factory.
- Location: `engine/`
- Contains: `base.py` (protocol), `cpsat/` (current implementation)
- Depends on: Domain
- Used by: Services, CLI

**CP-SAT Solver Layer:**
- Purpose: Build and solve constraint model. Lexicographic multi-round optimization.
- Location: `engine/cpsat/`
- Contains: `engine.py` (entry), `builder.py` (model construction), `objective.py` (solve loop)
- Depends on: Domain, Google OR-Tools
- Used by: Engine (wrapped by `SchedulerEngine` protocol)

**Store Layer:**
- Purpose: SQLite persistence. Scenario metadata and run records.
- Location: `store/`
- Contains: `db.py` (connections, schema), `repositories.py` (DAO objects)
- Depends on: Nothing (uses sqlite3 stdlib)
- Used by: Services, API

## Data Flow

### Primary Request Path (HTTP Run Submission)

1. **Request arrives** → FastAPI dependency injection resolves `get_db()`, `get_settings()`, `get_engine()` (`api/deps.py`)
2. **Scenario lookup** → `scenario_service.get_scenario(conn, scenario_id)` queries DB (`services/scenario_service.py`)
3. **Run row created** → `run_service.create_run(conn, scenario_id)` inserts PENDING run to DB, commits (`services/run_service.py:54`)
4. **Solve scheduled** → `run_service.submit_run(run_id, scenario, engine, db_path, data_dir)` submits `_execute()` closure to thread pool (`services/run_service.py:71`)
5. **Response returned** → HTTP 201 with run metadata (id, status=PENDING)

### Background Solve Execution (Worker Thread)

1. **Worker thread runs** `_execute(run_id, scenario, engine, db_path, data_dir)` (`services/run_service.py:74`)
2. **Run marked RUNNING** → `repo.set_running(run_id)`, commit to DB (`services/run_service.py:79`)
3. **Fixture loaded** → `load_problem(path)` transforms JSON fixture via `input_adapter.py` → `SchedulingProblem`
4. **Solve executes** → `engine.solve(problem, config)` returns `SolveResult`
5. **Metrics computed** → Schedule extracted, coverage/cost computed (`engine/cpsat/engine.py:38-80`)
6. **Result stored** → `repo.set_completed(run_id, result_json, status)`, commit to DB
7. **Client polls** → `GET /runs/{run_id}` returns run row with status update. `GET /runs/{run_id}/result` deserializes result_json.

**State Management:**
- Run state transitions: PENDING → RUNNING → COMPLETED/FAILED
- Persisted to `runs` table with timestamps (`started_at`, `finished_at`, `created_at`)
- Result JSON serialized via `serialize_result()` → stored in `result_json` column
- Exceptions caught, logged as `error`, run marked FAILED

### CLI Solve Execution (Synchronous)

1. **CLI entry** → `run.py main(argv)` called (`run.py:14`)
2. **Fixture loaded** → `load_problem(path)` (`run.py:20`)
3. **Engine created** → `create_engine("cpsat")` (`run.py:25`)
4. **Solve blocks** → `engine.solve(problem, config)` blocks until completion (`run.py:27`)
5. **Metrics printed** → Schedule rows, coverage, cost, function breakdowns printed to stdout

**State Management:**
- No database used in CLI
- Timing instrumented inline: `time.time()` before/after solve

## Key Abstractions

**SchedulingProblem:**
- Purpose: Immutable input to the solver. Contains members, tasks, demand, shift templates, availability/roster windows.
- Examples: `domain/problem.py`
- Pattern: Dataclass with typed fields, helper method `task(task_id)` for lookup.

**SolveResult:**
- Purpose: Immutable solution output. Schedule rows, metrics, solver stats.
- Examples: `domain/result.py`
- Pattern: Dataclass wrapping lists of `ScheduleRow`, metrics dictionary, solver stats.

**SchedulerEngine Protocol:**
- Purpose: Abstract interface for swappable solvers.
- Examples: `engine/base.py:18` defines protocol; `engine/cpsat/engine.py:22` implements.
- Pattern: Python Protocol with `solve()` method and `name` property.

**Member / Task / ShiftTemplate:**
- Purpose: Domain entities representing workforce and work.
- Examples: `domain/types.py`
- Pattern: Frozen dataclasses (immutable, hashable). Qualifications stored as nested list.

**Window / Break:**
- Purpose: Represent time availability (roster/availability) and shift breaks.
- Examples: `domain/types.py`
- Pattern: Frozen dataclass. All times in **hours from scenario start** (e.g., day-1 17:30 = 17.5h, day-2 06:00 = 30.0h).

**RunRepo / ScenarioRepo:**
- Purpose: Data access layer. Encapsulate SQL queries.
- Examples: `store/repositories.py`
- Pattern: Class constructor takes `sqlite3.Connection`, methods execute queries and return dicts (sqlite3.Row).

## Entry Points

**HTTP API:**
- Location: `api/main.py:25`
- Triggers: `uvicorn api.main:app --reload`
- Responsibilities: Bind routers (health, fixtures, scenarios, runs); set up lifespan (init_db on startup, shutdown worker pool on teardown)

**CLI:**
- Location: `run.py:53`
- Triggers: `python run.py [fixture_path] [engine_name] [time_limit_s]`
- Responsibilities: Load fixture, create engine, solve synchronously, print metrics and schedule sample

**Test Entry:**
- Location: `conftest.py` (pytest fixtures), `tests/test_*.py`
- Triggers: `pytest` or `pytest tests/test_api.py`
- Responsibilities: Set up temp DB, override `get_engine` dependency with stub, exercise API and service workflows

## Architectural Constraints

- **Threading:** Single-worker thread pool for solves (CPU-bound). Event loop never blocks. Each worker thread opens its own DB connection (sqlite3 not thread-safe by default; `check_same_thread=False` set on connections but actual concurrency serialized by pool).
- **Global state:** `_pool: Optional[ThreadPoolExecutor]` in `services/run_service.py` (module-level). Protected by `_pool_lock`. Solves are serialized (max 1 concurrent). If high concurrency needed, architect for multi-worker pool + distributed solve queue.
- **Database schema:** No migrations framework (DDL embedded in `store/db.py`). Manual schema evolution required. WAL pragma enables concurrent reads while single worker writes.
- **Circular imports:** None detected. Import graph flows cleanly upward (API → Services → Domain/Engine → Engine/Store). Domain imports nothing.
- **Time representation:** All times stored as **hours from scenario start** in domain/engine. Conversion happens at adapter boundary (`ingest/scenario_time.py`). Absolute times (ISO 8601) only in API/DB.

## Anti-Patterns

### Solver Blocking Event Loop

**What happens:** If `engine.solve()` were called on the request thread, the event loop would block for seconds-to-minutes, preventing other requests.

**Why it's wrong:** FastAPI is async-first. Blocking the event loop breaks concurrent request handling. Other clients see timeout/connection refused.

**Do this instead:** Submit to `ThreadPoolExecutor` (single-worker for serialization) in `services/run_service.submit_run()`. Return 201 immediately. Client polls status via `GET /runs/{run_id}`.

### Shared DB Connections Across Threads

**What happens:** SQLite connections aren't thread-safe. Creating one connection in main thread and reusing it in worker thread causes crashes.

**Why it's wrong:** SQLite uses internal locks that don't protect against inter-thread access. Race conditions on query execution, transaction state.

**Do this instead:** Each thread opens its own connection via `db.connect(db_path)` (worker in `services/run_service._execute()`). Each request opens its own via FastAPI dependency `get_db()`.

### Hard-Coded Solver Engine

**What happens:** If CP-SAT code were directly imported and instantiated in run_service, swapping to a different backend would require code changes.

**Why it's wrong:** Violates open/closed principle. New solvers can't be added without modifying service code.

**Do this instead:** Abstract via `SchedulerEngine` protocol in `engine/base.py`. Factory function `create_engine()` returns the implementation. Services depend only on the protocol.

### Time Zones Not Explicit

**What happens:** All times parsed from fixture are treated as local time. No timezone awareness.

**Why it's wrong:** Breaks when fixture and solver run in different zones. Edge cases at DST boundaries.

**Do this instead:** Fixture schema should specify timezone. `scenario_time.py` should parse and validate. Store absolute UTC times in domain if cross-zone compatibility needed.

## Error Handling

**Strategy:** Fail-safe with persistence. Exceptions caught and logged to run state.

**Patterns:**
- **Service layer:** Exceptions in `run_service._execute()` caught at line 90. Error logged as run.error field, run marked FAILED.
- **API layer:** Validation errors (Pydantic) return 422. 404 for not-found resources. Dependency failures propagate (500).
- **Engine layer:** CP-SAT returns status (OPTIMAL, FEASIBLE, UNKNOWN). No exceptions. If no solution found, `math.isnan(lex.round1_value)` returns empty schedule gracefully.
- **Ingest layer:** Malformed JSON raises on `json.load()`. Adapter catches _rows() missing keys, returns default lists.

## Cross-Cutting Concerns

**Logging:** None implemented. Use `print()` for CLI, or override with structured logging (e.g., Python `logging` module). No log abstraction exists.

**Validation:** Pydantic schemas validate API inputs (`api/schemas.py`). Domain types use frozen dataclasses (immutable by construction). Adapter applies schema clipping (`ingest/input_adapter.py:_clip()`) to ensure times fall within horizon.

**Authentication:** Not implemented. All endpoints public. JWT / API-key validation must be added at API router level.

**Serialization:** Custom serializer `services/serialize.py` converts `SolveResult` dataclass to JSON-compatible dict. Only `serialize_result()` exposed. Deserialization happens in API handlers via `json.loads()`.

---

*Architecture analysis: 2026-06-26*
