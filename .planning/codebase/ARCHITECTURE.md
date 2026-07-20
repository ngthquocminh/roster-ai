<!-- refreshed: 2026-07-20 -->
# Architecture

**Analysis Date:** 2026-07-20

## System Overview

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                           Frontend (Vite + React)                          │
│                     `frontend/src` (TypeScript + TSX)                      │
│  Routes: Home / Editor / RunHistory / ResultsView                          │
│  Components: Scenarios | Editor | Runs | Results | Layout | UI             │
│  Hooks: useScenarios, useRun, useRunResult, useApplyConstraint, etc.       │
│  State: TanStack Query (server cache) + React Router (route state)         │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
                    REST API + JSON (CORS enabled)
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend (HTTP Server)                      │
│                        `backend/api/main.py`                               │
│  Routers: health | fixtures | scenarios | runs | constraints               │
│  Schemas: Pydantic models for request/response validation                  │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Services   │  │    Domain    │  │  Store/DB    │
│              │  │              │  │              │
│ • Scenario   │  │ • Problem    │  │ • SQLite     │
│ • Run        │  │ • Result     │  │ • Repos      │
│ • Constraint │  │ • Types      │  │              │
│ • Insight    │  │              │  │              │
│ • Serialize  │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
    ┌────────┐        ┌────────┐
    │ Engine │        │  LLM   │
    │        │        │        │
    │ CP-SAT │        │Protocol│
    │        │        │ + 3    │
    │        │        │Impls   │
    └────────┘        └────────┘
        │
        ▼
    ┌────────────────────┐
    │  OR-Tools CP-SAT   │
    │  (Constraint       │
    │   Programming      │
    │   Solver)          │
    └────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Location |
|-----------|----------------|----------|
| FastAPI App | HTTP server, route mounting, lifespan (startup/shutdown) | `api/main.py` |
| Routers | Request handling, validation, HTTP responses for health/fixtures/scenarios/runs/constraints | `api/routers/*.py` |
| Pydantic Schemas | Request/response validation and serialization | `api/schemas.py` |
| Scenario Service | Fetch scenario metadata, manage test fixtures, store overrides | `services/scenario_service.py` |
| Run Service | Create run rows, orchestrate async solves, status persistence, worker pool mgmt | `services/run_service.py` |
| Constraint Service | Parse NL text → validate → persist constraint overrides on scenario | `services/constraint_service.py` |
| Insight Service | Generate or retrieve plain-language insight reports for completed runs | `services/insight_service.py` |
| Input Adapter | Transform JSON fixture into SchedulingProblem domain model | `ingest/input_adapter.py` |
| Domain Models | Immutable representations (SchedulingProblem, SolveResult, Member, Task, etc.) | `domain/*.py` |
| Scheduler Engine Protocol | Abstract solver interface (pluggable backend) | `engine/base.py` |
| CP-SAT Engine | Google OR-Tools constraint solver, lexicographic optimization | `engine/cpsat/*.py` |
| LLM Provider Protocol | Abstract LLM interface for constraint parsing & insight generation | `llm/base.py` |
| LLM Implementations | Stub (test), Gemini, OpenRouter (network-backed) | `llm/stub.py`, `llm/gemini.py`, `llm/openrouter.py` |
| SQLite Store | Persistent scenarios and run records, WAL mode concurrency | `store/db.py`, `store/repositories.py` |
| CLI | Direct solve execution without HTTP, synchronous results | `run.py` |
| Frontend Router | React Router, nested routes for scenario/run views | `frontend/src/App.tsx`, `frontend/src/routes/*.tsx` |
| Frontend Hooks | TanStack Query wrappers for API calls, data fetching/caching | `frontend/src/hooks/use*.ts` |
| Frontend Components | UI building blocks organized by feature (editor, results, runs, etc.) | `frontend/src/components/` |
| API Client | Single typed `openapi-fetch` instance, OpenAPI schema-based | `frontend/src/api/client.ts` |

## Pattern Overview

