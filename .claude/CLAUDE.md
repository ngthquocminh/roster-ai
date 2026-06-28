<!-- GSD:project-start source:PROJECT.md -->

## Project

**ShiftMind — LLM Layer (Phase 3)**

ShiftMind (repo `rosterai`) is a workforce scheduling assistant: it loads a
distribution-centre week of workforce + demand data, runs a constraint solver
(OR-Tools CP-SAT) to produce a weekly schedule, and serves the result over an
HTTP API. This GSD milestone adds the **LLM layer**: describe constraint tweaks
in plain English and have them applied to the solve, and turn run metrics into a
plain-language insight report.

**Core Value:** A user can express a scheduling constraint change in plain English and get back a
re-solved schedule that honors it (as a soft constraint) plus a readable
explanation of what changed — without touching solver code or JSON.

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

- Python 3.10–3.12 - All backend code: scheduling engine, FastAPI server, domain logic, ingest adapters, and CLI tooling

## Runtime

- Python 3.10–3.12 (see `backend/pyproject.toml` requires-python)
- uv (Astral's Python package manager) - Manages dependencies, creates `.venv`, installs from lockfile
- Lockfile: uv.lock (not present in current state; generated on `uv sync`)

## Frameworks

- FastAPI 0.x (latest) - HTTP API server for scenario/run lifecycle
- OR-Tools CP-SAT 9.11.4210 (pinned) - Constraint programming solver for workforce scheduling
- pytest (dev dependency) - Test runner
- uvicorn[standard] - ASGI server for FastAPI

## Key Dependencies

- ortools==9.11.4210 - OR-Tools constraint solver; core to scheduling engine
- fastapi - Web framework for HTTP API
- pandas - Data manipulation (optional in current code; listed as dependency)
- uvicorn[standard] - ASGI server
- sqlite3 (stdlib) - Local database

## Configuration

- No `.env` file in current state; env overrides via OS environment only
- Settings loaded fresh per request so overrides apply at runtime
- `backend/pyproject.toml` - Single source of truth for Python version, dependencies, test paths
- `ROSTERAI_DB` - Path to SQLite database (default: `backend/var/rosterai.db`)
- `ROSTERAI_DATA_DIR` - Path to input fixture directory (default: `<repo>/data`)

## Platform Requirements

- Python 3.10+ (local)
- uv (package manager)
- SQLite (built into Python)
- Platform: Linux, macOS, or Windows (WSL2 noted for ortools on some systems)
- Docker container deployment (noted as AWS ECR target in README.md)
- Python 3.10–3.12 in container
- SQLite or compatible database (current: local file via WAL mode)
- Deployment target: AWS (frontend → S3/CloudFront; backend → App Runner/ECS/EC2)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Snake_case for all Python modules: `input_adapter.py`, `run_service.py`, `scenarios.py`
- Router files grouped in subdirectories: `api/routers/scenarios.py`, `api/routers/runs.py`
- Config files and settings: `settings.py`, `constants.py`
- Snake_case for all functions: `create_scenario()`, `load_problem()`, `set_running()`
- Private functions prefixed with underscore: `_now()`, `_rows()`, `_to_float()`, `_dict()`, `_clip()`
- Async context managers: `lifespan()` defined with `@asynccontextmanager` decorator
- Snake_case for all variables: `scenario_id`, `contact_id`, `time_limit_s`
- Dictionary keys use snake_case: `"time_limit_s"`, `"solver_status"`
- Constants use UPPERCASE: `DEFAULT_TASK_RATE` (in `config/constants.py`)
- Loop variables use short names: `i`, `r`, `s`, `e`, `m` for meaningful context
- PascalCase for all classes: `ScenarioCreate`, `RunOut`, `SchedulingProblem`, `Member`
- Enums use PascalCase: `WindowKind`, `DemandFamily`
- Type hints use modern Python 3.10+ syntax with `|` for unions: `float | None`, `str | None`

## Code Style

- No explicit formatter configured (likely PEP 8 default)
- 100-character line length observed in multi-line constructs
- Proper spacing around operators and after commas
- Example from `api/schemas.py`:
- No explicit linter configured (.eslintrc, .pylintrc, ruff.toml, etc. absent)
- Code follows PEP 8 implicitly via conventions observed:

## Import Organization

- No path aliases configured; absolute imports from project root (`from domain.types import...` not relative `from ..domain.types import...`)
- Imports work because `conftest.py` adds backend directory to sys.path

## Error Handling

- **API endpoints:** Use `HTTPException` with status codes and detail messages
- **Services:** Raise exceptions; let caller (router/parent) handle with HTTPException
- **Background tasks:** Catch all exceptions (`except Exception as exc: # noqa: BLE001`) and persist to database
- **Data validation:** Use Pydantic models (FastAPI schemas) for request validation

## Logging

- **CLI:** Use `print()` for output (see `run.py`)
- **API:** No logging; errors persisted to database via service layer
- **Background tasks:** No logging; exceptions caught and stored in `runs.error` column

## Comments

- Module-level docstrings always present: explain module purpose, usage, or design decisions
- Function docstrings: minimal; rely on type hints and name clarity
- Inline comments: explain "why", not "what"
- Not used; this is Python, not TypeScript

## Function Design

- Type hints on all parameters: `def create_scenario(conn: sqlite3.Connection, name: str, fixture: str, ...)`
- Default values at the end: `time_limit_s: float = 60.0`
- Use keyword-only arguments after `*` when appropriate (not common in this codebase)
- Always annotated: `-> dict`, `-> Optional[dict]`, `-> SolveResult`
- Return early for error cases
- Example from `domain/types.py`:

## Module Design

- Modules export classes, functions, and constants used by other modules
- No explicit `__all__` lists (all public names exported)
- Example: `engine/base.py` exports `SchedulerEngine`, `SolverConfig`, `create_engine()`
- Minimal use; most `__init__.py` files empty or minimal
- `api/__init__.py`, `domain/__init__.py` are empty
- `engine/__init__.py` is empty
- **Dataclasses:** Use `@dataclass` or `@dataclass(frozen=True)` for immutable types
- **Protocols:** Use `typing.Protocol` for engine abstraction
- **Pydantic models:** Use for API request/response validation
- **Repository pattern:** Thin data-access layer wrapping SQLite
- **Service layer:** Business logic; operates on repos
- **Router layer:** FastAPI endpoints; use dependency injection

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

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

- **Domain-Driven Design:** Pure domain types (`domain/`) import nothing from framework or solver. Enables framework-agnostic reuse.
- **Engine Abstraction:** Solver swappable via factory pattern (`engine/base.py`). Current implementation: CP-SAT (Google OR-Tools).
- **Threading Model:** FastAPI event loop (async request handling) + single-worker `ThreadPoolExecutor` for CPU-bound solves. Prevents event loop blocking.
- **Async-First API:** FastAPI dependencies handle DB connections, engine injection. Dependencies yielded per request.
- **Database Concurrency:** SQLite WAL mode allows worker thread to write run status while request threads read scenario metadata.

## Layers

- Purpose: Expose solve capabilities via REST, manage scenario lifecycle, poll run status
- Location: `api/`
- Contains: FastAPI app, route handlers, Pydantic schemas
- Depends on: Services, Domain, Engine, Store
- Used by: HTTP clients, tests
- Purpose: Orchestrate use cases (scenario CRUD, run submission, async execution coordination)
- Location: `services/`
- Contains: `scenario_service.py`, `run_service.py`, serialization utilities
- Depends on: Domain, Engine, Store, Ingest
- Used by: API, CLI
- Purpose: Immutable representations of problems, solutions, and intermediate types. Framework-agnostic.
- Location: `domain/`
- Contains: `SchedulingProblem`, `SolveResult`, `Member`, `Task`, `Window`, `Qualification`, etc.
- Depends on: Nothing (no framework imports)
- Used by: Engine, Services, Ingest, Serialization
- Purpose: Adapt external fixture format (JSON) into domain SchedulingProblem
- Location: `ingest/`
- Contains: `input_adapter.py` (main transformer), `scenario_time.py` (time utilities)
- Depends on: Domain
- Used by: Services (run executor), CLI
- Purpose: Abstract solver backend. Pluggable via factory.
- Location: `engine/`
- Contains: `base.py` (protocol), `cpsat/` (current implementation)
- Depends on: Domain
- Used by: Services, CLI
- Purpose: Build and solve constraint model. Lexicographic multi-round optimization.
- Location: `engine/cpsat/`
- Contains: `engine.py` (entry), `builder.py` (model construction), `objective.py` (solve loop)
- Depends on: Domain, Google OR-Tools
- Used by: Engine (wrapped by `SchedulerEngine` protocol)
- Purpose: SQLite persistence. Scenario metadata and run records.
- Location: `store/`
- Contains: `db.py` (connections, schema), `repositories.py` (DAO objects)
- Depends on: Nothing (uses sqlite3 stdlib)
- Used by: Services, API

## Data Flow

### Primary Request Path (HTTP Run Submission)

### Background Solve Execution (Worker Thread)

- Run state transitions: PENDING → RUNNING → COMPLETED/FAILED
- Persisted to `runs` table with timestamps (`started_at`, `finished_at`, `created_at`)
- Result JSON serialized via `serialize_result()` → stored in `result_json` column
- Exceptions caught, logged as `error`, run marked FAILED

### CLI Solve Execution (Synchronous)

- No database used in CLI
- Timing instrumented inline: `time.time()` before/after solve

## Key Abstractions

- Purpose: Immutable input to the solver. Contains members, tasks, demand, shift templates, availability/roster windows.
- Examples: `domain/problem.py`
- Pattern: Dataclass with typed fields, helper method `task(task_id)` for lookup.
- Purpose: Immutable solution output. Schedule rows, metrics, solver stats.
- Examples: `domain/result.py`
- Pattern: Dataclass wrapping lists of `ScheduleRow`, metrics dictionary, solver stats.
- Purpose: Abstract interface for swappable solvers.
- Examples: `engine/base.py:18` defines protocol; `engine/cpsat/engine.py:22` implements.
- Pattern: Python Protocol with `solve()` method and `name` property.
- Purpose: Domain entities representing workforce and work.
- Examples: `domain/types.py`
- Pattern: Frozen dataclasses (immutable, hashable). Qualifications stored as nested list.
- Purpose: Represent time availability (roster/availability) and shift breaks.
- Examples: `domain/types.py`
- Pattern: Frozen dataclass. All times in **hours from scenario start** (e.g., day-1 17:30 = 17.5h, day-2 06:00 = 30.0h).
- Purpose: Data access layer. Encapsulate SQL queries.
- Examples: `store/repositories.py`
- Pattern: Class constructor takes `sqlite3.Connection`, methods execute queries and return dicts (sqlite3.Row).

## Entry Points

- Location: `api/main.py:25`
- Triggers: `uvicorn api.main:app --reload`
- Responsibilities: Bind routers (health, fixtures, scenarios, runs); set up lifespan (init_db on startup, shutdown worker pool on teardown)
- Location: `run.py:53`
- Triggers: `python run.py [fixture_path] [engine_name] [time_limit_s]`
- Responsibilities: Load fixture, create engine, solve synchronously, print metrics and schedule sample
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

### Shared DB Connections Across Threads

### Hard-Coded Solver Engine

### Time Zones Not Explicit

## Error Handling

- **Service layer:** Exceptions in `run_service._execute()` caught at line 90. Error logged as run.error field, run marked FAILED.
- **API layer:** Validation errors (Pydantic) return 422. 404 for not-found resources. Dependency failures propagate (500).
- **Engine layer:** CP-SAT returns status (OPTIMAL, FEASIBLE, UNKNOWN). No exceptions. If no solution found, `math.isnan(lex.round1_value)` returns empty schedule gracefully.
- **Ingest layer:** Malformed JSON raises on `json.load()`. Adapter catches _rows() missing keys, returns default lists.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
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
