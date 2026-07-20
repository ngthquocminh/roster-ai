# External Integrations

**Analysis Date:** 2026-07-20

## APIs & External Services

**Language Model Providers (Phase 3):**
- **Google Gemini**
  - What it's used for: Natural language constraint parsing and insight report generation (LLM-02)
  - SDK/Client: `google-genai>=2.10.0` (unified SDK, not legacy `google.generativeai`)
  - Implementation: `backend/llm/gemini.py`
  - Auth: `GEMINI_API_KEY` environment variable
  - Default model: `gemini-2.5-flash` (configurable via `LLM_MODEL`)
  - Features used: Function calling for constraint parsing, text generation for insights
  - Tool-calling mode: AUTO (never ANY) per `_PARSE_SYSTEM_INSTRUCTION` (D-08, RESEARCH.md)

- **OpenRouter**
  - What it's used for: Alternative LLM provider using OpenAI-compatible API
  - SDK/Client: `openai>=1.40` pointed at OpenRouter's base URL `https://openrouter.ai/api/v1`
  - Implementation: `backend/llm/openrouter.py`
  - Auth: `OPENROUTER_API_KEY` environment variable
  - Default model: `openai/gpt-oss-20b:free` (validated as tool-capable as of 2026-07-13; replaces `meta-llama/llama-3.3-70b-instruct:free` which was returning 429 rate-limit errors)
  - Configurable model: `OPENROUTER_MODEL`
  - Features used: Function calling (OpenAI tool schema), text generation

- **Stub Provider (Testing)**
  - What it's used for: Development and testing without live API calls
  - Implementation: `backend/llm/stub.py`
  - Auth: None required (keyless default)
  - Used by: CI/CD pipeline and local tests (marked with `@pytest.mark.live` excluded by default)

**LLM Provider Abstraction:**
- Factory: `backend/llm/base.py:create_provider()` (pluggable registry)
- Selection: `LLM_PROVIDER` environment variable (`"stub"` default, `"gemini"`, or `"openrouter"`)
- Protocol: `LLMProvider` exposes `parse_constraints()` and `generate_insights()` operations
- Vendor-neutral translation: `backend/llm/translate.py` converts provider-specific tool calls to `OverrideCall` domain objects (D-07)
- Security (T-04-01): API keys never interpolated into logs, exception messages, or auto-repr; flows only into client constructors

## Data Storage

**Databases:**
- **SQLite 3** (file-based, local)
  - Connection: `backend/store/db.py:connect()`
  - Path: `ROSTERAI_DB` environment variable (default: `backend/var/rosterai.db`)
  - Client: Python `sqlite3` stdlib module
  - Schema: `backend/store/db.py:_SCHEMA` (DDL embedded, no migration framework)
  - **Concurrency mode:** WAL (Write-Ahead Logging) enabled via `PRAGMA journal_mode=WAL`
    - Allows background worker thread to write run status while request threads read scenario metadata
    - Single-writer serialization (OR-Tools solves serialized in thread pool)
  - **Pragmas:**
    - `PRAGMA journal_mode=WAL` - Write-Ahead Logging for concurrency
    - `PRAGMA busy_timeout=5000` - 5-second timeout on database lock contention
    - `PRAGMA foreign_keys=ON` - Enforce referential integrity
    - `check_same_thread=False` - Allow connection sharing (controlled by architecture; actual concurrency serialized)
  - **Tables:**
    - `scenarios` - Fixture metadata, time limits, NL constraint overrides (Phase 3)
    - `runs` - Solve execution records, status transitions, result JSON, error logs, cached insights
    - Indices: `idx_runs_scenario` on `runs(scenario_id)`
  - **Schema evolution:** Additive migrations via `_has_column()` check (see `backend/store/db.py:60-61`)

**File Storage:**
- **Input fixtures** (scenario data in JSON format)
  - Location: `ROSTERAI_DATA_DIR` environment variable (default: `<repo-root>/data`)
  - Path traversal defense: `backend/settings.py:resolve_fixture_path()` validates against directory escape (CR-03)
  - Format: Real-schema workforce + demand JSON (see `data/sample_tiny_input.json`)
  - No external cloud storage; local filesystem only

**Caching:**
- **Query result caching (Frontend):**
  - Framework: TanStack Query (React Query) 5.101.2
  - Query keys: Hierarchical string arrays (e.g., `["scenarios"]`, `["runs", runId]`, `["runResult", runId]`)
  - Invalidation: Mutations trigger `queryClient.invalidateQueries()` to refresh stale data
  - Background polling: Used for run status polling (RUNNING state check on intervals)

- **Insight caching (Backend):**
  - Stored in `runs.insight_json` column after first generation (INS-04)
  - Retrieved without regenerating if LLM provider is unavailable (resilience)

## Authentication & Identity

**Auth Provider:**
- Custom (none)
  - No external auth provider (Cognito, Auth0, Firebase, etc.)
  - No user accounts, API keys, or session management
  - CORS origins (`CORS_ORIGINS` env var) provide the only cross-origin access control
  - No cookies or Authorization headers sent or validated (D-02)

