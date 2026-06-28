# Codebase Structure

**Analysis Date:** 2026-06-26

## Directory Layout

```
rosterai/
├── .git/                          # Git version control
├── .planning/                     # Planning artifacts (generated; not committed during phases)
│   └── codebase/                  # Codebase documentation (this directory)
│       ├── ARCHITECTURE.md
│       └── STRUCTURE.md
├── backend/                       # Main Python backend
│   ├── api/                       # HTTP API layer
│   │   ├── main.py                # FastAPI app, route mounting, lifespan
│   │   ├── deps.py                # Dependency injection (settings, DB, engine)
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── routers/               # API endpoint handlers
│   │       ├── health.py          # Health check
│   │       ├── scenarios.py       # Scenario CRUD
│   │       ├── fixtures.py        # Fixture management
│   │       └── runs.py            # Run lifecycle (trigger, poll, fetch result)
│   ├── config/                    # Configuration constants
│   │   ├── constants.py           # Solver constants, tuning parameters
│   │   └── __init__.py
│   ├── domain/                    # Pure domain models (framework-agnostic)
│   │   ├── problem.py             # SchedulingProblem (input to solver)
│   │   ├── result.py              # SolveResult, ScheduleRow, metrics
│   │   ├── types.py               # Member, Task, ShiftTemplate, etc.
│   │   └── __init__.py
│   ├── engine/                    # Solver abstraction layer
│   │   ├── base.py                # SchedulerEngine protocol, factory
│   │   ├── cpsat/                 # CP-SAT (Google OR-Tools) implementation
│   │   │   ├── engine.py          # Solver entry point
│   │   │   ├── builder.py         # Constraint model construction
│   │   │   ├── objective.py       # Lexicographic solve loop
│   │   │   └── __init__.py
│   │   └── __init__.py
│   ├── ingest/                    # Input adaptation
│   │   ├── input_adapter.py       # Transform JSON fixture → SchedulingProblem
│   │   ├── scenario_time.py       # Time parsing, window utilities
│   │   └── __init__.py
│   ├── services/                  # Business logic, use cases
│   │   ├── scenario_service.py    # Scenario CRUD operations
│   │   ├── run_service.py         # Run creation, async solve submission
│   │   ├── serialize.py           # SolveResult → JSON serialization
│   │   └── __init__.py
│   ├── store/                     # Data persistence
│   │   ├── db.py                  # SQLite connection, schema, init
│   │   ├── repositories.py        # ScenarioRepo, RunRepo DAOs
│   │   └── __init__.py
│   ├── fixtures/                  # Test data generation
│   │   ├── build_short_input.py   # Generate sample fixture
│   │   └── __init__.py
│   ├── tests/                     # Test suite
│   │   ├── test_adapter.py        # Input adapter tests
│   │   ├── test_api.py            # API endpoint tests
│   │   ├── test_engine_small.py   # Solver engine tests
│   │   └── __init__.py
│   ├── conftest.py                # Pytest configuration, shared fixtures
│   ├── run.py                     # CLI entry point
│   ├── settings.py                # Runtime settings (DB/data paths)
│   ├── .venv/                     # Python virtual environment (not committed)
│   ├── var/                       # Runtime data directory
│   │   └── rosterai.db            # SQLite database (generated)
│   ├── .pytest_cache/             # Pytest cache (not committed)
│   └── pyproject.toml             # Poetry/uv package definition
├── data/                          # Input fixture data (JSON)
│   ├── sample_tiny_input.json     # Small example fixture
│   └── [other fixtures]
├── docs/                          # Documentation
│   ├── decisions/                 # Architecture Decision Records (ADRs)
│   └── [markdown docs]
├── README.md                      # Project overview
├── PLAN.md                        # Development plan
├── design.md                      # System design document
└── .gitignore                     # Git ignore rules
```

## Directory Purposes

**`backend/`:**
- Purpose: Main application code (API, solver, services)
- Contains: All Python source, tests, configuration
- Key files: `api/main.py` (FastAPI app), `run.py` (CLI), `settings.py` (config)

**`backend/api/`:**
- Purpose: HTTP request/response handling
- Contains: FastAPI app, route handlers, Pydantic schemas, dependency injection
- Key files: `main.py` (app setup), `routers/` (endpoint implementations), `deps.py` (DI)