**Overall:** Layered architecture with clear separation of concerns (API → Services → Domain/Engine). Two independent frontends: HTTP API (FastAPI) and CLI. Frontend is a single-page app (SPA) communicating via REST/JSON. Both backends share pure domain and solver logic.

**Key Characteristics:**
- **Domain-Driven:** Pure domain types (`domain/`) import nothing from framework or solver
- **Pluggable Engines:** Solver and LLM backends swappable via Protocol + factory pattern
- **Async-First API:** FastAPI async request handling + single-worker thread pool for CPU-bound solves
- **Type Safety:** Full TypeScript frontend with OpenAPI-generated client, Python type hints throughout backend
- **Database Concurrency:** SQLite WAL mode allows worker thread to write run status while request threads read
- **Clean Boundaries:** LLM access behind `LLMProvider` Protocol; NL constraints validated and applied as soft overrides only

## Layers

**API Layer:**
- Purpose: Expose solve capabilities via REST, manage scenario lifecycle, poll run status, apply NL constraint overrides
- Location: `api/main.py`, `api/routers/`, `api/schemas.py`, `api/deps.py`
- Contains: FastAPI app, route handlers, Pydantic request/response models, dependency injection
- Depends on: Services, Domain, Engine, Store, LLM
- Used by: HTTP clients (frontend), external API consumers
- Incoming: HTTP POST/GET requests (JSON bodies, path/query params)
- Outgoing: JSON responses (200/201/400/404/409/502/503)

**Service Layer:**
- Purpose: Orchestrate use cases (scenario CRUD, run submission, async execution, constraint parsing, insight generation)
- Location: `services/*.py`
- Contains: Business logic for scenarios, runs, constraints, insights, and result serialization
- Depends on: Domain, Engine, Store, Ingest, LLM
- Used by: API routers, CLI
- Entry points: `scenario_service.get_scenario()`, `run_service.submit_run()`, `constraint_service.parse_and_apply()`, `insight_service.get_or_generate()`
- Error handling: Raises `LookupError` for missing resources (404); partial failures returned in structured response bodies

**Domain Layer:**
- Purpose: Immutable representations of problems, solutions, and workflow entities. Framework-agnostic.
- Location: `domain/`
- Contains: `SchedulingProblem`, `SolveResult`, `Member`, `Task`, `Window`, `Qualification`, `OverrideCall`, etc.
- Depends on: Nothing (no framework imports, pure dataclasses/frozen dataclasses)
- Used by: Engine, Services, Ingest, API (serialization)
- Guarantees: Hashable types (frozen dataclasses), correct default values, time in hours from scenario start

**Ingest Layer:**
- Purpose: Adapt external fixture format (JSON) into domain `SchedulingProblem`
- Location: `ingest/`
- Contains: `input_adapter.py` (main transformer), `scenario_time.py` (time utilities)
- Depends on: Domain
- Used by: Services (run executor), CLI
- Responsibility: Parse JSON, apply clipping to scenario horizon, build members/tasks/demand/templates, resolve wage caps

**Engine Layer:**
- Purpose: Abstract solver backend. Pluggable via factory.
- Location: `engine/base.py` (protocol definition)
- Contains: `SchedulerEngine` Protocol, `SolverConfig` dataclass, `create_engine()` factory
- Depends on: Domain
- Implementations: `engine/cpsat/` (Google OR-Tools CP-SAT)
- Used by: Services, CLI
- Interface: `solve(problem: SchedulingProblem, config: SolverConfig) -> SolveResult`

**CP-SAT Solver Implementation:**
- Purpose: Build constraint model and solve using Google OR-Tools lexicographic optimization
- Location: `engine/cpsat/engine.py`, `builder.py`, `objective.py`
- Depends on: Domain, Google OR-Tools, Domain overrides
- Responsibilities: Model construction (members, tasks, demand, shifts, qualifications, availability), two-round solve (round 1: maximize coverage, round 2: minimize cost subject to round-1 objective)
- Entry: `CpSatEngine.solve()` returns `SolveResult` with schedule rows, metrics, solver status

