# Technology Stack

**Analysis Date:** 2026-06-26

## Languages

**Primary:**
- Python 3.10–3.12 - All backend code: scheduling engine, FastAPI server, domain logic, ingest adapters, and CLI tooling

## Runtime

**Environment:**
- Python 3.10–3.12 (see `backend/pyproject.toml` requires-python)

**Package Manager:**
- uv (Astral's Python package manager) - Manages dependencies, creates `.venv`, installs from lockfile
- Lockfile: uv.lock (not present in current state; generated on `uv sync`)

## Frameworks

**Core:**
- FastAPI 0.x (latest) - HTTP API server for scenario/run lifecycle
  - Location: `backend/api/main.py` (entry point), `backend/api/routers/` (endpoints)
  - Routers: health, fixtures, scenarios, runs
  - Lifespan: async context manager handles DB init and worker thread shutdown

- OR-Tools CP-SAT 9.11.4210 (pinned) - Constraint programming solver for workforce scheduling
  - Location: `backend/engine/cpsat/` (builder.py, engine.py, objective.py)
  - **Note:** v9.15 segfaults on dev machine; 9.11.4210 is validated pin (see README.md)
  - Supports lexicographic objective (unmet hours → cost) with solve-and-lock rounds

**Testing:**
- pytest (dev dependency) - Test runner
  - Config: `backend/pyproject.toml` testpaths = ["tests"]
  - Location: `backend/tests/`
  - Run: `uv run pytest -q`

**Build/Dev:**
- uvicorn[standard] - ASGI server for FastAPI
  - Run: `uv run uvicorn api.main:app --reload` from `backend/`

## Key Dependencies

**Critical:**
- ortools==9.11.4210 - OR-Tools constraint solver; core to scheduling engine
  - Why it matters: The optimization solver that produces feasible/optimal schedules; pinned version to avoid segfaults
  - Implemented by: `backend/engine/cpsat/engine.py` via `CpSatEngine`

- fastapi - Web framework for HTTP API
  - Why it matters: Handles all scenario/run/fixture endpoints; FastAPI provides automatic OpenAPI schema generation (/docs, /openapi.json)
  - Used by: `backend/api/main.py`, all routers in `backend/api/routers/`

- pandas - Data manipulation (optional in current code; listed as dependency)
  - Where used: Listed in pyproject.toml but not currently imported in Phase 1–2; available for Phase 3 data processing

**Infrastructure:**
- uvicorn[standard] - ASGI server
  - Serves FastAPI app with hot-reload in development
  - Used by: `uv run uvicorn api.main:app --reload`

- sqlite3 (stdlib) - Local database
  - Stores: scenarios, runs, run results
  - Location: `backend/store/db.py` (schema, WAL mode setup)
  - Connection: Thread-per-request, WAL journal mode to allow concurrent solver writes

## Configuration

**Environment:**
- No `.env` file in current state; env overrides via OS environment only
- Settings loaded fresh per request so overrides apply at runtime

**Build:**
- `backend/pyproject.toml` - Single source of truth for Python version, dependencies, test paths
  - Defines: Python version range, 4 core dependencies, dev group (pytest, httpx for testing)

**Runtime Env Vars:**
- `ROSTERAI_DB` - Path to SQLite database (default: `backend/var/rosterai.db`)
- `ROSTERAI_DATA_DIR` - Path to input fixture directory (default: `<repo>/data`)
  - See `backend/settings.py` for defaults and override logic

## Platform Requirements

**Development:**
- Python 3.10+ (local)
- uv (package manager)
- SQLite (built into Python)
- Platform: Linux, macOS, or Windows (WSL2 noted for ortools on some systems)

**Production:**
- Docker container deployment (noted as AWS ECR target in README.md)
- Python 3.10–3.12 in container
- SQLite or compatible database (current: local file via WAL mode)
- Deployment target: AWS (frontend → S3/CloudFront; backend → App Runner/ECS/EC2)

---

*Stack analysis: 2026-06-26*
