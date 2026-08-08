<!-- GSD:project-start source:PROJECT.md -->

## Project

**ShiftMind**

ShiftMind (repo `rosterai`) is a workforce scheduling assistant: it loads a
distribution-centre week of workforce + demand data, runs a constraint solver
(OR-Tools CP-SAT) to produce a weekly schedule, and serves the result over an
HTTP API. Milestone v0.3 shipped the **LLM layer**: a user describes a
scheduling constraint change in plain English (any of five solver-hook tools),
it's validated and applied to the solve as a calibrated soft penalty, and a
separate on-demand endpoint turns run metrics into a grounded, plain-language
insight report. Two real, network-backed LLM providers (Gemini, OpenRouter)
sit behind a config-driven `LLMProvider` seam alongside the deterministic stub
that keeps default CI keyless. Milestone v0.4 shipped the **frontend**: the
full assistant is now usable end-to-end from a browser — create a scenario
from a fixture, shape it with plain-English constraints, trigger a solve and
watch it run, and read the resulting schedule, coverage, and insight report —
without ever touching curl or raw JSON.

**Core Value:** A user can express a scheduling constraint change in plain English and get back a
re-solved schedule that honors it (as a soft constraint) plus a readable
explanation of what changed — without touching solver code or JSON.

### Evidence files — read before writing one

Any story producing an `evidence/**/*.json` file MUST follow
`docs/EVIDENCE-CONVENTION.md`: **commit the code, then measure, then generate
through `backend/scripts/evidence_binding.py`, then commit the evidence
separately.** Never hand-type an evidence file — that is what produced an
unreproducible `git_commit` in all four Epic 1 evidence files. Gate A
operations (cutover, legacy-route flag, NVDA pass, readiness report) are in
`docs/GATE-A-RUNBOOK.md`.

### Constraints

- **Tech stack**: Python backend, OR-Tools CP-SAT solver, FastAPI, SQLite (WAL),
  uv-managed deps — established in Phases 1–2, not up for change in this milestone.

- **Architecture**: Domain stays pure (no solver/web/LLM imports); LLM access goes
  behind an `LLMProvider` Protocol; overrides applied only in the engine layer.

- **Safety**: NL-derived constraints must be validated against real scenario IDs
  and applied as soft constraints only — never able to make a solve infeasible.

- **Resilience**: Insight generation is a separate post-run step so an LLM failure
  never invalidates a successfully computed schedule.

- **Testing**: No live LLM API in CI — a stubbed provider must drive tests.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.10–3.12 - Backend: scheduling engine, FastAPI API server, domain logic, ingest adapters, CLI tooling (see `backend/pyproject.toml`)
- TypeScript 5.9.3 - Frontend: React components, hooks, API client, routing, type-safe interfaces
- JavaScript/JSX - React runtime and component structure
- CSS/Tailwind - Frontend styling via Tailwind CSS 4.3.2 with `@tailwindcss/vite` plugin (no separate config file needed)
- HTML5 - Frontend markup structure via React

## Runtime