**LLM Layer:**
- Purpose: Abstract language model backend for constraint parsing and insight generation
- Location: `llm/base.py` (protocol), `llm/stub.py`, `llm/gemini.py`, `llm/openrouter.py` (implementations)
- Contains: `LLMProvider` Protocol, `LLMProviderError` exception, factory
- Implementations:
  - **Stub:** Always returns empty list or fixed responses (test default)
  - **Gemini:** Network-backed Google Gemini API
  - **OpenRouter:** Network-backed OpenRouter API (model router)
- Interface:
  - `parse_constraints(text: str) -> list[OverrideCall]`: Parse NL to domain constraint calls
  - `generate_insights(summary: dict) -> str`: Plain-language insight report from solve metrics
- Used by: Constraint service (constraint parsing), Insight service (report generation)

**Store Layer:**
- Purpose: SQLite persistence, data access
- Location: `store/db.py` (connection, schema, migrations), `store/repositories.py` (DAO)
- Contains: Database connection management, schema definition, WAL mode setup, repository classes
- Depends on: Nothing (uses sqlite3 stdlib)
- Used by: Services, API dependencies
- Schema: Two tables (scenarios, runs) with migration support for additive columns
- Concurrency: WAL mode allows parallel reads with single writer

## Data Flow

### Primary Request Path (HTTP Run Submission)

1. **Request arrives at API** (`api/routers/runs.py:22`) - `POST /scenarios/{scenario_id}/runs`
2. **Validation + fetch scenario** (`api/routers/runs.py:28-30`) - Check scenario exists
3. **Create run row** (`services/run_service.py:55-66`) - Insert PENDING run to DB, commit immediately
4. **Submit to worker pool** (`services/run_service.py:72`) - Schedule async solve, return PENDING run to client
5. **Worker thread executes** (`services/run_service.py:75-101`):
   - Load fixture as `SchedulingProblem` (`ingest/input_adapter.py:45`)
   - Parse stored overrides JSON to `OverrideCall` list (`services/run_service.py:89-90`)
   - Call `engine.solve(problem, config)` → returns `SolveResult`
   - Persist result JSON + solver status to `runs` table
   - Catch any exception, mark run FAILED with error message
6. **Client polls run status** (`api/routers/runs.py:43-49`) - `GET /runs/{run_id}`
   - Returns run record with status (PENDING/RUNNING/COMPLETED/FAILED)
7. **Client fetches result** (when status=COMPLETED) (`api/routers/runs.py:52-64`) - `GET /runs/{run_id}/result`
   - Returns deserialized `SolveResult` (schedule rows, metrics, solver status)

**Threading Model:**
- Request threads: Event loop (Starlette async), each opens own DB connection via dependency
- Worker thread: Single-threaded pool (max 1 concurrent solve), opens own connection, serializes writes
- Database: WAL mode enables concurrent reads while single writer updates
- No shared mutable state across threads except module-level `_pool` (protected by lock)

### Constraint Parsing Flow (NL → Override)

1. **User submits constraint text** (`frontend/src/components/editor/ConstraintInput.tsx`) - `POST /constraints`
2. **API validates + calls LLM** (`api/routers/constraints.py:POST /constraints`):
   - Fetch scenario (validate scenario_id)
   - Call `constraint_service.parse_and_apply()` (`services/constraint_service.py:parse_and_apply()`)
3. **Service parses constraint**:
   - Call `provider.parse_constraints(text)` → `list[OverrideCall]` (LLM call or stub response)
   - Resolve human-readable tokens (member names, task names) to real IDs
   - Validate resolved IDs exist in the loaded problem
   - Partition into applied (valid), rejected (invalid token), clarification (ambiguous)
4. **Persist applied overrides**:
   - Read current `scenario.overrides` JSON (dict keyed by content-hash id)
   - Merge applied overrides, write back to DB
5. **Return structured response** - `{applied: [], rejected: [], clarification_needed: null, no_constraint_found: bool}`
6. **Frontend updates UI** - Display applied overrides list, rejected reasons, request clarification if needed

