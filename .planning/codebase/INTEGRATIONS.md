# External Integrations

**Analysis Date:** 2026-06-26

## APIs & External Services

**Current Phase (1–2):**
- None active. Phase 3 will add LLM provider (Claude via Anthropic SDK planned; see `design.md` and `PLAN.md`)

**Planned Integrations:**
- **LLM Provider** (Phase 3) - Natural-language constraint parsing and insight generation
  - Architecture: Protocol seam in `backend/services/` for swappability (Claude now; Gemini later)
  - Not yet implemented; reserved for Phase 3

## Data Storage

**Databases:**
- **SQLite** (local file)
  - Location: `backend/var/rosterai.db` (default; override with `ROSTERAI_DB` env var)
  - Setup: `backend/store/db.py` (schema, connection pooling, WAL mode)
  - Schema:
    - `scenarios` table - scenario name, fixture, time limit, created_at
    - `runs` table - run status (PENDING/RUNNING/COMPLETED/FAILED), solver status, result_json
    - Index: `idx_runs_scenario` on runs.scenario_id for queries
  - WAL Mode: Enabled to allow background solver threads to write while API reads
  - Constraints: foreign_keys enabled, busy_timeout 5000ms, check_same_thread=False for multi-threaded access
  - Connection Pool: Per-thread via `sqlite3.connect()` in `backend/store/db.py`

**File Storage:**
- **Local filesystem** (JSON fixtures only)
  - Location: `<repo>/data/` (override with `ROSTERAI_DATA_DIR` env var)
  - Contents: `sample_tiny_input.json` - real-schema weekly fixture with 759-member production model scaled down
  - Builder: `backend/fixtures/build_short_input.py` (generates fixture from full weekly input; stdlib only, no solver deps)
  - Schema: [See design.md section 3.4] Outbound Workload, Inbound Workload, Indirect Workforce Requirement, Team Member, Qualifications, Shift Templates, Roster Profile, Availability

**Caching:**
- Not used. Results cached in SQLite result_json field; no Redis/Memcached

## Authentication & Identity

**Auth Provider:**
- None active. No authentication/authorization layer in Phase 1–2
- Planned for later phases (user sessions, role-based access)
- All endpoints currently public (no API keys, bearer tokens, or OAuth)

## Monitoring & Observability

**Error Tracking:**
- None. Phase 1–2 rely on stdout/stderr logs and database error field
- Exceptions in solver thread caught and persisted to `runs.error` field

**Logs:**
- **Stdout/Stderr** - All logging via `print()` and exception traceback
  - CLI (`run.py`) - prints problem stats, solver time, metrics, coverage, schedule sample
  - API (`api/main.py`) - FastAPI automatic request/response logging; uvicorn access logs
  - Worker thread (`services/run_service.py`) - catches exceptions and stores in DB, no explicit logging
- **No structured logging** - Plain text output; no JSON, no log aggregation

**Performance Metrics:**
- Captured in `backend/domain/result.py` → SolveResult
  - wall_time_s - solve duration
  - unmet_objective_hours - labour-hours not covered
  - cost_objective - total wage cost
  - coverage_by_function, coverage_by_day - breakdown stats
- Stored in runs.result_json as JSON; queryable via `GET /runs/{run_id}/result`

## CI/CD & Deployment

**Hosting:**
- Not deployed. Target: AWS (see README.md notes)
  - Frontend: S3/CloudFront (static assets)
  - Backend: Container (App Runner/ECS/EC2)
  - Database: SQLite file or managed RDS (to be decided)

**CI Pipeline:**
- Not configured. No GitHub Actions, GitLab CI, or similar detected
- Manual testing only (see README.md quick start)

**Deployment Model:**
- Docker container (Dockerfile not yet created; inferred from AWS target)
- Environment: Python 3.10–3.12 + uv
- Entry: `uvicorn api.main:app` (exposed on port 8000 in dev; prod port TBD)

## Environment Configuration

**Required env vars:**
- None mandatory; all have sensible defaults (see `backend/settings.py`)

**Optional env vars:**
- `ROSTERAI_DB` - SQLite database file path (default: `backend/var/rosterai.db`)
- `ROSTERAI_DATA_DIR` - Input fixture directory (default: `<repo>/data`)

**Secrets location:**
- None currently. No API keys, database credentials, or secrets files
- When Phase 3 adds LLM (Claude API), `ANTHROPIC_API_KEY` will be required (handled by env or `.env` file, not yet implemented)

## Webhooks & Callbacks

**Incoming:**
- None. Runs are polled; no event subscriptions or inbound webhooks

**Outgoing:**
- None. No integrations with external services to notify

**Background Tasks:**
- Single-worker ThreadPoolExecutor for solver execution
  - Location: `backend/services/run_service.py` (module-level `_pool`)
  - Lifecycle: Created lazily on first `submit_run()`, shut down on app lifespan exit
  - Queue: FIFO; one solve at a time (CPU-bound, serialized)
  - Thread: Named "solve-<n>" for debugging

---

*Integration audit: 2026-06-26*
