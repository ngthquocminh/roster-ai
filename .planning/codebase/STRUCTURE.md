# Codebase Structure

**Analysis Date:** 2026-07-20

## Directory Layout

```
rosterai/
├── backend/                    # Python FastAPI service + solver engine
│   ├── api/                    # FastAPI application layer
│   │   ├── main.py             # App factory, router mounting, lifespan, CORS
│   │   ├── deps.py             # Dependency injection (get_db, get_engine, get_settings, get_llm_provider)
│   │   ├── schemas.py          # Pydantic models for request/response
│   │   ├── routers/            # Endpoint handlers by domain
│   │   │   ├── health.py       # GET /health (readiness check)
│   │   │   ├── fixtures.py     # GET /fixtures (available test data)
│   │   │   ├── scenarios.py    # CRUD scenarios (GET/POST /scenarios, GET /scenarios/{id})
│   │   │   ├── runs.py         # Run lifecycle (POST trigger, GET list, GET status, GET result, GET insights)
│   │   │   └── constraints.py  # NL constraint parsing (POST /constraints)
│   │   └── __init__.py
│   │
│   ├── services/               # Business logic layer
│   │   ├── scenario_service.py # Scenario metadata fetching, fixture loading
│   │   ├── run_service.py      # Run creation, async solve orchestration, worker pool
│   │   ├── constraint_service.py # NL parsing, token resolution, override validation/persistence
│   │   ├── insight_service.py  # Insight generation/caching, LLM calls
│   │   ├── serialize.py        # SolveResult serialization (JSON for storage)
│   │   └── __init__.py
│   │
│   ├── domain/                 # Pure domain types (framework-agnostic)
│   │   ├── problem.py          # SchedulingProblem (input)
│   │   ├── result.py           # SolveResult (output with schedule rows + metrics)
│   │   ├── types.py            # Domain entities (Member, Task, Window, Qualification, etc.)
│   │   ├── overrides.py        # OverrideCall (parsed NL constraint)
│   │   └── __init__.py
│   │
│   ├── engine/                 # Solver abstraction + implementations
│   │   ├── base.py             # SchedulerEngine protocol, SolverConfig, factory
│   │   ├── cpsat/              # Google OR-Tools CP-SAT implementation
│   │   │   ├── engine.py       # CpSatEngine.solve() entry point
│   │   │   ├── builder.py      # Constraint model construction
│   │   │   ├── objective.py    # Two-round optimization loop
│   │   │   └── __init__.py
│   │   └── __init__.py
│   │
│   ├── llm/                    # LLM provider abstraction + implementations
│   │   ├── base.py             # LLMProvider protocol, factory, LLMProviderError
│   │   ├── stub.py             # Stub provider (test default, no network)
│   │   ├── gemini.py           # Google Gemini provider
│   │   ├── openrouter.py       # OpenRouter provider
│   │   ├── translate.py        # Shared translation logic (tool call parsing)
│   │   └── __init__.py
│   │
│   ├── ingest/                 # JSON fixture → SchedulingProblem adapter
│   │   ├── input_adapter.py    # Main transformer (JSON → problem)
│   │   ├── scenario_time.py    # Time utilities (hours from start, window clipping)
│   │   └── __init__.py
│   │
│   ├── store/                  # Data persistence layer
│   │   ├── db.py               # SQLite connection, schema, WAL mode setup
│   │   ├── repositories.py     # DAO (ScenarioRepo, RunRepo)
│   │   └── __init__.py
│   │
│   ├── config/                 # Configuration/constants
│   │   ├── constants.py        # CONSTANT_VALUES (task rates, caps, etc.)
│   │   └── __init__.py
│   │
│   ├── fixtures/               # Test fixture generation
│   │   ├── build_short_input.py # Programmatic test data builder
│   │   └── __init__.py
│   │
│   ├── scripts/                # Utility scripts
│   │   ├── export_openapi.py   # Generate OpenAPI spec → frontend codegen
│   │   └── calibrate_penalties.py # Solver tuning utilities
│   │
│   ├── tests/                  # Test suite (pytest)
│   │   ├── test_adapter.py     # Ingest adapter tests
│   │   ├── test_api.py         # API endpoint tests
│   │   ├── test_engine.py      # Solver tests
│   │   ├── test_constraint_service.py
│   │   ├── test_insight_service.py
│   │   └── __init__.py
│   │
│   ├── run.py                  # CLI entry point (sync solve execution)
│   ├── settings.py             # Configuration (Settings dataclass, defaults from env)
│   ├── conftest.py             # pytest fixtures, dependencies override
│   ├── pyproject.toml          # Python package config, dependencies, test markers
│   └── .venv/                  # Virtual environment (uv managed, not committed)
│
├── frontend/                   # Vite + React + TypeScript SPA
│   ├── src/
│   │   ├── api/                # OpenAPI-generated client + typed wrappers
│   │   │   ├── client.ts       # Single openapi-fetch instance (typed)
│   │   │   ├── schema.d.ts     # Generated types from backend OpenAPI spec
│   │   │   ├── scenarios.ts    # Typed wrappers: listScenarios, createScenario, getScenario, getScenarioOverrides
│   │   │   ├── runs.ts         # Typed wrappers: listRuns, getRun, triggerRun, getRunResult
│   │   │   ├── constraints.ts  # Typed wrappers: applyConstraint
│   │   │   ├── insights.ts     # Typed wrappers: getRunInsights
│   │   │   ├── results.ts      # Typed wrappers: getRunResult (alt path)
│   │   ├── hooks/              # TanStack Query + custom logic
│   │   │   ├── useScenarios.ts # Query: list scenarios (key: ["scenarios"])
│   │   │   ├── useScenario.ts  # Query: get single scenario + validate 404
│   │   │   ├── useCreateScenario.ts # Mutation: create scenario (invalidates scenarios key)
│   │   │   ├── useFixtures.ts  # Query: list available fixtures
│   │   │   ├── useRuns.ts      # Query: list runs for scenario
│   │   │   ├── useRun.ts       # Query: get single run (with polling on PENDING/RUNNING)
│   │   │   ├── useTriggerRun.ts # Mutation: POST /scenarios/{id}/runs
│   │   │   ├── useRunResult.ts # Query: get result (enabled only when status=COMPLETED)
│   │   │   ├── useRunInsights.ts # Mutation: get/generate insights (on-demand)
│   │   │   ├── useApplyConstraint.ts # Mutation: POST /constraints (invalidates overrides)
│   │   │   ├── useOverrides.ts # Query: list applied overrides for scenario
│   │   │   └── __init__.ts (if present)
│   │   │
│   │   ├── routes/             # Page-level components (React Router matched components)
│   │   │   ├── Home.tsx        # SCEN-01: scenario list + create dialog
│   │   │   ├── ScenarioLayout.tsx # Three-tab nav (Editor/Runs/Results) + Outlet
│   │   │   ├── Editor.tsx      # SCEN-03 + CONS-01..05: constraint input + transcript + overrides
│   │   │   ├── RunHistory.tsx  # SCEN-04: run history table, trigger button, deep-link to results
│   │   │   ├── ResultsView.tsx # RES-01..06: composed results (coverage, chart, schedule, insight)
│   │   │   ├── router.test.tsx # Route tree tests (deep-link coverage)
│   │   │   └── *.test.tsx      # Component tests
│   │   │
│   │   ├── components/         # Reusable UI components (by feature)
│   │   │   ├── layout/
│   │   │   │   ├── AppBar.tsx  # Persistent header (logo, nav, status)
│   │   │   │   ├── RootErrorBoundary.tsx # Crash backstop (covers render + route errors)
│   │   │   │   ├── ErrorBanner.tsx # Backend-unreachable banner (SHELL-04)
│   │   │   │   └── PlaceholderView.tsx # Not-yet-implemented route fallback
│   │   │   ├── scenarios/
│   │   │   │   ├── ScenarioTable.tsx # SCEN-01: list table + create button
│   │   │   │   └── CreateScenarioDialog.tsx # SCEN-02: form modal (fixture picker, time limit)
│   │   │   ├── editor/
│   │   │   │   ├── ScenarioHeader.tsx # Scenario title + metadata + edit form
│   │   │   │   ├── ConstraintInput.tsx # CONS-01: text input + submit (calls useApplyConstraint)
│   │   │   │   ├── ConstraintTranscript.tsx # CONS-04: scrollable history of attempts/outcomes
│   │   │   │   ├── TranscriptEntry.tsx # Single transcript row (applied/rejected/clarification)
│   │   │   │   ├── OverridesList.tsx # Applied overrides table (tool + args + parsed text)
│   │   │   │   └── ProviderDownBanner.tsx # LLM provider status banner
│   │   │   ├── runs/
│   │   │   │   ├── RunHistoryTable.tsx # SCEN-04: paginated/sortable runs, status label, result link
│   │   │   │   ├── RunStatusLabel.tsx # Status badge (PENDING/RUNNING/COMPLETED/FAILED)
│   │   │   │   ├── RunInFlightPanel.tsx # Spinner + polling interval while PENDING/RUNNING
│   │   │   │   └── TriggerRunButton.tsx # Button to POST /scenarios/{id}/runs
│   │   │   ├── results/        # All six RES result components
│   │   │   │   ├── WarningsBanner.tsx # RES-01: solver status banner (if not OPTIMAL)
│   │   │   │   ├── CoverageSummary.tsx # RES-02: summary cards (demand met, cost, etc.)
│   │   │   │   ├── CoverageByDayTable.tsx # RES-03: coverage % by day
│   │   │   │   ├── DemandVsServedChart.tsx # RES-04: Recharts bar chart (demand vs served by function)
│   │   │   │   ├── ScheduleTable.tsx # RES-05: paginated schedule rows (member, function, time, shift)
│   │   │   │   └── InsightPanel.tsx # RES-06: NL insight report + generation spinner
│   │   │   └── ui/             # Shadcn/Radix UI primitives (button, card, table, dialog, etc.)
│   │   │       ├── button.tsx
│   │   │       ├── card.tsx
│   │   │       ├── table.tsx
│   │   │       ├── dialog.tsx
│   │   │       ├── input.tsx
│   │   │       ├── select.tsx
│   │   │       ├── tabs.tsx
│   │   │       ├── alert.tsx
│   │   │       ├── textarea.tsx
│   │   │       ├── tooltip.tsx
│   │   │       └── chart.tsx (Recharts integration)
│   │   │
│   │   ├── lib/                # Shared utilities
│   │   │   ├── env.ts          # API_BASE_URL resolution (VITE_API_BASE_URL)
│   │   │   ├── errors.ts       # Error parsing (getErrorStatus, humanize messages)
│   │   │   ├── formatShiftWindow.ts # Time formatting (hour range → "14:30–17:30")
│   │   │   ├── formatTimestamp.ts # ISO timestamp formatting
│   │   │   ├── runStatus.ts    # Run status helpers (color, label, polling logic)
│   │   │   ├── toolLabels.ts   # Constraint tool names (human-friendly display)
│   │   │   ├── utils.ts        # Tailwind cn() merge, shared helpers
│   │   │   └── *.test.ts       # Unit tests for lib functions
│   │   │
│   │   ├── test/               # Test setup + smoke tests
│   │   │   ├── setup.ts        # Vitest globals, testing library setup
│   │   │   └── smoke.test.tsx  # Sanity check (renders App without crashing)
│   │   │
│   │   ├── App.tsx             # Root component, route tree definition, RootLayout (persistent AppBar)
│   │   ├── main.tsx            # Entry point, providers (QueryClient, RouterProvider)
│   │   ├── index.css           # Tailwind directives, global styles
│   │
│   ├── public/                 # Static assets (favicon, etc. — if used)
│   ├── openapi.json            # Generated OpenAPI spec (regenerated via `npm run codegen`)
│   ├── package.json            # Dependencies, scripts (dev, build, test, codegen)
│   ├── package-lock.json       # Lockfile (npm)
│   ├── vite.config.ts          # Vite config (React plugin, Tailwind, vitest, @/ alias)
│   ├── tsconfig.json           # TypeScript base config
│   ├── tsconfig.app.json       # TypeScript app config (extends base)
│   ├── tsconfig.node.json      # TypeScript Node config (for vite.config.ts)
│   ├── .oxlintrc.json          # Linter config (oxlint)
│   ├── components.json         # Shadcn CLI config (component library source)
│   └── node_modules/           # Dependencies (npm, not committed)
│
├── data/                       # Test fixtures (JSON weekly schedules)
│   ├── sample_tiny_input.json  # Minimal test case
│   └── *.json                  # Other fixtures
│
├── docs/                       # Project documentation
│   ├── API.md                  # OpenAPI endpoint reference (hand-authored)
│   ├── design.md               # Design decisions, constraint model details
│   ├── PROJECT.md              # Phase notes, retrospectives
│   └── *.md                    # Phase-specific docs
│
├── .planning/                  # GSD workflow artifacts
│   └── codebase/               # Codebase analysis documents (this folder)
│       ├── ARCHITECTURE.md     # System design, layers, data flow
│       └── STRUCTURE.md        # Directory layout, file purposes
│
├── .claude/                    # Claude Code project config
│   ├── CLAUDE.md               # Project instructions, tech stack, conventions
│   └── skills/                 # Project-specific agent skills (if any)
│
├── .git/                       # Git repository (main branch, clean state)
├── .gitignore                  # Git excludes (.venv, node_modules, *.db, .env, etc.)
└── README.md                   # Project overview, setup, running
```