### Insight Generation Flow (Metrics → NL Report)

1. **Run completed, user requests insights** (`frontend/src/components/results/InsightPanel.tsx`) - `GET /runs/{run_id}/insights`
2. **API routes to insight service** (`api/routers/runs.py:67-91`):
   - Fetch run record (validate run_id exists)
   - Call `insight_service.get_or_generate(conn, provider, run_id)`
3. **Service generates or retrieves insight**:
   - Check if insight already cached in `runs.insight_json`
   - If cached: return deserialized, `ready=true`
   - If not cached + run COMPLETED:
     - Extract solve metrics from result JSON
     - Call `provider.generate_insights(summary_dict)` → plain-text report
     - Cache report in `runs.insight_json`
     - Return `ready=true` + report
   - If run not COMPLETED: return `ready=false` + run status
4. **Return response** - `{ready: bool, report?: str, status?: str, reason?: str}`
5. **Frontend displays** - Insight panel shows report or "still running" message

**Failure modes:**
- LLM provider timeout/quota → `LLMProviderError` → 502 Bad Gateway (D-08)
- Grounding validation failure → `InsightGenerationError` → 502 Bad Gateway (D-06)
- Run not found → 404 Not Found
- Run still PENDING/RUNNING → 200 with `ready=false` (not 409; deliberate per D-07)

### CLI Solve Execution (Synchronous)

1. **User invokes CLI** (`python run.py path/to/fixture.json [engine] [time_limit_s]`)
2. **Run.py main()** (`backend/run.py:14-50`):
   - Parse arguments (fixture path, engine name, time limit)
   - Load fixture → build `SchedulingProblem`
   - Create engine instance
   - Call `engine.solve()` synchronously
   - Print metrics and schedule sample to stdout
   - No database involved, no threading

## Key Abstractions

**SchedulingProblem:**
- Purpose: Immutable input to the solver. Contains members, tasks, demand, shift templates, availability/roster windows.
- Location: `domain/problem.py`
- Pattern: Dataclass with typed fields, helper method `task(task_id)` for lookup
- Horizon: All times stored as **hours from scenario start** (e.g., day-1 17:30 = 17.5h, day-2 06:00 = 30.0h)

**SolveResult:**
- Purpose: Immutable solution output. Schedule rows, metrics, solver stats.
- Location: `domain/result.py`
- Pattern: Dataclass wrapping `ScheduleRow[]`, metrics dict, solver stats (status, objective values)
- Metrics: Include total unmet hours, cost, coverage by function/day, scheduled members/shifts

**SchedulerEngine Protocol:**
- Purpose: Abstract interface for swappable solvers
- Location: `engine/base.py:26-30`
- Pattern: Python Protocol with `solve()` method and `name` property
- Implementation: CP-SAT engine in `engine/cpsat/`

**LLMProvider Protocol:**
- Purpose: Abstract interface for swappable language models
- Location: `llm/base.py:22-28`
- Pattern: Python Protocol with `parse_constraints()` and `generate_insights()` methods, `name` property
- Implementations: Stub, Gemini, OpenRouter
- Boundary: Provider-neutral `OverrideCall` crosses seam; vendor-specific payloads never exposed

**Domain Entities (Types):**
- Location: `domain/types.py`
- Pattern: Frozen dataclasses (immutable, hashable)
- Examples: `Member`, `Task`, `Window`, `Qualification`, `Break`, `ShiftTemplate`, `DemandBand`
- Time representation: All times in hours from scenario start (conversion at adapter boundary)

**OverrideCall:**
- Purpose: Parsed NL constraint representation (tool + args)
- Location: `domain/overrides.py`
- Pattern: Dataclass with id (content hash), tool (function name), args (parameters)
- Validation: Resolved IDs must exist in scenario problem; validated by constraint service