**`backend/domain/`:**
- Purpose: Immutable domain models (framework-agnostic)
- Contains: Pure Python dataclasses representing problem, solution, and entities
- Key files: `problem.py` (input model), `result.py` (output model), `types.py` (entities)

**`backend/engine/`:**
- Purpose: Solver backend abstraction and pluggable implementations
- Contains: Protocol definition and solver implementations
- Key files: `base.py` (protocol), `cpsat/` (current solver)

**`backend/engine/cpsat/`:**
- Purpose: Google OR-Tools CP-SAT solver implementation
- Contains: Model builder, solve loop, objective function
- Key files: `engine.py` (entry), `builder.py` (constraint construction), `objective.py` (optimization)

**`backend/ingest/`:**
- Purpose: Transform external fixture format into domain model
- Contains: JSON → SchedulingProblem adapter, time utilities
- Key files: `input_adapter.py` (main transformation), `scenario_time.py` (time parsing)

**`backend/services/`:**
- Purpose: Business use cases and orchestration
- Contains: Scenario management, run execution, result serialization
- Key files: `run_service.py` (async solve execution), `scenario_service.py` (scenario CRUD)

**`backend/store/`:**
- Purpose: Data persistence layer
- Contains: SQLite connection management, schema, data access objects
- Key files: `db.py` (connection/schema), `repositories.py` (DAOs)

**`backend/tests/`:**
- Purpose: Unit and integration tests
- Contains: Test modules for adapter, API, engine
- Key files: `test_api.py` (API endpoint tests), `test_engine_small.py` (solver tests)

**`backend/config/`:**
- Purpose: Static configuration
- Contains: Solver constants, tuning parameters
- Key files: `constants.py` (default values)

**`backend/fixtures/`:**
- Purpose: Test data generation utilities
- Contains: Fixture builders for tests
- Key files: `build_short_input.py` (sample input generator)

**`backend/var/`:**
- Purpose: Runtime data directory (generated, not committed)
- Contains: SQLite database file
- Key files: `rosterai.db` (created on app init)

**`data/`:**
- Purpose: Input fixture data (JSON test cases)
- Contains: Weekly scheduling problem definitions (materialized demand, workforce, tasks)
- Key files: `sample_tiny_input.json` (small example), custom fixtures

**`docs/`:**
- Purpose: Project documentation
- Contains: Architecture decision records, design notes, user guides
- Key files: `decisions/` (ADR logs)

## Key File Locations

**Entry Points:**
- `backend/api/main.py`: FastAPI HTTP server. Run: `uvicorn api.main:app --reload`
- `backend/run.py`: CLI solver. Run: `python run.py [fixture_path] [engine] [time_limit]`
- `backend/conftest.py`: Pytest fixtures. Run: `pytest`

**Configuration:**
- `backend/settings.py`: Runtime paths (DB, data directory)
- `backend/config/constants.py`: Solver tuning (time limits, weights)
- `pyproject.toml`: Package dependencies, Python version

**Core Logic:**
- `backend/api/main.py`: FastAPI app setup, route mounting
- `backend/services/run_service.py`: Run creation and async execution
- `backend/services/scenario_service.py`: Scenario CRUD
- `backend/engine/cpsat/engine.py`: Solver implementation
- `backend/ingest/input_adapter.py`: JSON → domain transformation

**Testing:**
- `backend/tests/test_api.py`: API endpoint tests
- `backend/tests/test_engine_small.py`: Solver tests
- `backend/conftest.py`: Shared pytest configuration

**Data Persistence:**
- `backend/store/db.py`: SQLite schema and connection management
- `backend/store/repositories.py`: Data access objects
- `backend/var/rosterai.db`: SQLite database file (generated at runtime)

## Naming Conventions

**Files:**
- Module files: `lowercase_with_underscores.py` (e.g., `input_adapter.py`, `run_service.py`)
- Test files: `test_<module>.py` (e.g., `test_adapter.py`, `test_api.py`)
- Config files: `<name>.py` or `<name>.toml` (e.g., `settings.py`, `pyproject.toml`)