- Python 3.10–3.12 (backend)
- Node.js (frontend)
- **Backend:** uv (Astral's Python package manager)
- **Frontend:** npm (Node package manager)

## Frameworks

- FastAPI (latest) - HTTP API server for scenario/run lifecycle (see `backend/api/main.py:26`)
- React 19.2.7 - Frontend component library and state management
- Vite 8.1.1 - Frontend build tool and dev server
- OR-Tools CP-SAT 9.11.4210 - Constraint programming solver for workforce scheduling
- React Router 8.2.0 - Client-side routing for multi-page frontend UI
- **Backend:** pytest - Test runner configured in `backend/pyproject.toml:23-28`
- **Frontend:** Vitest 4.1.10 - Fast unit test runner with Jest-compatible API
- TypeScript 5.9.3 - Type checking for frontend
- Oxlint 1.71.0 - Fast JavaScript/TypeScript linter for frontend

## Key Dependencies

- `ortools==9.11.4210` - Constraint solver engine; core to scheduling optimization
- `fastapi` - Web framework for HTTP API
- `uvicorn[standard]` - ASGI server for FastAPI (includes HTTP upgrade support)
- `google-genai>=2.10.0` - Google's unified generative AI SDK for Gemini support (see `backend/llm/gemini.py`)
- `openai>=1.40` - OpenAI SDK, used for OpenRouter provider (OpenRouter exposes OpenAI-compatible API)
- `pandas` - Data manipulation (optional in current code; listed as dependency)
- `python-dotenv>=1.2.2` - Environment variable management from `.env` file
- `pytest` (dev) - Test runner
- `httpx` (dev) - Async HTTP client for FastAPI test client
- `react@19.2.7` - UI library
- `react-dom@19.2.7` - React DOM renderer
- `react-router@8.2.0` - Client-side routing
- `@tanstack/react-query@5.101.2` - Data fetching, caching, background synchronization (previously "React Query")
- `openapi-fetch@0.17.0` - Type-safe REST client generated from OpenAPI spec
- `tailwindcss@4.3.2` - Utility-first CSS framework
- `@tailwindcss/vite@4.3.2` - Vite integration for Tailwind (replaces PostCSS)
- `tailwind-merge@3.6.0` - Merge Tailwind class utilities without conflicts
- `shadcn@4.13.0` - Headless component library builder
- `radix-ui@1.6.2` - Accessible primitive components (used by shadcn)
- `lucide-react@1.24.0` - Icon library
- `class-variance-authority@0.7.1` - Type-safe CSS class composition
- `clsx@2.1.1` - Conditional className concatenation
- `recharts@3.9.2` - Charting library built on React components
- `vitest@4.1.10` - Test runner
- `@testing-library/react@16.3.2` - React component testing utilities
- `@testing-library/jest-dom@6.9.1` - DOM matchers for assertions
- `jsdom@29.1.1` - DOM implementation for Node.js (test environment)
- `typescript@5.9.3` - Type checker
- `@vitejs/plugin-react@6.0.3` - React plugin for Vite
- `openapi-typescript@7.13.0` - Generate TypeScript types from OpenAPI spec
- `oxlint@1.71.0` - Fast linter

## Configuration

- Loaded via `backend/settings.py` from `.env` file and OS environment
- Settings object: `Settings` dataclass (frozen, immutable)
- **Required variables:**
- **LLM Provider Configuration:**
- **CORS Configuration:**
- Loaded via Vite's `import.meta.env` at build time and runtime
- **Required variables:**
- `.env` file not committed; copy from `frontend/.env.example` and customize
- **Backend:**
- **Frontend:**
- OpenAPI Schema → TypeScript Types:

## Platform Requirements

- Python 3.10, 3.11, or 3.12 (backend)
- Node.js 18+ (frontend)
- uv package manager (backend)
- npm or Node's package manager (frontend)
- SQLite 3 (built into Python 3.x)
- Platform: Linux, macOS, or Windows (including WSL2 for OR-Tools compatibility)
- **Frontend:**
- **Backend:**
- **Frontend:** S3 + CloudFront (static content delivery network)
- **Backend:** Docker container on AWS App Runner / ECS / EC2 (not Lambda — CP-SAT solves are CPU-heavy and long-running)
- Database: SQLite locally; future migration to RDS or EFS for distributed deployments

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## BACKEND (Python)

### Naming Patterns

- `snake_case` for all modules: `run_service.py`, `input_adapter.py`, `scenarios.py`
- Router files grouped in subdirectories: `api/routers/scenarios.py`, `api/routers/runs.py`
- Config and constant files: `settings.py`, `constants.py`
- `snake_case` for all function names: `create_scenario()`, `load_problem()`, `set_running()`
- Private functions prefixed with underscore: `_now()`, `_rows()`, `_to_float()`, `_dict()`, `_clip()`
- Async context managers use `@asynccontextmanager` decorator and lowercase names: `lifespan()`
- `snake_case` for all variables and attributes: `scenario_id`, `contact_id`, `time_limit_s`
- Dictionary keys use `snake_case`: `"time_limit_s"`, `"solver_status"`
- Loop variables use short names: `i`, `r`, `s`, `e`, `m` for meaningful context
- `PascalCase` for all classes: `SchedulingProblem`, `RunOut`, `Member`, `Task`, `Window`
- `PascalCase` for enum types: `WindowKind`, `DemandFamily`
- `UPPERCASE` with underscores: `DEFAULT_TASK_RATE`, `MAX_ITERATIONS`
- Modern Python 3.10+ syntax with `|` for unions (not `Union[]`): `float | None`, `str | None`, `dict[str, int]`
- Always present on function parameters and return types
- Example from `domain/types.py`:

### Code Style

- No explicit formatter configured; follows PEP 8 implicitly
- 100-character line length observed in multi-line constructs
- Proper spacing around operators (`=`, `==`, `+`) and after commas
- No explicit linter configured (`.pylintrc`, `ruff.toml` absent)
- Code adheres to PEP 8 via convention

### Import Organization

- Absolute imports from project root (not relative): `from domain.types import Member` not `from ..domain.types import`
- No path aliases configured; `conftest.py` adds backend directory to `sys.path` so absolute imports resolve
- Example from `api/routers/scenarios.py`:

### Error Handling

- Raise `HTTPException` with status codes and detail messages
- Example from `api/routers/scenarios.py`:
- Raise domain exceptions; let caller (router/parent) handle with `HTTPException`
- Exceptions propagate upward; caller (API) determines HTTP response
- Catch **all** exceptions: `except Exception as exc: # noqa: BLE001`
- Persist error string to database (`run.error` field), never crash worker
- Example from `services/run_service.py:97`:
- Use Pydantic models (FastAPI schemas) for request validation
- FastAPI automatically validates and returns 422 on validation errors
- Example: `ScenarioCreate` schema validates `name`, `fixture`, `time_limit_s`

### Logging

- **CLI operations** (`run.py`): Use `print()` for output
- **API routes**: No logging framework configured; errors persisted to database via service layer
- **Background tasks**: No logging; exceptions caught and stored in `runs.error` column
- **Test setup** (`conftest.py`): Uses `dotenv_values()` to read local `.env` without overriding test defaults

### Comments

- Always present; explain module purpose, usage, or design decisions
- Example from `run_service.py`:
- Minimal; rely on type hints and name clarity
- Include if docstring adds value beyond the signature
- Explain "why", not "what"
- Example from `api/main.py:28-34`:

### Function Design

- Type hints on all parameters: `def create_scenario(conn: sqlite3.Connection, name: str, fixture: str)`
- Default values at the end: `time_limit_s: float = 60.0`
- Return type always annotated: `-> dict`, `-> Optional[dict]`, `-> SolveResult`
- Return early for error cases
- Single exit path preferred but not enforced

### Module Design

- All public names exported (no explicit `__all__` lists)
- Example: `engine/base.py` exports `SchedulerEngine`, `SolverConfig`, `create_engine()`
- Immutable types use `@dataclass(frozen=True)` (hashable, thread-safe)
- Mutable types use `@dataclass` with `field(default_factory=list)` for mutable defaults
- Example from `domain/types.py`:
- Use `typing.Protocol` for abstract interfaces (pluggable backends)
- Example: `engine/base.py:18` defines `SchedulerEngine` protocol; `engine/cpsat/engine.py:22` implements
- Thin data-access layer wrapping SQLite queries
- Returns `sqlite3.Row` objects (dict-like)
- Example: `store/repositories.py:ScenarioRepo.get(scenario_id)`
- Orchestrates business logic; operates on repos
- Example: `services/scenario_service.py` manages scenario CRUD and fixture loading
- FastAPI endpoints; use dependency injection for DB connections and engine
- Example: `api/routers/scenarios.py:create_scenario()` uses `Depends(get_db)`, `Depends(get_settings)`

## FRONTEND (React + TypeScript)

### Naming Patterns

- React components: `PascalCase.tsx` (e.g., `ScenarioHeader.tsx`, `ConstraintInput.tsx`)
- Hooks: `camelCase`, prefixed `use`: `useScenarios.ts`, `useApplyConstraint.ts`
- Utilities/libraries: `camelCase.ts` (e.g., `errors.ts`, `formatShiftWindow.ts`)
- Test files: co-located with implementation: `Component.test.tsx`, `lib.test.ts`
- `camelCase` for all function names and variables: `getErrorStatus()`, `scenarioId`, `isLoading`
- Abbreviated loop variables: `r` for row, `i` for index
- `PascalCase` component names: `ScenarioHeader`, `ConstraintInput`
- Export as named exports: `export function ScenarioHeader({ ... })`
- Props as destructured object parameter with inline type annotation
- `camelCase`, prefixed `use`: `useScenarios()`, `useApplyConstraint()`
- Thin TanStack Query wrappers: `useScenarios()` wraps `listScenarios()`
- `UPPERCASE` or `camelCase` depending on scope
- Example: `MAX_LENGTH = 2000`, `COUNTER_THRESHOLD = 1800`
- TypeScript strict mode enabled (`noUnusedLocals`, `noUnusedParameters`)
- Union types with `|`: `string | null`, `number | undefined`
- Derived types from generated OpenAPI schema preferred over hand-authored interfaces
- Example from `src/api/scenarios.ts`:

### Code Style

- No explicit formatter configured (likely Prettier defaults); follows eslint/oxlint rules
- Consistent spacing around operators and after commas
- Multi-line JSX fragments use readable indentation
- `oxlint` (Rust-based linter)
- Config: `.oxlintrc.json` enables React and TypeScript plugins
- Rules enforced:
- `noUnusedLocals`: true — unused variables error
- `noUnusedParameters`: true — unused parameters error
- `noFallthroughCasesInSwitch`: true — enforce default case

### Import Organization

- `@/*` resolves to `./src/*` (configured in `vite.config.ts` and `tsconfig.json`)
- All imports use absolute `@` alias: `@/api/scenarios`, `@/hooks/useScenarios`, `@/components/ui/button`
- OpenAPI schema imported as: `import type { paths, components } from "@/api/schema"`
- Derived types: `type CreateScenarioBody = paths["/scenarios"]["post"]["requestBody"]["content"]["application/json"]`

### Error Handling

- Throw error objects with HTTP status attached: `throw { status: response.status, ...error }`
- Example from `src/api/scenarios.ts:48`:
- TanStack Query surfaces thrown errors as `query.error`/`mutation.error` (typed `unknown`)
- Use `getErrorStatus(error)` helper to safely extract status: `const status = getErrorStatus(error)`
- Status discrimination drives branching (404 → terminal view, 503 → provider-down banner)
- Example `src/lib/errors.ts`: Centralized `getErrorStatus()` prevents repeated type casts

### Comments

- Always present; explain purpose and reference design docs or tickets
- Example from `src/components/editor/ConstraintInput.tsx:1-22`:
- Explain "why", cite relevant design tickets
- Example from `src/components/editor/ConstraintInput.tsx:72-76`:

### React Patterns

- State-driven forms with `useState`, clear on success conditions (not always on HTTP 200)
- Example from `src/components/editor/ConstraintInput.tsx:70-75`:
- Thin TanStack Query wrappers; business logic belongs in components
- Example `src/hooks/useScenarios.ts`:
- TanStack Query `enabled` gates conditional queries
- Props passed to components for flexibility; dependency overrides in tests
- Use `react-router` for navigation; real route tests use `createMemoryRouter`
- Example from `src/components/editor/ScenarioHeader.test.tsx:35-45`:

### Module Design

- Thin typed wrappers over `openapi-fetch` client
- No hand-authored interfaces; derive from generated OpenAPI schema
- Every endpoint request/response shape comes from `./schema.d.ts`
- TanStack Query wrappers; no business logic
- Thin pass-through of query configuration
- Query keys are cross-plan contracts (e.g., `["scenarios"]` invalidated on creation)
- Pure functions: `getErrorStatus()`, `formatTimestamp()`, `formatShiftWindow()`
- Type safety via TypeScript; centralize repeated type casts
- Organize by feature/domain: `layout/`, `editor/`, `results/`
- Props interface inline or as dedicated type
- Export as named exports (not default)

## Cross-Codebase Patterns

### Type Safety Philosophy

- Static type hints on all functions (PEP 484)
- Pydantic models for validation
- Strict-by-design (exceptions throw, don't return error codes)
- Strict TypeScript compiler flags
- Types derived from generated OpenAPI schema (source of truth)
- Hand-authored types only when schema generation cannot provide them

### Error Handling Philosophy

### Documentation Style

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

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

- **Domain-Driven:** Pure domain types (`domain/`) import nothing from framework or solver
- **Pluggable Engines:** Solver and LLM backends swappable via Protocol + factory pattern
- **Async-First API:** FastAPI async request handling + single-worker thread pool for CPU-bound solves
- **Type Safety:** Full TypeScript frontend with OpenAPI-generated client, Python type hints throughout backend
- **Database Concurrency:** SQLite WAL mode allows worker thread to write run status while request threads read
- **Clean Boundaries:** LLM access behind `LLMProvider` Protocol; NL constraints validated and applied as soft overrides only

## Layers

- Purpose: Expose solve capabilities via REST, manage scenario lifecycle, poll run status, apply NL constraint overrides
- Location: `api/main.py`, `api/routers/`, `api/schemas.py`, `api/deps.py`
- Contains: FastAPI app, route handlers, Pydantic request/response models, dependency injection
- Depends on: Services, Domain, Engine, Store, LLM
- Used by: HTTP clients (frontend), external API consumers
- Incoming: HTTP POST/GET requests (JSON bodies, path/query params)
- Outgoing: JSON responses (200/201/400/404/409/502/503)
- Purpose: Orchestrate use cases (scenario CRUD, run submission, async execution, constraint parsing, insight generation)
- Location: `services/*.py`
- Contains: Business logic for scenarios, runs, constraints, insights, and result serialization
- Depends on: Domain, Engine, Store, Ingest, LLM
- Used by: API routers, CLI
- Entry points: `scenario_service.get_scenario()`, `run_service.submit_run()`, `constraint_service.parse_and_apply()`, `insight_service.get_or_generate()`
- Error handling: Raises `LookupError` for missing resources (404); partial failures returned in structured response bodies
- Purpose: Immutable representations of problems, solutions, and workflow entities. Framework-agnostic.
- Location: `domain/`
- Contains: `SchedulingProblem`, `SolveResult`, `Member`, `Task`, `Window`, `Qualification`, `OverrideCall`, etc.
- Depends on: Nothing (no framework imports, pure dataclasses/frozen dataclasses)
- Used by: Engine, Services, Ingest, API (serialization)
- Guarantees: Hashable types (frozen dataclasses), correct default values, time in hours from scenario start
- Purpose: Adapt external fixture format (JSON) into domain `SchedulingProblem`
- Location: `ingest/`
- Contains: `input_adapter.py` (main transformer), `scenario_time.py` (time utilities)
- Depends on: Domain
- Used by: Services (run executor), CLI
- Responsibility: Parse JSON, apply clipping to scenario horizon, build members/tasks/demand/templates, resolve wage caps
- Purpose: Abstract solver backend. Pluggable via factory.
- Location: `engine/base.py` (protocol definition)
- Contains: `SchedulerEngine` Protocol, `SolverConfig` dataclass, `create_engine()` factory
- Depends on: Domain
- Implementations: `engine/cpsat/` (Google OR-Tools CP-SAT)
- Used by: Services, CLI
- Interface: `solve(problem: SchedulingProblem, config: SolverConfig) -> SolveResult`
- Purpose: Build constraint model and solve using Google OR-Tools lexicographic optimization
- Location: `engine/cpsat/engine.py`, `builder.py`, `objective.py`
- Depends on: Domain, Google OR-Tools, Domain overrides
- Responsibilities: Model construction (members, tasks, demand, shifts, qualifications, availability), two-round solve (round 1: maximize coverage, round 2: minimize cost subject to round-1 objective)
- Entry: `CpSatEngine.solve()` returns `SolveResult` with schedule rows, metrics, solver status
- Purpose: Abstract language model backend for constraint parsing and insight generation
- Location: `llm/base.py` (protocol), `llm/stub.py`, `llm/gemini.py`, `llm/openrouter.py` (implementations)
- Contains: `LLMProvider` Protocol, `LLMProviderError` exception, factory
- Implementations:
- Interface:
- Used by: Constraint service (constraint parsing), Insight service (report generation)
- Purpose: SQLite persistence, data access
- Location: `store/db.py` (connection, schema, migrations), `store/repositories.py` (DAO)
- Contains: Database connection management, schema definition, WAL mode setup, repository classes
- Depends on: Nothing (uses sqlite3 stdlib)
- Used by: Services, API dependencies
- Schema: Two tables (scenarios, runs) with migration support for additive columns
- Concurrency: WAL mode allows parallel reads with single writer

## Data Flow

### Primary Request Path (HTTP Run Submission)

- Request threads: Event loop (Starlette async), each opens own DB connection via dependency
- Worker thread: Single-threaded pool (max 1 concurrent solve), opens own connection, serializes writes
- Database: WAL mode enables concurrent reads while single writer updates
- No shared mutable state across threads except module-level `_pool` (protected by lock)

### Constraint Parsing Flow (NL → Override)

### Insight Generation Flow (Metrics → NL Report)

- LLM provider timeout/quota → `LLMProviderError` → 502 Bad Gateway (D-08)
- Grounding validation failure → `InsightGenerationError` → 502 Bad Gateway (D-06)
- Run not found → 404 Not Found
- Run still PENDING/RUNNING → 200 with `ready=false` (not 409; deliberate per D-07)

### CLI Solve Execution (Synchronous)

## Key Abstractions

- Purpose: Immutable input to the solver. Contains members, tasks, demand, shift templates, availability/roster windows.
- Location: `domain/problem.py`
- Pattern: Dataclass with typed fields, helper method `task(task_id)` for lookup
- Horizon: All times stored as **hours from scenario start** (e.g., day-1 17:30 = 17.5h, day-2 06:00 = 30.0h)
- Purpose: Immutable solution output. Schedule rows, metrics, solver stats.
- Location: `domain/result.py`
- Pattern: Dataclass wrapping `ScheduleRow[]`, metrics dict, solver stats (status, objective values)
- Metrics: Include total unmet hours, cost, coverage by function/day, scheduled members/shifts
- Purpose: Abstract interface for swappable solvers
- Location: `engine/base.py:26-30`
- Pattern: Python Protocol with `solve()` method and `name` property
- Implementation: CP-SAT engine in `engine/cpsat/`
- Purpose: Abstract interface for swappable language models
- Location: `llm/base.py:22-28`
- Pattern: Python Protocol with `parse_constraints()` and `generate_insights()` methods, `name` property
- Implementations: Stub, Gemini, OpenRouter
- Boundary: Provider-neutral `OverrideCall` crosses seam; vendor-specific payloads never exposed
- Location: `domain/types.py`
- Pattern: Frozen dataclasses (immutable, hashable)
- Examples: `Member`, `Task`, `Window`, `Qualification`, `Break`, `ShiftTemplate`, `DemandBand`
- Time representation: All times in hours from scenario start (conversion at adapter boundary)
- Purpose: Parsed NL constraint representation (tool + args)
- Location: `domain/overrides.py`
- Pattern: Dataclass with id (content hash), tool (function name), args (parameters)
- Validation: Resolved IDs must exist in scenario problem; validated by constraint service
- Purpose: Data access layer, encapsulate SQL queries
- Location: `store/repositories.py`
- Pattern: Class constructor takes `sqlite3.Connection`, methods execute queries and return dicts (sqlite3.Row)
- Examples: `ScenarioRepo`, `RunRepo`
- Immutability: Methods return read-only row objects, no direct UPDATE/DELETE on dicts

## Entry Points

- Location: `api/main.py:25`
- Invocation: `uv run uvicorn api.main:app --reload` (dev) or `uvicorn api.main:app` (prod)
- Startup: Lifespan handler initializes DB, creates engine
- Shutdown: Lifespan handler shuts down worker pool
- Responsibilities: Bind routers (health, fixtures, scenarios, runs, constraints); mount CORS middleware
- Location: `run.py:53`
- Invocation: `python run.py [fixture_path] [engine_name] [time_limit_s]`
- Responsibilities: Load fixture, create engine, solve synchronously, print metrics and schedule
- Location: `conftest.py`, `tests/test_*.py`
- Invocation: `pytest` (backend) or `npm test` (frontend)
- Backend: Fixtures override `get_engine()` dependency with stubbed provider; exercise API/service workflows
- Frontend: Vitest with React Testing Library, mocks API client via MSW or direct mocking
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

### Hard-Coded Solver Engine

### LLM Vendor Lock-in

### Time Zone Ambiguity

### Shared DB Connections Across Threads

### Implicit Solver Config Defaults

## Error Handling

- **LookupError** → 404 Not Found (unknown scenario_id, run_id, etc.)
- **HTTPException** → Used in API layer only (FastAPI validation, status/detail)
- **LLMProviderError** → 502 Bad Gateway (vendor failure, quota, auth)
- **InsightGenerationError** → 502 Bad Gateway (grounding validation failure, see D-06)
- **Exception (generic)** → Run marked FAILED with error message in DB (background execution), never propagates to client
- **Pydantic ValidationError** → 422 Unprocessable Entity (request body invalid)

## Cross-Cutting Concerns

- CLI: `print()` to stdout (see `run.py`)
- API: No logging; errors persisted to database via service layer
- Background tasks: No logging; exceptions caught and stored in `runs.error` column
- LLM calls: Provider errors caught, mapped to `LLMProviderError`, logged in response/status
- Request body: Pydantic models in `api/schemas.py` validate at route entry
- Scenario IDs: Service layer fetches from DB, raises `LookupError` if not found
- Fixture paths: Adapter loads JSON, raises on malformed input (caught by service, marked run FAILED)
- Constraint tokens: Service resolves to real IDs, returns clarification if ambiguous (no exception)
- None (stateless HTTP API, CORS-enabled for frontend)
- Note: D-02 explicitly states "this app never sends cookies or an Authorization header" — no auth seam needed
- None enforced (all endpoints public, scenario IDs are UUIDs, not predictable)
- Run metrics persisted to DB (solver status, objective values, coverage, etc.)
- Insight reports cached in `runs.insight_json` (avoid repeated LLM calls)
- Error messages stored in `runs.error` for debugging failed runs

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| bmad-advanced-elicitation | 'Push the LLM to reconsider, refine, and improve its recent output. Use when user asks for deeper critique or mentions a known deeper critique method, e.g. socratic, first principles, pre-mortem, red team.' | `.claude/skills/bmad-advanced-elicitation/SKILL.md` |
| bmad-agent-analyst | Strategic business analyst and requirements expert. Use when the user asks to talk to Mary or requests the business analyst. | `.claude/skills/bmad-agent-analyst/SKILL.md` |
| bmad-agent-architect | System architect and technical design leader. Use when the user asks to talk to Winston or requests the architect. | `.claude/skills/bmad-agent-architect/SKILL.md` |
| bmad-agent-builder | Builds, edits or analyzes Agent Skills through conversational discovery. Use when the user requests to "Create an Agent", "Analyze an Agent" or "Edit an Agent". | `.claude/skills/bmad-agent-builder/SKILL.md` |
| bmad-agent-dev | Senior software engineer for story execution and code implementation. Use when the user asks to talk to Amelia or requests the developer agent. | `.claude/skills/bmad-agent-dev/SKILL.md` |
| bmad-agent-pm | Product manager for PRD creation and requirements discovery. Use when the user asks to talk to John or requests the product manager. | `.claude/skills/bmad-agent-pm/SKILL.md` |
| bmad-agent-tech-writer | Technical documentation specialist and knowledge curator. Use when the user asks to talk to Paige or requests the tech writer. | `.claude/skills/bmad-agent-tech-writer/SKILL.md` |
| bmad-agent-ux-designer | UX designer and UI specialist. Use when the user asks to talk to Sally or requests the UX designer. | `.claude/skills/bmad-agent-ux-designer/SKILL.md` |
| bmad-architecture | 'Produce the architecture: a lean spine of invariants that keeps everything built from it consistent, projected into whatever format the work needs. Use when the user says "create the architecture", "create technical architecture", "architecture spine", or "create a solution design".' | `.claude/skills/bmad-architecture/SKILL.md` |
| bmad-bmb-setup | Sets up BMad Builder module in a project. Use when the user requests to 'install bmb module', 'configure BMad Builder', or 'setup BMad Builder'. | `.claude/skills/bmad-bmb-setup/SKILL.md` |
| bmad-brainstorming | Facilitate a brainstorming session using diverse creative techniques. Use when the user says 'help me brainstorm' or 'help me ideate'. | `.claude/skills/bmad-brainstorming/SKILL.md` |
| bmad-check-implementation-readiness | 'Validate PRD, UX, Architecture and Epics specs are complete. Use when the user says "check implementation readiness".' | `.claude/skills/bmad-check-implementation-readiness/SKILL.md` |
| bmad-checkpoint-preview | 'LLM-assisted human-in-the-loop review. Make sense of a change, focus attention where it matters, test. Use when the user says "checkpoint", "human review", or "walk me through this change".' | `.claude/skills/bmad-checkpoint-preview/SKILL.md` |
| bmad-cis-agent-brainstorming-coach | Elite brainstorming specialist for facilitated ideation sessions. Use when the user asks to talk to Carson or requests the Brainstorming Specialist. | `.claude/skills/bmad-cis-agent-brainstorming-coach/SKILL.md` |
| bmad-cis-agent-creative-problem-solver | Master problem solver for systematic problem-solving methodologies. Use when the user asks to talk to Dr. Quinn or requests the Master Problem Solver. | `.claude/skills/bmad-cis-agent-creative-problem-solver/SKILL.md` |
| bmad-cis-agent-design-thinking-coach | Design thinking maestro for human-centered design processes. Use when the user asks to talk to Maya or requests the Design Thinking Maestro. | `.claude/skills/bmad-cis-agent-design-thinking-coach/SKILL.md` |
| bmad-cis-agent-innovation-strategist | Disruptive innovation oracle for business model innovation and strategic disruption. Use when the user asks to talk to Victor or requests the Disruptive Innovation Oracle. | `.claude/skills/bmad-cis-agent-innovation-strategist/SKILL.md` |
| bmad-cis-agent-presentation-master | Visual communication and presentation expert for slide decks, pitch decks, and visual storytelling. Use when the user asks to talk to Caravaggio or requests the Presentation Expert. | `.claude/skills/bmad-cis-agent-presentation-master/SKILL.md` |
| bmad-cis-agent-storyteller | Master storyteller for compelling narratives using proven frameworks. Use when the user asks to talk to Sophia or requests the Master Storyteller. | `.claude/skills/bmad-cis-agent-storyteller/SKILL.md` |
| bmad-cis-design-thinking | 'Guide human-centered design processes using empathy-driven methodologies. Use when the user says "lets run design thinking" or "I want to apply design thinking"' | `.claude/skills/bmad-cis-design-thinking/SKILL.md` |
| bmad-cis-innovation-strategy | 'Identify disruption opportunities and architect business model innovation. Use when the user says "lets create an innovation strategy" or "I want to find disruption opportunities"' | `.claude/skills/bmad-cis-innovation-strategy/SKILL.md` |
| bmad-cis-problem-solving | 'Apply systematic problem-solving methodologies to complex challenges. Use when the user says "guide me through structured problem solving" or "I want to crack this challenge with guided problem solving techniques"' | `.claude/skills/bmad-cis-problem-solving/SKILL.md` |
| bmad-cis-storytelling | 'Craft compelling narratives using story frameworks. Use when the user says "help me with storytelling" or "I want to create a narrative through storytelling"' | `.claude/skills/bmad-cis-storytelling/SKILL.md` |
| bmad-code-review | 'Review code changes adversarially using parallel review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) with structured triage into actionable categories. Use when the user says "run code review" or "review this code"' | `.claude/skills/bmad-code-review/SKILL.md` |
| bmad-correct-course | 'Manage significant changes during sprint execution. Use when the user says "correct course" or "propose sprint change"' | `.claude/skills/bmad-correct-course/SKILL.md` |
| bmad-create-architecture | 'DEPRECATED — consolidated into bmad-architecture create intent - this skill will be removed in v7 in favor of `bmad-architecture`.' | `.claude/skills/bmad-create-architecture/SKILL.md` |
| bmad-create-epics-and-stories | 'Break requirements into epics and user stories. Use when the user says "create the epics and stories list"' | `.claude/skills/bmad-create-epics-and-stories/SKILL.md` |
| bmad-create-prd | 'DEPRECATED — consolidated into bmad-prd create intent - this skill will be removed in v7 in favor of `bmad-prd`.' | `.claude/skills/bmad-create-prd/SKILL.md` |
| bmad-create-story | 'Creates a dedicated story file with all the context the agent will need to implement it later. Use when the user says "create the next story" or "create story [story identifier]"' | `.claude/skills/bmad-create-story/SKILL.md` |
| bmad-customize | Authors and updates customization overrides for installed BMad skills. Use when the user says 'customize bmad', 'override a skill', 'change agent behavior', or 'customize a workflow'. | `.claude/skills/bmad-customize/SKILL.md` |
| bmad-dev-auto | 'One iteration of an unattended development loop. Use when invoked by name.' | `.claude/skills/bmad-dev-auto/SKILL.md` |
| bmad-dev-story | 'Execute story implementation following a context filled story spec file. Use when the user says "dev this story [story file]" or "implement the next story in the sprint plan"' | `.claude/skills/bmad-dev-story/SKILL.md` |
| bmad-document-project | 'Document brownfield projects for AI context. Use when the user says "document this project" or "generate project docs"' | `.claude/skills/bmad-document-project/SKILL.md` |
| bmad-domain-research | 'Conduct domain and industry research. Use when the user says wants to do domain research for a topic or industry' | `.claude/skills/bmad-domain-research/SKILL.md` |
| bmad-edit-prd | 'DEPRECATED — consolidated into bmad-prd update intent - this skill will be removed in v7 in favor of `bmad-prd`.' | `.claude/skills/bmad-edit-prd/SKILL.md` |
| bmad-editorial-review-prose | 'Clinical copy-editor that reviews text for communication issues. Use when user says review for prose or improve the prose' | `.claude/skills/bmad-editorial-review-prose/SKILL.md` |
| bmad-editorial-review-structure | 'Structural editor that proposes cuts, reorganization, and simplification while preserving comprehension. Use when user requests structural review or editorial review of structure' | `.claude/skills/bmad-editorial-review-structure/SKILL.md` |
| bmad-eval-runner | Run a skill's evals and report results. Use when the user wants to evaluate a skill, run evals, benchmark a skill, validate triggers, optimize a description, or grade skill outputs. | `.claude/skills/bmad-eval-runner/SKILL.md` |
| bmad-forge-idea | Pressure-test an idea through persona-driven interrogation until it hardens, proves out, or dies cheaply. Use when the user says 'forge an idea', 'pressure-test this idea', 'stress-test my thinking', or 'harden this idea'. | `.claude/skills/bmad-forge-idea/SKILL.md` |
| bmad-generate-project-context | 'Create project-context.md with AI rules. Use when the user says "generate project context" or "create project context"' | `.claude/skills/bmad-generate-project-context/SKILL.md` |
| bmad-help | 'Analyzes current state and user query to answer BMad questions or recommend the next skill(s) to use. Use when user asks for help, bmad help, what to do next, or what to start with in BMad.' | `.claude/skills/bmad-help/SKILL.md` |
| bmad-index-docs | 'Generates or updates an index.md to reference all docs in the folder. Use if user requests to create or update an index of all files in a specific folder' | `.claude/skills/bmad-index-docs/SKILL.md` |
| bmad-loop-resolve | 'Interactive escalation-resolution workflow for the bmad-loop orchestrator. A bmad-loop run paused on a CRITICAL escalation (a contradiction or gap a dev/review session could not safely resolve alone); you and the human disambiguate the frozen spec so the story can be re-driven. Invoked as /bmad-loop-resolve <story-key>. Unlike the automated dev/review sessions this session is interactive — a human is present and you SHOULD ask.' | `.claude/skills/bmad-loop-resolve/SKILL.md` |
| 'bmad-loop-setup' | Sets up BMAD Loop Skills module in a project. Use when the user requests to 'install bmad-loop module', 'configure BMAD Loop Skills', or 'setup BMAD Loop Skills'. | `.claude/skills/bmad-loop-setup/SKILL.md` |
| bmad-loop-sweep | 'Triage the deferred-work ledger for the bmad-loop orchestrator: verify every open entry against the actual codebase and return a machine-readable partition (bundles, already-resolved, blocked, skip, human decisions). Also migrates legacy pre-DW-format ledgers when invoked with --migrate. Automation-only — invoked by bmad-loop sweep runs, not by humans.' | `.claude/skills/bmad-loop-sweep/SKILL.md` |
| bmad-market-research | 'Conduct market research on competition and customers. Use when the user says they need market research' | `.claude/skills/bmad-market-research/SKILL.md` |
| bmad-module-builder | Plans, creates, and validates BMad modules. Use when the user requests to 'ideate module', 'plan a module', 'create module', 'build a module', or 'validate module'. | `.claude/skills/bmad-module-builder/SKILL.md` |
| bmad-party-mode | 'Orchestrates lively group discussions between installed BMAD agents or custom personas, and helps author custom parties. Use when the user requests party mode, a roundtable, or multiple agent perspectives — or wants to create/configure a party, define personas, or build an AI focus-group panel.' | `.claude/skills/bmad-party-mode/SKILL.md` |
| bmad-prd | Create, update, or validate a PRD. Use when the user wants help producing, editing, or validating a PRD. | `.claude/skills/bmad-prd/SKILL.md` |
| bmad-prfaq | Working Backwards PRFAQ challenge that stress-tests a product concept customer-first. Use when the user requests to 'create a PRFAQ', 'work backwards', or 'run the PRFAQ challenge'. | `.claude/skills/bmad-prfaq/SKILL.md` |
| bmad-product-brief | Create, update, or validate a product brief. Use when the user wants help producing, editing, or validating a brief. | `.claude/skills/bmad-product-brief/SKILL.md` |
| bmad-qa-generate-e2e-tests | 'Generate end to end automated tests for existing features. Use when the user says "create qa automated tests for [feature]"' | `.claude/skills/bmad-qa-generate-e2e-tests/SKILL.md` |
| bmad-quick-dev | 'Implements any user intent, requirement, story, bug fix or change request by producing clean working code artifacts that follow the project''s existing architecture, patterns and conventions. Use when the user wants to build, fix, tweak, refactor, add or modify any code, component or feature.' | `.claude/skills/bmad-quick-dev/SKILL.md` |
| bmad-retrospective | 'Post-epic review to extract lessons and assess success. Use when the user says "run a retrospective" or "lets retro the epic [epic]"' | `.claude/skills/bmad-retrospective/SKILL.md` |
| bmad-review-adversarial-general | 'Perform a Cynical Review and produce a findings report. Use when the user requests a critical review of something' | `.claude/skills/bmad-review-adversarial-general/SKILL.md` |
| bmad-review-edge-case-hunter | 'Walk every branching path and boundary condition in content, report only unhandled edge cases. Orthogonal to adversarial review - method-driven not attitude-driven. Use when you need exhaustive edge-case analysis of code, specs, or diffs.' | `.claude/skills/bmad-review-edge-case-hunter/SKILL.md` |
| bmad-shard-doc | 'Splits large markdown documents into smaller, organized files based on level 2 (default) sections. Use if the user says perform shard document' | `.claude/skills/bmad-shard-doc/SKILL.md` |
| bmad-spec | Distill any intent input into the SPEC kernel + companions — the canonical, preservation-validated machine contract for downstream work. Use when the user says "create a spec", "distill this into a spec", "validate this spec", or "update the spec". | `.claude/skills/bmad-spec/SKILL.md` |
| bmad-sprint-planning | 'Generate sprint status tracking from epics. Use when the user says "run sprint planning" or "generate sprint plan"' | `.claude/skills/bmad-sprint-planning/SKILL.md` |
| bmad-sprint-status | 'Summarize sprint status and surface risks. Use when the user says "check sprint status" or "show sprint status"' | `.claude/skills/bmad-sprint-status/SKILL.md` |
| bmad-tea | Master Test Architect and Quality Advisor. Use when the user asks to talk to Murat or requests the Test Architect. | `.claude/skills/bmad-tea/SKILL.md` |
| bmad-teach-me-testing | 'Teach testing progressively through structured sessions. Use when user says "lets learn testing" or "I want to study test practices"' | `.claude/skills/bmad-teach-me-testing/SKILL.md` |
| bmad-technical-research | 'Conduct technical research on technologies and architecture. Use when the user says they would like to do or produce a technical research report' | `.claude/skills/bmad-technical-research/SKILL.md` |
| bmad-testarch-atdd | 'Generate red-phase acceptance test scaffolds using the TDD cycle. Use when the user says "lets write acceptance tests" or "I want to do ATDD"' | `.claude/skills/bmad-testarch-atdd/SKILL.md` |
| bmad-testarch-automate | 'Expand test automation coverage for codebase. Use when user says "lets expand test coverage" or "I want to automate tests"' | `.claude/skills/bmad-testarch-automate/SKILL.md` |
| bmad-testarch-ci | 'Scaffold CI/CD quality pipeline with test execution. Use when the user says "lets setup CI pipeline" or "I want to create quality gates"' | `.claude/skills/bmad-testarch-ci/SKILL.md` |
| bmad-testarch-framework | 'Initialize test framework with Playwright or Cypress. Use when the user says "lets setup test framework" or "I want to initialize testing framework"' | `.claude/skills/bmad-testarch-framework/SKILL.md` |
| bmad-testarch-nfr | 'Audit NFR evidence for performance, security, reliability, and scalability. Use when implementation evidence exists and the user says "audit NFR evidence", "audit NFRs", or "evaluate non-functional requirements"' | `.claude/skills/bmad-testarch-nfr/SKILL.md` |
| bmad-testarch-test-design | 'Create system-level or epic-level test plans. Use when the user says "lets design test plan" or "I want to create test strategy"' | `.claude/skills/bmad-testarch-test-design/SKILL.md` |
| bmad-testarch-test-review | 'Review test quality using best practices validation. Use when user says "lets review tests" or "I want to evaluate test quality"' | `.claude/skills/bmad-testarch-test-review/SKILL.md` |
| bmad-testarch-trace | 'Generate traceability matrix and quality gate decision. Use when the user says "lets create traceability matrix" or "I want to analyze test coverage"' | `.claude/skills/bmad-testarch-trace/SKILL.md` |
| bmad-ux | Plan UX patterns and design specifications. Use when the user says "lets create UX design" or "create UX specifications" or "help me plan the UX" | `.claude/skills/bmad-ux/SKILL.md` |
| bmad-validate-prd | 'DEPRECATED — consolidated into bmad-prd validate intent - this skill will be removed in v7 in favor of `bmad-prd`.' | `.claude/skills/bmad-validate-prd/SKILL.md` |
| bmad-workflow-builder | Builds, edits, and analyzes workflows and skills. Use when the user requests to "build a workflow", "modify a workflow", "quality check workflow", or "analyze skill". | `.claude/skills/bmad-workflow-builder/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