**Repository Pattern:**
- Purpose: Data access layer, encapsulate SQL queries
- Location: `store/repositories.py`
- Pattern: Class constructor takes `sqlite3.Connection`, methods execute queries and return dicts (sqlite3.Row)
- Examples: `ScenarioRepo`, `RunRepo`
- Immutability: Methods return read-only row objects, no direct UPDATE/DELETE on dicts

## Entry Points

**HTTP API Server:**
- Location: `api/main.py:25`
- Invocation: `uv run uvicorn api.main:app --reload` (dev) or `uvicorn api.main:app` (prod)
- Startup: Lifespan handler initializes DB, creates engine
- Shutdown: Lifespan handler shuts down worker pool
- Responsibilities: Bind routers (health, fixtures, scenarios, runs, constraints); mount CORS middleware

**CLI Solver:**
- Location: `run.py:53`
- Invocation: `python run.py [fixture_path] [engine_name] [time_limit_s]`
- Responsibilities: Load fixture, create engine, solve synchronously, print metrics and schedule

**Test Suite:**
- Location: `conftest.py`, `tests/test_*.py`
- Invocation: `pytest` (backend) or `npm test` (frontend)
- Backend: Fixtures override `get_engine()` dependency with stubbed provider; exercise API/service workflows
- Frontend: Vitest with React Testing Library, mocks API client via MSW or direct mocking

**Frontend App:**
- Location: `frontend/src/main.tsx:15`
- Invocation: `npm run dev` (dev) or `npm run build && npm run preview` (prod)
- Initialization: Create QueryClient (TanStack Query), mount RouterProvider and QueryClientProvider
- Responsibilities: Set up React Router, establish SPA entry point

## Architectural Constraints

- **Threading:** Single-worker thread pool for solves (CPU-bound). Event loop never blocks. Each worker thread opens its own DB connection (sqlite3 not thread-safe by default; `check_same_thread=False` set on connections but actual concurrency serialized by pool).
- **Global state:** `_pool: Optional[ThreadPoolExecutor]` in `services/run_service.py` (module-level). Protected by `_pool_lock`. Solves are serialized (max 1 concurrent). High-concurrency deployments require multi-worker pool + distributed solve queue (out of scope for Phase 3).
- **Database schema:** No migrations framework (DDL embedded in `store/db.py`). Manual schema evolution required. WAL pragma enables concurrent reads while single worker writes.
- **Circular imports:** None detected. Import graph flows cleanly upward (API → Services → Domain/Engine → Engine/Store). Domain imports nothing.
- **Time representation:** All times stored as **hours from scenario start** in domain/engine. Conversion happens at adapter boundary (`ingest/scenario_time.py`). Absolute times (ISO 8601) only in API/DB.
- **API CORS:** Resolved once at process/import time (not per-request). Origins stored in Settings, read via `get_settings()` at app construction. `allow_credentials=False` (no cookies/Authorization header needed per D-02).
- **LLM Error Handling:** Provider errors caught at service layer, mapped to 502 Bad Gateway. NL-derived constraints never able to make a solve infeasible (soft overrides only, D-01).
- **Frontend State:** Route state (scenario/run IDs) via React Router, server cache (scenarios, runs, results) via TanStack Query. No Zustand/Redux/Context for server state (Query handles it).

## Anti-Patterns

### Solver Blocking Event Loop

**What happens:** CPU-bound solve runs synchronously on event loop thread.
**Why it's wrong:** Blocks HTTP handling, timeouts, other requests queued.
**Do this instead:** Use single-worker `ThreadPoolExecutor` in `services/run_service.py:38`. Submit solve to pool via `_get_pool().submit(_execute(...))`. Worker thread opens its own DB connection, persists status updates.

### Hard-Coded Solver Engine

**What happens:** Imports `CpSatEngine` directly, engine name not configurable.
**Why it's wrong:** No ability to swap solvers without code changes. Tests must wait for real solves.
**Do this instead:** Use `engine/base.py`'s `create_engine(name)` factory. Register new solver in factory; tests override `get_engine()` dependency. See `engine/cpsat/engine.py:22` for implementation protocol.

### LLM Vendor Lock-in