**Directories:**
- Package directories: `lowercase_with_underscores/` (e.g., `backend/`, `api/`, `ingest/`)
- Multi-word domains: `lowercase_with_underscores/` (e.g., `engine/cpsat/`, not `Engine.CPSAT`)
- Data directories: `lowercase_with_underscores/` (e.g., `var/`, `data/`)

**Functions:**
- Regular functions: `lowercase_with_underscores()` (e.g., `create_run()`, `load_problem()`)
- Private functions: `_lowercase_with_leading_underscore()` (e.g., `_execute()`, `_get_pool()`)
- Class methods: `lowercase_with_underscores()` (e.g., `get()`, `insert()`)

**Classes & Types:**
- Domain models: `PascalCase` (e.g., `SchedulingProblem`, `Member`, `Task`, `SolveResult`)
- Protocols: `PascalCase` with "Protocol" suffix implicitly (e.g., `SchedulerEngine` in code, but defined as `class SchedulerEngine(Protocol)`)
- Enums: `PascalCase` (e.g., `WindowKind`)
- Dataclasses: `PascalCase` (e.g., `RunOut`, `ScenarioCreate`)

**Variables:**
- Local/module scope: `lowercase_with_underscores` (e.g., `problem`, `task_ids`, `schedule`)
- Constants: `UPPERCASE` (e.g., `_SCHEMA`, `_BACKEND_DIR`) 
- Protected module state: `_lowercase_with_leading_underscore` (e.g., `_pool`, `_pool_lock`)

## Where to Add New Code

**New Feature (e.g., constraint override endpoint):**
- API handler: `backend/api/routers/<feature>.py`
- Pydantic schema: Add to `backend/api/schemas.py`
- Service logic: `backend/services/<feature>_service.py`
- Domain model changes: `backend/domain/types.py` or `backend/domain/problem.py`
- Tests: `backend/tests/test_<feature>.py`

**New Solver Backend (e.g., Gurobi, SCIP):**
- Implementation: `backend/engine/<solver_name>/engine.py`, `builder.py`, `objective.py`
- Register in factory: Update `backend/engine/base.py:create_engine()`
- Protocol: Implement `SchedulerEngine` protocol
- Tests: `backend/tests/test_engine_<solver_name>.py`

**New Domain Entity (e.g., Availability Preference):**
- Type definition: `backend/domain/types.py`
- Adapter mapping: Update `backend/ingest/input_adapter.py` to parse from fixture
- Engine integration: Update `backend/engine/cpsat/builder.py` to build constraints
- Serialization: Update `backend/services/serialize.py` if needed in result

**New Utility/Helper:**
- Shared utilities: `backend/domain/` (if domain-related) or `backend/ingest/scenario_time.py` pattern
- Service utilities: `backend/services/` (if service-related)
- Store utilities: `backend/store/` (if persistence-related)

**New Test:**
- Unit test: `backend/tests/test_<module>.py`
- API test: Add to `backend/tests/test_api.py`
- Integration test: `backend/tests/test_integration_<feature>.py`

## Special Directories

**`backend/.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No (listed in `.gitignore`)
- Usage: Activate with `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows)

**`backend/var/`:**
- Purpose: Runtime-generated data (SQLite database, logs if added)
- Generated: Yes (on app startup)
- Committed: No
- Usage: Configured via `ROSTERAI_DB` environment variable in `settings.py`

**`backend/.pytest_cache/`:**
- Purpose: Pytest internal cache
- Generated: Yes
- Committed: No (listed in `.gitignore`)

**`.planning/`:**
- Purpose: Planning artifacts from GSD workflow
- Generated: Yes (by `/gsd-map-codebase`, `/gsd-plan-phase`, etc.)
- Committed: Conditionally (design docs committed, phase directories not)

**`data/`:**
- Purpose: Input fixtures (JSON scheduling problems)
- Generated: Can be (via `build_short_input.py`)
- Committed: Yes (test fixtures)
- Usage: Referenced in scenario `fixture` field, loaded by CLI and run_service

**`docs/decisions/`:**
- Purpose: Architecture Decision Records
- Generated: Manually or by tools
- Committed: Yes
- Format: Markdown ADR format

---

*Structure analysis: 2026-06-26*