## Directory Purposes

**backend/**
- Purpose: Python FastAPI service + OR-Tools solver
- Key entry points: `api/main.py` (HTTP server), `run.py` (CLI)
- Test runner: `pytest` (discovers tests/ automatically)

**backend/api/**
- Purpose: HTTP request handling, FastAPI routing, Pydantic validation
- Key files: `main.py` (app factory), `routers/*` (endpoints), `schemas.py` (models), `deps.py` (DI)

**backend/services/**
- Purpose: Business logic orchestration
- Contains: Scenario CRUD, run lifecycle, constraint parsing, insight generation
- No domain logic here — this layer calls domain entities and services

**backend/domain/**
- Purpose: Pure, framework-agnostic domain types
- Immutable: frozen dataclasses, type hints, no external imports
- Used by: Engine, Services, Ingest adapters

**backend/engine/**
- Purpose: Solver abstraction (pluggable backend)
- Protocol: `SchedulerEngine.solve(problem, config) -> SolveResult`
- Implementation: `cpsat/` (Google OR-Tools)

**backend/llm/**
- Purpose: LLM provider abstraction (pluggable backend)
- Protocol: `LLMProvider.parse_constraints(text)` + `generate_insights(summary)`
- Implementations: `stub.py` (test), `gemini.py`, `openrouter.py` (network-backed)

**backend/ingest/**
- Purpose: JSON fixture → domain model transformation
- Contains: Schema conversion, time handling, deduplication
- Entry: `load_problem(path: str) -> SchedulingProblem`

**backend/store/**
- Purpose: SQLite persistence (connection, schema, DAOs)
- Schema: Two tables (scenarios, runs), WAL mode, additive migrations
- DAO: `ScenarioRepo`, `RunRepo` (thin wrappers over sqlite3.Row)

**backend/config/**
- Purpose: Constants and configuration values
- Example: DEFAULT_TASK_RATE, max_hours_per_week defaults

**backend/fixtures/**
- Purpose: Programmatic test data generation
- Builder: `build_short_input.py` (creates minimal test scenarios)

**backend/scripts/**
- Purpose: Utility scripts for development/ops
- `export_openapi.py`: Generate OpenAPI spec → frontend codegen
- `calibrate_penalties.py`: Solver tuning

**backend/tests/**
- Purpose: pytest test suite
- Coverage: API endpoints, services, engine, adapter
- Stub provider injected via conftest.py (no live LLM calls by default)

**frontend/src/api/**
- Purpose: OpenAPI-generated typed API client
- `client.ts`: Single openapi-fetch instance (NEVER create another)
- `schema.d.ts`: Generated types (REGENERATE via `npm run codegen`, never hand-edit)
- `*.ts`: Thin typed wrappers (no business logic here)

**frontend/src/hooks/**
- Purpose: TanStack Query + custom business logic
- Pattern: `useQuery()` for fetching, `useMutation()` for mutations
- Query keys: Shared contracts (e.g., `["scenarios"]` invalidated by create mutation)
- Enabled gates: `enabled: Boolean` to prevent premature fetches (e.g., only fetch result when status=COMPLETED)

**frontend/src/routes/**
- Purpose: Page-level components matched by React Router
- Structure: Top-level route components (Home, Editor, RunHistory, ResultsView)
- Layout: ScenarioLayout (persistent tab nav), RootLayout (persistent AppBar)
- Tests: router.test.tsx validates route structure and deep-linking

**frontend/src/components/**
- Purpose: Reusable UI components, organized by feature
- layout/: App-wide layout (AppBar, ErrorBoundary, banners)
- scenarios/: Scenario list/creation
- editor/: Constraint editor (input, transcript, overrides)
- runs/: Run history and status
- results/: Six result visualizations (coverage, chart, schedule, insight)
- ui/: Shadcn/Radix primitives (button, card, table, dialog, etc.)

**frontend/src/lib/**
- Purpose: Shared utility functions
- env.ts: API_BASE_URL resolution (from VITE_API_BASE_URL env var)
- errors.ts: HTTP error parsing (status code extraction for branching)
- formatShiftWindow.ts, formatTimestamp.ts: Data formatting
- runStatus.ts: Run status helpers (polling intervals, label, color)
- utils.ts: Tailwind cn() for class merging

**frontend/src/test/**
- Purpose: Vitest setup and smoke tests
- setup.ts: Global test utilities, testing library configuration
- smoke.test.tsx: Sanity check (App renders without crashing)

**data/**
- Purpose: Test fixtures (JSON weekly schedules)
- Format: Weekly workload data (scenarios, members, tasks, demand)
- Used by: Backend CLI, adapter tests

**docs/**
- Purpose: Project documentation
- API.md: OpenAPI reference (hand-authored, canonical endpoint docs)
- design.md: Design decisions, constraint model theory
- PROJECT.md: Phase notes, retrospectives

## Key File Locations

**Entry Points:**
- `backend/api/main.py`: FastAPI HTTP server startup
- `backend/run.py`: CLI sync solve execution
- `frontend/src/main.tsx`: React app bootstrap
- `frontend/src/App.tsx`: Root component, route tree

**Configuration:**
- `backend/settings.py`: Settings dataclass, env overrides
- `backend/pyproject.toml`: Python version, dependencies, test config
- `backend/config/constants.py`: CONSTANT_VALUES (rates, caps, etc.)
- `frontend/src/lib/env.ts`: API_BASE_URL resolution
- `frontend/vite.config.ts`: Build, test, alias config
- `frontend/package.json`: npm scripts, dependencies

**Core Logic:**
- `backend/domain/*`: Pure domain types (SchedulingProblem, SolveResult, etc.)
- `backend/services/constraint_service.py`: NL → override logic
- `backend/services/run_service.py`: Async solve orchestration
- `backend/engine/cpsat/builder.py`: Constraint model construction

**Frontend State Management:**
- `frontend/src/main.tsx`: QueryClient setup (TanStack Query)
- `frontend/src/api/client.ts`: OpenAPI client (single instance)
- `frontend/src/hooks/use*.ts`: Query/mutation hooks (per endpoint)
- `frontend/src/App.tsx`: Router setup

**Testing:**
- `backend/conftest.py`: pytest fixtures, dependency overrides
- `backend/tests/`: Test suite
- `frontend/src/test/setup.ts`: Vitest globals
- `frontend/src/**/*.test.tsx`: Component/hook tests (co-located)

## Naming Conventions

**Files:**

- **Python modules:** snake_case, e.g., `input_adapter.py`, `run_service.py`
- **Python packages:** snake_case directories: `backend/api/`, `backend/services/`
- **TypeScript/React:** camelCase files, `.ts` for utilities, `.tsx` for components
  - Hooks: `use*.ts` (e.g., `useScenarios.ts`)
  - Components: `PascalCase.tsx` (e.g., `ScenarioTable.tsx`)
  - Tests: `*.test.ts` (co-located with source)

**Directories:**

- **Backend feature modules:** `api/`, `services/`, `domain/`, `engine/`, `llm/`, `ingest/`, `store/`, `config/`, `fixtures/`, `scripts/`, `tests/`
- **Frontend feature modules:** `api/`, `hooks/`, `routes/`, `components/`, `lib/`, `test/`
- **Public assets:** `frontend/public/`

**Python Functions:**
- snake_case: `create_scenario()`, `load_problem()`, `set_running()`
- Private functions prefixed with underscore: `_now()`, `_rows()`, `_resolve_task()`

**Python Classes:**
- PascalCase: `SchedulingProblem`, `RunOut`, `ScenarioCreate`, `CpSatEngine`, `Member`
- Enums: PascalCase: `WindowKind`, `DemandFamily`

**Python Dataclasses:**
- Frozen (immutable): `@dataclass(frozen=True)` for domain types (Member, Task, Window)
- Regular (mutable): `@dataclass` for services/config

**TypeScript/React:**
- Components: PascalCase: `ScenarioTable`, `ConstraintInput`, `ResultsView`
- Hooks: `use` prefix, camelCase: `useScenarios`, `useRun`, `useApplyConstraint`
- Utilities: camelCase: `formatTimestamp`, `getErrorStatus`
- Types/Interfaces: PascalCase (generated from OpenAPI: `paths`, `components`)
- Variables: camelCase: `scenarioId`, `runQuery`, `onOutcome`

**Database:**
- Tables: snake_case, plural: `scenarios`, `runs`
- Columns: snake_case: `scenario_id`, `created_at`, `status`

**API Endpoints:**
- Path style: kebab-case (not used in this API; underscore used): `/scenarios`, `/runs`, `/fixtures`, `/constraints`
- No trailing slashes

## Where to Add New Code

**New Backend Feature (e.g., a new endpoint):**
- Endpoint handler: `backend/api/routers/my_feature.py`
- Service logic: `backend/services/my_feature_service.py`
- Pydantic schema: Add model to `backend/api/schemas.py`
- Domain types: Add to `backend/domain/types.py` (if needed)
- Test: `backend/tests/test_my_feature.py`
- Import in router init: Add to `backend/api/routers/__init__.py` (if exists)

**New Frontend Route/View:**
- Route component: `frontend/src/routes/MyView.tsx`
- Layout: Update `frontend/src/App.tsx` route tree (if adding new top-level route)
- Nested tabs: Update `frontend/src/routes/ScenarioLayout.tsx` (if adding tab under scenario)
- Tests: `frontend/src/routes/MyView.test.tsx`

**New Frontend Component:**
- Component file: `frontend/src/components/feature_name/MyComponent.tsx`
- Tests: `frontend/src/components/feature_name/MyComponent.test.tsx` (co-located)
- UI primitives: Reuse from `frontend/src/components/ui/` (shadcn)

**New Frontend Hook (for API call or custom logic):**
- Hook file: `frontend/src/hooks/useMyHook.ts`
- Tests: `frontend/src/hooks/useMyHook.test.tsx`
- API call: Import from `frontend/src/api/my_endpoint.ts`
- Query key: Establish contract (e.g., `["myFeature"]` so mutations can invalidate)

**New API Client Wrapper (after adding backend endpoint):**
- Wrapper: `frontend/src/api/my_endpoint.ts`
- Regenerate types: `npm run codegen` (from `export_openapi.py`)
- Tests: `frontend/src/api/my_endpoint.test.ts`

**New Test Fixture:**
- Fixture JSON: `data/my_scenario.json` (follow existing format)
- Or programmatic builder: Extend `backend/fixtures/build_short_input.py`

**New Utility Function:**
- Backend: `backend/services/serialize.py` or new `backend/lib/my_util.py`
- Frontend: `frontend/src/lib/my_util.ts`
- Tests: `frontend/src/lib/my_util.test.ts` (co-located)

## Special Directories

**backend/.venv/**
- Purpose: Virtual environment (uv-managed, Python 3.10+)
- Generated: Yes (from uv.lock)
- Committed: No (.gitignore'd)

**frontend/node_modules/**
- Purpose: npm dependencies
- Generated: Yes (from package-lock.json)
- Committed: No (.gitignore'd)

**backend/var/**
- Purpose: Runtime data (SQLite database, logs)
- Generated: Yes (by app at runtime)
- Committed: No (.gitignore'd)
- Default location for `ROSTERAI_DB`: `backend/var/rosterai.db`

**frontend/dist/**
- Purpose: Production build output (Vite)
- Generated: Yes (from `npm run build`)
- Committed: No (.gitignore'd)

**.planning/**
- Purpose: GSD workflow artifacts (plans, execution logs, codebase docs)
- Generated: Yes (by GSD commands)
- Committed: Yes (to repo)

**.claude/**
- Purpose: Claude Code project config and skills
- CLAUDE.md: Project instructions (committed, version-controlled)
- skills/: Project-specific agent skills (if any)

**.git/**
- Purpose: Git repository metadata
- Generated: Yes (by git)
- Committed: N/A

**docs/**
- Purpose: Human-readable project documentation
- Committed: Yes
- Contents: API reference, design docs, phase notes

## Build & Run

**Backend (Development):**
```bash
cd backend
uv sync                           # Install dependencies from uv.lock
uv run uvicorn api.main:app --reload
```

**Backend (CLI):**
```bash
cd backend
python run.py ../data/sample_tiny_input.json
```

**Backend (Tests):**
```bash
cd backend
pytest                            # Run all tests
pytest -m live                    # Include live LLM tests (requires API key)
```

**Frontend (Development):**
```bash
cd frontend
npm install
npm run dev                       # Vite dev server (localhost:5173)
```

**Frontend (Build):**
```bash
cd frontend
npm run build
npm run preview
```

**Frontend (Tests):**
```bash
cd frontend
npm test                          # Vitest run mode
npm run test:watch              # Watch mode (if script defined)
```

**Frontend (Codegen):**
```bash
cd frontend
npm run codegen                   # Export OpenAPI + generate types
```

---

*Structure analysis: 2026-07-20*