**What happens:** LLM calls made directly in service logic; provider-specific exceptions cross boundaries.
**Why it's wrong:** Vendor failures (quota, downtime) propagate as untyped exceptions. Hard to swap providers.
**Do this instead:** Behind `LLMProvider` Protocol (`llm/base.py:22`). Implementations catch vendor errors, raise `LLMProviderError` only. Service layer maps to 502. See `llm/gemini.py` and `llm/openrouter.py` for examples.

### Time Zone Ambiguity

**What happens:** Times stored in mixed formats (UTC ISO 8601 in DB, hours from start in domain).
**Why it's wrong:** Off-by-one bugs on timezone boundaries. Midnight crossings compute wrong.
**Do this instead:** All domain times in **hours from scenario start** (stored as float). Conversion at adapter boundary only (`ingest/scenario_time.py`). API always receives/returns ISO 8601 with explicit timezone. See `scenario_time.py:day_window_hours()` for conversion patterns.

### Shared DB Connections Across Threads

**What happens:** Single connection object used by multiple threads (request + worker).
**Why it's wrong:** sqlite3 is not thread-safe by default. Race conditions on schema/data.
**Do this instead:** Each unit of work opens its own connection. API dependency `get_db()` yields per-request. Worker thread calls `db.connect()` before execute. WAL mode enables concurrent reads. See `store/db.py:45` and `services/run_service.py:77`.

### Implicit Solver Config Defaults

**What happens:** `SolverConfig` not passed; engine uses hardcoded defaults.
**Why it's wrong:** Scenario-specific time limits not respected. Debugging hard (are defaults being used?).
**Do this instead:** Always construct `SolverConfig` with explicit overrides. Defaults in dataclass definition (`engine/base.py:12-24`) are a fallback only. Services pass config explicitly: `engine.solve(problem, config)` (see `services/run_service.py:92`).

## Error Handling

**Strategy:** Exceptions at service layer (not API). API catches and maps to HTTP status.

**Patterns:**
- **LookupError** → 404 Not Found (unknown scenario_id, run_id, etc.)
- **HTTPException** → Used in API layer only (FastAPI validation, status/detail)
- **LLMProviderError** → 502 Bad Gateway (vendor failure, quota, auth)
- **InsightGenerationError** → 502 Bad Gateway (grounding validation failure, see D-06)
- **Exception (generic)** → Run marked FAILED with error message in DB (background execution), never propagates to client
- **Pydantic ValidationError** → 422 Unprocessable Entity (request body invalid)

**Run failure:** Any exception in `run_service._execute()` (line 97) caught, logged as `run.error`, status set FAILED. Run never crashes the pool.

**Constraint parsing:** LLM call failures caught in `constraint_service.parse_and_apply()`, returned in response body as rejected constraints or clarification_needed (never raises unless scenario not found).

## Cross-Cutting Concerns

**Logging:**
- CLI: `print()` to stdout (see `run.py`)
- API: No logging; errors persisted to database via service layer
- Background tasks: No logging; exceptions caught and stored in `runs.error` column
- LLM calls: Provider errors caught, mapped to `LLMProviderError`, logged in response/status

**Validation:**
- Request body: Pydantic models in `api/schemas.py` validate at route entry
- Scenario IDs: Service layer fetches from DB, raises `LookupError` if not found
- Fixture paths: Adapter loads JSON, raises on malformed input (caught by service, marked run FAILED)
- Constraint tokens: Service resolves to real IDs, returns clarification if ambiguous (no exception)

**Authentication:**
- None (stateless HTTP API, CORS-enabled for frontend)
- Note: D-02 explicitly states "this app never sends cookies or an Authorization header" — no auth seam needed

**Authorization:**
- None enforced (all endpoints public, scenario IDs are UUIDs, not predictable)

**Monitoring:**
- Run metrics persisted to DB (solver status, objective values, coverage, etc.)
- Insight reports cached in `runs.insight_json` (avoid repeated LLM calls)
- Error messages stored in `runs.error` for debugging failed runs

---

*Architecture analysis: 2026-07-20*
