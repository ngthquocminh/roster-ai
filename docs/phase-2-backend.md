# Phase 2 — Backend skeleton

> **Status: ✅ Completed** (commit `203db1b`). Written retroactively to match the
> per-phase doc workflow in [`PLAN.md`](PLAN.md); it records the plan and design
> as built. The durable design also lives in [`design.md`](design.md); the HTTP
> contract in [`API.md`](API.md).

## Goal

Put a FastAPI backend in front of the Phase-1 engine so a schedule can be
produced over HTTP: create a **scenario** from an input fixture, **trigger a
run** that solves off the request thread, poll its status, and fetch the
**result** (coverage, cost, schedule). SQLite for persistence. No LLM, no
frontend.

## Targets (acceptance criteria)

All measured end-to-end via HTTP:

- [x] `POST /scenarios` creates a scenario bound to a fixture; unknown fixture → `400`.
- [x] `POST /scenarios/{id}/runs` returns immediately with a `PENDING` run; the
      solve runs **off the event loop** (the API stays responsive during a solve).
- [x] Run status is persisted and transitions `PENDING → RUNNING → COMPLETED/FAILED`.
- [x] `GET /runs/{id}/result` returns metrics + schedule once `COMPLETED`; `409`
      before that.
- [x] A **time-limited** solve still ends `COMPLETED`, reporting the unmet-optimal
      schedule with `solver_status = UNKNOWN` (reuses Phase-1 graceful degradation).
- [x] The engine is swappable behind a seam so tests can inject a stub (no real
      solve in CI).
- [x] Tests green: 10 total (5 engine + 5 API lifecycle).

## Design

**Layering** (dependencies point inward): `api → services → store + engine/domain`.

```
backend/
  settings.py          # env-driven paths (ROSTERAI_DB, ROSTERAI_DATA_DIR)
  store/               # SQLite persistence (no web deps)
    db.py              # connect() (WAL), init_db(), inline schema
    repositories.py    # ScenarioRepo, RunRepo (return plain dicts)
  services/            # use-cases (no web deps)
    scenario_service.py
    run_service.py     # threaded run executor + lifecycle
    serialize.py       # SolveResult -> JSON-safe dict (NaN -> null)
  api/                 # FastAPI web layer
    main.py            # app + lifespan (init_db on start, pool shutdown on stop)
    deps.py            # get_settings, get_db, get_engine (the swap seam)
    schemas.py         # Pydantic ScenarioCreate / ScenarioOut / RunOut
    routers/           # health, fixtures, scenarios, runs
```

**Data model** (SQLite, WAL; stdlib `sqlite3`, no ORM):

- `scenarios(id, name, fixture, time_limit_s, overrides, created_at)` —
  `overrides` is a JSON column reserved for Phase-3 NL constraints.
- `runs(id, scenario_id, status, created_at, started_at, finished_at,
  solver_status, error, result_json)` — the serialized `SolveResult` is stored
  as JSON on the run row.

**Run execution** (`services/run_service.py`): a module-level
`ThreadPoolExecutor(max_workers=1)` — solves are CPU-bound, run one at a time.
The request handler inserts a `PENDING` run, commits (so the worker can see it),
then submits the job. The worker opens its **own** SQLite connection (connections
aren't shared across threads), sets `RUNNING`, solves, and writes
`COMPLETED`/`FAILED`. The pool is created lazily and recreated after shutdown so
repeated app lifespans (and tests) work.

**Engine seam**: `get_engine()` is a FastAPI dependency returning
`create_engine("cpsat")`. Tests override it with a stub engine that returns a
canned `SolveResult` instantly, so the whole lifecycle is exercised without
running CP-SAT.

**Endpoints** (full reference in [`API.md`](API.md)):

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /fixtures` | list input files in the data dir |
| `POST /scenarios` · `GET /scenarios` · `GET /scenarios/{id}` | scenario CRUD |
| `POST /scenarios/{id}/runs` · `GET /scenarios/{id}/runs` | trigger / list runs |
| `GET /runs/{id}` · `GET /runs/{id}/result` | run status / result |

## Step-by-step plan

1. `settings.py` + `store/db.py` (connection, WAL, schema) + `store/repositories.py`.
2. `services/serialize.py` (SolveResult → JSON, NaN → null).
3. `services/scenario_service.py` (create/list/get).
4. `services/run_service.py` (create run, submit to pool, threaded executor).
5. `api/deps.py` (settings, per-request DB connection, engine seam).
6. `api/schemas.py` + `api/routers/{health,fixtures,scenarios,runs}.py`.
7. `api/main.py` (app, lifespan: init DB on start, shut pool on stop).
8. Add deps: `fastapi`, `uvicorn[standard]`, `httpx` (dev); git-ignore the DB.
9. `tests/test_api.py` — stub engine via dependency override; scenario → run →
   poll → result, plus validation/404 cases.
10. README: uvicorn run + curl walkthrough.

## Decisions / open questions (resolved)

- **Async via worker thread pool, not FastAPI BackgroundTasks** — a solve is
  CPU-bound and long; the pool keeps it off the event loop with bounded
  concurrency and a DB-persisted status lifecycle. (See [`design.md`](design.md) §3.7.)
- **Persistence: stdlib `sqlite3` + thin repos, not SQLAlchemy/Alembic** — two
  tables don't justify an ORM yet. Pydantic is still used for API schemas.
- **Input = fixtures in `data/`, no upload endpoint yet** — scenarios reference a
  fixture file name; CSV/JSON upload is deferred.
- **Single-tenant** — no sessions/auth in this phase.
- **Insights belong to Phase 3, not here** — Phase 2 stops at a solved schedule;
  a run is `COMPLETED` on solve so a later LLM step can't fail a valid schedule.

## Outcome

Shipped all targets. Verified end-to-end with the real CP-SAT engine: created a
scenario, triggered a run, and it finished `COMPLETED` / `UNKNOWN` in ~11s at an
8s time limit while the API stayed responsive. 10 tests pass. DB lives at
`backend/var/rosterai.db` (override with `ROSTERAI_DB`).

**Follow-ups (optional, not blocking):** run cancellation + concurrency limits;
an input upload endpoint; per-scenario engine selection.