## Monitoring & Observability

**Error Tracking:**
- None detected
  - Errors are persisted to `runs.error` column (backend) or displayed in UI error banners (frontend)
  - No Sentry, DataDog, New Relic, or similar integration

**Logs:**
- **Backend:**
  - CLI: `print()` output to stdout (see `backend/run.py`)
  - API: No structured logging; HTTP errors returned via FastAPI exception handlers
  - Background tasks: Exceptions caught and stored in `runs.error` column for async observability
  
- **Frontend:**
  - Console logs via browser developer tools (no external aggregation)
  - Error boundaries and error banners display failures to users
  - No remote logging provider configured

## CI/CD & Deployment

**Hosting:**
- **Frontend:**
  - Target: AWS S3 + CloudFront (static content delivery)
  - Build output: `frontend/dist/` directory (pre-built static assets)
  - No server runtime required

- **Backend:**
  - Target: AWS App Runner / ECS / EC2 (container compute, not Lambda)
  - Container image: Docker (details in planned deploy phase)
  - Rationale: CP-SAT solves are CPU-heavy and long-running; Lambda's time/resource limits unsuitable
  - Database: SQLite locally; future migration path to RDS or EFS for distributed deployments

**CI Pipeline:**
- None detected in current state (`.github/workflows`, `.gitlab-ci.yml`, `.circleci`, etc. absent)
- Planned: Path-filtered CI per subdir (backend/, frontend/) per ARCHITECTURE.md

## Environment Configuration

**Required env vars (Backend):**
- `ROSTERAI_DB` - SQLite database file path (default: `backend/var/rosterai.db`)
- `ROSTERAI_DATA_DIR` - Input fixture directory (default: `<repo-root>/data`)
- `LLM_PROVIDER` - Provider selection: `"stub"` (default), `"gemini"`, `"openrouter"`
- `LLM_MODEL` - Model ID for selected provider (default: `"gemini-2.5-flash"`)
- `GEMINI_API_KEY` - Google Gemini API key (required if `LLM_PROVIDER=gemini`)
- `OPENROUTER_API_KEY` - OpenRouter API key (required if `LLM_PROVIDER=openrouter`)
- `OPENROUTER_MODEL` - Model slug for OpenRouter (default: `"openai/gpt-oss-20b:free"`)
- `CORS_ORIGINS` - Comma-separated allowed origins (default: `"http://localhost:5173,http://localhost:4173"`)

**Required env vars (Frontend):**
- `VITE_API_BASE_URL` - Backend API origin (e.g., `"http://localhost:8000"`)
  - Fails loudly at module import if unset (see `frontend/src/lib/env.ts:14-20`)

**Secrets location:**
- Backend: `.env` file in `backend/` directory (git-ignored; copy from `.env.example`)
  - Loaded once at import time by `python-dotenv` in `backend/settings.py:23`
  - OS environment variables override `.env` values
  
- Frontend: `.env` file in `frontend/` directory (git-ignored; copy from `.env.example`)
  - Loaded by Vite at build time via `import.meta.env`
  - Production bundles must have `VITE_API_BASE_URL` set at build time

## Webhooks & Callbacks

**Incoming:**
- None detected
  - API exposes REST endpoints only (GET, POST per CORS middleware)
  - No webhook listener endpoints

**Outgoing:**
- None detected
  - Backend does not call third-party webhooks
  - No async event delivery to external systems

## API Communication

**Frontend ↔ Backend:**
- **Protocol:** HTTP/REST via `openapi-fetch` 0.17.0
- **Type-safety:** OpenAPI TypeScript schema generation
  - Backend exports `/openapi.json` (FastAPI built-in)
  - Export script: `backend/scripts/export_openapi.py` (generates `frontend/openapi.json`)
  - Type generation: `openapi-typescript 7.13.0` → `frontend/src/api/schema.d.ts`
  - Pipeline: `npm run codegen` (export + generate)
  
- **Client:** `frontend/src/api/client.ts`
  - Single typed instance using `createClient<paths>()` from openapi-fetch
  - Base URL: `VITE_API_BASE_URL` from `frontend/src/lib/env.ts`
  - No second client instances allowed (enforced by import centralization)

- **Endpoints:** Defined in `backend/api/routers/`
  - `health.py` - Server health check
  - `fixtures.py` - List available input fixtures
  - `scenarios.py` - CRUD scenario metadata + list
  - `runs.py` - Create/list/fetch run records and results
  - `constraints.py` - Apply natural language constraint overrides (Phase 3)

- **Response serialization:**
  - Results: `backend/services/run_service.py` serializes `SolveResult` to `result_json` column via `serialize_result()`
  - Insights: `backend/services/insights_service.py` generates NL report, cached in `insight_json` column
  - Status: Run state machine transitions (PENDING → RUNNING → COMPLETED/FAILED) persisted to `status` column

---

*Integration audit: 2026-07-20*
